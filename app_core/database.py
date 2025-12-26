import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/app.db")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory configured."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create base tables if they are missing."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('editor', 'viewer')),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                color TEXT DEFAULT '#f5b400',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                data_json TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                segment_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_chart_comment_column() -> None:
    """Ensure the charts table has a comment column."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(charts)").fetchall()]
        if "comment" not in cols:
            conn.execute("ALTER TABLE charts ADD COLUMN comment TEXT DEFAULT ''")
            conn.commit()
        if "segment_id" not in cols:
            conn.execute("ALTER TABLE charts ADD COLUMN segment_id INTEGER DEFAULT NULL")
            conn.commit()
        if "section" not in cols:
            conn.execute("ALTER TABLE charts ADD COLUMN section TEXT DEFAULT 'NS Landscape'")
            conn.commit()
        if "filter_json" not in cols:
            conn.execute("ALTER TABLE charts ADD COLUMN filter_json TEXT DEFAULT '{}' ")
            conn.commit()


def migrate_charts_table() -> None:
    """Create or migrate the charts table to the latest shape."""
    with get_connection() as conn:
        schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='charts'"
        ).fetchone()
        if not schema_row:
            conn.execute(
                """
                CREATE TABLE charts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    chart_type TEXT NOT NULL,
                    x_col TEXT NOT NULL,
                    y_cols TEXT NOT NULL,
                    dataset_id INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    comment TEXT DEFAULT '',
                    segment_id INTEGER,
                    section TEXT DEFAULT 'NS Landscape',
                    filter_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            return

        schema_sql = schema_row["sql"] or ""
        needs_migration = "CHECK(chart_type" in schema_sql
        has_comment = "comment" in schema_sql
        if not needs_migration and has_comment:
            return

        conn.execute(
            """
                CREATE TABLE IF NOT EXISTS charts_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    chart_type TEXT NOT NULL,
                    x_col TEXT NOT NULL,
                    y_cols TEXT NOT NULL,
                    dataset_id INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    comment TEXT DEFAULT '',
                    segment_id INTEGER,
                    section TEXT DEFAULT 'NS Landscape',
                    filter_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
        )
        conn.execute(
            """
            INSERT INTO charts_new (id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, segment_id, section, filter_json, created_at)
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by,
                   COALESCE(comment, '') AS comment,
                   NULL AS segment_id,
                   'NS Landscape' AS section,
                   '{}' AS filter_json,
                   created_at
            FROM charts
            """
        )
        conn.execute("DROP TABLE charts")
        conn.execute("ALTER TABLE charts_new RENAME TO charts")
        conn.commit()


def ensure_tables_table() -> None:
    """Ensure a table exists for saved data tables on dashboards."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dataset_id INTEGER NOT NULL,
                columns_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                comment TEXT DEFAULT '',
                segment_id INTEGER,
                section TEXT DEFAULT 'NS Landscape',
                filter_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(tables)").fetchall()]
        if "filter_json" not in cols:
            conn.execute("ALTER TABLE tables ADD COLUMN filter_json TEXT DEFAULT '{}' ")
        conn.commit()


def ensure_media_table() -> None:
    """Ensure table for uploaded media shown on dashboard sections."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                created_by TEXT NOT NULL,
                segment_id INTEGER,
                section TEXT NOT NULL,
                comment TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_uploads_segment_column(default_segment_id: Optional[int]) -> None:
    """Ensure uploads carry a segment reference."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()]
        if "segment_id" not in cols:
            conn.execute("ALTER TABLE uploads ADD COLUMN segment_id INTEGER")
            if default_segment_id:
                conn.execute("UPDATE uploads SET segment_id = ?", (default_segment_id,))
            conn.commit()


def ensure_uploads_data_path_column() -> None:
    """Add a column to track on-disk storage for uploads."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()]
        if "data_path" not in cols:
            conn.execute("ALTER TABLE uploads ADD COLUMN data_path TEXT DEFAULT ''")
            conn.commit()


def clear_all_data() -> None:
    """Dangerous: delete uploads, charts, tables, media and drop stored files."""
    from .uploads import DATA_UPLOAD_DIR

    with get_connection() as conn:
        conn.execute("DELETE FROM charts")
        conn.execute("DELETE FROM tables")
        conn.execute("DELETE FROM media")
        conn.execute("DELETE FROM uploads")
        conn.commit()
    if DATA_UPLOAD_DIR.exists():
        for f in DATA_UPLOAD_DIR.glob("*"):
            try:
                f.unlink()
            except OSError:
                pass


def ensure_battleground_notes_table() -> None:
    """Ensure table for battleground JTBD text blocks exists."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS battleground_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL,
                tab_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                working_text TEXT DEFAULT '',
                jtbd_text TEXT DEFAULT '',
                created_by TEXT DEFAULT '',
                updated_at TEXT NOT NULL,
                UNIQUE(segment_id, tab_index)
            )
            """
        )
        conn.commit()


def ensure_segments_excel_columns() -> None:
    """Ensure segments table has excel_name and filter_column columns."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(segments)").fetchall()]
        if "excel_name" not in cols:
            conn.execute("ALTER TABLE segments ADD COLUMN excel_name TEXT DEFAULT ''")
        if "filter_column" not in cols:
            conn.execute("ALTER TABLE segments ADD COLUMN filter_column TEXT DEFAULT 'Segment_Col_1'")
        conn.commit()


def ensure_media_title_column() -> None:
    """Ensure media table has a title column."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(media)").fetchall()]
        if "title" not in cols:
            conn.execute("ALTER TABLE media ADD COLUMN title TEXT DEFAULT ''")
            conn.commit()
