"""Approval adapters from the chat graph to leave services."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.leave import LeaveReviewRequest
from app.services.leave_service import (
    LeaveConflictError,
    LeaveNotFoundError,
    LeaveValidationError,
    review_leave_by_hr,
    review_leave_by_manager,
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


def manager_review_tool(
    db: Session,
    current_user: User,
    application_id: str,
    decision: str,
    comment: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    try:
        application = review_leave_by_manager(
            db=db,
            application_id=application_id,
            manager=current_user,
            review=LeaveReviewRequest(decision=decision, comment=comment),
            ip_address=ip_address,
        )
    except (LeaveValidationError, LeaveConflictError, LeaveNotFoundError) as exc:
        return _expected_error_result(exc)
    return {
        "success": True,
        "data": serialize_leave_application(application),
    }


def hr_review_tool(
    db: Session,
    current_user: User,
    application_id: str,
    decision: str,
    comment: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    try:
        application = review_leave_by_hr(
            db=db,
            application_id=application_id,
            hr_user=current_user,
            review=LeaveReviewRequest(decision=decision, comment=comment),
            ip_address=ip_address,
        )
    except (LeaveValidationError, LeaveConflictError, LeaveNotFoundError) as exc:
        return _expected_error_result(exc)
    return {
        "success": True,
        "data": serialize_leave_application(application),
    }
