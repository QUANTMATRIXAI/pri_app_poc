import json
from typing import Dict

from .database import get_connection


def load_config() -> Dict:
    with get_connection() as conn:
        row = conn.execute("SELECT payload FROM config WHERE id = 1").fetchone()
        if row:
            return json.loads(row["payload"])
        default_config = {
            "ssl_endpoint": "https://example.com",
            "check_frequency_minutes": 15,
            "notify_email": "ops@example.com",
        }
        conn.execute(
            "INSERT OR REPLACE INTO config (id, payload) VALUES (1, ?)",
            (json.dumps(default_config),),
        )
        conn.commit()
        return default_config


def save_config(payload: Dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (id, payload) VALUES (1, ?)",
            (json.dumps(payload),),
        )
        conn.commit()

