import datetime
from typing import List, Optional

from .database import get_connection

SEGMENT_ORDER = ["Value", "Deluxe", "Premium", "SPIB", "SP BIO"]


def create_default_segments() -> int:
    """Ensure the default five segments exist; return the first segment id."""
    defaults = [
        ("Value", "Value-focused customers", "#f5b400"),
        ("Deluxe", "High-touch, curated experiences", "#6c8cff"),
        ("Premium", "Top-tier premium segment", "#34c38f"),
        ("SPIB", "Strategic projects in business", "#ff7f50"),
        ("SP BIO", "Bio-focused strategic plays", "#9c6bdb"),
    ]
    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM segments ORDER BY id ASC").fetchall()
        now = datetime.datetime.utcnow().isoformat()

        # Rename existing rows to align with defaults when possible
        for idx, row in enumerate(existing):
            if idx < len(defaults):
                name, desc, color = defaults[idx]
                conn.execute(
                    "UPDATE segments SET name = ?, description = ?, color = ? WHERE id = ?",
                    (name, desc, color, row["id"]),
                )

        # Insert missing defaults
        for idx in range(len(existing), len(defaults)):
            name, desc, color = defaults[idx]
            conn.execute(
                "INSERT INTO segments (name, description, color, created_at) VALUES (?, ?, ?, ?)",
                (name, desc, color, now),
            )

        conn.commit()
        row = conn.execute("SELECT id FROM segments ORDER BY id ASC LIMIT 1").fetchone()
        return row["id"]


def _sort_segments(rows) -> List[dict]:
    ordered = []
    remaining = []
    order_lookup = {name: idx for idx, name in enumerate(SEGMENT_ORDER)}
    for r in rows:
        name = r["name"]
        if name in order_lookup:
            ordered.append((order_lookup[name], dict(r)))
        else:
            remaining.append(dict(r))
    ordered_sorted = [pair[1] for pair in sorted(ordered, key=lambda x: x[0])]
    return ordered_sorted + remaining


def get_segments() -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, color FROM segments"
        ).fetchall()
    return _sort_segments(rows)


def get_segment(segment_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, color FROM segments WHERE id = ?",
            (segment_id,),
        ).fetchone()
        return dict(row) if row else None
