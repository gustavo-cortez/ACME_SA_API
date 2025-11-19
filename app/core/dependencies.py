from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..services.inventory import UserRecord
from .context import inventory_state, settings, synchronizer
from .security import decode_access_token, hash_password, verify_password

bearer_scheme = HTTPBearer(auto_error=False)


def _build_user_context(credentials: HTTPAuthorizationCredentials | None) -> UserRecord:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")
    stored = inventory_state.get_user(username)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    user_record, _ = stored
    return user_record


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> UserRecord:
    return _build_user_context(credentials)


def require_admin(user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operação restrita a administradores")
    return user


def authenticate_user(username: str, password: str) -> UserRecord:
    stored = inventory_state.get_user(username)
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    user_record, password_hash = stored
    if not verify_password(password, password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    return user_record


async def ensure_admin_user() -> None:
    stored = inventory_state.get_user(settings.admin_user)
    if stored:
        return
    password_hash = hash_password(settings.admin_password)
    user = inventory_state.upsert_user(username=settings.admin_user, password_hash=password_hash, role="admin")
    await synchronizer.broadcast(
        "user_upsert",
        {"user": user.to_dict(), "password_hash": password_hash},
    )
