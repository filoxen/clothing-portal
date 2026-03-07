from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from src import database
from src.auth import verify_password, create_session_token
from src.templates import templates

router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = await database.get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password",
        })

    response = RedirectResponse(url="/upload", status_code=303)
    response.set_cookie("session", create_session_token(user["id"]), httponly=True, samesite="lax")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response
