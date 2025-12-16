import json

import pandas as pd
import streamlit as st

from app_core.charts import count_charts, count_uploads, delete_chart, get_dataset_label
from app_core.uploads import load_dataset

from .charts import plot_chart


def draw_dashboard(charts, is_editor: bool = False) -> None:
    st.subheader("Dashboard")
    search = st.text_input("Search charts", placeholder="Search by chart name, dataset, or note...")
    uploads_total = count_uploads()
    charts_total = count_charts()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Datasets</div>
                <div class="metric-value">{uploads_total}</div>
                <div class="stCaption">Uploaded by editors</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Published charts</div>
                <div class="metric-value">{charts_total}</div>
                <div class="stCaption">Visible on dashboard</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("")
    if not charts:
        st.info("No charts published yet. Editors can build charts from uploaded data.")
        sample = pd.DataFrame(
            {
                "timestamp": pd.date_range(pd.Timestamp.today(), periods=10, freq="H"),
                "latency_ms": [120, 110, 150, 130, 125, 118, 160, 140, 135, 128],
                "success_rate": [0.99, 0.98, 0.985, 0.99, 0.995, 0.97, 0.965, 0.99, 0.993, 0.997],
            }
        )
        st.line_chart(sample.set_index("timestamp"))
        return

    filtered = []
    search_lower = (search or "").strip().lower()
    for chart in charts:
        dataset_label = get_dataset_label(chart["dataset_id"])
        comment = chart["comment"] if "comment" in chart.keys() else ""
        haystack = " ".join([chart["name"], dataset_label, comment or ""]).lower()
        if search_lower and search_lower not in haystack:
            continue
        filtered.append((chart, dataset_label, comment))

    if not filtered:
        st.info("No charts match your search.")
        return

    for i in range(0, len(filtered), 2):
        cols = st.columns(2)
        for offset, pack in enumerate(filtered[i : i + 2]):
            chart, dataset_label, comment = pack
            with cols[offset]:
                df = load_dataset(chart["dataset_id"])
                if df is None or df.empty:
                    st.warning(f"Dataset missing for chart '{chart['name']}'.")
                    continue
                y_cols = json.loads(chart["y_cols"])
                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                st.markdown(f"<h4 class='chart-title'>{chart['name']}</h4>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
                    unsafe_allow_html=True,
                )
                if comment:
                    st.markdown(
                        f"<div class='comment-box'>{comment}</div>",
                        unsafe_allow_html=True,
                    )
                plot_chart(df, chart["chart_type"], chart["x_col"], y_cols)
                if is_editor:
                    if st.button("Delete chart", key=f"del_{chart['id']}"):
                        delete_chart(chart["id"])
                        st.success("Chart removed")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

