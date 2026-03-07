from fastapi import APIRouter, Request, Depends

from src import database
from src.auth import require_user
from src.templates import templates

router = APIRouter()


@router.get("/history")
async def history_page(request: Request, user: dict = Depends(require_user)):
    uploads = await database.get_upload_history()
    return templates.TemplateResponse("history.html", {
        "request": request, "user": user, "uploads": uploads,
    })
