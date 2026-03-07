from fastapi import APIRouter, Request, Depends, Form

from src import database
from src.auth import require_admin, hash_password
from src.templates import templates

router = APIRouter(prefix="/admin")


async def _render(request, user, **kwargs):
    users = await database.get_all_users()
    return templates.TemplateResponse("admin.html", {
        "request": request, "user": user, "users": users, **kwargs,
    })


@router.get("")
async def admin_page(request: Request, user: dict = Depends(require_admin)):
    return await _render(request, user)


@router.post("/create-user")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str = Form("0"),
    user: dict = Depends(require_admin),
):
    existing = await database.get_user_by_username(username)
    if existing:
        return await _render(request, user, error=f"User '{username}' already exists")

    await database.create_user(username, hash_password(password), is_admin=is_admin == "1")
    return await _render(request, user, success=f"User '{username}' created")


@router.post("/reset-password")
async def reset_password(
    request: Request,
    user_id: int = Form(...),
    password: str = Form(...),
    user: dict = Depends(require_admin),
):
    await database.update_user_password(user_id, hash_password(password))
    return await _render(request, user, success="Password updated")


@router.post("/delete-user")
async def delete_user(
    request: Request,
    user_id: int = Form(...),
    user: dict = Depends(require_admin),
):
    if user_id == user["id"]:
        return await _render(request, user, error="Cannot delete yourself")
    await database.delete_user(user_id)
    return await _render(request, user, success="User deleted")
