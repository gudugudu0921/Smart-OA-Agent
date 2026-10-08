"""Persistent state carried by the Redis-checkpointed chat graph."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    user_message: str
    thread_id: str

    user_id: int
    user_role: str
    user_department: str
    manager_id: int | None

    intent: str
    extracted_info: dict[str, Any]
    application_id: str | None

    tool_name: str | None
    tool_result: dict[str, Any] | None

    error: str | None
    success: bool
    response: str

    current_task: str | None
    conversation_context: str
    pending_intent: str | None
    pending_fields: list[str]
    last_query_results: list[dict[str, Any]]
    turn_count: int
    cancel_current_task: bool
    reference_index: int | None
