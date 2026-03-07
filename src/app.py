import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from rbx_upload import RobloxClient

from src.auth import NotAuthenticatedError
from src.config import ROBLOSECURITY_TOKEN, PUBLISHER_USER_ID, ROBLOX_PROXY
from src.database import init_db
from src.services.queue import process_onsale_queue

roblox_client: RobloxClient = None
_queue_task: asyncio.Task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global roblox_client, _queue_task

    await init_db()

    async with RobloxClient(
        roblosecurity=ROBLOSECURITY_TOKEN,
        publisher_user_id=int(PUBLISHER_USER_ID),
        proxy=ROBLOX_PROXY or None,
    ) as client:
        roblox_client = client
        _queue_task = asyncio.create_task(process_onsale_queue(roblox_client))
        yield
        _queue_task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Import and include routers
from src.routes.auth import router as auth_router
from src.routes.admin import router as admin_router
from src.routes.groups import router as groups_router
from src.routes.upload import router as upload_router
from src.routes.history import router as history_router
from src.routes.manage import router as manage_router

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(groups_router)
app.include_router(upload_router)
app.include_router(history_router)
app.include_router(manage_router)


@app.get("/")
async def index():
    return RedirectResponse(url="/upload")


@app.exception_handler(NotAuthenticatedError)
async def redirect_to_login(request: Request, exc):
    return RedirectResponse(url="/login", status_code=303)
