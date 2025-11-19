from __future__ import annotations

from fastapi import APIRouter, Request

from ..core.dependencies import authenticate_user
from ..core.http import dual_request_body, get_payload
from ..core.security import create_access_token
from ..schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/login",
    response_model=TokenResponse,
    openapi_extra=dual_request_body(LoginRequest),
)
async def login(request: Request) -> TokenResponse:
    payload: LoginRequest = await get_payload(request, LoginRequest)
    user = authenticate_user(payload.username, payload.password)
    token = create_access_token(subject=user.username, role=user.role)
    return TokenResponse(access_token=token)
