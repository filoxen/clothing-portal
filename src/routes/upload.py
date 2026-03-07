import asyncio
import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, HTTPException

logger = logging.getLogger(__name__)
from sse_starlette.sse import EventSourceResponse

from src import database
from src.auth import require_user
from src.templates import templates

router = APIRouter()

# In-memory batch progress tracking
batch_progress: dict[str, list[dict]] = {}


@router.get("/upload")
async def upload_page(request: Request, user: dict = Depends(require_user)):
    return templates.TemplateResponse("upload.html", {"request": request, "user": user})


@router.post("/api/upload/batch")
async def start_batch_upload(
    request: Request,
    group_id: int = Form(...),
    asset_type: int = Form(...),
    price: int = Form(...),
    names: str = Form(...),
    descriptions: str = Form(...),
    images: list[UploadFile] = File(...),
    user: dict = Depends(require_user),
):
    name_list = json.loads(names)
    desc_list = json.loads(descriptions)

    if len(name_list) != len(images):
        raise HTTPException(400, "Mismatch between names and images count")

    batch_id = uuid.uuid4().hex[:12]
    items = []

    for i, (name, desc, image_file) in enumerate(zip(name_list, desc_list, images)):
        image_bytes = await image_file.read()
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        upload_id = await database.create_upload(
            user_id=user["id"],
            batch_id=batch_id,
            name=name,
            description=desc,
            asset_type=asset_type,
            group_id=group_id,
            price=price,
            image_hash=image_hash,
        )

        items.append({
            "upload_id": upload_id,
            "name": name,
            "description": desc,
            "image": image_bytes,
            "image_hash": image_hash,
            "asset_type": asset_type,
            "group_id": group_id,
            "price": price,
            "index": i,
        })

    # Initialize progress
    batch_progress[batch_id] = [{"index": i, "status": "pending"} for i in range(len(items))]

    # Start upload in background
    asyncio.create_task(_process_batch(batch_id, items))

    return {"batch_id": batch_id}


async def _process_batch(batch_id: str, items: list[dict]):
    from src.app import roblox_client
    from rbx_upload import RateLimitError, RbxAssetType

    try:
        for item in items:
            idx = item["index"]
            batch_progress[batch_id][idx] = {"index": idx, "status": "uploading", "name": item["name"]}

            try:
                # Check for duplicate
                dup = await database.get_duplicate_upload(item["image_hash"], item["asset_type"])
                if dup:
                    await database.update_upload_status(item["upload_id"], "duplicate", asset_id=dup["asset_id"])
                    batch_progress[batch_id][idx] = {
                        "index": idx, "status": "duplicate", "asset_id": dup["asset_id"], "name": item["name"],
                    }
                    continue

                # Upload
                result = await roblox_client.upload_clothing_image(
                    image=item["image"],
                    name=item["name"],
                    description=item["description"],
                    asset_type=RbxAssetType(item["asset_type"]),
                    group_id=item["group_id"],
                )
                asset_id = result["asset_id"]
                await database.update_upload_status(item["upload_id"], "uploaded", asset_id=asset_id)

                # Wait for processing
                await asyncio.sleep(5)

                # Publish as Limited, then put on sale
                collectible_item_id = await roblox_client.publish_collectible(
                    asset_id, item["group_id"], item["name"], item["description"], item["price"]
                )
                try:
                    await roblox_client.onsale_asset(collectible_item_id, price=item["price"])
                    await database.update_upload_status(item["upload_id"], "onsale", asset_id=asset_id)
                    batch_progress[batch_id][idx] = {
                        "index": idx, "status": "onsale", "asset_id": asset_id, "name": item["name"],
                    }
                except RateLimitError:
                    logger.warning(f"Rate limited putting '{item['name']}' on sale (asset {asset_id}), queued for retry")
                    await database.add_to_onsale_queue(
                        upload_id=item["upload_id"],
                        asset_id=asset_id,
                        price=item["price"],
                        collectible_item_id=collectible_item_id,
                    )
                    batch_progress[batch_id][idx] = {
                        "index": idx, "status": "uploaded (queued for sale)", "asset_id": asset_id, "name": item["name"],
                    }

            except Exception as exc:
                logger.error(f"Upload failed for '{item['name']}' (batch {batch_id}): {exc}")
                await database.update_upload_status(item["upload_id"], "failed", error=str(exc))
                batch_progress[batch_id][idx] = {
                    "index": idx, "status": "failed", "error": str(exc), "name": item["name"],
                }
            finally:
                # Release image bytes after processing each item
                item.pop("image", None)
    finally:
        # Always mark done so SSE clients can clean up
        batch_progress.setdefault(batch_id, []).append({"type": "done"})


@router.get("/api/upload/progress/{batch_id}")
async def upload_progress(batch_id: str, user: dict = Depends(require_user)):
    if batch_id not in batch_progress:
        raise HTTPException(404, "Batch not found")

    async def event_stream():
        sent = 0
        while True:
            progress = batch_progress.get(batch_id, [])
            while sent < len(progress):
                entry = progress[sent]
                yield {"data": json.dumps(entry)}
                if entry.get("type") == "done":
                    batch_progress.pop(batch_id, None)
                    return
                sent += 1
            await asyncio.sleep(0.5)

    return EventSourceResponse(event_stream())
