"""Traditional OA leave workflow and query operations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Query, Session

from app.models.leave_application import LeaveApplication
from app.models.user import User
from app.schemas.leave import LeaveCreate, LeaveReviewRequest
from app.services.audit_service import create_audit_log
from app.services.notification_service import (
    notify_hr_reviewed,
    notify_leave_created,
    notify_manager_reviewed,
)


ACTIVE_LEAVE_STATUSES = ("pending", "approved")


class LeaveServiceError(Exception):
    """Base exception for expected leave workflow errors."""


class LeaveValidationError(LeaveServiceError):
    """Raised when submitted business data is invalid."""


class LeaveConflictError(LeaveServiceError):
    """Raised when the application state conflicts with an operation."""


class LeaveNotFoundError(LeaveServiceError):
    """Raised for missing or deliberately hidden leave applications."""


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise LeaveValidationError("start_date must be on or before end_date")


def _apply_date_filters(
    query: Query,
    start_date: date | None,
    end_date: date | None,
) -> Query:
    if start_date is not None and end_date is not None:
        _validate_date_range(start_date, end_date)
    if start_date is not None:
        query = query.filter(LeaveApplication.end_date >= start_date)
    if end_date is not None:
        query = query.filter(LeaveApplication.start_date <= end_date)
    return query


def _commit_and_refresh(db: Session, application: LeaveApplication) -> LeaveApplication:
    try:
        db.commit()
        db.refresh(application)
    except Exception:
        db.rollback()
        raise
    return application


def create_leave_application(
    db: Session,
    employee: User,
    payload: LeaveCreate,
    ip_address: str | None = None,
) -> LeaveApplication:
    _validate_date_range(payload.start_date, payload.end_date)
    if payload.start_date < date.today():
        raise LeaveValidationError("start_date cannot be in the past")
    if employee.manager_id is None:
        raise LeaveValidationError("Employee does not have a direct manager")

    # Serialize submissions for one employee so concurrent requests cannot both
    # pass overlap validation before either transaction commits.
    db.query(User).filter(User.id == employee.id).with_for_update().one()

    overlap = (
        db.query(LeaveApplication.id)
        .filter(
            LeaveApplication.employee_id == employee.id,
            LeaveApplication.status.in_(ACTIVE_LEAVE_STATUSES),
            LeaveApplication.start_date <= payload.end_date,
            LeaveApplication.end_date >= payload.start_date,
        )
        .first()
    )
    if overlap is not None:
        raise LeaveConflictError(
            "Leave dates overlap an existing pending or approved application"
        )

    now = datetime.now()
    leave_days = (payload.end_date - payload.start_date).days + 1
    application = LeaveApplication(
        id=str(uuid4()),
        employee_id=employee.id,
        leave_type=payload.leave_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        leave_days=Decimal(f"{leave_days}.0"),
        reason=payload.reason,
        status="pending",
        manager_status="pending",
        manager_id=employee.manager_id,
        hr_status="pending",
        submitted_at=now,
    )
    db.add(application)
    create_audit_log(
        db=db,
        user_id=employee.id,
        action="CREATE_LEAVE",
        resource_type="leave_application",
        resource_id=application.id,
        detail={
            "old_status": None,
            "new_status": "pending",
            "leave_type": payload.leave_type,
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
        },
        ip_address=ip_address,
    )
    notify_leave_created(db, application, employee)
    return _commit_and_refresh(db, application)


def get_my_leave_applications(
    db: Session,
    employee_id: int,
    status: str | None = None,
    leave_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[LeaveApplication]:
    query = db.query(LeaveApplication).filter(
        LeaveApplication.employee_id == employee_id
    )
    if status is not None:
        query = query.filter(LeaveApplication.status == status)
    if leave_type is not None:
        query = query.filter(LeaveApplication.leave_type == leave_type)
    query = _apply_date_filters(query, start_date, end_date)
    return (
        query.order_by(LeaveApplication.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_leave_application(
    db: Session,
    application_id: str,
    current_user: User,
) -> LeaveApplication:
    application = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.id == application_id)
        .first()
    )
    if application is None:
        raise LeaveNotFoundError("Leave application not found")

    can_view = (
        (current_user.role == "employee" and application.employee_id == current_user.id)
        or (current_user.role == "manager" and application.manager_id == current_user.id)
        or current_user.role in {"hr", "admin"}
    )
    if not can_view:
        raise LeaveNotFoundError("Leave application not found")
    return application


def cancel_leave_application(
    db: Session,
    application_id: str,
    employee: User,
    ip_address: str | None = None,
) -> LeaveApplication:
    application = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.id == application_id,
            LeaveApplication.employee_id == employee.id,
        )
        .with_for_update()
        .first()
    )
    if application is None:
        raise LeaveNotFoundError("Leave application not found")
    if application.status != "pending" or application.manager_status != "pending":
        raise LeaveConflictError("Only an unreviewed pending application can be cancelled")

    old_status = application.status
    application.status = "cancelled"
    application.cancelled_at = datetime.now()
    create_audit_log(
        db=db,
        user_id=employee.id,
        action="CANCEL_LEAVE",
        resource_type="leave_application",
        resource_id=application.id,
        detail={"old_status": old_status, "new_status": "cancelled"},
        ip_address=ip_address,
    )
    return _commit_and_refresh(db, application)


def get_manager_pending_applications(
    db: Session,
    manager_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[LeaveApplication]:
    return (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.manager_id == manager_id,
            LeaveApplication.manager_status == "pending",
            LeaveApplication.status == "pending",
        )
        .order_by(LeaveApplication.submitted_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def review_leave_by_manager(
    db: Session,
    application_id: str,
    manager: User,
    review: LeaveReviewRequest,
    ip_address: str | None = None,
) -> LeaveApplication:
    application = (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.id == application_id,
            LeaveApplication.manager_id == manager.id,
        )
        .with_for_update()
        .first()
    )
    if application is None:
        raise LeaveNotFoundError("Leave application not found")
    if application.manager_status != "pending" or application.status != "pending":
        raise LeaveConflictError("Leave application has already been processed")

    old_status = application.status
    application.manager_status = review.decision
    application.manager_comment = review.comment
    application.manager_approved_at = datetime.now()
    if review.decision == "rejected":
        application.status = "rejected"

    action = (
        "MANAGER_APPROVE_LEAVE"
        if review.decision == "approved"
        else "MANAGER_REJECT_LEAVE"
    )
    create_audit_log(
        db=db,
        user_id=manager.id,
        action=action,
        resource_type="leave_application",
        resource_id=application.id,
        detail={
            "old_status": old_status,
            "new_status": application.status,
            "old_manager_status": "pending",
            "new_manager_status": review.decision,
            "comment": review.comment,
        },
        ip_address=ip_address,
    )
    notify_manager_reviewed(db, application, review.comment)
    return _commit_and_refresh(db, application)


def get_manager_team_history(
    db: Session,
    manager_id: int,
    employee_id: int | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[LeaveApplication]:
    query = (
        db.query(LeaveApplication)
        .join(User, LeaveApplication.employee_id == User.id)
        .filter(User.manager_id == manager_id)
    )
    if employee_id is not None:
        query = query.filter(LeaveApplication.employee_id == employee_id)
    if status is not None:
        query = query.filter(LeaveApplication.status == status)
    if leave_type is not None:
        query = query.filter(LeaveApplication.leave_type == leave_type)
    query = _apply_date_filters(query, start_date, end_date)
    return (
        query.order_by(LeaveApplication.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_hr_pending_applications(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> list[LeaveApplication]:
    return (
        db.query(LeaveApplication)
        .filter(
            LeaveApplication.manager_status == "approved",
            LeaveApplication.hr_status == "pending",
            LeaveApplication.status == "pending",
        )
        .order_by(LeaveApplication.manager_approved_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def review_leave_by_hr(
    db: Session,
    application_id: str,
    hr_user: User,
    review: LeaveReviewRequest,
    ip_address: str | None = None,
) -> LeaveApplication:
    application = (
        db.query(LeaveApplication)
        .filter(LeaveApplication.id == application_id)
        .with_for_update()
        .first()
    )
    if application is None:
        raise LeaveNotFoundError("Leave application not found")
    if (
        application.manager_status != "approved"
        or application.hr_status != "pending"
        or application.status != "pending"
    ):
        raise LeaveConflictError("Leave application is not awaiting HR review")

    old_status = application.status
    application.hr_status = review.decision
    application.hr_id = hr_user.id
    application.hr_comment = review.comment
    application.hr_approved_at = datetime.now()
    application.status = review.decision

    action = (
        "HR_APPROVE_LEAVE"
        if review.decision == "approved"
        else "HR_REJECT_LEAVE"
    )
    create_audit_log(
        db=db,
        user_id=hr_user.id,
        action=action,
        resource_type="leave_application",
        resource_id=application.id,
        detail={
            "old_status": old_status,
            "new_status": application.status,
            "old_hr_status": "pending",
            "new_hr_status": review.decision,
            "comment": review.comment,
        },
        ip_address=ip_address,
    )
    notify_hr_reviewed(db, application, review.comment)
    return _commit_and_refresh(db, application)


def get_all_leave_applications(
    db: Session,
    employee_id: int | None = None,
    department: str | None = None,
    status: str | None = None,
    leave_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[LeaveApplication]:
    query = db.query(LeaveApplication)
    if department is not None:
        query = query.join(
            User,
            LeaveApplication.employee_id == User.id,
        ).filter(User.department == department)
    if employee_id is not None:
        query = query.filter(LeaveApplication.employee_id == employee_id)
    if status is not None:
        query = query.filter(LeaveApplication.status == status)
    if leave_type is not None:
        query = query.filter(LeaveApplication.leave_type == leave_type)
    query = _apply_date_filters(query, start_date, end_date)
    return (
        query.order_by(LeaveApplication.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
