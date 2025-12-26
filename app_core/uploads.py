import datetime
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import duckdb

from .database import get_connection

DATA_UPLOAD_DIR = Path("data/uploads")
DATA_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def persist_upload_file(upload_id: int, df: pd.DataFrame) -> None:
    """Write the dataset to parquet and update the row."""
    path = DATA_UPLOAD_DIR / f"{upload_id}.parquet"
    df.to_parquet(path, index=False, engine="pyarrow", compression="snappy")
    with get_connection() as conn:
        conn.execute(
            "UPDATE uploads SET data_path = ?, data_json = ?, uploaded_at = ? WHERE id = ?",
            (str(path), "", datetime.datetime.utcnow().isoformat(), upload_id),
        )
        conn.commit()


def save_upload(filename: str, df: pd.DataFrame, uploaded_by: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at, segment_id) VALUES (?, ?, ?, ?, ?)",
            (
                filename,
                "",
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
                None,
            ),
        )
        conn.commit()
    upload_id = int(cursor.lastrowid)
    persist_upload_file(upload_id, df)
    return upload_id


def save_upload_for_segment(filename: str, df: pd.DataFrame, uploaded_by: str, segment_id: int) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at, segment_id) VALUES (?, ?, ?, ?, ?)",
            (
                filename,
                "",
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
                segment_id,
            ),
        )
        conn.commit()
    upload_id = int(cursor.lastrowid)
    persist_upload_file(upload_id, df)
    return upload_id


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
            "SELECT data_json, data_path FROM uploads WHERE id = ?",
            (upload_id,),
        ).fetchone()
    if not row:
        return None
    if row["data_path"]:
        try:
            return pd.read_parquet(row["data_path"])
        except (ValueError, FileNotFoundError):
            pass
    if not row["data_json"]:
        return None
    try:
        return pd.read_json(row["data_json"])
    except ValueError:
        return None


def load_latest_dataset() -> Tuple[Optional[int], Optional[pd.DataFrame]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, data_json, data_path FROM uploads ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None, None
    if row["data_path"]:
        try:
            return row["id"], pd.read_parquet(row["data_path"])
        except (ValueError, FileNotFoundError):
            pass
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
    rows = []
    brands = ["Alpha", "Beta"]
    for year in [2023, 2024]:
        for month in range(1, 13):
            for brand in brands:
                base = 100 if brand == "Alpha" else 85
                sales = base + (month * 2) + (year - 2023) * 5
                volume = base + month * 3
                price = round(sales / max(volume, 1) * 10, 2)
                rows.append(
                    {
                        "year": year,
                        "month": month,
                        "brand": brand,
                        "sales": round(sales, 2),
                        "volume": round(volume, 2),
                        "price": price,
                    }
                )
    return pd.DataFrame(rows)


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


def overwrite_dataset(upload_id: int, df: pd.DataFrame) -> None:
    """Persist edited dataframe back to the uploads table."""
    persist_upload_file(upload_id, df)


def query_segment_filtered(upload_path: str, segment_excel_name: str, filter_column: str, years: list[str]) -> pd.DataFrame:
    """Use DuckDB to filter the parquet by the appropriate segment column and PRI Year, returning a pandas DataFrame."""
    con = duckdb.connect()
    excel_name = segment_excel_name.strip()
    year_list = ", ".join([f"'{y}'" for y in years]) if years else "'A23','A24','A25'"
    query = f"""
        SELECT *
        FROM read_parquet('{upload_path}')
        WHERE trim("{filter_column}") = '{excel_name}'
          AND "PRI Year" IN ({year_list})
    """
    try:
        df = con.execute(query).fetch_df()
    finally:
        con.close()
    return df


def delete_upload(upload_id: int) -> tuple[bool, str]:
    charts_c, tables_c = get_dataset_usage(upload_id)
    if charts_c or tables_c:
        return False, "Dataset in use by dashboard content; delete charts/tables first."
    with get_connection() as conn:
        conn.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
        conn.commit()
    return True, "Dataset deleted"
