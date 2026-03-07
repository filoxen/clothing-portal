from fastapi import APIRouter, Depends

from src.auth import require_user
from src.services.roblox import get_uploadable_groups

router = APIRouter(prefix="/api")


@router.get("/groups")
async def list_groups(user: dict = Depends(require_user)):
    groups = await get_uploadable_groups()
    return groups
