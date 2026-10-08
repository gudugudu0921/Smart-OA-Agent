"""Redis-checkpointed single-agent LangGraph workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.chat_state import ChatState
from app.agents.recognition import recognize_intent
from app.db.redis import get_redis_checkpointer
from app.models.user import User
from app.tools.approval_tools import hr_review_tool, manager_review_tool
from app.tools.leave_tools import cancel_leave_tool, submit_leave_tool
from app.tools.query_tools import (
    query_hr_pending_tool,
    query_manager_pending_tool,
    query_my_leave_tool,
)


SUPPORTED_INTENTS = {
    "submit_leave",
    "query_my_leave",
    "cancel_leave",
    "query_manager_pending",
    "manager_review",
    "query_hr_pending",
    "hr_review",
    "general_chat",
}
ALLOWED_INTENTS_BY_ROLE = {
    "employee": {"submit_leave", "query_my_leave", "cancel_leave", "general_chat"},
    "manager": {"query_manager_pending", "manager_review", "general_chat"},
    "hr": {"query_hr_pending", "hr_review", "general_chat"},
    "admin": {"general_chat"},
}
REQUIRED_FIELDS = {
    "submit_leave": ("leave_type", "start_date", "end_date"),
    "cancel_leave": ("application_id",),
    "manager_review": ("application_id", "decision"),
    "hr_review": ("application_id", "decision"),
}
MISSING_FIELD_LABELS = {
    "leave_type": "请假类型",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "application_id": "申请编号",
    "decision": "审批决定",
}
LEAVE_TYPE_LABELS = {
    "annual": "年假",
    "sick": "病假",
    "personal": "事假",
    "marriage": "婚假",
    "maternity": "产假",
    "bereavement": "丧假",
    "other": "其他",
}


@dataclass(frozen=True)
class AgentExecutionContext:
    db: Session
    current_user: User
    ip_address: str | None


def _validate_request_node(state: ChatState) -> dict:
    if state.get("cancel_current_task") and state.get("pending_intent"):
        return {
            "intent": "general_chat",
            "extracted_info": {},
            "application_id": None,
            "pending_intent": None,
            "pending_fields": [],
            "current_task": None,
            "cancel_current_task": False,
            "error": "current_task_cancelled",
            "success": True,
            "response": "已取消当前未完成的操作。",
        }
    if state.get("cancel_current_task"):
        return {
            "intent": "general_chat",
            "cancel_current_task": False,
            "error": "no_pending_task",
            "success": True,
            "response": "当前没有未完成的操作。",
        }
    if state.get("error"):
        return {}

    intent = state.get("intent", "")
    if intent not in SUPPORTED_INTENTS:
        return {
            "intent": "general_chat",
            "error": "unsupported_intent",
            "success": False,
            "response": "暂时无法识别该请求，请使用系统支持的请假相关功能。",
        }

    allowed = ALLOWED_INTENTS_BY_ROLE.get(state["user_role"], {"general_chat"})
    if intent not in allowed:
        return {
            "error": "permission_denied",
            "success": False,
            "response": "当前账号没有执行该操作的权限。",
        }

    extracted = dict(state.get("extracted_info", {}))
    application_id = extracted.get("application_id")
    reference_index = state.get("reference_index")
    if application_id in (None, "") and reference_index is not None:
        results = state.get("last_query_results", [])
        match = next(
            (item for item in results if item.get("index") == reference_index),
            None,
        )
        if match is None:
            return {
                "error": "invalid_reference_index",
                "success": False,
                "response": "请先查询相关申请，并使用申请编号或列表序号指定目标。",
            }
        application_id = match["application_id"]
        extracted["application_id"] = application_id

    missing = [
        field
        for field in REQUIRED_FIELDS.get(intent, ())
        if extracted.get(field) in (None, "")
    ]
    if missing:
        labels = "、".join(MISSING_FIELD_LABELS[field] for field in missing)
        if intent in {"cancel_leave", "manager_review", "hr_review"} and (
            "application_id" in missing
        ):
            response = "请先查询相关申请，并使用申请编号或列表序号指定目标。"
        else:
            response = f"请补充{labels}。"
        return {
            "extracted_info": extracted,
            "pending_intent": intent,
            "pending_fields": missing,
            "current_task": intent,
            "error": "missing_fields",
            "success": False,
            "response": response,
        }

    if application_id is not None:
        try:
            UUID(str(application_id))
        except (TypeError, ValueError, AttributeError):
            return {
                "error": "invalid_application_id",
                "success": False,
                "response": "请提供有效的 UUID 申请编号。",
            }
    return {
        "extracted_info": extracted,
        "application_id": application_id,
        "pending_fields": [],
    }


def _route_intent_node(state: ChatState) -> dict:
    return {"tool_name": state.get("intent")}


def _after_validation(state: ChatState) -> str:
    return "generate_response" if state.get("error") else "route_intent"


def _select_intent(state: ChatState) -> str:
    return state["intent"]


def _format_leave_lines(items: list[dict[str, Any]], include_employee: bool) -> str:
    lines = []
    for index, item in enumerate(items, start=1):
        employee_text = ""
        if include_employee and item.get("employee"):
            employee = item["employee"]
            employee_text = f"，员工：{employee['name']}（{employee['employee_no']}）"
        lines.append(
            f"{index}. 申请编号：{item['application_id']}{employee_text}，"
            f"类型：{LEAVE_TYPE_LABELS.get(item['leave_type'], item['leave_type'])}，"
            f"日期：{item['start_date']} 至 {item['end_date']}，"
            f"天数：{item['leave_days']:.1f}，状态：{item['status']}，"
            f"主管状态：{item['manager_status']}，HR状态：{item['hr_status']}"
        )
    return "\n".join(lines)


def _query_references(result: dict[str, Any]) -> list[dict[str, Any]]:
    if not result.get("success") or not isinstance(result.get("data"), list):
        return []
    return [
        {
            "index": index,
            "application_id": item["application_id"],
            "summary": (
                f"{item.get('start_date')}至{item.get('end_date')} "
                f"{item.get('leave_type')} {item.get('status')}"
            ),
        }
        for index, item in enumerate(result["data"][:20], start=1)
    ]


def _generate_response_node(state: ChatState) -> dict:
    response = state.get("response", "")
    success = state.get("success", False)
    error = state.get("error")
    if not response:
        intent = state["intent"]
        result = state.get("tool_result") or {"success": True, "data": None}
        if not result.get("success", False):
            success = False
            error = result.get("error_type", "tool_error")
            response = f"操作失败：{result.get('message', '未知错误')}。"
        else:
            success = True
            data = result.get("data")
            if intent == "submit_leave":
                response = (
                    f"请假申请已提交成功，申请编号为 {data['application_id']}，"
                    "当前状态为等待主管审批。"
                )
            elif intent == "cancel_leave":
                response = f"请假申请 {data['application_id']} 已撤销。"
            elif intent == "manager_review":
                response = (
                    f"主管审批已完成，申请 {data['application_id']} 的主管状态为 "
                    f"{data['manager_status']}。"
                )
            elif intent == "hr_review":
                response = (
                    f"HR审批已完成，申请 {data['application_id']} 的最终状态为 "
                    f"{data['status']}。"
                )
            elif intent == "query_my_leave":
                response = (
                    "当前没有请假记录。"
                    if not data
                    else "你的请假记录如下：\n" + _format_leave_lines(data, False)
                )
            elif intent == "query_manager_pending":
                response = (
                    "当前没有待审批申请。"
                    if not data
                    else "待你审批的申请如下：\n" + _format_leave_lines(data, True)
                )
            elif intent == "query_hr_pending":
                response = (
                    "当前没有待 HR 审批的申请。"
                    if not data
                    else "待 HR 审批的申请如下：\n" + _format_leave_lines(data, True)
                )
            else:
                response = (
                    "你好，我是智能 OA 请假助手。我可以帮助员工提交、查询和撤销请假，"
                    "帮助主管查询及审批申请，也可以帮助 HR 查询和审批进入 HR 环节的申请。"
                )

    updates: dict[str, Any] = {
        "success": success,
        "error": error,
        "response": response,
        "messages": [AIMessage(content=response)],
    }
    result = state.get("tool_result") or {}
    if success and state.get("intent") != "general_chat" and result.get("success"):
        updates.update(
            {
                "pending_intent": None,
                "pending_fields": [],
                "current_task": None,
                "extracted_info": {},
            }
        )
    return updates


def build_chat_graph(
    context: AgentExecutionContext,
    recognizer: Callable[[ChatState], dict] | None = None,
):
    """Build a request-scoped graph using the shared Redis checkpointer."""
    recognize_node = recognizer or recognize_intent

    def submit_leave_node(state: ChatState) -> dict:
        extracted = state["extracted_info"]
        result = submit_leave_tool(
            db=context.db,
            current_user=context.current_user,
            leave_data={
                "leave_type": extracted.get("leave_type"),
                "start_date": extracted.get("start_date"),
                "end_date": extracted.get("end_date"),
                "reason": extracted.get("reason"),
            },
            ip_address=context.ip_address,
        )
        return {"tool_name": "submit_leave_tool", "tool_result": result}

    def query_my_leave_node(state: ChatState) -> dict:
        result = query_my_leave_tool(context.db, context.current_user)
        return {
            "tool_name": "query_my_leave_tool",
            "tool_result": result,
            "last_query_results": _query_references(result),
        }

    def cancel_leave_node(state: ChatState) -> dict:
        result = cancel_leave_tool(
            db=context.db,
            current_user=context.current_user,
            application_id=state["extracted_info"]["application_id"],
            ip_address=context.ip_address,
        )
        return {"tool_name": "cancel_leave_tool", "tool_result": result}

    def query_manager_pending_node(state: ChatState) -> dict:
        result = query_manager_pending_tool(context.db, context.current_user)
        return {
            "tool_name": "query_manager_pending_tool",
            "tool_result": result,
            "last_query_results": _query_references(result),
        }

    def manager_review_node(state: ChatState) -> dict:
        extracted = state["extracted_info"]
        result = manager_review_tool(
            db=context.db,
            current_user=context.current_user,
            application_id=extracted["application_id"],
            decision=extracted["decision"],
            comment=extracted.get("comment"),
            ip_address=context.ip_address,
        )
        return {"tool_name": "manager_review_tool", "tool_result": result}

    def query_hr_pending_node(state: ChatState) -> dict:
        result = query_hr_pending_tool(context.db, context.current_user)
        return {
            "tool_name": "query_hr_pending_tool",
            "tool_result": result,
            "last_query_results": _query_references(result),
        }

    def hr_review_node(state: ChatState) -> dict:
        extracted = state["extracted_info"]
        result = hr_review_tool(
            db=context.db,
            current_user=context.current_user,
            application_id=extracted["application_id"],
            decision=extracted["decision"],
            comment=extracted.get("comment"),
            ip_address=context.ip_address,
        )
        return {"tool_name": "hr_review_tool", "tool_result": result}

    def general_chat_node(state: ChatState) -> dict:
        return {"tool_name": None, "tool_result": {"success": True, "data": None}}

    graph = StateGraph(ChatState)
    graph.add_node("recognize_intent", recognize_node)
    graph.add_node("validate_request", _validate_request_node)
    graph.add_node("route_intent", _route_intent_node)
    graph.add_node("submit_leave", submit_leave_node)
    graph.add_node("query_my_leave", query_my_leave_node)
    graph.add_node("cancel_leave", cancel_leave_node)
    graph.add_node("query_manager_pending", query_manager_pending_node)
    graph.add_node("manager_review", manager_review_node)
    graph.add_node("query_hr_pending", query_hr_pending_node)
    graph.add_node("hr_review", hr_review_node)
    graph.add_node("general_chat", general_chat_node)
    graph.add_node("generate_response", _generate_response_node)
    graph.add_edge(START, "recognize_intent")
    graph.add_edge("recognize_intent", "validate_request")
    graph.add_conditional_edges(
        "validate_request",
        _after_validation,
        {"route_intent": "route_intent", "generate_response": "generate_response"},
    )
    graph.add_conditional_edges(
        "route_intent", _select_intent, {intent: intent for intent in SUPPORTED_INTENTS}
    )
    for intent in SUPPORTED_INTENTS:
        graph.add_edge(intent, "generate_response")
    graph.add_edge("generate_response", END)
    return graph.compile(checkpointer=get_redis_checkpointer())


def run_chat_agent(
    db: Session,
    current_user: User,
    thread_id: str,
    user_message: str,
    ip_address: str | None = None,
    recognizer: Callable[[ChatState], dict] | None = None,
) -> ChatState:
    context = AgentExecutionContext(
        db=db, current_user=current_user, ip_address=ip_address
    )
    graph = build_chat_graph(context, recognizer=recognizer)
    turn_input: ChatState = {
        "messages": [HumanMessage(content=user_message)],
        "user_message": user_message,
        "thread_id": thread_id,
        "user_id": current_user.id,
        "user_role": current_user.role,
        "user_department": current_user.department,
        "manager_id": current_user.manager_id,
        "application_id": None,
        "tool_name": None,
        "tool_result": None,
        "reference_index": None,
        "cancel_current_task": False,
        "error": None,
        "success": False,
        "response": "",
    }
    return graph.invoke(
        turn_input, config={"configurable": {"thread_id": thread_id}}
    )
