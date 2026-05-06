"""
CipherLens — Authentication Endpoints

POST /api/auth/register  — Create account, generate RSA key pair, return JWT
POST /api/auth/login     — Validate credentials, return JWT (JSON body)
POST /api/auth/token     — OAuth2 form-based login (used by Swagger Authorize)
GET  /api/auth/me        — Return current user profile (requires JWT)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import get_db, get_current_user
from backend.core.crypto import generate_rsa_keypair, encrypt_private_key
from backend.config import MASTER_KEY
from backend.core.security import create_access_token, hash_password, verify_password
from backend.models.models import AuditLog, User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ─── Request / Response Schemas ───────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    public_key: str
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Endpoints ────────────────────────────────────────────

@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    data: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a new CipherLens account.

    - Validates uniqueness of username & email.
    - Generates a 2048-bit RSA key pair for the user.
    - Returns a JWT access token on success.
    """
    # Check for existing user
    existing = (
        db.query(User)
        .filter((User.username == data.username) | (User.email == data.email))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already registered",
        )

    # Generate RSA key pair
    private_key_pem, public_key_pem = generate_rsa_keypair()

    # Create user record
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        public_key=public_key_pem,
        private_key_encrypted=encrypt_private_key(private_key_pem, MASTER_KEY),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Audit trail
    db.add(
        AuditLog(
            user_id=user.id,
            action="REGISTER",
            ip_address=request.client.host if request.client else "unknown",
            details=f"User '{data.username}' registered",
        )
    )
    db.commit()

    token = create_access_token(data={"sub": user.id, "username": user.username})
    return TokenResponse(access_token=token, username=user.username)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and receive a JWT",
)
async def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Authenticate with username & password (JSON). Returns a JWT access token."""
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Audit trail
    db.add(
        AuditLog(
            user_id=user.id,
            action="LOGIN",
            ip_address=request.client.host if request.client else "unknown",
            details=f"User '{user.username}' logged in",
        )
    )
    db.commit()

    token = create_access_token(data={"sub": user.id, "username": user.username})
    return TokenResponse(access_token=token, username=user.username)


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="OAuth2 token endpoint (Swagger Authorize)",
)
async def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    OAuth2-compatible form login used by Swagger UI's Authorize button.
    Accepts `application/x-www-form-urlencoded` with `username` and `password`.
    """
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Audit trail
    db.add(
        AuditLog(
            user_id=user.id,
            action="LOGIN",
            ip_address=request.client.host if request.client else "unknown",
            details=f"User '{user.username}' logged in (Swagger)",
        )
    )
    db.commit()

    token = create_access_token(data={"sub": user.id, "username": user.username})
    return TokenResponse(access_token=token, username=user.username)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user
