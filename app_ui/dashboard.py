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
            section_charts = [dict(row) for row in charts_by_section.get(section, [])]
            section_tables = [dict(row) for row in tables_by_section.get(section, [])]
            blocks = (
                [{"type": "chart", **row} for row in section_charts]
                + [{"type": "table", **row} for row in section_tables]
            )
            blocks = filter_blocks(blocks, search_lower)
            blocks = sorted(blocks, key=lambda b: b.get("created_at", ""), reverse=True)
            if not blocks:
                st.info("No content yet. Publish from Data Studio.")
                continue
            render_blocks(blocks, is_editor)


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


def filter_blocks(blocks, search_lower: str):
    if not search_lower:
        return blocks
    filtered = []
    for block in blocks:
        dataset_label = get_dataset_label(block["dataset_id"])
        comment = block["comment"] if "comment" in block.keys() else ""
        haystack = " ".join([block["name"], dataset_label, comment or "", block.get("type", "")]).lower()
        if search_lower in haystack:
            filtered.append(block)
    return filtered


def render_blocks(blocks, is_editor: bool) -> None:
    for i in range(0, len(blocks), 2):
        cols = st.columns(2)
        for offset, block in enumerate(blocks[i : i + 2]):
            with cols[offset]:
                if block["type"] == "chart":
                    render_chart_block(block, is_editor)
                else:
                    render_table_block(block, is_editor)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)


def render_chart_block(chart, is_editor: bool) -> None:
    df = load_dataset(chart["dataset_id"])
    if df is None or df.empty:
        st.warning(f"Dataset missing for chart '{chart['name']}'.")
        return
    y_cols = json.loads(chart["y_cols"])
    dataset_label = get_dataset_label(chart["dataset_id"])
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown(f"<div class='pill'>Chart</div>", unsafe_allow_html=True)
    st.markdown(f"<h4 class='chart-title'>{chart['name']}</h4>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
        unsafe_allow_html=True,
    )
    comment = chart["comment"] if "comment" in chart.keys() else ""
    if comment:
        st.markdown(f"<div class='comment-box'>{comment}</div>", unsafe_allow_html=True)
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


def render_table_block(table, is_editor: bool) -> None:
    dataset_label = get_dataset_label(table["dataset_id"])
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown(f"<div class='pill'>Table</div>", unsafe_allow_html=True)
    st.markdown(f"<h4 class='chart-title'>{table['name']}</h4>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
        unsafe_allow_html=True,
    )
    comment = table["comment"] if "comment" in table.keys() else ""
    if comment:
        st.markdown(f"<div class='comment-box'>{comment}</div>", unsafe_allow_html=True)
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
