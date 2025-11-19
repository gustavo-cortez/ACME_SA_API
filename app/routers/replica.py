from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..core.context import inventory_state
from ..core.security import require_replication_token

router = APIRouter(prefix="/replica", tags=["Replicação"])


@router.post("/event", dependencies=[Depends(require_replication_token)])
async def aplicar_evento(evento: dict):
    tipo = evento.get("tipo")
    payload = evento.get("payload", {})
    if tipo == "order_created":
        order_payload = payload.get("order")
        cliente_payload = payload.get("cliente")
        produtos_payload = payload.get("produtos", [])
        if not order_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para pedido")
        record = inventory_state.apply_remote_order(order_payload, cliente_payload, produtos_payload)
        return {"status": "ok", "order": record.to_dict()}
    if tipo == "stock_update":
        entry_payload = payload.get("entry")
        produto_payload = payload.get("produto")
        if produto_payload:
            inventory_state.apply_remote_product(produto_payload)
        if not entry_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para estoque")
        entry = await inventory_state.apply_remote_stock(
            product_id=entry_payload["product_id"],
            saldo=entry_payload["saldo"],
            versao=entry_payload["versao"],
            origem=entry_payload.get("origem", "replica"),
            referencia=entry_payload.get("referencia"),
            atualizado_em=entry_payload.get("atualizado_em"),
        )
        return {"status": "ok", "entry": entry.to_dict()}
    if tipo == "client_upsert":
        client_payload = payload.get("client")
        if not client_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para cliente")
        client = inventory_state.apply_remote_client(client_payload)
        return {"status": "ok", "client": client.to_dict()}
    if tipo == "product_upsert":
        product_payload = payload.get("product")
        if not product_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para produto")
        product = inventory_state.apply_remote_product(product_payload)
        return {"status": "ok", "product": product.to_dict()}
    if tipo == "user_upsert":
        user_payload = payload.get("user")
        password_hash = payload.get("password_hash")
        if not user_payload or not password_hash:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload inválido para usuário")
        user = inventory_state.apply_remote_user(
            {
                "username": user_payload["username"],
                "role": user_payload.get("role", "user"),
                "password_hash": password_hash,
                "criado_em": user_payload.get("criado_em"),
            }
        )
        return {"status": "ok", "user": user.to_dict()}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tipo de evento desconhecido")
