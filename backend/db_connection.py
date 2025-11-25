"""
Database connection abstraction layer for DocuFlow.
Supports both SQLite (development) and PostgreSQL (production).
"""
import os
import logging
from typing import Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# Get database URL from environment or use SQLite default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./docuflow.db")

# Determine database type
if DATABASE_URL.startswith("postgresql"):
    DB_TYPE = "postgresql"
    import asyncpg
elif DATABASE_URL.startswith("sqlite"):
    DB_TYPE = "sqlite"
    try:
        import aiosqlite
    except ImportError:
        aiosqlite = None
else:
    raise ValueError(f"Unsupported database URL: {DATABASE_URL}")

logger.info(f"Using database type: {DB_TYPE}")


class DatabaseConnection:
    """
    Unified database connection interface for both SQLite and PostgreSQL.
    Provides a consistent API regardless of the underlying database.
    """

    def __init__(self, connection):
        self.connection = connection
        self.db_type = DB_TYPE

    async def execute(self, query: str, *args):
        """Execute a query with parameters."""
        if self.db_type == "sqlite":
            return await self.connection.execute(query, args if args else ())
        else:  # postgresql
            # Convert SQLite-style ? placeholders to PostgreSQL $1, $2, etc.
            pg_query = self._convert_placeholders(query)
            return await self.connection.execute(pg_query, *args)

    async def fetch(self, query: str, *args):
        """Fetch all rows from a query."""
        if self.db_type == "sqlite":
            cursor = await self.connection.execute(query, args if args else ())
            return await cursor.fetchall()
        else:  # postgresql
            pg_query = self._convert_placeholders(query)
            return await self.connection.fetch(pg_query, *args)

    async def fetchone(self, query: str, *args):
        """Fetch one row from a query."""
        if self.db_type == "sqlite":
            cursor = await self.connection.execute(query, args if args else ())
            return await cursor.fetchone()
        else:  # postgresql
            pg_query = self._convert_placeholders(query)
            return await self.connection.fetchrow(pg_query, *args)

    async def fetchval(self, query: str, *args):
        """Fetch a single value from a query."""
        if self.db_type == "sqlite":
            cursor = await self.connection.execute(query, args if args else ())
            row = await cursor.fetchone()
            return row[0] if row else None
        else:  # postgresql
            pg_query = self._convert_placeholders(query)
            return await self.connection.fetchval(pg_query, *args)

    async def commit(self):
        """Commit the transaction."""
        if self.db_type == "sqlite":
            await self.connection.commit()
        # PostgreSQL commits automatically unless in a transaction block

    async def close(self):
        """Close the connection."""
        if self.db_type == "sqlite":
            await self.connection.close()
        else:  # postgresql
            await self.connection.close()

    def _convert_placeholders(self, query: str) -> str:
        """Convert SQLite ? placeholders to PostgreSQL $1, $2, etc."""
        if self.db_type != "postgresql":
            return query

        result = []
        param_num = 1
        in_string = False
        escape_next = False

        for char in query:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            if char in ("'", '"'):
                in_string = not in_string
                result.append(char)
                continue

            if char == '?' and not in_string:
                result.append(f'${param_num}')
                param_num += 1
            else:
                result.append(char)

        return ''.join(result)

    @property
    def lastrowid(self):
        """Get the last inserted row ID (SQLite only)."""
        if self.db_type == "sqlite":
            return self.connection.lastrowid
        return None


async def get_db_connection() -> DatabaseConnection:
    """
    Get a database connection based on DATABASE_URL.

    Returns:
        DatabaseConnection: Unified database connection interface
    """
    if DB_TYPE == "sqlite":
        if aiosqlite is None:
            raise RuntimeError("aiosqlite is not installed")

        # Extract path from sqlite URL
        db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        if not db_path.startswith("/"):
            # Relative path
            db_path = Path(__file__).parent.parent / db_path

        conn = await aiosqlite.connect(str(db_path), timeout=30.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute("PRAGMA journal_mode=WAL")

        return DatabaseConnection(conn)

    else:  # postgresql
        # Parse PostgreSQL URL
        # Format: postgresql://user:password@host:port/database
        conn = await asyncpg.connect(DATABASE_URL, timeout=30.0)
        return DatabaseConnection(conn)


def get_sync_db_connection():
    """
    Get a synchronous database connection (SQLite only).
    Used for legacy sync code paths.
    """
    if DB_TYPE != "sqlite":
        raise RuntimeError("Synchronous connections only supported for SQLite")

    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not db_path.startswith("/"):
        db_path = Path(__file__).parent.parent / db_path

    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    return conn
