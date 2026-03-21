from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.rate_limit import limiter
from app.repo import user as user_repo
from app.schemas.auth import LoginRequest, PasswordChangeRequest, Token, UserResponse, RefreshTokenRequest

router = APIRouter(tags=["Authentication"])


@router.post("/auth/login", response_model=Token)
@limiter.limit("5/minute")
def login(request: Request, login_data: LoginRequest, db: Session = Depends(get_mysql_db)):
    """Authenticate user and return JWT token."""
    user = user_repo.get_user_by_email(db, login_data.email)
    if not user or not security.verify_password(
        login_data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role}
    )
    refresh_token = security.create_refresh_token(
        data={"sub": user.email, "role": user.role}
    )
    return {
        "access_token": access_token, 
        "refresh_token": refresh_token,
        "token_type": "bearer", 
        "role": user.role
    }


@router.post("/auth/refresh", response_model=Token)
@limiter.limit("10/minute")
def refresh_token(request: Request, data: RefreshTokenRequest, db: Session = Depends(get_mysql_db)):
    """Refresh access token."""
    email = security.verify_refresh_token(data.refresh_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    user = user_repo.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    access_token = security.create_access_token(
        data={"sub": user.email, "role": user.role}
    )
    new_refresh_token = security.create_refresh_token(
        data={"sub": user.email, "role": user.role}
    )
    return {
        "access_token": access_token, 
        "refresh_token": new_refresh_token,
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
    current_user=Depends(security.get_current_user),
):
    """Change the password of the currently authenticated user."""
    if not security.verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect current password"
        )

    current_user.password_hash = security.get_password_hash(data.new_password)
    db.commit()
    return None
