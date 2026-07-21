from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models import AuditLog, RefreshToken, User, utcnow

settings = get_settings()
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)
ROLE_LEVEL = {"viewer": 0, "sales": 1, "analyst": 2, "admin": 3}


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user: User) -> str:
    now = utcnow()
    return jwt.encode(
        {"sub": user.id, "role": user.role.name, "email": user.email, "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes), "type": "access"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def issue_refresh_token(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=utcnow() + timedelta(days=settings.refresh_token_days)))
    db.commit()
    return raw


def consume_refresh_token(db: Session, raw: str) -> User:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest, RefreshToken.revoked_at.is_(None)))
    if not token or _as_utc(token.expires_at) <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token invalid or expired")
    user = db.get(User, token.user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled")
    token.revoked_at = utcnow()
    db.commit()
    return user


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access": raise ValueError("wrong token type")
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired access token") from exc
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user disabled")
    return user


def require_role(minimum: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if ROLE_LEVEL.get(user.role.name, -1) < ROLE_LEVEL[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user
    return dependency


def audit(db: Session, request: Request | None, user: User | None, action: str, entity_type: str | None = None, entity_id: str | None = None, details: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type, entity_id=entity_id, details=details or {}, ip_address=request.client.host if request and request.client else None))
    db.commit()
