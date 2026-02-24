from sqlalchemy.orm import Session
from app.models.user import User

def get_user_by_email(db: Session, email: str):
    """Find a user by their email address."""
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, user_data: dict):
    """Create a new user."""
    db_user = User(**user_data)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
