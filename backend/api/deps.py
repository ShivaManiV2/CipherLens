"""
CipherLens — FastAPI Dependency Injection

Provides:
  • get_db()          — Yields a SQLAlchemy session (auto-closed)
  • get_current_user() — Extracts & validates JWT, returns the User ORM object
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.core.security import verify_token
from backend.models.models import User

# The tokenUrl tells Swagger UI where to send login requests
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def get_db():
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate the JWT Bearer token and return the corresponding User.

    Raises:
        HTTPException 401 if the token is missing, invalid, expired,
        or the user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = verify_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception

    return user
