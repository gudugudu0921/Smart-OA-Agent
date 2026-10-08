"""Read-only adapters from the chat graph to leave services."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.leave_application import LeaveApplication
from app.models.user import User
from app.services.leave_service import (
    get_hr_pending_applications,
    get_manager_pending_applications,
    get_my_leave_applications,
)


def serialize_leave_application(
    application: LeaveApplication,
    include_employee: bool = False,
) -> dict[str, Any]:
    """Convert an ORM object into the limited structure exposed to the agent."""
    data = {
        "application_id": application.id,
        "leave_type": application.leave_type,
        "start_date": application.start_date.isoformat(),
        "end_date": application.end_date.isoformat(),
        "leave_days": float(application.leave_days),
        "status": application.status,
        "manager_status": application.manager_status,
        "hr_status": application.hr_status,
    }
    if include_employee:
        data["employee"] = {
            "id": application.employee.id,
            "employee_no": application.employee.employee_no,
            "name": application.employee.name,
        }
    return data


def query_my_leave_tool(db: Session, current_user: User) -> dict[str, Any]:
    applications = get_my_leave_applications(
        db=db,
        employee_id=current_user.id,
        limit=20,
    )
    return {
        "success": True,
        "data": [serialize_leave_application(item) for item in applications],
    }


def query_manager_pending_tool(db: Session, current_user: User) -> dict[str, Any]:
    applications = get_manager_pending_applications(
        db=db,
        manager_id=current_user.id,
        limit=20,
    )
    return {
        "success": True,
        "data": [
            serialize_leave_application(item, include_employee=True)
            for item in applications
        ],
    }


def query_hr_pending_tool(db: Session, current_user: User) -> dict[str, Any]:
    applications = get_hr_pending_applications(db=db, limit=20)
    return {
        "success": True,
        "data": [
            serialize_leave_application(item, include_employee=True)
            for item in applications
        ],
    }
