from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None
_fallback_sessions: dict[str, list[dict[str, Any]]] = {}

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
    try:
        pool = await get_pool()
        row = await pool.fetchrow("INSERT INTO sessions DEFAULT VALUES RETURNING id")
        return str(row["id"])
    except Exception:
        session_id = str(uuid4())
        _fallback_sessions.setdefault(session_id, [])
        return session_id


async def save_message(
    session_id: str,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    confidence: float = 0.0,
) -> None:
    payload = {
        "role": role,
        "content": content,
        "citations": citations or [],
        "confidence": confidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
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
    except Exception:
        _fallback_sessions.setdefault(session_id, []).append(payload)


async def get_history(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return last `limit` messages for a session, oldest first."""
    try:
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
    except Exception:
        return _fallback_sessions.get(session_id, [])[-limit:]


async def session_exists(session_id: str) -> bool:
    try:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT 1 FROM sessions WHERE id = $1::uuid", session_id
        )
        return row is not None
    except Exception:
        return session_id in _fallback_sessions
