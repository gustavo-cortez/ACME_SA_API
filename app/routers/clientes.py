from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core.context import inventory_state, synchronizer
from ..core.dependencies import get_current_user
from ..core.http import dual_request_body, get_payload
from ..schemas import ClientRequest

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.post(
    "",
    dependencies=[Depends(get_current_user)],
    openapi_extra=dual_request_body(ClientRequest),
)
async def criar_cliente(request: Request):
    payload: ClientRequest = await get_payload(request, ClientRequest)
    client = inventory_state.upsert_client(
        client_id=str(uuid.uuid4()),
        nome=payload.nome,
        documento=payload.documento,
        email=payload.email,
    )
    await synchronizer.broadcast("client_upsert", {"client": client.to_dict()})
    return client.to_dict()


@router.get("")
async def listar_clientes(user=Depends(get_current_user)):
    return [client.to_dict() for client in inventory_state.list_clients()]


@router.get("/{cliente_id}")
async def obter_cliente(cliente_id: str, user=Depends(get_current_user)):
    client = inventory_state.get_client(cliente_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente não encontrado")
    return client.to_dict()
