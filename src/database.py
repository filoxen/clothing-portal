import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                batch_id TEXT NOT NULL,
                asset_id INTEGER,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                asset_type INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                price INTEGER NOT NULL DEFAULT 5,
                image_hash TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS onsale_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                upload_id INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                collectible_item_id TEXT,
                price INTEGER NOT NULL DEFAULT 5,
                retry_count INTEGER DEFAULT 0,
                next_retry DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (upload_id) REFERENCES uploads(id)
            );
        """)
        await db.commit()
        try:
            await db.execute("ALTER TABLE onsale_queue ADD COLUMN collectible_item_id TEXT")
            await db.commit()
        except Exception:
            pass
    finally:
        await db.close()


# --- User queries ---

async def get_user_by_username(username: str) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_user_by_id(user_id: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_all_users() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def create_user(username: str, password_hash: str, is_admin: bool = False) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
            (username, password_hash, int(is_admin)),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def delete_user(user_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
    finally:
        await db.close()


async def update_user_password(user_id: int, password_hash: str):
    db = await get_db()
    try:
        await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        await db.commit()
    finally:
        await db.close()


# --- Upload queries ---

async def create_upload(user_id: int, batch_id: str, name: str, description: str,
                        asset_type: int, group_id: int, price: int, image_hash: str) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            """INSERT INTO uploads (user_id, batch_id, name, description, asset_type, group_id, price, image_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, batch_id, name, description, asset_type, group_id, price, image_hash),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def update_upload_status(upload_id: int, status: str, asset_id: int | None = None, error: str | None = None):
    db = await get_db()
    try:
        if asset_id is not None:
            await db.execute(
                "UPDATE uploads SET status = ?, asset_id = ?, error = ? WHERE id = ?",
                (status, asset_id, error, upload_id),
            )
        else:
            await db.execute(
                "UPDATE uploads SET status = ?, error = ? WHERE id = ?",
                (status, error, upload_id),
            )
        await db.commit()
    finally:
        await db.close()


async def get_uploads_by_batch(batch_id: str) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM uploads WHERE batch_id = ? ORDER BY id", (batch_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_upload_history(limit: int = 100) -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT u.*, usr.username FROM uploads u
               JOIN users usr ON u.user_id = usr.id
               ORDER BY u.created_at DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def get_duplicate_upload(image_hash: str, asset_type: int) -> dict | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM uploads WHERE image_hash = ? AND asset_type = ? AND status IN ('uploaded', 'onsale')",
            (image_hash, asset_type),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


# --- Onsale queue queries ---

async def add_to_onsale_queue(upload_id: int, asset_id: int, price: int,
                               collectible_item_id: str | None = None):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO onsale_queue (upload_id, asset_id, collectible_item_id, price)
               VALUES (?, ?, ?, ?)""",
            (upload_id, asset_id, collectible_item_id, price),
        )
        await db.commit()
    finally:
        await db.close()


async def get_pending_onsale() -> list[dict]:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM onsale_queue WHERE next_retry <= CURRENT_TIMESTAMP ORDER BY next_retry"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def update_onsale_retry(queue_id: int, retry_count: int, delay_seconds: int):
    db = await get_db()
    try:
        await db.execute(
            """UPDATE onsale_queue SET retry_count = ?, next_retry = datetime('now', '+' || ? || ' seconds')
               WHERE id = ?""",
            (retry_count, delay_seconds, queue_id),
        )
        await db.commit()
    finally:
        await db.close()


async def remove_from_onsale_queue(queue_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM onsale_queue WHERE id = ?", (queue_id,))
        await db.commit()
    finally:
        await db.close()
