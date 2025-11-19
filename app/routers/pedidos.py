from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core.context import inventory_state, synchronizer
from ..core.dependencies import get_current_user
from ..core.http import dual_request_body, get_payload
from ..schemas import PedidoRequest
from ..services.inventory import EntityNotFound, OrderItem, StockUnavailableError

router = APIRouter(prefix="/pedido", tags=["Pedidos"])


@router.post(
    "",
    openapi_extra=dual_request_body(PedidoRequest),
)
async def criar_pedido(request: Request, user=Depends(get_current_user)):
    payload: PedidoRequest = await get_payload(request, PedidoRequest)
    if not payload.cliente_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cliente_id é obrigatório")
    itens = [OrderItem(produto_id=item.produto_id, quantidade=item.quantidade) for item in payload.itens]
    try:
        order, stock_entries, produtos_map = await inventory_state.register_order(
            payload.cliente_id, itens, payload.pedido_id
        )
    except EntityNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StockUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    cliente = inventory_state.get_client(order.cliente_id)
    produtos_payload = [produtos_map[pid].to_dict() for pid in produtos_map]
    order_data = order.to_dict()
    await synchronizer.broadcast(
        "order_created",
        {
            "order": order_data,
            "cliente": cliente.to_dict() if cliente else None,
            "produtos": produtos_payload,
        },
    )
    await asyncio.gather(
        *[
            synchronizer.broadcast(
                "stock_update",
                {
                    "entry": entry.to_dict(),
                    "produto": produtos_map[entry.product_id].to_dict(),
                },
            )
            for entry in stock_entries
        ]
    )
    return {"pedido": order_data}


@router.get("/{pedido_id}")
async def obter_pedido(pedido_id: str, user=Depends(get_current_user)):
    order = inventory_state.get_order(pedido_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado")
    return order.to_dict()
