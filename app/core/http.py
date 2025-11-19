from __future__ import annotations

import json
from typing import Any, Dict, Type

from fastapi import HTTPException, Request, status


def dual_request_body(model: Type) -> Dict[str, Any]:
    schema = model.model_json_schema()
    return {
        "requestBody": {
            "content": {
                "application/json": {"schema": schema},
                "application/x-www-form-urlencoded": {"schema": schema},
            }
        }
    }


def parse_payload(model: Type, data: Dict[str, Any]) -> Any:
    if model.__name__ == "PedidoRequest":
        itens_raw = data.get("itens") or data.get("itens_json")
        if isinstance(itens_raw, str):
            try:
                data["itens"] = json.loads(itens_raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Itens inválidos (JSON)",
                ) from exc
    return model(**data)


async def get_payload(request: Request, model: Type) -> Any:
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        raw = await request.json()
    else:
        form = await request.form()
        raw = dict(form)
    return parse_payload(model, raw)
