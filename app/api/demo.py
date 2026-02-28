from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.configs.db_config import get_db
from app.models.demo import DemoBooking
from app.schemas.demo import DemoBookingCreate, ScheduleDemoResponse
import uuid

router = APIRouter(tags=["Demo"])

@router.post("/schedule-demo", response_model=ScheduleDemoResponse)
async def schedule_demo(
    booking: DemoBookingCreate,
    db: Session = Depends(get_db)
):
    # Check if slot is already booked (basic check)
    existing_booking = db.query(DemoBooking).filter(
        DemoBooking.selected_slot == booking.selected_slot,
        DemoBooking.status == "scheduled"
    ).first()
    
    if existing_booking:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This time slot has already been booked."
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
        meeting_link=meet_link
    )
    
    try:
        db.add(db_booking)
        db.commit()
        db.refresh(db_booking)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create booking: {str(e)}"
        )
        
    return ScheduleDemoResponse(
        message="Demo scheduled successfully",
        meet_link=meet_link,
        scheduled_at=db_booking.selected_slot
    )
