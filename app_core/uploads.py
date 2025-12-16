import datetime
from typing import Optional, Tuple

import pandas as pd

from .database import get_connection


def save_upload(filename: str, df: pd.DataFrame, uploaded_by: str) -> int:
    data_json = df.to_json(orient="records")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?)",
            (
                filename,
                data_json,
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return int(cursor.lastrowid)


def get_upload_history(limit: int = 10):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, uploaded_by, uploaded_at FROM uploads ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows


def get_uploads():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, filename, uploaded_by, uploaded_at FROM uploads ORDER BY uploaded_at DESC"
        ).fetchall()


def load_dataset(upload_id: int) -> Optional[pd.DataFrame]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data_json FROM uploads WHERE id = ?",
            (upload_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return pd.read_json(row["data_json"])
    except ValueError:
        return None


def load_latest_dataset() -> Tuple[Optional[int], Optional[pd.DataFrame]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, data_json FROM uploads ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None, None
    try:
        return row["id"], pd.read_json(row["data_json"])
    except ValueError:
        return None, None

