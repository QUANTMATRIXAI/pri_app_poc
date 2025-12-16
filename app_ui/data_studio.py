from typing import Dict, List

import pandas as pd
import streamlit as st

from app_core.charts import save_chart
from app_core.constants import SECTIONS
from app_core.tables import save_table
from app_core.uploads import (
    get_upload_history,
    get_uploads,
    load_dataset,
    save_upload_for_segment,
)

from .charts import plot_chart


def render_data_upload(current_user: Dict, segment: Dict) -> None:
    st.subheader(f"Data Studio · {segment['name']}")
    st.caption(
        "Publish charts or tables to the dashboard for this segment. All uploads, previews, and saves stay within this segment."
    )

    chart_tab, table_tab, upload_tab = st.tabs(["Publish chart", "Publish table", "Upload data"])

    with chart_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Build a chart and add a note")
        render_chart_builder(current_user, segment)
        st.markdown("</div>", unsafe_allow_html=True)

    with table_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Publish a data table")
        render_table_builder(current_user, segment)
        st.markdown("</div>", unsafe_allow_html=True)

    with upload_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Upload CSV / Excel to this segment")
        uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"], key=f"upload_{segment['id']}")
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                upload_id = save_upload_for_segment(uploaded.name, df, current_user["username"], segment["id"])
                st.success(f"Saved {uploaded.name} (rows: {len(df)}) as dataset #{upload_id} for {segment['name']}")
                st.dataframe(df.head(), use_container_width=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to process file: {exc}")
        st.markdown('<div style="margin-top:0.5rem;" class="stCaption">Recent uploads</div>', unsafe_allow_html=True)
        history = get_upload_history(segment_id=segment["id"])
        if not history:
            st.write("No uploads yet.")
        else:
            st.table(history)
        st.markdown("</div>", unsafe_allow_html=True)


def render_chart_builder(current_user: Dict, segment: Dict) -> None:
    uploads = get_uploads(segment_id=segment["id"])
    if not uploads:
        st.info("Upload data first to build charts for this segment.")
        return

    preview_key = f"chart_preview_{segment['id']}"
    comment_key = f"chart_preview_comment_{segment['id']}"
    reset_key = f"chart_preview_comment_reset_{segment['id']}"

    if preview_key not in st.session_state:
        st.session_state[preview_key] = None
    if comment_key not in st.session_state:
        st.session_state[comment_key] = ""
    if st.session_state.get(reset_key):
        st.session_state[comment_key] = ""
        st.session_state[reset_key] = False

    upload_options = {f"#{row['id']} - {row['filename']}": row["id"] for row in uploads}

    with st.form(f"chart_builder_{segment['id']}"):
        st.markdown("**Step 1: Dataset & chart type**")
        top_left, top_right = st.columns(2)
        with top_left:
            chart_name = st.text_input("Chart name", value="SSL Health Overview", key=f"chart_name_{segment['id']}")
            selected_label = st.selectbox(
                "Dataset",
                options=list(upload_options.keys()),
                index=0,
                key=f"chart_dataset_{segment['id']}",
            )
        with top_right:
            chart_type = st.selectbox(
                "Chart type", options=["line", "area", "bar", "correlation"], key=f"chart_type_{segment['id']}"
            )

        dataset_id = upload_options[selected_label]
        df = load_dataset(dataset_id)
        if df is None or df.empty:
            st.warning("Selected dataset is empty.")
            st.form_submit_button("Preview chart", disabled=True)
            return
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        default_y = [numeric_cols[0]] if numeric_cols else []

        st.markdown("**Step 2: Columns**")
        col_x, col_y = st.columns([1, 1.3])
        with col_x:
            if chart_type == "correlation":
                x_col = df.columns.tolist()[0]
                st.text_input(
                    "X axis column",
                    value=x_col,
                    disabled=True,
                    help="Not used for correlation heatmap.",
                    key=f"x_disabled_{segment['id']}",
                )
            else:
                x_col = st.selectbox(
                    "X axis column", options=df.columns.tolist(), index=0, key=f"x_col_{segment['id']}"
                )
        with col_y:
            if chart_type == "correlation":
                y_cols = st.multiselect(
                    "Columns for correlation heatmap (numeric)",
                    options=df.columns.tolist(),
                    default=numeric_cols[:4],
                    key=f"y_cols_corr_{segment['id']}",
                )
            else:
                y_cols = st.multiselect(
                    "Y axis columns", options=df.columns.tolist(), default=default_y, key=f"y_cols_{segment['id']}"
                )

        st.markdown("**Step 3: Dashboard destination**")
        section = st.selectbox(
            "Dashboard section",
            options=SECTIONS,
            index=0,
            key=f"chart_section_{segment['id']}",
            help="Choose where this chart will appear on the dashboard.",
        )

        preview = st.form_submit_button("Preview chart", use_container_width=True)

    if preview:
        if not y_cols:
            st.error("Select at least one Y column.")
            st.session_state[preview_key] = None
        else:
            st.session_state[preview_key] = {
                "chart_name": chart_name.strip() or "Chart",
                "chart_type": chart_type,
                "x_col": x_col,
                "y_cols": y_cols,
                "dataset_id": dataset_id,
                "section": section,
            }
            st.session_state[comment_key] = ""

    preview_data = st.session_state.get(preview_key)
    if preview_data:
        df_preview = load_dataset(preview_data["dataset_id"])
        if df_preview is None or df_preview.empty:
            st.warning("Dataset unavailable for preview.")
            return
        prev_col, note_col = st.columns([1.6, 1])
        with prev_col:
            st.markdown("#### Preview")
            plot_chart(df_preview, preview_data["chart_type"], preview_data["x_col"], preview_data["y_cols"])
        with note_col:
            st.markdown("#### Add note and publish")
            comment = st.text_area(
                "Dashboard note (optional)",
                key=comment_key,
                placeholder="Add context for viewers...",
            )
            if st.button("Save chart to dashboard", use_container_width=True, key=f"save_chart_{segment['id']}"):
                save_chart(
                    preview_data["chart_name"],
                    preview_data["chart_type"],
                    preview_data["x_col"],
                    preview_data["y_cols"],
                    preview_data["dataset_id"],
                    current_user["username"],
                    segment["id"],
                    preview_data["section"],
                    comment.strip(),
                )
                st.success(
                    f"Saved chart to dashboard ({preview_data['section']}) using dataset #{preview_data['dataset_id']}"
                )
                st.session_state[preview_key] = None
                st.session_state[reset_key] = True
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()


def render_table_builder(current_user: Dict, segment: Dict) -> None:
    uploads = get_uploads(segment_id=segment["id"])
    if not uploads:
        st.info("Upload data first to publish tables for this segment.")
        return

    table_key = f"table_preview_{segment['id']}"
    table_comment_key = f"table_comment_{segment['id']}"
    table_reset_key = f"table_comment_reset_{segment['id']}"

    if table_key not in st.session_state:
        st.session_state[table_key] = None
    if table_comment_key not in st.session_state:
        st.session_state[table_comment_key] = ""
    if st.session_state.get(table_reset_key):
        st.session_state[table_comment_key] = ""
        st.session_state[table_reset_key] = False

    upload_options = {f"#{row['id']} - {row['filename']}": row["id"] for row in uploads}

    with st.form(f"table_builder_{segment['id']}"):
        st.markdown("**Step 1: Dataset**")
        selected_label = st.selectbox(
            "Dataset", options=list(upload_options.keys()), index=0, key=f"table_dataset_{segment['id']}"
        )
        dataset_id = upload_options[selected_label]
        df = load_dataset(dataset_id)
        if df is None or df.empty:
            st.warning("Selected dataset is empty.")
            st.form_submit_button("Preview table", disabled=True)
            return

        st.markdown("**Step 2: Columns & destination**")
        cols_left, cols_right = st.columns([1, 1])
        with cols_left:
            table_name = st.text_input(
                "Table name",
                value="Dataset snapshot",
                key=f"table_name_{segment['id']}",
            )
            selected_columns: List[str] = st.multiselect(
                "Columns to include",
                options=df.columns.tolist(),
                default=df.columns.tolist()[:5],
                key=f"table_columns_{segment['id']}",
            )
        with cols_right:
            section = st.selectbox(
                "Dashboard section",
                options=SECTIONS,
                index=0,
                key=f"table_section_{segment['id']}",
            )
        preview = st.form_submit_button("Preview table", use_container_width=True)

    if preview:
        if not selected_columns:
            st.error("Pick at least one column.")
            st.session_state[table_key] = None
        else:
            st.session_state[table_key] = {
                "dataset_id": dataset_id,
                "name": table_name.strip() or "Dataset snapshot",
                "columns": selected_columns,
                "section": section,
            }
            st.session_state[table_comment_key] = ""

    table_preview = st.session_state.get(table_key)
    if table_preview:
        df_preview = load_dataset(table_preview["dataset_id"])
        if df_preview is None or df_preview.empty:
            st.warning("Dataset unavailable for preview.")
            return
        st.markdown("#### Preview")
        st.dataframe(df_preview[table_preview["columns"]].head(100), use_container_width=True)
        comment = st.text_area(
            "Dashboard note (optional)",
            key=table_comment_key,
            placeholder="Add context for viewers...",
        )
        if st.button("Save table to dashboard", use_container_width=True, key=f"save_table_{segment['id']}"):
            save_table(
                table_preview["name"],
                table_preview["dataset_id"],
                table_preview["columns"],
                current_user["username"],
                segment["id"],
                table_preview["section"],
                comment.strip(),
            )
            st.success(
                f"Saved table to dashboard ({table_preview['section']}) using dataset #{table_preview['dataset_id']}"
            )
            st.session_state[table_key] = None
            st.session_state[table_reset_key] = True
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
