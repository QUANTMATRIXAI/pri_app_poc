import datetime
from typing import List, Optional

from .database import get_connection


def create_default_segments() -> int:
    """Seed default segments if none exist; return the first segment id."""
    defaults = [
        ("North Star", "Primary strategic segment", "#f5b400"),
        ("Growth", "Emerging opportunities", "#6c8cff"),
        ("Retention", "Keep and win back customers", "#34c38f"),
    ]
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM segments ORDER BY id ASC").fetchall()
        if existing:
            return existing[0]["id"]

        now = datetime.datetime.utcnow().isoformat()
        for name, desc, color in defaults:
            conn.execute(
                "INSERT INTO segments (name, description, color, created_at) VALUES (?, ?, ?, ?)",
                (name, desc, color, now),
            )
        conn.commit()
        row = conn.execute("SELECT id FROM segments ORDER BY id ASC LIMIT 1").fetchone()
        return row["id"]


def get_segments() -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, color FROM segments ORDER BY id ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_segment(segment_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, color FROM segments WHERE id = ?",
            (segment_id,),
        ).fetchone()
        return dict(row) if row else None
