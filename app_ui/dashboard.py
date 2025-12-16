import json
from typing import Dict, List

import streamlit as st

from app_core.charts import count_charts_for_segment, delete_chart, get_dataset_label
from app_core.constants import SECTIONS
from app_core.tables import build_table_preview, delete_table
from app_core.uploads import count_uploads_for_segment, load_dataset

from .charts import plot_chart


def draw_dashboard(segment: Dict, charts, tables, is_editor: bool = False) -> None:
    st.subheader(f"Dashboard · {segment['name']}")
    search = st.text_input(
        "Search charts/tables",
        placeholder="Search by name, dataset, or note...",
        key=f"dash_search_{segment['id']}",
    )
    uploads_total = count_uploads_for_segment(segment["id"])
    charts_total = count_charts_for_segment(segment["id"])
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Datasets</div>
                <div class="metric-value">{uploads_total}</div>
                <div class="stCaption">Uploaded for this segment</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Published blocks</div>
                <div class="metric-value">{charts_total + len(tables)}</div>
                <div class="stCaption">Charts and tables on this dashboard</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("")

    search_lower = (search or "").strip().lower()
    section_tabs = st.tabs(SECTIONS)
    charts_by_section = group_by_section(charts)
    tables_by_section = group_by_section(tables)

    for section, tab in zip(SECTIONS, section_tabs):
        with tab:
            section_charts = charts_by_section.get(section, [])
            section_tables = tables_by_section.get(section, [])
            section_charts = filter_by_search(section_charts, search_lower)
            section_tables = filter_by_search(section_tables, search_lower, is_table=True)
            if not section_charts and not section_tables:
                st.info("No content yet. Publish from Data Studio.")
                continue

            if section_charts:
                st.markdown("### Charts")
                render_chart_grid(section_charts, is_editor)

            if section_tables:
                st.markdown("### Tables")
                render_tables(section_tables, is_editor)


def group_by_section(rows) -> Dict[str, List]:
    grouped = {}
    for row in rows:
        sec = row["section"] if row["section"] else SECTIONS[0]
        grouped.setdefault(sec, []).append(row)
    return grouped


def filter_by_search(items, search_lower: str, is_table: bool = False):
    if not search_lower:
        return items
    filtered = []
    for item in items:
        dataset_label = get_dataset_label(item["dataset_id"])
        comment = item["comment"] if "comment" in item.keys() else ""
        haystack = " ".join([item["name"], dataset_label, comment or ""]).lower()
        if search_lower in haystack:
            filtered.append(item)
    return filtered


def render_chart_grid(charts, is_editor: bool) -> None:
    for i in range(0, len(charts), 2):
        cols = st.columns(2)
        for offset, chart in enumerate(charts[i : i + 2]):
            with cols[offset]:
                df = load_dataset(chart["dataset_id"])
                if df is None or df.empty:
                    st.warning(f"Dataset missing for chart '{chart['name']}'.")
                    continue
                y_cols = json.loads(chart["y_cols"])
                dataset_label = get_dataset_label(chart["dataset_id"])
                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                st.markdown(f"<h4 class='chart-title'>{chart['name']}</h4>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
                    unsafe_allow_html=True,
                )
                if chart.get("comment"):
                    st.markdown(
                        f"<div class='comment-box'>{chart['comment']}</div>",
                        unsafe_allow_html=True,
                    )
                plot_chart(df, chart["chart_type"], chart["x_col"], y_cols)
                if is_editor:
                    if st.button("Delete chart", key=f"del_chart_{chart['id']}"):
                        delete_chart(chart["id"])
                        st.success("Chart removed")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)


def render_tables(tables, is_editor: bool) -> None:
    for table in tables:
        dataset_label = get_dataset_label(table["dataset_id"])
        st.markdown('<div class="chart-card">', unsafe_allow_html=True)
        st.markdown(f"<h4 class='chart-title'>{table['name']}</h4>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
            unsafe_allow_html=True,
        )
        if table.get("comment"):
            st.markdown(f"<div class='comment-box'>{table['comment']}</div>", unsafe_allow_html=True)
        preview_df = build_table_preview(table)
        if preview_df is None or preview_df.empty:
            st.warning("Dataset missing or empty for this table.")
        else:
            st.dataframe(preview_df, use_container_width=True)
        if is_editor:
            if st.button("Delete table", key=f"del_table_{table['id']}"):
                delete_table(table["id"])
                st.success("Table removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        st.markdown("</div>", unsafe_allow_html=True)
