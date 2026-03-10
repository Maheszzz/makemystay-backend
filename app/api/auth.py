from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.schemas.auth import Token, UserResponse, LoginRequest, PasswordChangeRequest
from app.repo import user as user_repo
from app.core import security

router = APIRouter(tags=["Authentication"])

@router.post("/auth/login", response_model=Token)
def login(login_data: LoginRequest, db: Session = Depends(get_mysql_db)):
    """ Authenticate user and return JWT token. """
    user = user_repo.get_user_by_email(db, login_data.email)
    if not user or not security.verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role}
    )
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user.role
    }

@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: UserResponse = Depends(security.get_current_user)):
    return current_user

@router.put("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChangeRequest,
    db: Session = Depends(get_mysql_db),
    current_user = Depends(security.get_current_user)
):
    """ Change the password of the currently authenticated user. """
    if not security.verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    current_user.password_hash = security.get_password_hash(data.new_password)
    db.commit()
    return None
