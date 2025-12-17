import json
import os
import re
import uuid
from typing import Dict, List

import pandas as pd
import streamlit as st

from app_core.charts import count_charts_for_segment, delete_chart, get_dataset_label
from app_core.constants import SECTIONS
from app_core.filters import apply_filters
from app_core.media import delete_media_for_section, get_media_for_segment
from app_core.battlegrounds import get_battleground_notes
from app_core.tables import build_table_preview, delete_table
from app_core.uploads import count_uploads_for_segment, load_dataset, overwrite_dataset

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
    media_by_section = group_by_section(get_media_for_segment(segment["id"]))

    for section, tab in zip(SECTIONS, section_tabs):
        with tab:
            section_charts = [dict(row) for row in charts_by_section.get(section, [])]
            section_tables = [dict(row) for row in tables_by_section.get(section, [])]
            section_media_items = [dict(row) for row in media_by_section.get(section, [])]
            blocks = (
                [{"type": "chart", **row} for row in section_charts]
                + [{"type": "table", **row} for row in section_tables]
            )
            if section_media_items:
                if section == "NS Landscape":
                    names = sorted({m["name"] for m in section_media_items})
                    for name in names:
                        filtered = [m for m in section_media_items if m["name"] == name]
                        blocks.append({"type": "media", "section": section, "items": filtered, "name": name})
                else:
                    blocks.append({"type": "media", "section": section, "items": section_media_items, "name": section})
            # Brand Truths and Segment Trends are image-only
            if section in {"Brand Truths", "Segment Trends"}:
                blocks = [b for b in blocks if b["type"] == "media"]
            blocks = filter_blocks(blocks, search_lower)
            blocks = sorted(blocks, key=lambda b: b.get("created_at", ""), reverse=True)
            if not blocks:
                if section == "Battlegrounds":
                    render_battleground_tabs_view(segment["id"], is_editor)
                else:
                    st.info("No content yet. Publish from Data Studio.")
                continue
            render_blocks(blocks, is_editor, media_by_section, current_section=section, segment_id=segment["id"])


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


def render_blocks(
    blocks, is_editor: bool, media_by_section: Dict[str, List], current_section: str, segment_id: int
) -> None:
    ns_media = media_by_section.get("NS Landscape") or []
    other_blocks = [b for b in blocks if not (b.get("type") == "media" and b.get("section") == "NS Landscape")]
    ns_media_rendered = False

    if current_section == "Battlegrounds":
        render_battleground_tabs_view(segment_id, is_editor)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    for i in range(0, len(other_blocks), 2):
        cols = st.columns(2)
        for offset, block in enumerate(other_blocks[i : i + 2]):
            with cols[offset]:
                if block["type"] == "chart":
                    render_chart_block(block, is_editor)
                    if block.get("section") == "NS Landscape":
                        extra_media = media_by_section.get("NS Landscape") or []
                        all_media = ns_media or extra_media
                        if all_media:
                            seg_id = all_media[0].get("segment_id", "")
                            render_media_tabs(
                                all_media,
                                is_editor,
                                title="NS Landscape Images",
                                key_prefix=f"ns_media_{seg_id}",
                            )
                            ns_media_rendered = True
                elif block["type"] == "table":
                    render_table_block(block, is_editor)
                else:
                    render_media_block(block, is_editor)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)

    # Show NS Landscape media once even if chart is missing
    if current_section == "NS Landscape" and ns_media and not ns_media_rendered:
        seg_id = ns_media[0].get("segment_id", "")
        render_media_tabs(ns_media, is_editor, title="NS Landscape Images", key_prefix=f"ns_media_fallback_{seg_id}")


def format_comment(text: str) -> str:
    """Lightweight formatting: **bold**, ## heading, line breaks."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = safe.splitlines()
    rendered = []
    for line in lines:
        if line.startswith("##"):
            rendered.append(f"<div style='font-size:1.08rem;font-weight:700'>{line.lstrip('#').strip()}</div>")
        elif line.startswith("•"):
            rendered.append(f"<div style='margin-left:0.6rem;'>• {line.lstrip('•').strip()}</div>")
        else:
            rendered.append(re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line))
    return "<br>".join(rendered)


def render_chart_block(chart, is_editor: bool) -> None:
    df = load_dataset(chart["dataset_id"])
    if df is None or df.empty:
        st.warning(f"Dataset missing for chart '{chart['name']}'.")
        return
    filters = json.loads(chart["filter_json"]) if "filter_json" in chart.keys() else {}
    df = apply_filters(df, filters)
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
        st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
    plot_chart(df, chart["chart_type"], chart["x_col"], y_cols, chart_key=f"dash_chart_{chart['id']}")
    with st.expander("View data"):
        st.dataframe(df[[chart["x_col"]] + y_cols].head(200), use_container_width=True)
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
        st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
    preview_df = build_table_preview(table)
    if preview_df is None or preview_df.empty:
        st.warning("Dataset missing or empty for this table.")
    else:
        styled = preview_df.style.apply(highlight_extremes, axis=0)
        st.dataframe(styled, use_container_width=True)
        if is_editor:
            editable_df = preview_df.copy()
            if "Notes" not in editable_df.columns:
                editable_df["Notes"] = ""
            st.caption("Editable view (changes can overwrite the dataset for this table).")
            edited = st.data_editor(
                editable_df.head(500),
                use_container_width=True,
                num_rows="dynamic",
                key=f"edit_table_{table['id']}",
            )
            csv = edited.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download edited CSV", data=csv, file_name=f"table_{table['id']}_edited.csv", key=f"dl_table_{table['id']}"
            )
            if st.button("Save edits to dataset", key=f"save_table_edits_{table['id']}"):
                overwrite_dataset(table["dataset_id"], edited)
                st.success("Dataset updated with your edits.")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    if is_editor:
        if st.button("Delete table", key=f"del_table_{table['id']}"):
            delete_table(table["id"])
            st.success("Table removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def highlight_extremes(series: pd.Series):
    if not pd.api.types.is_numeric_dtype(series):
        return [""] * len(series)
    max_val = series.max()
    min_val = series.min()
    styles = []
    for val in series:
        if pd.isna(val):
            styles.append("")
        elif val == max_val:
            styles.append("background-color: #e8f7ff; font-weight: 700;")
        elif val == min_val:
            styles.append("background-color: #fff3e0; font-weight: 700;")
        else:
            styles.append("")
    return styles


def render_media_block(block, is_editor: bool) -> None:
    items = block.get("items") or []
    if not items:
        st.info("No images uploaded for this section.")
        return
    prefix_base = f"media_{block.get('section','').replace(' ', '_')}_{block.get('name','').replace(' ', '_')}".strip("_")
    if items and items[0].get("segment_id"):
        prefix_base = f"{prefix_base}_{items[0]['segment_id']}"
    st.markdown('<div class="chart-card">', unsafe_allow_html=True)
    st.markdown(f"<div class='pill'>Image</div>", unsafe_allow_html=True)
    title_label = block.get("name") or block.get("section", "Image")
    st.markdown(f"<h4 class='chart-title'>{title_label}</h4>", unsafe_allow_html=True)

    if len(items) > 1:
        tab_labels = [item.get("name") or f"Image {i+1}" for i, item in enumerate(items)]
        tabs = st.tabs(tab_labels)
        for idx, tab in enumerate(tabs):
            with tab:
                render_media_item(items[idx], is_editor, key_prefix=f"{prefix_base}_{idx}")
    else:
        render_media_item(items[0], is_editor, key_prefix=prefix_base)


def render_media_item(media, is_editor: bool, key_prefix: str = "media") -> None:
    comment = media.get("comment") or ""
    if comment:
        st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
    file_path = media.get("file_path")
    if file_path and os.path.exists(file_path):
        if str(file_path).lower().endswith((".ppt", ".pptx")):
            st.caption("PPT preview not available; download to view.")
            with open(file_path, "rb") as f:
                st.download_button(
                    "Download PPT",
                    data=f.read(),
                    file_name=os.path.basename(file_path),
                    key=f"dl_ppt_{key_prefix}",
                )
        else:
            st.image(file_path, use_container_width=True)
    else:
        st.warning("File missing.")
    if is_editor:
        unique_suffix = uuid.uuid4().hex
        btn_key = f"del_media_{media.get('id') or 'noid'}_{key_prefix}_{unique_suffix}"
        if st.button(
            "Delete images",
            key=btn_key,
            help="Remove all images for this section entry.",
        ):
            delete_media_for_section(media.get("segment_id"), media.get("section"), media.get("name"))
            st.success("Images removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_media_tabs(items, is_editor: bool, title: str = "Images", key_prefix: str = "media_tabs") -> None:
    if title:
        st.markdown(f"##### {title}")
    tab_labels = [item.get("name") or f"Image {i+1}" for i, item in enumerate(items)]
    tabs = st.tabs(tab_labels)
    for idx, tab in enumerate(tabs):
        with tab:
            render_media_item(items[idx], is_editor, key_prefix=f"{key_prefix}_{idx}")


def render_battleground_tabs_view(segment_id: int, is_editor: bool) -> None:
    """Display JTBD tabs in the Battlegrounds section."""
    notes = get_battleground_notes(segment_id)
    if not notes:
        st.info("No Battlegrounds JTBD tabs published yet. Editors can add them in Data Studio.")
        return
    labels = [n.get("title") or f"Cluster {n['tab_index']}" for n in notes]
    tabs = st.tabs(labels)
    for note, tab in zip(notes, tabs):
        with tab:
            title = note.get("title") or f"Cluster {note['tab_index']}"
            st.markdown(f"### {title}")
            cols = st.columns(2)
            with cols[0]:
                st.markdown("**What's Working & Holding Us Back?**")
                st.markdown(f"<div class='comment-box'>{format_comment(note.get('working_text',''))}</div>", unsafe_allow_html=True)
            with cols[1]:
                st.markdown("**JTBDs**")
                st.markdown(f"<div class='comment-box'>{format_comment(note.get('jtbd_text',''))}</div>", unsafe_allow_html=True)
