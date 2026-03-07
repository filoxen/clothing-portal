import bcrypt
from fastapi import Request, HTTPException
from itsdangerous import URLSafeSerializer

from src.config import SECRET_KEY

serializer = URLSafeSerializer(SECRET_KEY)


class NotAuthenticatedError(Exception):
    pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"user_id": user_id})


def get_session_user_id(token: str) -> int | None:
    try:
        data = serializer.loads(token)
        return data.get("user_id")
    except Exception:
        return None


async def require_user(request: Request) -> dict:
    from src.database import get_user_by_id

    token = request.cookies.get("session")
    if not token:
        raise NotAuthenticatedError()

    user_id = get_session_user_id(token)
    if user_id is None:
        raise NotAuthenticatedError()

    user = await get_user_by_id(user_id)
    if user is None:
        raise NotAuthenticatedError()

    return user


async def require_admin(request: Request) -> dict:
    user = await require_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
