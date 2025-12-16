import datetime
from typing import Optional, Tuple

import pandas as pd

from .database import get_connection


def save_upload(filename: str, df: pd.DataFrame, uploaded_by: str) -> int:
    data_json = df.to_json(orient="records")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at, segment_id) VALUES (?, ?, ?, ?, ?)",
            (
                filename,
                data_json,
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
                None,
            ),
        )
        conn.commit()
    return int(cursor.lastrowid)


def save_upload_for_segment(filename: str, df: pd.DataFrame, uploaded_by: str, segment_id: int) -> int:
    data_json = df.to_json(orient="records")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at, segment_id) VALUES (?, ?, ?, ?, ?)",
            (
                filename,
                data_json,
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
                segment_id,
            ),
        )
        conn.commit()
    return int(cursor.lastrowid)


def get_upload_history(limit: int = 10, segment_id: int | None = None):
    with get_connection() as conn:
        if segment_id is None:
            rows = conn.execute(
                "SELECT id, filename, uploaded_by, uploaded_at, segment_id FROM uploads ORDER BY uploaded_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, filename, uploaded_by, uploaded_at, segment_id
                FROM uploads
                WHERE segment_id = ?
                ORDER BY uploaded_at DESC
                LIMIT ?
                """,
                (segment_id, limit),
            ).fetchall()
        return rows


def get_uploads(segment_id: int | None = None):
    with get_connection() as conn:
        if segment_id is None:
            return conn.execute(
                "SELECT id, filename, uploaded_by, uploaded_at, segment_id FROM uploads ORDER BY uploaded_at DESC"
            ).fetchall()
        return conn.execute(
            """
            SELECT id, filename, uploaded_by, uploaded_at, segment_id
            FROM uploads
            WHERE segment_id = ?
            ORDER BY uploaded_at DESC
            """,
            (segment_id,),
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


def count_uploads_for_segment(segment_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM uploads WHERE segment_id = ?",
            (segment_id,),
        ).fetchone()
        return row["c"] if row else 0


def get_sample_dataset() -> pd.DataFrame:
    data = {
        "year": [2019, 2020, 2021, 2022, 2023, 2019, 2020, 2021, 2022, 2023],
        "brand": ["Alpha", "Alpha", "Alpha", "Alpha", "Alpha", "Beta", "Beta", "Beta", "Beta", "Beta"],
        "sales": [12.3, 13.1, 14.0, 15.2, 16.8, 9.5, 10.1, 11.4, 12.0, 12.9],
        "volume": [110, 120, 130, 142, 155, 90, 95, 105, 112, 118],
        "price": [112, 109, 108, 107, 108, 105, 106, 108, 107, 109],
    }
    return pd.DataFrame(data)


def get_dataset_usage(upload_id: int) -> tuple[int, int]:
    """Return (charts_count, tables_count) referencing the dataset."""
    with get_connection() as conn:
        charts_count = conn.execute(
            "SELECT COUNT(*) AS c FROM charts WHERE dataset_id = ?",
            (upload_id,),
        ).fetchone()["c"]
        tables_count = conn.execute(
            "SELECT COUNT(*) AS c FROM tables WHERE dataset_id = ?",
            (upload_id,),
        ).fetchone()["c"]
        return charts_count, tables_count


def delete_upload(upload_id: int) -> tuple[bool, str]:
    charts_c, tables_c = get_dataset_usage(upload_id)
    if charts_c or tables_c:
        return False, "Dataset in use by dashboard content; delete charts/tables first."
    with get_connection() as conn:
        conn.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
        conn.commit()
    return True, "Dataset deleted"
