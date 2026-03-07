import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request, HTTPException
from sse_starlette.sse import EventSourceResponse

from src.auth import require_user
from src.services.roblox import fetch_group_clothing, onsale_asset, offsale_asset
from src.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory progress for bulk operations
manage_progress: dict[str, list[dict]] = {}


@router.get("/manage")
async def manage_page(request: Request, user: dict = Depends(require_user)):
    return templates.TemplateResponse("manage.html", {"request": request, "user": user})


@router.get("/api/manage/clothing")
async def list_clothing(group_id: int, cursor: str = "", user: dict = Depends(require_user)):
    data = await fetch_group_clothing(group_id, cursor)
    return data


@router.post("/api/manage/onsale")
async def bulk_onsale(
    request: Request,
    user: dict = Depends(require_user),
):
    body = await request.json()
    items = body.get("items", [])  # [{collectible_item_id, name}, ...]
    price = body.get("price", 5)

    if not items:
        raise HTTPException(400, "No items selected")

    op_id = f"onsale-{id(items)}"
    manage_progress[op_id] = []

    asyncio.create_task(_bulk_sale_operation(op_id, items, price, "onsale"))
    return {"op_id": op_id}


@router.post("/api/manage/offsale")
async def bulk_offsale(
    request: Request,
    user: dict = Depends(require_user),
):
    body = await request.json()
    items = body.get("items", [])

    if not items:
        raise HTTPException(400, "No items selected")

    op_id = f"offsale-{id(items)}"
    manage_progress[op_id] = []

    asyncio.create_task(_bulk_sale_operation(op_id, items, 0, "offsale"))
    return {"op_id": op_id}


async def _bulk_sale_operation(op_id: str, items: list[dict], price: int, action: str):
    try:
        for i, item in enumerate(items):
            asset_id = item["id"]
            name = item.get("name", str(asset_id))
            manage_progress[op_id].append({
                "index": i, "name": name, "status": "processing",
            })
            try:
                if action == "onsale":
                    await onsale_asset(item["collectible_item_id"], price=price)
                else:
                    await offsale_asset(item["collectible_item_id"], price=int(item.get("price") or 5))

                manage_progress[op_id][-1]["status"] = "done"
            except Exception as exc:
                logger.error(f"{action} failed for '{name}': {exc}")
                manage_progress[op_id][-1]["status"] = f"failed: {exc}"

            if i < len(items) - 1:
                await asyncio.sleep(1)
    finally:
        manage_progress[op_id].append({"type": "done"})


@router.get("/api/manage/progress/{op_id}")
async def manage_op_progress(op_id: str, user: dict = Depends(require_user)):
    if op_id not in manage_progress:
        raise HTTPException(404, "Operation not found")

    async def event_stream():
        sent = 0
        while True:
            progress = manage_progress.get(op_id, [])
            while sent < len(progress):
                entry = progress[sent]
                yield {"data": json.dumps(entry)}
                if entry.get("type") == "done":
                    manage_progress.pop(op_id, None)
                    return
                sent += 1
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_stream())
