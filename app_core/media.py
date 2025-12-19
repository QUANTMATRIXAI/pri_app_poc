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
    label: str | None = None,
) -> str:
    """Persist an uploaded media file to disk and record in DB."""
    import uuid
    display_name = label or uploaded_file.name
    # Use UUID to ensure unique filenames even when saving multiple files at once
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{datetime.datetime.utcnow().timestamp()}_{unique_id}_{uploaded_file.name}"
    file_path = MEDIA_DIR / filename
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO media (name, file_path, created_by, segment_id, section, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                display_name,
                str(file_path),
                created_by,
                segment_id,
                section,
                comment,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return str(file_path)


def save_media_uploads_batch(
    images_with_names: List[tuple],
    segment_id: int,
    section: str,
    created_by: str,
    label: str | None = None,
) -> int:
    """Save multiple media files in a single database transaction."""
    import uuid
    import time
    
    saved_paths = []
    records = []
    
    # First, save all files to disk
    for idx, (uploaded_file, comment) in enumerate(images_with_names):
        display_name = label or uploaded_file.name
        unique_id = uuid.uuid4().hex[:8]
        # Add index to ensure unique timestamps
        timestamp = datetime.datetime.utcnow().timestamp() + (idx * 0.001)
        filename = f"{timestamp}_{unique_id}_{uploaded_file.name}"
        file_path = MEDIA_DIR / filename
        
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        saved_paths.append(str(file_path))
        records.append((
            display_name,
            str(file_path),
            created_by,
            segment_id,
            section,
            comment,
            datetime.datetime.utcnow().isoformat(),
        ))
        # Small delay to ensure unique timestamps
        time.sleep(0.01)
    
    # Then insert all records in a single transaction
    with get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO media (name, file_path, created_by, segment_id, section, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            records
        )
        conn.commit()
    
    return len(records)


def get_media_for_segment(segment_id: int) -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, file_path, created_by, segment_id, section, comment, created_at
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


def delete_media(media_id: int) -> None:
    with get_connection() as conn:
        row = conn.execute("SELECT file_path FROM media WHERE id = ?", (media_id,)).fetchone()
        conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
        conn.commit()
    if row and row["file_path"] and os.path.exists(row["file_path"]):
        try:
            os.remove(row["file_path"])
        except OSError:
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
    for row in rows:
        if row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
