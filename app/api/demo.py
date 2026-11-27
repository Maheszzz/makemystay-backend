import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core import security
from app.core.rate_limit import limiter
from app.configs.db_config import get_db
from app.models.demo import DemoBooking
from app.schemas.demo import (
    DemoBookingCreate,
    DemoBookingResponse,
    ScheduleDemoResponse,
)
from app.utils.email_utils import email_service

router = APIRouter(tags=["Demo"])


@celery_app.task(name="send_demo_email_task")
def send_demo_email_task(booking_data: dict, meet_link: str):
    from app.utils.email_utils import email_service
    from app.schemas.demo import DemoBookingCreate
    # pyrefly: ignore [unused-coroutine]
    email_service.send_booking_confirmation(DemoBookingCreate(**booking_data), meet_link)


@router.post("/schedule-demo", response_model=ScheduleDemoResponse)
@limiter.limit("5/minute")
async def schedule_demo(
    request: Request,
    booking: DemoBookingCreate,
    db: Session = Depends(get_db),
):

    # Check if slot is already booked (basic check)
    existing_booking = (
        db.query(DemoBooking)
        .filter(
            DemoBooking.selected_slot == booking.selected_slot,
            DemoBooking.status == "scheduled",
        )
        .first()
    )

    if existing_booking:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This time slot has already been booked.",
        )

    # In a real app, integrate with Google Meet API here
    # For now, generate a mock meeting link
    unique_id = uuid.uuid4().hex[:8]
    meet_link = f"https://meet.google.com/mock-{unique_id}"

    # Save to database
    db_booking = DemoBooking(
        name=booking.name,
        email=booking.email,
        phone=booking.phone,
        company=booking.company,
        units=booking.units,
        selected_slot=booking.selected_slot,
        status="scheduled",
        meeting_link=meet_link,
    )

    try:
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)

        # Abstracted off FastAPI Thread loop to Celery Worker
        send_demo_email_task.delay(booking.model_dump(), meet_link)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create booking: {str(e)}"
        )

    return ScheduleDemoResponse(
        message="Demo scheduled successfully",
        meet_link=meet_link,
        scheduled_at=db_booking.selected_slot,
    )


@router.get("/schedule-demo", response_model=list[DemoBookingResponse])
async def get_all_demos(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _user=Depends(security.admin_or_employee_required),
):
    """Get all scheduled demos (admin/employee only — contains customer contact details)."""
    bookings = (
        db.query(DemoBooking)
        .order_by(DemoBooking.selected_slot.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return bookings


@router.get("/schedule-demo/booked-slots", response_model=list[datetime])
@limiter.limit("30/minute")
async def get_booked_demo_slots(request: Request, db: Session = Depends(get_db)):
    """Public: upcoming booked slot times only (no names, emails or phones)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        db.query(DemoBooking.selected_slot)
        .filter(DemoBooking.status == "scheduled", DemoBooking.selected_slot >= now)
        .order_by(DemoBooking.selected_slot.asc())
        .limit(500)
        .all()
    )
    return [r[0] for r in rows if r[0] is not None]
