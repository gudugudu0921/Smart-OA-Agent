"""Authenticated chat and Redis-backed session endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.agents.chat_agent import run_chat_agent
from app.core.dependencies import get_current_business_user
from app.db.mysql import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.session import (
    SessionCreateResponse,
    SessionListResponse,
    SessionMessagesResponse,
    SessionSummary,
)
from app.services.session_service import (
    SessionNotFoundError,
    create_session,
    delete_session,
    get_session_messages,
    get_session,
    list_sessions,
    touch_session,
    validate_session_owner,
)


router = APIRouter()


def _session_summary(metadata: dict[str, str]) -> SessionSummary:
    return SessionSummary.model_validate(metadata)


@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(
    current_user: User = Depends(get_current_business_user),
) -> SessionCreateResponse:
    metadata = create_session(current_user.id)
    return SessionCreateResponse.model_validate(metadata)


@router.get("/sessions", response_model=SessionListResponse)
def get_chat_sessions(
    current_user: User = Depends(get_current_business_user),
) -> SessionListResponse:
    sessions = list_sessions(current_user.id)
    return SessionListResponse(
        sessions=[_session_summary(metadata) for metadata in sessions]
    )


@router.get("/sessions/{thread_id}", response_model=SessionSummary)
def get_chat_session(
    thread_id: UUID,
    current_user: User = Depends(get_current_business_user),
) -> SessionSummary:
    metadata = get_session(current_user.id, thread_id)
    return _session_summary(metadata)


@router.get(
    "/sessions/{thread_id}/messages",
    response_model=SessionMessagesResponse,
)
def get_chat_session_messages(
    thread_id: UUID,
    current_user: User = Depends(get_current_business_user),
) -> SessionMessagesResponse:
    messages = get_session_messages(current_user.id, thread_id)
    return SessionMessagesResponse(thread_id=thread_id, messages=messages)


@router.delete("/sessions/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat_session(
    thread_id: UUID,
    current_user: User = Depends(get_current_business_user),
) -> Response:
    delete_session(current_user.id, thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_business_user),
) -> ChatResponse:
    thread_id = str(payload.thread_id)
    validate_session_owner(current_user.id, thread_id)
    result = run_chat_agent(
        db=db,
        current_user=current_user,
        thread_id=thread_id,
        user_message=payload.message,
        ip_address=request.client.host if request.client is not None else None,
    )
    touch_session(current_user.id, thread_id, payload.message)

    tool_result = result.get("tool_result") or {}
    return ChatResponse(
        success=result.get("success", False),
        thread_id=payload.thread_id,
        intent=result.get("intent", "general_chat"),
        response=result.get("response", "暂时无法处理该请求。"),
        data=tool_result.get("data"),
    )
