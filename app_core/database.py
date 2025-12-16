import sqlite3
from pathlib import Path

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
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                data_json TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
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
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO charts_new (id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at)
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by,
                   COALESCE(comment, '') AS comment, created_at
            FROM charts
            """
        )
        conn.execute("DROP TABLE charts")
        conn.execute("ALTER TABLE charts_new RENAME TO charts")
        conn.commit()

