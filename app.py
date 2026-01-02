import pandas as pd
import streamlit as st

from app_core.auth import create_default_users
from app_core.charts import get_charts_for_segment
from app_core.database import (
    ensure_chart_comment_column,
    ensure_tables_table,
    ensure_media_table,
    ensure_media_title_column,
    ensure_battleground_notes_table,
    ensure_uploads_segment_column,
    ensure_uploads_data_path_column,
    ensure_segments_excel_columns,
    clear_all_data,
    init_db,
    migrate_charts_table,
    get_connection,
)
from app_core.segments import create_default_segments, get_segment, get_segments
from app_core.tables import get_tables_for_segment
from app_core.uploads import save_upload
from app_ui.auth import login_panel
from app_ui.data_studio import render_data_upload
from app_ui.dashboard import draw_dashboard
from app_ui.segments import render_segment_landing
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
    ensure_segments_excel_columns()  # Add new columns for excel_name and filter_column
    default_segment_id = create_default_segments()
    ensure_uploads_segment_column(default_segment_id)
    ensure_chart_comment_column()
    ensure_tables_table()
    ensure_media_table()
    ensure_battleground_notes_table()
    ensure_uploads_data_path_column()
    ensure_media_title_column()
    with get_connection() as conn:
        if default_segment_id:
            conn.execute("UPDATE uploads SET segment_id = ? WHERE segment_id IS NULL", (default_segment_id,))
            conn.execute("UPDATE charts SET segment_id = ? WHERE segment_id IS NULL", (default_segment_id,))
            conn.commit()
    create_default_users()


def render_header() -> None:
    # Create container for the card
    st.markdown(
        """
        <div class="info-card" style="margin-bottom: 1rem; background: white; padding: 2rem; border: 1px solid rgba(0,0,0,0.08);">
        """,
        unsafe_allow_html=True,
    )
    
    # Create two columns inside the card
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown(
            """
            <div class="pill">Secure Workspace</div>
            <h1 style="margin-bottom:0.5rem; margin-top:0.8rem; color: #1d2733; font-size: 2.5rem; font-weight: 700; letter-spacing: -0.5px;">Strategic Alignment Dashboard</h1>
            <p style="color: #f5b400; margin-bottom:0; font-size: 1.1rem; font-weight: 600;">For Pernod Ricard India</p>
            """,
            unsafe_allow_html=True,
        )
    
    with col2:
        # Display Pernod Ricard logo
        import os
        logo_path = "static/Pernod_Ricard_logo_2019.svg.png"
        if os.path.exists(logo_path):
            st.image(logo_path, width=200)
    
    # Close the card
    st.markdown("</div>", unsafe_allow_html=True)


def render_footer() -> None:
    st.markdown(
        """
        <div style='
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #f8f9fa;
            padding: 0.8rem 2rem;
            text-align: center;
            border-top: 1px solid rgba(0,0,0,0.08);
            z-index: 999;
        '>
            <p style='margin: 0; color: #6c757d; font-size: 0.9rem;'>
                Powered by <span style='font-weight: 600; color: #1d2733;'>Quant Matrix AI</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Strategic Alignment Dashboard",
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
    # Global upload for editors (reused across segments)
    if current_user["role"] == "editor":
        uploaded_global = st.sidebar.file_uploader("Upload data file (CSV/XLSX)", type=["csv", "xlsx", "xls"])
        if uploaded_global:
            spinner_slot = st.sidebar.empty()
            try:
                with spinner_slot, st.spinner("Preparing file..."):
                    if uploaded_global.name.endswith(".csv"):
                        df_global = pd.read_csv(uploaded_global)
                    else:
                        df_global = pd.read_excel(uploaded_global)
                    # Coerce object columns to string to avoid parquet type errors
                    for col in df_global.select_dtypes(include=["object"]).columns:
                        df_global[col] = df_global[col].astype("string")
                    save_upload(uploaded_global.name, df_global, current_user["username"])
                spinner_slot.empty()
                st.sidebar.success(
                    f"Saved {uploaded_global.name} for all segments (rows: {len(df_global)}, cols: {len(df_global.columns)})."
                )
            except Exception as exc:  # noqa: BLE001
                spinner_slot.empty()
                st.sidebar.error(f"Failed to process file: {exc}")
        if st.sidebar.button("Clear all data (uploads + dashboard)", key="clear_all_data"):
            clear_all_data()
            st.sidebar.success("All data cleared.")
            trigger_rerun()
    else:
        if st.sidebar.button("Refresh dashboard"):
            trigger_rerun()
    if st.sidebar.button("Log out"):
        st.session_state["user"] = None
        trigger_rerun()
        return

    segments = get_segments()
    if "selected_segment_id" not in st.session_state:
        st.session_state["selected_segment_id"] = None

    # clear selection if segment removed
    if st.session_state["selected_segment_id"] and not any(
        seg["id"] == st.session_state["selected_segment_id"] for seg in segments
    ):
        st.session_state["selected_segment_id"] = None

    if st.session_state["selected_segment_id"] is None:
        render_header()
        render_segment_landing(segments)
        render_footer()
        return

    segment = get_segment(st.session_state["selected_segment_id"])
    if not segment:
        st.session_state["selected_segment_id"] = None
        trigger_rerun()
        return

    st.sidebar.markdown(
        f"<div class='pill'>Segment</div><div style='margin-top:0.2rem; font-weight:700;'>{segment['name']}</div>",
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Change segment"):
        st.session_state["selected_segment_id"] = None
        trigger_rerun()
        return

    render_header()

    is_editor = current_user["role"] == "editor"
    
    # Editors only see Data Studio, viewers only see Dashboard
    if is_editor:
        menu = ["Data Studio"]
        selection = "Data Studio"
    else:
        menu = ["Dashboard"]
        selection = st.sidebar.radio("Navigate", options=menu, index=0)

    charts = get_charts_for_segment(segment["id"])
    tables = get_tables_for_segment(segment["id"])
    if selection == "Dashboard":
        draw_dashboard(segment, charts, tables, is_editor=False)
    elif selection == "Data Studio" and is_editor:
        render_data_upload(current_user, segment)
    else:
        st.warning("You do not have access to this section.")
    
    # Render footer
    render_footer()


if __name__ == "__main__":
    main()
