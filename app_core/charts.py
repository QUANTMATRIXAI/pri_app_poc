import datetime
import json

from .database import get_connection


def check_chart_needs_refresh(chart_row, current_dataset_id: int) -> bool:
    """Check if a saved chart uses an outdated dataset and needs refresh."""
    if chart_row is None:
        return False
    return chart_row["dataset_id"] != current_dataset_id


def update_chart_dataset(chart_id: int, new_dataset_id: int) -> None:
    """Update a chart's dataset_id to point to the new dataset."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE charts SET dataset_id = ? WHERE id = ?",
            (new_dataset_id, chart_id),
        )
        conn.commit()


def update_chart_config(chart_id: int, new_dataset_id: int, new_filter_json: str) -> None:
    """Update a chart's dataset_id and filter_json together."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE charts SET dataset_id = ?, filter_json = ? WHERE id = ?",
            (new_dataset_id, new_filter_json, chart_id),
        )
        conn.commit()


def save_chart(
    name: str,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    dataset_id: int,
    created_by: str,
    segment_id: int,
    section: str,
    filter_json: str,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO charts (name, chart_type, x_col, y_cols, dataset_id, created_by, comment, segment_id, section, filter_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                chart_type,
                x_col,
                json.dumps(y_cols),
                dataset_id,
                created_by,
                comment,
                segment_id,
                section,
                filter_json,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_saved_charts():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, segment_id, section, filter_json, created_at
            FROM charts
            ORDER BY created_at DESC
            """
        ).fetchall()


def get_charts_for_segment(segment_id: int):
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, segment_id, section, filter_json, created_at
            FROM charts
            WHERE segment_id = ?
            ORDER BY created_at DESC
            """,
            (segment_id,),
        ).fetchall()


def count_uploads() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM uploads").fetchone()
        return row["c"]


def count_charts() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM charts").fetchone()
        return row["c"]


def count_charts_for_segment(segment_id: int) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM charts WHERE segment_id = ?",
            (segment_id,),
        ).fetchone()
        return row["c"] if row else 0


def get_dataset_label(dataset_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT filename FROM uploads WHERE id = ?",
            (dataset_id,),
        ).fetchone()
    return row["filename"] if row else f"Dataset #{dataset_id}"


def delete_chart(chart_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM charts WHERE id = ?", (chart_id,))
        conn.commit()


def delete_charts_for_section(segment_id: int, section: str, name: str | None = None) -> None:
    """Remove charts for a given section (and optional name) in a segment to avoid duplicates."""
    with get_connection() as conn:
        if name:
            conn.execute(
                "DELETE FROM charts WHERE segment_id = ? AND section = ? AND name = ?",
                (segment_id, section, name),
            )
        else:
            conn.execute(
                "DELETE FROM charts WHERE segment_id = ? AND section = ?",
                (segment_id, section),
            )
        conn.commit()
