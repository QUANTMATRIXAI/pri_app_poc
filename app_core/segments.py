import datetime
from typing import List, Optional

from .database import get_connection

# No longer needed - segments are dynamic
# SEGMENT_ORDER = ["Value", "Deluxe", "Premium", "SPIB", "SP BIO"]


def create_default_segments() -> int:
    """Ensure the default 12 segments exist; return the first segment id."""
    defaults = [
        ("Deluxe", "1. Admix Deluxe", "Segment_Col_1", "#6c8cff"),
        ("Premium", "2. Admix Premium", "Segment_Col_1", "#34c38f"),
        ("S&PIB Browns", "3. S&PIB Browns", "Segment_Col_1", "#ff7f50"),
        ("SP+IB Browns", "4. SP+IB Browns", "Segment_Col_1", "#f5b400"),
        ("S&PIB Whites", "5. S&PIB Whites", "Segment_Col_1", "#9c6bdb"),
        ("SP+IB Whites", "6. SP+IB Whites", "Segment_Col_1", "#20c997"),
        ("S&PIB BII Scotch Browns", "7. S&PIB BII Scotch Browns", "Segment_Col_2", "#e83e8c"),
        ("S&PIB Prem BIO Browns", "8. S&PIB Prem BIO Browns", "Segment_Col_2", "#fd7e14"),
        ("SP BIO+ BROWNS (SCOTCH)", "9. SP BIO+ Browns (Scotch)", "Segment_Col_2", "#6610f2"),
        ("Single Malt", "10. Single Malt", "Segment_Col_2", "#17a2b8"),
        ("Whites", "11. Whites", "Segment_Col_2", "#28a745"),
        ("SP+IB Others", "12. SP+IB Others", "Segment_Col_1", "#dc3545"),
    ]
    
    with get_connection() as conn:
        # Get all existing segments
        existing = conn.execute("SELECT id, name FROM segments ORDER BY id ASC").fetchall()
        existing_dict = {row["name"]: row["id"] for row in existing}
        
        now = datetime.datetime.utcnow().isoformat()
        
        # Get the names we want to keep
        target_names = {dashboard_name for dashboard_name, _, _, _ in defaults}
        
        # Delete segments that are not in our target list
        for name, seg_id in existing_dict.items():
            if name not in target_names:
                # Delete the segment (this will cascade delete related data)
                conn.execute("DELETE FROM segments WHERE id = ?", (seg_id,))
        
        # Now update or insert the target segments
        for dashboard_name, excel_name, filter_col, color in defaults:
            if dashboard_name in existing_dict:
                # Update existing segment
                conn.execute(
                    "UPDATE segments SET excel_name = ?, filter_column = ?, color = ?, description = '' WHERE name = ?",
                    (excel_name, filter_col, color, dashboard_name),
                )
            else:
                # Insert new segment
                conn.execute(
                    "INSERT INTO segments (name, description, color, excel_name, filter_column, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (dashboard_name, "", color, excel_name, filter_col, now),
                )

        conn.commit()
        row = conn.execute("SELECT id FROM segments ORDER BY id ASC LIMIT 1").fetchone()
        return row["id"] if row else None


def get_segments() -> List[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, color, excel_name, filter_column FROM segments ORDER BY id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_segment(segment_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, color, excel_name, filter_column FROM segments WHERE id = ?",
            (segment_id,),
        ).fetchone()
        return dict(row) if row else None
