"""Mutation adapters from the chat graph to leave services."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.leave import LeaveCreate
from app.services.leave_service import (
    LeaveConflictError,
    LeaveNotFoundError,
    LeaveValidationError,
    cancel_leave_application,
    create_leave_application,
)
from app.tools.query_tools import serialize_leave_application


def _expected_error_result(error: Exception) -> dict[str, Any]:
    if isinstance(error, LeaveValidationError):
        error_type = "validation"
    elif isinstance(error, LeaveConflictError):
        error_type = "conflict"
    else:
        error_type = "not_found"
    return {
        "success": False,
        "error_type": error_type,
        "message": str(error),
    }


def submit_leave_tool(
    db: Session,
    current_user: User,
    leave_data: dict[str, Any],
    ip_address: str | None = None,
) -> dict[str, Any]:
    try:
        application = create_leave_application(
            db=db,
            employee=current_user,
            payload=LeaveCreate.model_validate(leave_data),
            ip_address=ip_address,
        )
    except (LeaveValidationError, LeaveConflictError, LeaveNotFoundError) as exc:
        return _expected_error_result(exc)
    return {
        "success": True,
        "data": serialize_leave_application(application),
    }


def cancel_leave_tool(
    db: Session,
    current_user: User,
    application_id: str,
    ip_address: str | None = None,
) -> dict[str, Any]:
    try:
        application = cancel_leave_application(
            db=db,
            application_id=application_id,
            employee=current_user,
            ip_address=ip_address,
        )
    except (LeaveValidationError, LeaveConflictError, LeaveNotFoundError) as exc:
        return _expected_error_result(exc)
    return {
        "success": True,
        "data": serialize_leave_application(application),
    }
