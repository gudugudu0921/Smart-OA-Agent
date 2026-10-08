"""Schemas for Redis-backed chat sessions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    thread_id: UUID
    title: str
    created_at: datetime


class SessionSummary(BaseModel):
    thread_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionMessagesResponse(BaseModel):
    thread_id: UUID
    messages: list[SessionMessage]
