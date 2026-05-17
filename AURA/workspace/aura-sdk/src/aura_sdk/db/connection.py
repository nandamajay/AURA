"""SQLite connection factory with WAL mode and async support.

Uses aiosqlite for async compatibility with FastAPI.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

# Global database path — set during init
_DB_PATH: str = ""


async def init_db(path: str) -> int:
    """Initialize the database: create directory, run migrations.

    Args:
        path: Path to SQLite database file.

    Returns:
        Number of migrations applied.
    """
    global _DB_PATH
    _DB_PATH = path

    # Ensure directory exists
    db_dir = Path(path).parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # Run migrations
    from aura_sdk.db.migrations import MigrationRunner

    runner = MigrationRunner(path)
    count = await runner.migrate()
    if count > 0:
        print(f"Applied {count} database migrations")

    return count


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an aiosqlite connection with WAL + FK enabled.

    Usage:
        async with get_db() as db:
            rows = await db.execute_fetchall("SELECT * FROM patches")
    """
    if not _DB_PATH:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("PRAGMA journal_mode = WAL")
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("PRAGMA synchronous = NORMAL")
        await db.execute("PRAGMA cache_size = 10000")
        await db.execute("PRAGMA temp_store = MEMORY")
        await db.execute("PRAGMA mmap_size = 268435456")
        await db.execute("PRAGMA busy_timeout = 5000")
        db.row_factory = aiosqlite.Row
        yield db
