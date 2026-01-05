import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/app.db")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row factory configured."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
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
        # Create indexes for faster queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_charts_segment_section 
            ON charts(segment_id, section)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_charts_dataset 
            ON charts(dataset_id)
            """
        )
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

        # Check if migration is needed by inspecting actual columns
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(charts)").fetchall()]
        required_cols = ["comment", "segment_id", "section", "filter_json"]
        has_all_cols = all(col in cols for col in required_cols)
        
        schema_sql = schema_row["sql"] or ""
        needs_migration = "CHECK(chart_type" in schema_sql
        
        if not needs_migration and has_all_cols:
            return

        # Drop any leftover charts_new from failed previous migration
        conn.execute("DROP TABLE IF EXISTS charts_new")
        
        conn.execute(
            """
                CREATE TABLE charts_new (
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
        # Create indexes for faster queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tables_segment_section 
            ON tables(segment_id, section)
            """
        )
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
        # Create indexes for faster queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_media_segment_section 
            ON media(segment_id, section)
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
        # Create index for faster queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_uploads_segment 
            ON uploads(segment_id)
            """
        )
        conn.commit()


def ensure_uploads_data_path_column() -> None:
    """Add a column to track on-disk storage for uploads."""
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(uploads)").fetchall()]
        if "data_path" not in cols:
            conn.execute("ALTER TABLE uploads ADD COLUMN data_path TEXT DEFAULT ''")
            conn.commit()


def clear_all_data() -> None:
    """Dangerous: delete ALL data from ALL segments - uploads, charts, tables, media and drop stored files."""
    from .uploads import DATA_UPLOAD_DIR
    from .media import MEDIA_DIR
    from pathlib import Path

    with get_connection() as conn:
        # Safe deletion - only delete from tables that exist
        try:
            conn.execute("DELETE FROM charts")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM tables")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM media")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM uploads")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("DELETE FROM battleground_notes")
        except sqlite3.OperationalError:
            pass
        conn.commit()
    
    # Delete all upload files with enhanced path validation
    if DATA_UPLOAD_DIR.exists() and DATA_UPLOAD_DIR.is_dir():
        try:
            upload_dir_resolved = DATA_UPLOAD_DIR.resolve(strict=True)
            
            # Safety check: ensure we're in the expected data directory
            if "data" not in str(upload_dir_resolved).lower() or "uploads" not in str(upload_dir_resolved).lower():
                pass  # Skip this directory but continue with others
            else:
                for f in DATA_UPLOAD_DIR.glob("*"):
                    try:
                        # Skip if not a file
                        if not f.is_file():
                            continue
                        
                        file_resolved = f.resolve(strict=True)
                        
                        # Multiple safety checks:
                        # 1. File must be direct child of upload directory
                        # 2. No parent directory traversal
                        # 3. File path must start with upload directory path
                        if (file_resolved.parent == upload_dir_resolved and 
                            upload_dir_resolved in file_resolved.parents and
                            str(file_resolved).startswith(str(upload_dir_resolved))):
                            f.unlink()
                    except (OSError, ValueError, RuntimeError):
                        # Skip files that can't be resolved or deleted
                        continue
        except (OSError, ValueError, RuntimeError):
            # If directory can't be resolved, skip deletion
            pass
    
    # Delete all media files with enhanced path validation
    if MEDIA_DIR.exists() and MEDIA_DIR.is_dir():
        try:
            media_dir_resolved = MEDIA_DIR.resolve(strict=True)
            
            # Safety check: ensure we're in the expected data directory
            if "data" not in str(media_dir_resolved).lower() or "media" not in str(media_dir_resolved).lower():
                pass  # Skip this directory but continue
            else:
                for f in MEDIA_DIR.glob("*"):
                    try:
                        # Skip if not a file
                        if not f.is_file():
                            continue
                        
                        file_resolved = f.resolve(strict=True)
                        
                        # Multiple safety checks:
                        # 1. File must be direct child of media directory
                        # 2. No parent directory traversal
                        # 3. File path must start with media directory path
                        if (file_resolved.parent == media_dir_resolved and 
                            media_dir_resolved in file_resolved.parents and
                            str(file_resolved).startswith(str(media_dir_resolved))):
                            f.unlink()
                    except (OSError, ValueError, RuntimeError):
                        # Skip files that can't be resolved or deleted
                        continue
        except (OSError, ValueError, RuntimeError):
            # If directory can't be resolved, skip deletion
            pass


def clear_segment_data(segment_id: int) -> None:
    """Delete all data for a specific segment only (keeps uploads as they're shared)."""
    from .media import MEDIA_DIR
    from pathlib import Path
    
    # Validate segment_id is a positive integer
    if not isinstance(segment_id, int) or segment_id <= 0:
        return
    
    with get_connection() as conn:
        # Get all media file paths for this segment before deleting records
        media_files = conn.execute(
            "SELECT file_path FROM media WHERE segment_id = ?",
            (segment_id,)
        ).fetchall()
        
        # Delete database records for this segment
        conn.execute("DELETE FROM charts WHERE segment_id = ?", (segment_id,))
        conn.execute("DELETE FROM tables WHERE segment_id = ?", (segment_id,))
        conn.execute("DELETE FROM media WHERE segment_id = ?", (segment_id,))
        conn.execute("DELETE FROM battleground_notes WHERE segment_id = ?", (segment_id,))
        conn.commit()
    
    # Delete media files for this segment with enhanced path validation
    if MEDIA_DIR.exists() and MEDIA_DIR.is_dir():
        try:
            media_dir_resolved = MEDIA_DIR.resolve(strict=True)
            
            # Safety check: ensure we're in the expected data directory
            if "data" not in str(media_dir_resolved).lower() or "media" not in str(media_dir_resolved).lower():
                return  # Abort if path doesn't look right
            
            for row in media_files:
                file_path = row["file_path"]
                if not file_path:
                    continue
                
                try:
                    # Convert to Path object
                    file_to_delete = Path(file_path)
                    
                    # Skip if not a file
                    if not file_to_delete.exists() or not file_to_delete.is_file():
                        continue
                    
                    file_resolved = file_to_delete.resolve(strict=True)
                    
                    # Multiple safety checks:
                    # 1. File must be within MEDIA_DIR (direct child or subdirectory)
                    # 2. No parent directory traversal
                    # 3. File path must start with media directory path
                    # 4. File must actually exist
                    if (media_dir_resolved in file_resolved.parents and
                        str(file_resolved).startswith(str(media_dir_resolved)) and
                        file_resolved.exists() and
                        file_resolved.is_file()):
                        file_to_delete.unlink()
                except (OSError, FileNotFoundError, ValueError, RuntimeError):
                    # Skip files that can't be resolved or deleted
                    continue
        except (OSError, ValueError, RuntimeError):
            # If directory can't be resolved, skip deletion
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
        # Create index for faster queries
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_battleground_notes_segment 
            ON battleground_notes(segment_id)
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
