import asyncio
import logging

from src import database

logger = logging.getLogger(__name__)

RETRY_INTERVAL = 60
RETRY_DELAY = 300


async def process_onsale_queue(roblox_client):
    from rbx_upload import RateLimitError

    while True:
        try:
            pending = await database.get_pending_onsale()
            for item in pending:
                try:
                    collectible_item_id = item["collectible_item_id"] or await roblox_client.get_collectible_item_id(item["asset_id"])
                    await roblox_client.onsale_asset(collectible_item_id, price=item["price"])
                    await database.update_upload_status(item["upload_id"], "onsale", asset_id=item["asset_id"])
                    await database.remove_from_onsale_queue(item["id"])
                    logger.info(f"Onsale succeeded for asset {item['asset_id']}")
                except RateLimitError:
                    retry = item["retry_count"] + 1
                    await database.update_onsale_retry(item["id"], retry, RETRY_DELAY)
                    logger.warning(f"Rate limited for asset {item['asset_id']}, retry #{retry}")
                except Exception as e:
                    retry = item["retry_count"] + 1
                    await database.update_onsale_retry(item["id"], retry, RETRY_DELAY * 2)
                    logger.error(f"Onsale failed for asset {item['asset_id']}: {e}")
        except Exception as e:
            logger.error(f"Queue processing error: {e}")

        await asyncio.sleep(RETRY_INTERVAL)
