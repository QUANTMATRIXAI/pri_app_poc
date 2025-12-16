import datetime
import hashlib
import os
import sqlite3
from typing import Dict, Optional, Tuple

from .database import get_connection


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash a password with PBKDF2 and return (salt, hash)."""
    salt_value = salt or os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 390000
    ).hex()
    return salt_value, hashed


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, hashed = hash_password(password, salt)
    return hashed == expected_hash


def create_default_users() -> None:
    """Seed the database with a default editor and viewer."""
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if existing:
            return

        now = datetime.datetime.utcnow().isoformat()
        defaults = [
            ("admin", "admin123", "editor"),
            ("viewer", "viewer123", "viewer"),
        ]
        for username, password, role in defaults:
            salt, hashed = hash_password(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, hashed, salt, role, now),
            )
        conn.commit()


def add_user(username: str, password: str, role: str) -> Tuple[bool, str]:
    try:
        salt, hashed = hash_password(password)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    username,
                    hashed,
                    salt,
                    role,
                    datetime.datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return True, "User created"
    except sqlite3.IntegrityError:
        return False, "Username already exists"


def verify_credentials(username: str, password: str) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, salt, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    if verify_password(password, row["salt"], row["password_hash"]):
        return {"username": row["username"], "role": row["role"]}
    return None

