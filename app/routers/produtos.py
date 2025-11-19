from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..core.context import inventory_state, synchronizer
from ..core.dependencies import get_current_user, require_admin
from ..core.http import dual_request_body, get_payload
from ..schemas import ProductRequest

router = APIRouter(prefix="/produtos", tags=["Produtos"])


@router.post(
    "",
    dependencies=[Depends(require_admin)],
    openapi_extra=dual_request_body(ProductRequest),
)
async def criar_produto(request: Request):
    payload: ProductRequest = await get_payload(request, ProductRequest)
    product = inventory_state.upsert_product(
        product_id=str(uuid.uuid4()),
        nome=payload.nome,
        descricao=payload.descricao,
        ativo=payload.ativo,
    )
    await synchronizer.broadcast("product_upsert", {"product": product.to_dict()})
    return product.to_dict()


@router.get("")
async def listar_produtos(user=Depends(get_current_user)):
    return [product.to_dict() for product in inventory_state.list_products()]


@router.get("/{produto_id}")
async def obter_produto(produto_id: str, user=Depends(get_current_user)):
    product = inventory_state.get_product(produto_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")
    return product.to_dict()
