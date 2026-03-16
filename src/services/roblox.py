import asyncio
import base64
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

from src.config import ROBLOSECURITY_TOKEN, PUBLISHER_USER_ID, ROBLOX_PROXY

_groups_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 300  # 5 minutes
MAX_RETRIES = 3
RETRY_DELAY = 3.0


async def get_uploadable_groups() -> list[dict]:
    cache_key = "groups"
    now = time.time()

    if cache_key in _groups_cache:
        cached_time, cached_data = _groups_cache[cache_key]
        if now - cached_time < CACHE_TTL:
            return cached_data

    base_url = "groups.roblox.com"
    if ROBLOX_PROXY:
        base_url = base_url.replace("roblox.com", ROBLOX_PROXY)

    url = f"https://{base_url}/v1/users/{PUBLISHER_USER_ID}/groups/roles"

    async with httpx.AsyncClient(cookies={".ROBLOSECURITY": ROBLOSECURITY_TOKEN}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    groups = []
    for entry in data.get("data", []):
        group = entry.get("group", {})
        role = entry.get("role", {})
        rank = role.get("rank", 0)

        if rank >= 254:
            groups.append({
                "id": group["id"],
                "name": group["name"],
                "role": role.get("name", ""),
            })

    _groups_cache[cache_key] = (now, groups)
    return groups


def _proxy_url(url: str) -> str:
    if not ROBLOX_PROXY:
        return url
    return url.replace("roblox.com", ROBLOX_PROXY)


def _auth_cookies() -> dict:
    return {".ROBLOSECURITY": ROBLOSECURITY_TOKEN}


async def _get_csrf_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        _proxy_url("https://apis.roblox.com/assets/user-auth/v1/assets"),
        cookies=_auth_cookies(),
    )
    csrf = resp.headers.get("X-CSRF-TOKEN")
    if not csrf:
        raise Exception("Failed to get CSRF token")
    return csrf


async def _retry(coro_fn, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            return await coro_fn()
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))


def _encode_cursor(state: dict) -> str:
    return base64.b64encode(json.dumps(state).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.b64decode(cursor).decode())


async def fetch_group_clothing(group_id: int, cursor: str = "") -> dict:
    state = _decode_cursor(cursor) if cursor else {"type": "Shirt", "cursor": ""}
    asset_type = state["type"]
    inner_cursor = state["cursor"]

    async with httpx.AsyncClient(cookies=_auth_cookies()) as client:
        # Step 1: get a page of asset IDs from itemconfiguration
        id_params = {"assetType": asset_type, "groupId": group_id, "limit": 100}
        if inner_cursor:
            id_params["cursor"] = inner_cursor

        async def _fetch_ids():
            resp = await client.get(
                _proxy_url("https://itemconfiguration.roblox.com/v1/creations/get-assets"),
                params=id_params,
            )
            resp.raise_for_status()
            return resp.json()

        id_data = await _retry(_fetch_ids)
        asset_ids = [item["assetId"] for item in id_data.get("data", [])]
        next_inner_cursor = id_data.get("nextPageCursor", "")

        if not asset_ids:
            if asset_type == "Shirt":
                return {"items": [], "next_cursor": _encode_cursor({"type": "Pants", "cursor": ""})}
            return {"items": [], "next_cursor": ""}

        # Step 2+3: fetch details and thumbnails concurrently
        async def _fetch_details():
            csrf = await _get_csrf_token(client)
            resp = await client.post(
                _proxy_url("https://catalog.roblox.com/v1/catalog/items/details"),
                json={"items": [{"itemType": "Asset", "id": i} for i in asset_ids]},
                headers={"X-CSRF-TOKEN": csrf},
            )
            resp.raise_for_status()
            by_id = {}
            for item in resp.json().get("data", []):
                by_id[item["id"]] = item
            return by_id

        async def _fetch_thumbnails():
            resp = await client.get(
                _proxy_url("https://thumbnails.roblox.com/v1/assets"),
                params={"assetIds": ",".join(str(i) for i in asset_ids), "returnPolicy": "PlaceHolder", "size": "150x150", "format": "Png", "isCircular": "false"},
            )
            resp.raise_for_status()
            thumbs = {}
            for t in resp.json().get("data", []):
                thumbs[t["targetId"]] = t.get("imageUrl", "")
            return thumbs

        details_by_id, thumbnails = await asyncio.gather(
            _retry(_fetch_details), _retry(_fetch_thumbnails),
        )

    items = []
    asset_type_id = 11 if asset_type == "Shirt" else 12
    for asset_id in asset_ids:
        detail = details_by_id.get(asset_id, {})
        price = detail.get("price")
        lowest_price = detail.get("lowestPrice")
        items.append({
            "id": asset_id,
            "group_id": group_id,
            "collectible_item_id": detail.get("collectibleItemId", ""),
            "name": detail.get("name", ""),
            "asset_type": detail.get("assetType", asset_type_id),
            "price": price,
            "lowest_price": lowest_price,
            "off_sale": price is None and lowest_price is None,
            "thumbnail": thumbnails.get(asset_id, ""),
            "created_utc": detail.get("itemCreatedUtc", ""),
        })

    # Build next cursor
    if next_inner_cursor:
        next_cursor = _encode_cursor({"type": asset_type, "cursor": next_inner_cursor})
    elif asset_type == "Shirt":
        next_cursor = _encode_cursor({"type": "Pants", "cursor": ""})
    else:
        next_cursor = ""

    return {"items": items, "next_cursor": next_cursor}


_SALE_HEADERS = {
    "Referer": "https://create.roblox.com/",
    "Origin": "https://create.roblox.com",
}


async def onsale_asset(collectible_item_id: str, price: int):
    async with httpx.AsyncClient(cookies=_auth_cookies()) as client:
        csrf = await _get_csrf_token(client)
        resp = await client.patch(
            f"https://itemconfiguration.roblox.com/v1/collectibles/{collectible_item_id}",
            json={
                "saleLocationConfiguration": {"saleLocationType": 1, "places": []},
                "saleStatus": 0,
                "quantityLimitPerUser": 0,
                "resaleRestriction": 2,
                "priceInRobux": price,
                "priceOffset": 0,
                "optOutFromRegionalPricing": False,
                "isFree": False,
            },
            headers={"X-CSRF-TOKEN": csrf, **_SALE_HEADERS},
        )
        if resp.status_code == 429:
            raise Exception("Rate limited")
        resp.raise_for_status()
        return resp.json() if resp.text else {}


async def offsale_asset(collectible_item_id: str, price: int = 5):
    async with httpx.AsyncClient(cookies=_auth_cookies()) as client:
        csrf = await _get_csrf_token(client)
        resp = await client.patch(
            f"https://itemconfiguration.roblox.com/v1/collectibles/{collectible_item_id}",
            json={
                "saleLocationConfiguration": {"saleLocationType": 1, "places": []},
                "saleStatus": 1,
                "quantityLimitPerUser": 0,
                "resaleRestriction": 2,
                "priceInRobux": price,
                "priceOffset": 0,
                "optOutFromRegionalPricing": False,
                "isFree": False,
            },
            headers={"X-CSRF-TOKEN": csrf, **_SALE_HEADERS},
        )
        if resp.status_code == 429:
            raise Exception("Rate limited")
        resp.raise_for_status()
        return resp.json() if resp.text else {}
