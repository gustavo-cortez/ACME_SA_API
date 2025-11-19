from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core.context import inventory_state, synchronizer
from ..core.dependencies import get_current_user
from ..core.http import dual_request_body, get_payload
from ..schemas import EstoqueUpdateRequest
from ..services.inventory import EntityNotFound, StockUnavailableError

router = APIRouter(prefix="/estoque", tags=["Estoque"])


@router.get("/{produto_id}")
async def obter_estoque(produto_id: str, user=Depends(get_current_user)):
    entry = inventory_state.get_stock(produto_id)
    return entry.to_dict()


@router.put(
    "/{produto_id}",
    openapi_extra=dual_request_body(EstoqueUpdateRequest),
)
async def atualizar_estoque(request: Request, produto_id: str, user=Depends(get_current_user)):
    payload: EstoqueUpdateRequest = await get_payload(request, EstoqueUpdateRequest)
    if payload.variacao == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variação não pode ser zero")
    referencia = payload.motivo or "ajuste-manual"
    try:
        entry = await inventory_state.adjust_stock(produto_id, payload.variacao, referencia)
    except EntityNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    product = inventory_state.get_product(produto_id)
    await synchronizer.broadcast(
        "stock_update",
        {"entry": entry.to_dict(), "produto": product.to_dict() if product else None},
    )
    return entry.to_dict()
