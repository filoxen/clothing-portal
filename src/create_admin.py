"""CLI script to create an admin user.

Usage: uv run python -m src.create_admin
"""
import asyncio
import getpass

from src.database import init_db, get_user_by_username, create_user
from src.auth import hash_password


async def main():
    await init_db()

    username = input("Admin username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    existing = await get_user_by_username(username)
    if existing:
        print(f"User '{username}' already exists.")
        return

    password = getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty.")
        return

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return

    await create_user(username, hash_password(password), is_admin=True)
    print(f"Admin user '{username}' created.")


if __name__ == "__main__":
    asyncio.run(main())
