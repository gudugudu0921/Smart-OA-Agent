"""Chat API request and response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    thread_id: UUID
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatResponse(BaseModel):
    success: bool
    thread_id: UUID
    intent: str
    response: str
    data: dict[str, Any] | list[dict[str, Any]] | None = None
