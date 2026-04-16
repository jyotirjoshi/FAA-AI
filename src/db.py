from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:YQ4MPeBzY2wfA9UK@db.fdrpeifcfztrysbaomje.supabase.co:5432/postgres",
)


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def create_session() -> str:
    pool = await get_pool()
    row = await pool.fetchrow("INSERT INTO sessions DEFAULT VALUES RETURNING id")
    return str(row["id"])


async def save_message(
    session_id: str,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    confidence: float = 0.0,
) -> None:
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO messages (session_id, role, content, citations, confidence)
        VALUES ($1::uuid, $2, $3, $4::jsonb, $5)
        """,
        session_id,
        role,
        content,
        json.dumps(citations or []),
        confidence,
    )


async def get_history(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return last `limit` messages for a session, oldest first."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT role, content, citations, confidence, created_at
        FROM messages
        WHERE session_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2
        """,
        session_id,
        limit,
    )
    return [
        {
            "role": r["role"],
            "content": r["content"],
            "citations": json.loads(r["citations"]) if r["citations"] else [],
            "confidence": r["confidence"],
        }
        for r in reversed(rows)
    ]


async def session_exists(session_id: str) -> bool:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM sessions WHERE id = $1::uuid", session_id
    )
    return row is not None
