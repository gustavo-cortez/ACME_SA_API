from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status
from passlib.context import CryptContext

from .config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(*, subject: str, role: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    expire_delta = expires_minutes or settings.jwt_expires_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_delta)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc
    return payload


def require_replication_token(x_replica_token: str | None = Header(default=None)) -> str:
    settings = get_settings()
    if x_replica_token != settings.replication_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Replica token inválido")
    return x_replica_token
