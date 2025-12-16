from typing import Dict

import streamlit as st

from app_core import auth
from app_core.config_store import load_config as load_config_payload, save_config
from app_core.database import get_connection


def render_config(config: Dict) -> Dict:
    st.subheader("Configuration")
    with st.form("config_form"):
        endpoint = st.text_input("SSL endpoint", value=config.get("ssl_endpoint", ""))
        freq = st.number_input(
            "Check frequency (minutes)",
            min_value=1,
            value=int(config.get("check_frequency_minutes", 15)),
        )
        email = st.text_input("Notify email", value=config.get("notify_email", ""))
        submitted = st.form_submit_button("Save configuration")
    if submitted:
        new_config = {
            "ssl_endpoint": endpoint.strip(),
            "check_frequency_minutes": freq,
            "notify_email": email.strip(),
        }
        save_config(new_config)
        st.success("Configuration saved")
        return new_config
    return config


def render_user_management() -> None:
    st.subheader("User Management")
    with get_connection() as conn:
        users = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    st.table(users)

    st.markdown("**Add user**")
    with st.form("add_user"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", options=["editor", "viewer"])
        submitted = st.form_submit_button("Create user")
    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        else:
            ok, msg = auth.add_user(username.strip(), password, role)
            if ok:
                st.success(f"{msg}: {username} ({role})")
            else:
                st.error(msg)


def get_or_create_config() -> Dict:
    """Helper to load or initialize config in one call."""
    return load_config_payload()

