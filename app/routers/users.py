from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..core.context import inventory_state, synchronizer
from ..core.dependencies import get_current_user, require_admin
from ..core.http import dual_request_body, get_payload
from ..core.security import hash_password
from ..schemas import TokenResponse, UserCreateRequest

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post(
    "",
    dependencies=[Depends(require_admin)],
    openapi_extra=dual_request_body(UserCreateRequest),
)
async def criar_usuario(request: Request):
    payload: UserCreateRequest = await get_payload(request, UserCreateRequest)
    password_hash = hash_password(payload.password)
    user = inventory_state.upsert_user(
        username=payload.username,
        password_hash=password_hash,
        role=payload.role,
    )
    await synchronizer.broadcast(
        "user_upsert",
        {"user": user.to_dict(), "password_hash": password_hash},
    )
    return user.to_dict()


@router.get("/me")
async def usuario_atual(user=Depends(get_current_user)):
    return user.to_dict()
