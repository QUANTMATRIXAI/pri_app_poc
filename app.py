import streamlit as st

from app_core.auth import create_default_users
from app_core.charts import get_saved_charts
from app_core.database import ensure_chart_comment_column, init_db, migrate_charts_table
from app_ui.auth import login_panel
from app_ui.data_studio import render_data_upload
from app_ui.dashboard import draw_dashboard
from app_ui.styles import inject_styles


def trigger_rerun() -> None:
    """Trigger a Streamlit rerun, handling the legacy API name."""
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def bootstrap() -> None:
    """Initialize persistence and default data."""
    init_db()
    migrate_charts_table()
    ensure_chart_comment_column()
    create_default_users()


def render_header() -> None:
    st.markdown(
        """
        <div class="info-card" style="margin-bottom: 1rem;">
            <div class="pill">Secure Workspace</div>
            <h1 style="margin-bottom:0.2rem;">Trial Dashboard</h1>
            <p style="color: var(--muted); margin-bottom:0;">Editors manage data and publish charts; viewers see the live dashboard only.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Trial Dashboard",
        page_icon=":bar_chart:",
        layout="wide",
    )
    inject_styles()
    bootstrap()

    if "user" not in st.session_state:
        st.session_state["user"] = None

    current_user = st.session_state["user"]

    if not current_user:
        login_panel()
        return

    st.markdown(
        "<style>[data-testid='stSidebar'] { display: block; }</style>",
        unsafe_allow_html=True,
    )
    st.sidebar.success(f"Logged in as {current_user['username']} ({current_user['role']})")
    if current_user["role"] != "editor":
        if st.sidebar.button("Refresh dashboard"):
            trigger_rerun()
    if st.sidebar.button("Log out"):
        st.session_state["user"] = None
        trigger_rerun()
        return

    render_header()

    is_editor = current_user["role"] == "editor"
    menu = ["Dashboard"]
    if is_editor:
        menu.append("Data Studio")
    selection = st.sidebar.radio("Navigate", options=menu, index=0)

    saved_charts = get_saved_charts()
    if selection == "Dashboard":
        draw_dashboard(saved_charts, is_editor=is_editor)
    elif selection == "Data Studio" and is_editor:
        render_data_upload(current_user)
    else:
        st.warning("You do not have access to this section.")


if __name__ == "__main__":
    main()

