import datetime
import json

from .database import get_connection
from .uploads import load_dataset


def save_chart(
    name: str,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    dataset_id: int,
    created_by: str,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO charts (name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                chart_type,
                x_col,
                json.dumps(y_cols),
                dataset_id,
                created_by,
                comment,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_saved_charts():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at
            FROM charts
            ORDER BY created_at DESC
            """
        ).fetchall()


def count_uploads() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM uploads").fetchone()
        return row["c"]


def count_charts() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM charts").fetchone()
        return row["c"]


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

