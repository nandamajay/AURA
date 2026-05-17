"""SQLite migration runner.

Migrations are SQL files in knowledge/schema/, named NNN_descriptive_name.sql.
Applied migrations tracked in _migrations table.
"""

import os
from pathlib import Path
from typing import Optional

import aiosqlite

def _discover_default_migrations_dir() -> Path:
    """Locate knowledge/schema by walking up from this module."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "knowledge" / "schema"
        if candidate.exists():
            return candidate
    # Fallback for expected monorepo shape; may not exist.
    return here.parents[5] / "knowledge" / "schema"


# Default migrations directory (auto-discovered relative to repo root)
DEFAULT_MIGRATIONS_DIR = _discover_default_migrations_dir()

# Allow override via environment
_MIGRATIONS_DIR = Path(os.environ.get("AURA_MIGRATIONS_DIR", DEFAULT_MIGRATIONS_DIR))


class MigrationRunner:
    """SQLite migration runner. Version tracked in _migrations table."""

    def __init__(self, db_path: str, migrations_dir: Optional[Path] = None):
        self.db_path = db_path
        self.migrations_dir = migrations_dir or _MIGRATIONS_DIR

    async def migrate(self) -> int:
        """Run pending migrations. Returns count run.

        Each migration runs in a transaction. On failure, rolls back
        and re-raises the exception.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.execute("PRAGMA foreign_keys = ON")

            # Ensure migrations tracking table exists
            await db.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY,
                    filename TEXT NOT NULL UNIQUE,
                    applied_at INTEGER NOT NULL DEFAULT (unixepoch()),
                    checksum TEXT
                )
            """)
            await db.commit()

            # Get already applied
            cursor = await db.execute("SELECT filename FROM _migrations")
            applied = {row[0] for row in await cursor.fetchall()}

            # Find pending migrations (sorted by filename for order)
            if not self.migrations_dir.exists():
                print(f"Migrations directory not found: {self.migrations_dir}")
                return 0

            migration_files = sorted(
                f for f in os.listdir(self.migrations_dir)
                if f.endswith(".sql") and not f.endswith(".down.sql") and f not in applied
            )

            count = 0
            for filename in migration_files:
                filepath = self.migrations_dir / filename
                sql = filepath.read_text()

                # Execute migration in transaction
                await db.execute("BEGIN TRANSACTION")
                try:
                    await db.executescript(sql)
                    await db.execute(
                        "INSERT INTO _migrations (filename) VALUES (?)",
                        (filename,),
                    )
                    await db.commit()
                    count += 1
                    print(f"Applied migration: {filename}")
                except Exception:
                    await db.rollback()
                    raise

            # Verify integrity
            cursor = await db.execute("PRAGMA integrity_check")
            integrity = await cursor.fetchone()
            if integrity and integrity[0] != "ok":
                raise RuntimeError(f"Database integrity check failed: {integrity[0]}")

            return count

    async def current_version(self) -> Optional[str]:
        """Return latest applied migration filename."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT filename FROM _migrations ORDER BY id DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            return row[0] if row else None

    async def applied_count(self) -> int:
        """Return total number of applied migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM _migrations")
            row = await cursor.fetchone()
            return row[0] if row else 0
