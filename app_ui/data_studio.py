from typing import Dict

import pandas as pd
import streamlit as st

from app_core.charts import save_chart
from app_core.uploads import get_upload_history, get_uploads, load_dataset, save_upload

from .charts import plot_chart


def render_data_upload(current_user: Dict) -> None:
    st.subheader("Data Studio")
    st.caption("Editors only. Publish charts with a note; dashboard shows the chart name, dataset, and note.")
    st.markdown(
        """
        <ul style="color: var(--muted); margin-top:0.1rem; margin-bottom:0.4rem;">
            <li>Select dataset, chart type, and columns.</li>
            <li>Preview the chart, add a note, then save.</li>
            <li>Saved charts appear on the dashboard for viewers.</li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    chart_tab, upload_tab = st.tabs(["Publish chart", "Upload data"])

    with chart_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Build a chart and add a note")
        render_chart_builder(current_user)
        st.markdown("</div>", unsafe_allow_html=True)

    with upload_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Upload CSV / Excel")
        uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"])
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                upload_id = save_upload(uploaded.name, df, current_user["username"])
                st.success(f"Saved {uploaded.name} (rows: {len(df)}) as dataset #{upload_id}")
                st.dataframe(df.head(), use_container_width=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to process file: {exc}")
        st.markdown('<div style="margin-top:0.5rem;" class="stCaption">Recent uploads</div>', unsafe_allow_html=True)
        history = get_upload_history()
        if not history:
            st.write("No uploads yet.")
        else:
            st.table(history)
        st.markdown("</div>", unsafe_allow_html=True)


def render_chart_builder(current_user: Dict) -> None:
    uploads = get_uploads()
    if not uploads:
        st.info("Upload data first to build charts.")
        return

    if "chart_preview" not in st.session_state:
        st.session_state["chart_preview"] = None
    if "chart_preview_comment" not in st.session_state:
        st.session_state["chart_preview_comment"] = ""

    upload_options = {f"#{row['id']} - {row['filename']}": row["id"] for row in uploads}

    with st.form("chart_builder"):
        st.markdown("**Step 1: Dataset & chart type**")
        top_left, top_right = st.columns(2)
        with top_left:
            chart_name = st.text_input("Chart name", value="SSL Health Overview")
            selected_label = st.selectbox("Dataset", options=list(upload_options.keys()), index=0)
        with top_right:
            chart_type = st.selectbox("Chart type", options=["line", "area", "bar", "correlation"])

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
                st.text_input("X axis column", value=x_col, disabled=True, help="Not used for correlation heatmap.")
            else:
                x_col = st.selectbox("X axis column", options=df.columns.tolist(), index=0)
        with col_y:
            if chart_type == "correlation":
                y_cols = st.multiselect(
                    "Columns for correlation heatmap (numeric)",
                    options=df.columns.tolist(),
                    default=numeric_cols[:4],
                )
            else:
                y_cols = st.multiselect("Y axis columns", options=df.columns.tolist(), default=default_y)

        preview = st.form_submit_button("Preview chart", use_container_width=True)

    if preview:
        if not y_cols:
            st.error("Select at least one Y column.")
            st.session_state["chart_preview"] = None
        else:
            st.session_state["chart_preview"] = {
                "chart_name": chart_name.strip() or "Chart",
                "chart_type": chart_type,
                "x_col": x_col,
                "y_cols": y_cols,
                "dataset_id": dataset_id,
            }
            st.session_state["chart_preview_comment"] = ""

    preview_data = st.session_state.get("chart_preview")
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
                key="chart_preview_comment",
                placeholder="Add context for viewers...",
            )
            if st.button("Save chart to dashboard", use_container_width=True):
                save_chart(
                    preview_data["chart_name"],
                    preview_data["chart_type"],
                    preview_data["x_col"],
                    preview_data["y_cols"],
                    preview_data["dataset_id"],
                    current_user["username"],
                    comment.strip(),
                )
                st.success(f"Saved chart to dashboard using dataset #{preview_data['dataset_id']}")
                st.session_state["chart_preview"] = None
                st.session_state["chart_preview_comment"] = ""

