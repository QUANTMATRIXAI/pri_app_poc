import datetime
import os
import shutil
from pathlib import Path
from typing import List

from .database import get_connection

MEDIA_DIR = Path("data/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)


def save_media_upload(
    uploaded_file,
    segment_id: int,
    section: str,
    created_by: str,
    comment: str = "",
    title: str = "",
    label: str | None = None,
) -> str:
    """Persist an uploaded media file to disk and record in DB."""
    display_name = label or uploaded_file.name
    filename = f"{datetime.datetime.utcnow().timestamp()}_{uploaded_file.name}"
    file_path = MEDIA_DIR / filename
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO media (name, file_path, created_by, segment_id, section, comment, title, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                display_name,
                str(file_path),
                created_by,
                segment_id,
                section,
                comment,
                title,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return str(file_path)


def get_media_for_segment(segment_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, file_path, created_by, segment_id, section, comment, title, created_at
            FROM media
            WHERE segment_id = ?
            ORDER BY created_at DESC
            """,
            (segment_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_media_comment(media_id: int, comment: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE media SET comment = ? WHERE id = ?",
            (comment, media_id),
        )
        conn.commit()


def update_media_metadata(media_id: int, title: str, comment: str) -> None:
    """Update title and comment for existing media"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE media SET title = ?, comment = ? WHERE id = ?",
            (title, comment, media_id),
        )
        conn.commit()


def delete_media(media_id: int) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT file_path FROM media WHERE id = ?", (media_id,)).fetchone()
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.commit()
    
    if row and row["file_path"]:
        try:
            file_to_delete = Path(row["file_path"])
            
            # Skip if file doesn't exist
            if not file_to_delete.exists() or not file_to_delete.is_file():
                return
            
            # Resolve paths with strict validation
            media_dir_resolved = MEDIA_DIR.resolve(strict=True)
            file_resolved = file_to_delete.resolve(strict=True)
            
            # Multiple safety checks:
            # 1. File must be within MEDIA_DIR
            # 2. No parent directory traversal
            # 3. File path must start with media directory path
            if (media_dir_resolved in file_resolved.parents and
                str(file_resolved).startswith(str(media_dir_resolved)) and
                file_resolved.exists() and
                file_resolved.is_file()):
                os.remove(row["file_path"])
        except (OSError, ValueError, RuntimeError):
            # Skip files that can't be resolved or deleted
            pass


def delete_media_for_section(segment_id: int, section: str, name: str | None = None) -> None:
    query = "SELECT id, file_path FROM media WHERE segment_id = ? AND section = ?"
    params: list = [segment_id, section]
    if name:
        query += " AND name = ?"
        params.append(name)
    with get_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        if name:
            conn.execute("DELETE FROM media WHERE segment_id = ? AND section = ? AND name = ?", (segment_id, section, name))
        else:
            conn.execute("DELETE FROM media WHERE segment_id = ? AND section = ?", (segment_id, section))
        conn.commit()
    
    # Delete files with enhanced path validation
    if MEDIA_DIR.exists() and MEDIA_DIR.is_dir():
        try:
            media_dir_resolved = MEDIA_DIR.resolve(strict=True)
            
            for row in rows:
                if not row["file_path"]:
                    continue
                
                try:
                    file_to_delete = Path(row["file_path"])
                    
                    # Skip if not a file
                    if not file_to_delete.exists() or not file_to_delete.is_file():
                        continue
                    
                    file_resolved = file_to_delete.resolve(strict=True)
                    
                    # Multiple safety checks:
                    # 1. File must be within MEDIA_DIR
                    # 2. No parent directory traversal
                    # 3. File path must start with media directory path
                    if (media_dir_resolved in file_resolved.parents and
                        str(file_resolved).startswith(str(media_dir_resolved)) and
                        file_resolved.exists() and
                        file_resolved.is_file()):
                        os.remove(row["file_path"])
                except (OSError, ValueError, RuntimeError):
                    # Skip files that can't be resolved or deleted
                    continue
        except (OSError, ValueError, RuntimeError):
            # If directory can't be resolved, skip deletion
            pass
