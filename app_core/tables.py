import datetime
import json
from typing import List

import pandas as pd

from .database import get_connection
from .uploads import load_dataset


def check_table_needs_refresh(table_row, current_dataset_id: int) -> bool:
    """Check if a saved table uses an outdated dataset and needs refresh."""
    if table_row is None:
        return False
    return table_row["dataset_id"] != current_dataset_id


def update_table_dataset(table_id: int, new_dataset_id: int) -> None:
    """Update a table's dataset_id to point to the new dataset."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE tables SET dataset_id = ? WHERE id = ?",
            (new_dataset_id, table_id),
        )
        conn.commit()


def get_table_by_id(table_id: int):
    """Get a single table by ID to verify updates."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, name, dataset_id FROM tables WHERE id = ?",
            (table_id,),
        ).fetchone()


def save_table(
    name: str,
    dataset_id: int,
    columns: List[str],
    created_by: str,
    segment_id: int,
    section: str,
    filter_json: str,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tables (name, dataset_id, columns_json, created_by, comment, segment_id, section, filter_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                dataset_id,
                json.dumps(columns),
                created_by,
                comment,
                segment_id,
                section,
                filter_json,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_tables_for_segment(segment_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, dataset_id, columns_json, created_by, comment, section, filter_json, created_at
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


def delete_tables_for_section(segment_id: int, section: str, name: str | None = None) -> None:
    """Remove tables for a given section (and optional name) in a segment to avoid duplicates."""
    with get_connection() as conn:
        if name:
            conn.execute(
                "DELETE FROM tables WHERE segment_id = ? AND section = ? AND name = ?",
                (segment_id, section, name),
            )
        else:
            conn.execute(
                "DELETE FROM tables WHERE segment_id = ? AND section = ?",
                (segment_id, section),
            )
        conn.commit()


def build_table_preview(table_row) -> pd.DataFrame | None:
    df = load_dataset(table_row["dataset_id"])
    if df is None or df.empty:
        return None
    cols = json.loads(table_row["columns_json"])
    filters = json.loads(table_row["filter_json"]) if "filter_json" in table_row.keys() else {}
    from app_core.filters import apply_filters  # local import to avoid cycle

    df = apply_filters(df, filters)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return df.head(100)
    return df[cols].head(100)
