import logging
import time

import httpx

logger = logging.getLogger(__name__)

from src.config import ROBLOSECURITY_TOKEN, PUBLISHER_USER_ID, ROBLOX_PROXY

_groups_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 300  # 5 minutes


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


async def fetch_group_clothing(group_id: int, cursor: str = "") -> dict:
    url = _proxy_url("https://catalog.roblox.com/v1/search/items/details")
    params = {
        "Category": 3,
        "CreatorType": 2,
        "CreatorTargetId": group_id,
        "IncludeNotForSale": "true",
        "Limit": 30,
    }
    if cursor:
        params["Cursor"] = cursor

    async with httpx.AsyncClient(cookies=_auth_cookies()) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        raw_items = data.get("data", [])
        asset_ids = [item.get("id") for item in raw_items if item.get("id")]

        thumbnails = {}
        if asset_ids:
            thumb_resp = await client.get(
                _proxy_url("https://thumbnails.roblox.com/v1/assets"),
                params={"assetIds": ",".join(str(i) for i in asset_ids), "returnPolicy": "PlaceHolder", "size": "150x150", "format": "Png", "isCircular": "false"},
            )
            if thumb_resp.status_code == 200:
                for t in thumb_resp.json().get("data", []):
                    thumbnails[t["targetId"]] = t.get("imageUrl", "")

    items = []
    for item in raw_items:
        asset_id = item.get("id")
        items.append({
            "id": asset_id,
            "group_id": group_id,
            "collectible_item_id": item.get("collectibleItemId", ""),
            "name": item.get("name", ""),
            "asset_type": item.get("assetType"),
            "price": item.get("price"),
            "lowest_price": item.get("lowestPrice"),
            "off_sale": item.get("priceStatus") == "Off Sale" or (item.get("price") is None and item.get("lowestPrice") is None),
            "thumbnail": thumbnails.get(asset_id, ""),
            "created_utc": item.get("itemCreatedUtc", ""),
        })

    return {
        "items": items,
        "next_cursor": data.get("nextPageCursor") or "",
    }


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
