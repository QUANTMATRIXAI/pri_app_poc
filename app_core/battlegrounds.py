import datetime
from typing import List

from .database import get_connection


def get_battleground_notes(segment_id: int) -> List[dict]:
    """Return saved JTBD tabs for a segment."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, segment_id, tab_index, title, working_text, jtbd_text, created_by, updated_at
            FROM battleground_notes
            WHERE segment_id = ?
            ORDER BY tab_index ASC
            """,
            (segment_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_battleground_note(
    segment_id: int,
    tab_index: int,
    title: str,
    working_text: str,
    jtbd_text: str,
    username: str,
) -> None:
    """Upsert a JTBD tab for a segment."""
    now = datetime.datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO battleground_notes (segment_id, tab_index, title, working_text, jtbd_text, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id, tab_index) DO UPDATE
            SET title=excluded.title,
                working_text=excluded.working_text,
                jtbd_text=excluded.jtbd_text,
                created_by=excluded.created_by,
                updated_at=excluded.updated_at
            """,
            (segment_id, tab_index, title, working_text, jtbd_text, username, now),
        )
        conn.commit()
