"""Traditional OA leave application routes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TypeVar

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_business_user, require_roles
from app.db.mysql import get_db
from app.models.user import User
from app.schemas.leave import LeaveCreate, LeaveResponse, LeaveReviewRequest, LeaveType
from app.services.leave_service import (
    LeaveConflictError,
    LeaveNotFoundError,
    LeaveValidationError,
    cancel_leave_application,
    create_leave_application,
    get_all_leave_applications,
    get_hr_pending_applications,
    get_leave_application,
    get_manager_pending_applications,
    get_manager_team_history,
    get_my_leave_applications,
    review_leave_by_hr,
    review_leave_by_manager,
)


router = APIRouter()
T = TypeVar("T")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client is not None else None


def _execute(operation: Callable[[], T]) -> T:
    return operation()


@router.post("/", response_model=LeaveResponse, status_code=status.HTTP_201_CREATED)
def submit_leave(
    payload: LeaveCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("employee")),
) -> LeaveResponse:
    return _execute(
        lambda: create_leave_application(
            db=db,
            employee=current_user,
            payload=payload,
            ip_address=_client_ip(request),
        )
    )


@router.get("/my", response_model=list[LeaveResponse])
def read_my_leaves(
    status_filter: str | None = Query(default=None, alias="status"),
    leave_type: LeaveType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("employee")),
) -> list[LeaveResponse]:
    return _execute(
        lambda: get_my_leave_applications(
            db=db,
            employee_id=current_user.id,
            status=status_filter,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )
    )


@router.get("/pending/manager", response_model=list[LeaveResponse])
def read_manager_pending_leaves(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
) -> list[LeaveResponse]:
    return get_manager_pending_applications(
        db=db,
        manager_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.get("/team", response_model=list[LeaveResponse])
def read_manager_team_history(
    employee_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    leave_type: LeaveType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
) -> list[LeaveResponse]:
    return _execute(
        lambda: get_manager_team_history(
            db=db,
            manager_id=current_user.id,
            employee_id=employee_id,
            status=status_filter,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )
    )


@router.get("/pending/hr", response_model=list[LeaveResponse])
def read_hr_pending_leaves(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("hr")),
) -> list[LeaveResponse]:
    return get_hr_pending_applications(db=db, skip=skip, limit=limit)


@router.get("/all", response_model=list[LeaveResponse])
def read_all_leaves(
    employee_id: int | None = None,
    department: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    leave_type: LeaveType | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles("hr", "admin")),
) -> list[LeaveResponse]:
    return _execute(
        lambda: get_all_leave_applications(
            db=db,
            employee_id=employee_id,
            department=department,
            status=status_filter,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            skip=skip,
            limit=limit,
        )
    )


@router.get("/{application_id}", response_model=LeaveResponse)
def read_leave(
    application_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_business_user),
) -> LeaveResponse:
    return _execute(
        lambda: get_leave_application(
            db=db,
            application_id=application_id,
            current_user=current_user,
        )
    )


@router.post("/{application_id}/cancel", response_model=LeaveResponse)
def cancel_leave(
    application_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("employee")),
) -> LeaveResponse:
    return _execute(
        lambda: cancel_leave_application(
            db=db,
            application_id=application_id,
            employee=current_user,
            ip_address=_client_ip(request),
        )
    )


@router.post("/{application_id}/manager-review", response_model=LeaveResponse)
def manager_review_leave(
    application_id: str,
    review: LeaveReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("manager")),
) -> LeaveResponse:
    return _execute(
        lambda: review_leave_by_manager(
            db=db,
            application_id=application_id,
            manager=current_user,
            review=review,
            ip_address=_client_ip(request),
        )
    )


@router.post("/{application_id}/hr-review", response_model=LeaveResponse)
def hr_review_leave(
    application_id: str,
    review: LeaveReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("hr")),
) -> LeaveResponse:
    return _execute(
        lambda: review_leave_by_hr(
            db=db,
            application_id=application_id,
            hr_user=current_user,
            review=review,
            ip_address=_client_ip(request),
        )
    )
