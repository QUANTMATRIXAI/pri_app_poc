import datetime
import json
from typing import List

import pandas as pd

from .database import get_connection
from .uploads import load_dataset


def save_table(
    name: str,
    dataset_id: int,
    columns: List[str],
    created_by: str,
    segment_id: int,
    section: str,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tables (name, dataset_id, columns_json, created_by, comment, segment_id, section, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                dataset_id,
                json.dumps(columns),
                created_by,
                comment,
                segment_id,
                section,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_tables_for_segment(segment_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, dataset_id, columns_json, created_by, comment, section, created_at
            FROM tables
            WHERE segment_id = ?
            ORDER BY created_at DESC
            """,
            (segment_id,),
        ).fetchall()


def count_tables_for_segment(segment_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM tables WHERE segment_id = ?",
            (segment_id,),
        ).fetchone()
        return row["c"] if row else 0


def delete_table(table_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM tables WHERE id = ?", (table_id,))
        conn.commit()


def build_table_preview(table_row) -> pd.DataFrame | None:
    df = load_dataset(table_row["dataset_id"])
    if df is None or df.empty:
        return None
    cols = json.loads(table_row["columns_json"])
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return df.head(100)
    return df[cols].head(100)
