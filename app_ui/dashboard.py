import json
import os
import re
import uuid
from typing import Dict, List

import numpy as np
import pandas as pd
import streamlit as st

from app_core.charts import count_charts_for_segment, delete_chart, get_dataset_label
from app_core.constants import SECTIONS
from app_core.filters import apply_filters
from app_core.media import delete_media_for_section, get_media_for_segment
from app_core.battlegrounds import get_battleground_notes
from app_core.tables import build_table_preview, delete_table, get_tables_for_segment, delete_tables_for_section, save_table
from app_core.uploads import count_uploads_for_segment, overwrite_dataset, get_uploads, query_segment_filtered, load_dataset

from .charts import plot_chart


def draw_dashboard(segment: Dict, charts, tables, is_editor: bool = False) -> None:
    st.subheader(f"Segment: {segment['name']}")
    
    # Check if there's any published content
    if not charts and not tables:
        st.info("No content published yet. Editors can publish content from the Data Studio.")
        return
    
    # Show content in tabs
    tabs = st.tabs(["NS Landscape", "Segment Truths", "Brand Truths", "Segment Trends", "Brand Trends", "Battlegrounds"])
    
    # NS Landscape tab
    with tabs[0]:
        render_ns_landscape_dashboard(segment, charts, tables, is_editor)
    
    # Segment Truths tab
    with tabs[1]:
        render_segment_truths_dashboard(segment, tables, is_editor)
    
    # Brand Truths tab
    with tabs[2]:
        render_brand_truths_dashboard(segment, tables, is_editor)
    
    # Segment Trends tab
    with tabs[3]:
        render_segment_trends_dashboard(segment, is_editor)
    
    # Brand Trends tab
    with tabs[4]:
        render_brand_trends_dashboard(segment, tables, is_editor)
    
    # Battlegrounds tab
    with tabs[5]:
        render_battlegrounds_dashboard(segment, tables, is_editor)
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
    """Lightweight formatting: **bold**, __underline__, *italic*, ## heading, - bullets, line breaks."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = safe.splitlines()
    rendered = []
    for line in lines:
        if line.startswith("##"):
            heading_text = line.lstrip('#').strip()
            # Apply formatting to heading
            heading_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", heading_text)
            heading_text = re.sub(r"__(.+?)__", r"<u>\1</u>", heading_text)
            heading_text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", heading_text)
            rendered.append(f"<div style='font-size:1.08rem;font-weight:700'>{heading_text}</div>")
        elif line.startswith("•") or line.strip().startswith("-"):
            # Support both • and - for bullets
            text_content = line.lstrip('•').lstrip('-').strip()
            # Apply formatting to bullet content
            text_content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text_content)
            text_content = re.sub(r"__(.+?)__", r"<u>\1</u>", text_content)
            text_content = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text_content)
            rendered.append(f"<div style='margin-left:0.6rem;'>• {text_content}</div>")
        else:
            # Apply bold **text**
            line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
            # Apply underline __text__
            line = re.sub(r"__(.+?)__", r"<u>\1</u>", line)
            # Apply italic *text* (must be after bold to avoid conflicts)
            line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", line)
            rendered.append(line)
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
    st.markdown(f"### {chart['name']}")
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


def render_table_block(table, is_editor: bool) -> None:
    dataset_label = get_dataset_label(table["dataset_id"])
    st.markdown(f"### {table['name']}")
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


def render_section_placeholder(section: str) -> None:
    st.info(f"No content configured yet for {section}.")


def filter_df_by_segment(df: pd.DataFrame, segment: Dict) -> pd.DataFrame:
    """Filter dataframe by segment using excel_name and filter_column."""
    excel_name = segment.get("excel_name", segment["name"])
    filter_column = segment.get("filter_column", "Segment_Col_1")
    
    if filter_column not in df.columns:
        return pd.DataFrame()  # Return empty if column doesn't exist
    
    return df[df[filter_column].astype(str).str.strip() == excel_name]


def get_latest_upload_row(segment_id: int):
    uploads = get_uploads(segment_id=segment_id)
    if uploads:
        return sorted(uploads, key=lambda r: r["uploaded_at"], reverse=True)[0]
    all_uploads = get_uploads()
    if all_uploads:
        return sorted(all_uploads, key=lambda r: r["uploaded_at"], reverse=True)[0]
    return None


@st.cache_data(show_spinner=False)
def get_filtered_df_for_segment(upload_id: int, upload_path: str, segment_excel_name: str, filter_column: str):
    excel_name = segment_excel_name.strip()
    years = ["A23", "A24", "A25"]
    df = query_segment_filtered(upload_path, excel_name, filter_column, years)
    years_available = [y for y in years if y in df["PRI Year"].unique().tolist()] if not df.empty else []
    return df, years_available


def render_segment_ns_pivot(segment: Dict) -> bool:
    """Render NS Landscape manufacturing pivot with YoY and 2yr CAGR for the segment. Returns True if shown."""
    upload_row = get_latest_upload_row(segment["id"])
    if not upload_row:
        st.info("Upload a dataset to render this view.")
        return False

    df, years_available = get_filtered_df_for_segment(upload_row["id"], upload_row["data_path"], segment["name"])
    if df is None or df.empty:
        st.info("No rows for this segment in the uploaded file.")
        return False

    selected_years = st.multiselect(
        "Fiscal years to include",
        options=years_available,
        default=years_available,
        key=f"ns_years_{segment['id']}",
    )
    if not selected_years:
        st.info("Select at least one fiscal year.")
        return False
    df = df[df["PRI Year"].isin(selected_years)]
    if df.empty:
        st.info("No data for the selected years.")
        return False

    pivot_mfs = pd.pivot_table(
        df,
        index="Mfg Com",
        columns="PRI Year",
        values="NS M INR",
        aggfunc="sum",
        fill_value=0,
    )
    pivot_mfs = pivot_mfs.reindex(columns=selected_years).fillna(0)

    segment_total = pivot_mfs.sum(axis=0).to_frame().T
    segment_total.index = ["Segment Total"]
    pivot_mfs = pd.concat([pivot_mfs, segment_total], axis=0)

    # YoY growth for consecutive years
    yoy_df = pivot_mfs[selected_years].pct_change(axis=1) * 100
    if len(selected_years) > 1:
        yoy_df = yoy_df.iloc[:, 1:].round(2)
        yoy_df.columns = [f"{col} Growth %" for col in selected_years[1:]]
    else:
        yoy_df = pd.DataFrame(index=pivot_mfs.index)

    # 2-year CAGR (A23 -> A25) when both present
    if "A23" in selected_years and "A25" in selected_years:
        start = pivot_mfs["A23"]
        end = pivot_mfs["A25"]
        cagr_vals = np.where(start > 0, ((end / start) ** 0.5 - 1) * 100, np.nan)
        cagr_series = pd.Series(cagr_vals, index=pivot_mfs.index, name="2 Yr CAGR %").round(2)
    else:
        cagr_series = pd.Series([np.nan] * len(pivot_mfs), index=pivot_mfs.index, name="2 Yr CAGR %")

    # Formatting
    pivot_fmt = pivot_mfs[selected_years].applymap(lambda x: f"{x:.0f}" if pd.notnull(x) else "")
    yoy_fmt = yoy_df.applymap(lambda x: f"{x:.2f}%" if pd.notnull(x) else "")
    cagr_fmt = cagr_series.apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "")
    cagr_fmt = cagr_fmt.to_frame()

    final_table = pd.concat([pivot_fmt, yoy_fmt, cagr_fmt], axis=1).reset_index()
    final_table.rename(columns={"index": "Mfg Com"}, inplace=True)

    custom_order = ["Segment Total", "PRI", "Diageo", "Others"]
    final_table["Mfg Com"] = pd.Categorical(final_table["Mfg Com"], categories=custom_order, ordered=True)
    final_table = final_table.sort_values("Mfg Com").reset_index(drop=True)

    st.markdown(f"#### Manufacturing View ({segment['name']})")
    st.dataframe(final_table, use_container_width=True)
    growth_rows = final_table[final_table["Mfg Com"].isin(custom_order)].copy()
    if not growth_rows.empty:
        growth_rows["Mfg Com"] = growth_rows["Mfg Com"].replace({"Segment Total": "Segment"})
        growth_cols = [col for col in ["A24 Growth %", "A25 Growth %", "2 Yr CAGR %"] if col in growth_rows.columns]
        if growth_cols:
            growth_display = growth_rows[["Mfg Com"] + growth_cols].copy()
            rename_map = {"Mfg Com": "Segment", "A24 Growth %": "A24", "A25 Growth %": "A25", "2 Yr CAGR %": "2Yr CAGR"}
            growth_display = growth_display.rename(columns={k: v for k, v in rename_map.items() if k in growth_display.columns})
            st.markdown(f"#### {segment['name']} growth summary")
            st.table(growth_display)
    return True


def render_ns_landscape_dashboard(segment: Dict, charts: List, tables: List, is_editor: bool) -> None:
    """Render NS Landscape section with Manufacturing Pivot and Brand Chart"""
    import plotly.graph_objects as go
    
    # Filter for NS Landscape content
    ns_charts = [c for c in charts if c["section"] == "NS Landscape"]
    ns_tables = [t for t in tables if t["section"] == "NS Landscape"]
    
    if not ns_charts and not ns_tables:
        st.info("No content published for NS Landscape yet. Editors can configure it in Data Studio.")
        return
    
    # Get all components
    pivot_table = next((t for t in ns_tables if t["name"] == "Manufacturing Pivot"), None)
    brand_chart = next((c for c in ns_charts if c["name"] == "Brand Performance"), None)
    family_chart = next((c for c in ns_charts if c["name"] == "Brand Family Performance"), None)
    zonal_table = next((t for t in ns_tables if t["name"] == "Zonal Pivot"), None)
    north_drilldown = next((t for t in ns_tables if t["name"] == "NORTH State Drill-Down"), None)
    west_drilldown = next((t for t in ns_tables if t["name"] == "WEST+CSD State Drill-Down"), None)
    east_drilldown = next((t for t in ns_tables if t["name"] == "EAST State Drill-Down"), None)
    south_drilldown = next((t for t in ns_tables if t["name"] == "SOUTH State Drill-Down"), None)
    
    # Render Manufacturing Pivot (table and comment side by side)
    if pivot_table:
        render_manufacturing_pivot_dashboard(pivot_table, segment, is_editor)
    
    # Render Brand Performance Chart below (full width)
    if brand_chart:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        render_brand_chart_dashboard(brand_chart, segment, is_editor)
    
    # Render Brand Family chart below (full width)
    if family_chart:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        render_brand_family_chart_dashboard(family_chart, segment, is_editor)
    
    # Render zonal table below (full width)
    if zonal_table:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        render_zonal_pivot_dashboard(zonal_table, segment, is_editor)
    
    # Render zone state drill-downs in tabs
    zone_drilldowns = []
    if north_drilldown:
        zone_drilldowns.append(("NORTH", north_drilldown, "North Zone"))
    if west_drilldown:
        zone_drilldowns.append(("WEST+CSD", west_drilldown, "West+CSD Zone"))
    if east_drilldown:
        zone_drilldowns.append(("EAST", east_drilldown, "East Zone"))
    if south_drilldown:
        zone_drilldowns.append(("SOUTH", south_drilldown, "South Zone"))
    
    if zone_drilldowns:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        
        # Create tabs for each zone
        tab_labels = [zone[0] for zone in zone_drilldowns]
        tabs = st.tabs(tab_labels)
        
        for idx, (zone_label, table_row, zone_name) in enumerate(zone_drilldowns):
            with tabs[idx]:
                render_zone_drilldown_dashboard(table_row, segment, is_editor, zone_name)
    
    # Render Placeholder Images
    from app_core.media import get_media_for_segment
    existing_media = get_media_for_segment(segment["id"])
    placeholder_images = [m for m in existing_media if m.get("section") == "NS Landscape" and m.get("name") == "Placeholder Images"]
    placeholder_images = sorted(placeholder_images, key=lambda x: x.get("id", 0))
    
    if placeholder_images:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        
        for idx, img in enumerate(placeholder_images):
            file_path = img.get("file_path")
            title = img.get("title", "")
            comment = img.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                # Display title first (outside columns)
                if title:
                    st.markdown(f"### {title}")
                
                # Image on left, comment on right
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                # Add spacing between images
                if idx < len(placeholder_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for editors
        if is_editor:
            if st.button("Delete Placeholder Images", key=f"del_ns_placeholder_{segment['id']}"):
                from app_core.media import delete_media_for_section
                delete_media_for_section(segment["id"], "NS Landscape", "Placeholder Images")
                st.success("Placeholder images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Render Custom Trends View
    custom_trends = next((t for t in ns_tables if t["name"] == "Custom Trends View"), None)
    if custom_trends:
        st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        render_custom_trends_dashboard(custom_trends, segment, is_editor)


def render_manufacturing_pivot_dashboard(table_row: Dict, segment: Dict, is_editor: bool) -> None:
    """Render the manufacturing pivot table with YoY and CAGR - table and comment side by side"""
    # Get custom title from config
    filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
    custom_title = filter_config.get("title", "NS Overview") if isinstance(filter_config, dict) else "NS Overview"
    
    st.markdown(f"### {custom_title}")
    
    # Create two columns: table on left, comment on right
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Load data and apply filters
        df = load_dataset(table_row["dataset_id"])
        if df is None or df.empty:
            st.warning("Dataset not found.")
            return
        
        # Filter by segment
        df = filter_df_by_segment(df, segment)
        
        # Get year filter from config
        filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
        selected_years = filter_config.get("years", ["A23", "A24", "A25"]) if isinstance(filter_config, dict) else ["A23", "A24", "A25"]
        df = df[df["PRI Year"].isin(selected_years)]
        
        if df.empty:
            st.warning("No data available for selected filters.")
            return
        
        # Create pivot
        pivot = pd.pivot_table(
            df,
            index="Mfg Com",
            columns="PRI Year",
            values="NS M INR",
            aggfunc="sum",
            fill_value=0
        )
        pivot = pivot.reindex(columns=selected_years, fill_value=0)
        
        # Add Segment Total
        segment_total = pivot.sum(axis=0).to_frame().T
        segment_total.index = ["Segment Total"]
        pivot = pd.concat([pivot, segment_total], axis=0)
        
        # Keep only growth columns and CAGR (no base year)
        columns_to_keep = ["Mfg Com"]
        
        # Calculate YoY Growth
        for i in range(1, len(selected_years)):
            prev_year = selected_years[i-1]
            curr_year = selected_years[i]
            col_name = f"{curr_year} Growth %"
            pivot[col_name] = ((pivot[curr_year] - pivot[prev_year]) / pivot[prev_year] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)
            columns_to_keep.append(col_name)
        
        # Calculate 2-Year CAGR
        if "A23" in selected_years and "A25" in selected_years:
            start = pivot["A23"]
            end = pivot["A25"]
            pivot["2 Yr CAGR %"] = np.where(
                start > 0,
                ((end / start) ** 0.5 - 1) * 100,
                0
            ).round(1)
            columns_to_keep.append("2 Yr CAGR %")
        
        # Format and sort
        pivot = pivot.reset_index()
        pivot = pivot.rename(columns={"index": "Mfg Com"})
        
        custom_order = ["Segment Total", "PRI", "Diageo", "Others"]
        pivot["sort_key"] = pivot["Mfg Com"].apply(lambda x: custom_order.index(x) if x in custom_order else 999)
        pivot = pivot.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)
        
        # Select only required columns
        final_columns = [col for col in columns_to_keep if col in pivot.columns]
        pivot_display = pivot[final_columns].copy()
        
        # Format growth and CAGR columns to show % symbol
        for col in pivot_display.columns:
            if 'Growth %' in col or 'CAGR %' in col:
                pivot_display[col] = pivot_display[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "0.0%")
        
        # Apply styling to highlight Segment Total row
        def highlight_segment_total(row):
            """Highlight the Segment Total row with golden background"""
            mfg_com = pivot_display.loc[row.name, 'Mfg Com']
            if mfg_com == "Segment Total":
                return ['background-color: #FFF3CD; font-weight: bold; border-top: 3px solid #f5b400; border-bottom: 3px solid #f5b400; color: #856404'] * len(row)
            return [''] * len(row)
    
        # Display with styling
        styled_pivot = pivot_display.style.apply(highlight_segment_total, axis=1)
        st.dataframe(styled_pivot, use_container_width=True, hide_index=True)
    
    with col2:
        # Show comment in right column
        comment = table_row["comment"] if table_row["comment"] else ""
        if comment:
            st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
        
        # Delete button for editors
        if is_editor:
            if st.button("Delete Pivot Table", key=f"del_pivot_{table_row['id']}"):
                delete_table(table_row["id"])
                st.success("Pivot table removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()


def render_brand_chart_dashboard(chart_row: Dict, segment: Dict, is_editor: bool) -> None:
    """Render the brand performance chart with NS M INR and growth rates"""
    import plotly.express as px
    
    st.markdown(f"### Brand Performance")
    
    # Load data and apply filters
    df = load_dataset(chart_row["dataset_id"])
    if df is None or df.empty:
        st.warning("Dataset not found.")
        return
    
    # Filter by segment
    df = filter_df_by_segment(df, segment)
    
    # Get filters from config
    filter_config = json.loads(chart_row["filter_json"] if chart_row["filter_json"] else "{}")
    selected_brands = filter_config.get("brands", []) if isinstance(filter_config, dict) else []
    selected_years = filter_config.get("years", ["A23", "A24", "A25"]) if isinstance(filter_config, dict) else ["A23", "A24", "A25"]
    excluded_states = filter_config.get("excluded_states", []) if isinstance(filter_config, dict) else []
    
    # Apply state exclusion filter
    if excluded_states and "State" in df.columns:
        df = df[~df["State"].isin(excluded_states)]
        st.caption(f"🚫 Excluding {len(excluded_states)} state(s): {', '.join(excluded_states)}")
    
    # Apply filters
    df = df[df["Brand"].isin(selected_brands)]
    df = df[df["PRI Year"].isin(selected_years)]
    
    if df.empty:
        st.warning("No data available for selected brands and years.")
        return
    
    # Aggregate data
    chart_data = df.groupby(["Brand", "Brand Family", "PRI Year"])["NS M INR"].sum().reset_index()
    
    # Create pivot to calculate growth rates
    pivot_wide = chart_data.pivot_table(
        index=["Brand", "Brand Family"],
        columns="PRI Year",
        values="NS M INR",
        aggfunc="sum"
    ).reset_index()
    
    # Calculate growth rates and CAGR for each brand
    growth_rates = {}
    cagr_values = {}
    for _, row in pivot_wide.iterrows():
        brand = row["Brand"]
        ns_a23 = row.get("A23", 0) or 0
        ns_a24 = row.get("A24", 0) or 0
        ns_a25 = row.get("A25", 0) or 0
        
        # A24 Growth % (YoY from A23)
        a24_growth = ((ns_a24 - ns_a23) / ns_a23 * 100) if ns_a23 != 0 else 0
        
        # A25 Growth % (YoY from A24)
        a25_growth = ((ns_a25 - ns_a24) / ns_a24 * 100) if ns_a24 != 0 else 0
        
        # 2-Year CAGR (A23 to A25)
        cagr_2yr = (((ns_a25 / ns_a23) ** 0.5) - 1) * 100 if ns_a23 != 0 else 0
        
        growth_rates[brand] = {
            "A23": None,  # No growth for base year - don't show anything
            "A24": round(a24_growth, 1),
            "A25": round(a25_growth, 1)
        }
        cagr_values[brand] = round(cagr_2yr, 1)
    
    # Add growth rate text - empty for A23 (no growth rate for base year)
    chart_data["Growth Text"] = chart_data.apply(
        lambda r: f"{growth_rates[r['Brand']][r['PRI Year']]:.1f}%" if r['PRI Year'] != 'A23' else "",
        axis=1
    )
    
    # Sort brands by Brand Family total NS, then by brand total NS
    brand_totals = chart_data.groupby(["Brand", "Brand Family"])["NS M INR"].sum().reset_index()
    brand_totals.columns = ["Brand", "Brand Family", "Total"]
    
    family_totals = brand_totals.groupby("Brand Family")["Total"].sum().reset_index()
    family_totals.columns = ["Brand Family", "Family Total"]
    family_totals = family_totals.sort_values("Family Total", ascending=False)
    
    brand_totals = brand_totals.merge(family_totals, on="Brand Family")
    brand_totals = brand_totals.sort_values(["Family Total", "Total"], ascending=[False, False])
    
    # Create ordered brand list
    brand_order = brand_totals["Brand"].tolist()
    
    # Green color scheme - light to dark
    color_map = {
        "A23": "#90EE90",  # Light Green
        "A24": "#4CAF50",  # Medium Green
        "A25": "#1B5E20"   # Dark Green
    }
    
    # Create multi-bar chart with Plotly Express
    fig = px.bar(
        chart_data,
        x="Brand",
        y="NS M INR",
        color="PRI Year",
        barmode="group",
        text="Growth Text",
        height=500,
        color_discrete_map=color_map,
        category_orders={"PRI Year": ["A23", "A24", "A25"], "Brand": brand_order}
    )
    
    # Format growth rate text on top of bars
    fig.update_traces(textposition='outside', textfont=dict(size=11, family="Arial Black", color="#2E7D32"))
    
    # Get max Y value for positioning CAGR boxes
    max_y = chart_data["NS M INR"].max()
    
    # Add CAGR boxes above each brand with neutral styling
    annotations = []
    for brand in brand_order:
        cagr = cagr_values[brand]
        
        annotations.append(dict(
            x=brand,
            y=max_y * 1.15,  # Position above the bars
            text=f"<b>2yr CAGR: {cagr:.1f}%</b>",
            showarrow=False,
            font=dict(size=10, color="white", family="Arial"),
            bgcolor="#607D8B",  # Neutral gray-blue color
            bordercolor="#FFFFFF",
            borderwidth=1,
            borderpad=6,
            xanchor='center',
            yanchor='bottom',
            opacity=0.95
        ))
    
    fig.update_layout(
        xaxis_title="Brand",
        yaxis_title="NS M INR",
        legend_title="PRI Year",
        annotations=annotations,
        yaxis=dict(range=[0, max_y * 1.25])  # Extend Y-axis to fit CAGR boxes
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Show comment below the chart
    comment = chart_row["comment"] if chart_row["comment"] else ""
    if comment:
        st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
    
    # Show data table with growth rates in expander
    with st.expander("View Data with Growth Rates"):
        # Create summary table with NS values and growth rates
        summary_df = pivot_wide.copy()
        
        # Calculate growth rates for each brand
        summary_df["A24 Growth %"] = summary_df.apply(
            lambda r: round(((r.get("A24", 0) or 0) - (r.get("A23", 0) or 0)) / (r.get("A23", 0) or 1) * 100, 1) if (r.get("A23", 0) or 0) != 0 else 0, 
            axis=1
        )
        summary_df["A25 Growth %"] = summary_df.apply(
            lambda r: round(((r.get("A25", 0) or 0) - (r.get("A24", 0) or 0)) / (r.get("A24", 0) or 1) * 100, 1) if (r.get("A24", 0) or 0) != 0 else 0, 
            axis=1
        )
        summary_df["2-Yr CAGR %"] = summary_df.apply(
            lambda r: round((((r.get("A25", 0) or 0) / (r.get("A23", 0) or 1)) ** 0.5 - 1) * 100, 1) if (r.get("A23", 0) or 0) != 0 else 0, 
            axis=1
        )
        
        # Calculate Brand Family totals
        family_summary = []
        for family in summary_df["Brand Family"].unique():
            family_data = summary_df[summary_df["Brand Family"] == family]
            
            # Sum NS values for the family
            a23_total = family_data["A23"].sum() if "A23" in family_data.columns else 0
            a24_total = family_data["A24"].sum() if "A24" in family_data.columns else 0
            a25_total = family_data["A25"].sum() if "A25" in family_data.columns else 0
            
            # Calculate family-level growth rates
            a24_growth = ((a24_total - a23_total) / a23_total * 100) if a23_total != 0 else 0
            a25_growth = ((a25_total - a24_total) / a24_total * 100) if a24_total != 0 else 0
            cagr_2yr = (((a25_total / a23_total) ** 0.5 - 1) * 100) if a23_total != 0 else 0
            
            family_summary.append({
                "Brand Family": family,
                "Brand": f"📊 {family} Total",
                "A23": a23_total,
                "A24": a24_total,
                "A25": a25_total,
                "A24 Growth %": round(a24_growth, 1),
                "A25 Growth %": round(a25_growth, 1),
                "2-Yr CAGR %": round(cagr_2yr, 1),
                "is_family_total": True
            })
        
        # Add is_family_total flag to brand rows
        summary_df["is_family_total"] = False
        
        # Combine family totals with brand data
        family_df = pd.DataFrame(family_summary)
        combined_df = pd.concat([family_df, summary_df], ignore_index=True)
        
        # Sort by Brand Family, then by is_family_total (True first), then by Brand
        combined_df = combined_df.sort_values(
            by=["Brand Family", "is_family_total", "Brand"],
            ascending=[True, False, True]
        ).reset_index(drop=True)
        
        # Reorder columns: Brand Family, Brand, A23, A24, A25, A24 Growth %, A25 Growth %, 2-Yr CAGR %
        column_order = ["Brand Family", "Brand"]
        if "A23" in combined_df.columns:
            column_order.append("A23")
        if "A24" in combined_df.columns:
            column_order.append("A24")
        if "A25" in combined_df.columns:
            column_order.append("A25")
        if "A24 Growth %" in combined_df.columns:
            column_order.append("A24 Growth %")
        if "A25 Growth %" in combined_df.columns:
            column_order.append("A25 Growth %")
        column_order.append("2-Yr CAGR %")
        
        # Select and display columns
        display_df = combined_df[column_order].copy()
        
        # Format NS columns with commas
        for col in ["A23", "A24", "A25"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x > 0 else "0")
        
        # Format growth columns with % symbol
        for col in ["A24 Growth %", "A25 Growth %", "2-Yr CAGR %"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "0.0%")
        
        # Apply styling to highlight family total rows
        def highlight_family_totals(row):
            """Highlight the Brand Family total rows"""
            brand_name = combined_df.loc[row.name, 'Brand']
            if "Total" in str(brand_name) and "📊" in str(brand_name):
                return ['background-color: #E8F5E9; font-weight: bold; border-top: 2px solid #4CAF50; border-bottom: 1px solid #4CAF50'] * len(row)
            return [''] * len(row)
        
        # Display with styling
        styled_df = display_df.style.apply(highlight_family_totals, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # Delete button for editors
    if is_editor:
        if st.button("Delete Brand Chart", key=f"del_chart_{chart_row['id']}"):
            delete_chart(chart_row["id"])
            st.success("Brand chart removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_brand_family_chart_dashboard(chart_row: Dict, segment: Dict, is_editor: bool) -> None:
    """Render the brand family performance chart with NS M INR and growth rates"""
    import plotly.express as px
    
    st.markdown(f"### Brand Family Performance")
    
    # Load data and apply filters
    df = load_dataset(chart_row["dataset_id"])
    if df is None or df.empty:
        st.warning("Dataset not found.")
        return
    
    # Filter by segment
    df = filter_df_by_segment(df, segment)
    
    # Get filters from config
    filter_config = json.loads(chart_row["filter_json"] if chart_row["filter_json"] else "{}")
    selected_brands = filter_config.get("brands", []) if isinstance(filter_config, dict) else []
    selected_years = filter_config.get("years", ["A23", "A24", "A25"]) if isinstance(filter_config, dict) else ["A23", "A24", "A25"]
    excluded_states = filter_config.get("excluded_states", []) if isinstance(filter_config, dict) else []
    
    # Apply state exclusion filter
    if excluded_states and "State" in df.columns:
        df = df[~df["State"].isin(excluded_states)]
        st.caption(f"🚫 Excluding {len(excluded_states)} state(s): {', '.join(excluded_states)}")
    
    # Apply filters
    df = df[df["Brand"].isin(selected_brands)]
    df = df[df["PRI Year"].isin(selected_years)]
    
    if df.empty:
        st.warning("No data available for selected brands and years.")
        return
    
    # Aggregate by Brand Family and Year
    chart_data = df.groupby(["Brand Family", "PRI Year"])["NS M INR"].sum().reset_index()
    
    # Create pivot to calculate growth rates
    pivot_wide = chart_data.pivot_table(
        index="Brand Family",
        columns="PRI Year",
        values="NS M INR",
        aggfunc="sum"
    ).reset_index()
    
    # Calculate growth rates and CAGR for each family
    growth_rates = {}
    cagr_values = {}
    for _, row in pivot_wide.iterrows():
        family = row["Brand Family"]
        ns_a23 = row.get("A23", 0) or 0
        ns_a24 = row.get("A24", 0) or 0
        ns_a25 = row.get("A25", 0) or 0
        
        # A24 Growth % (YoY from A23)
        a24_growth = ((ns_a24 - ns_a23) / ns_a23 * 100) if ns_a23 != 0 else 0
        
        # A25 Growth % (YoY from A24)
        a25_growth = ((ns_a25 - ns_a24) / ns_a24 * 100) if ns_a24 != 0 else 0
        
        # 2-Year CAGR (A23 to A25)
        cagr_2yr = (((ns_a25 / ns_a23) ** 0.5) - 1) * 100 if ns_a23 != 0 else 0
        
        growth_rates[family] = {
            "A23": None,
            "A24": round(a24_growth, 1),
            "A25": round(a25_growth, 1)
        }
        cagr_values[family] = round(cagr_2yr, 1)
    
    # Add growth rate text
    chart_data["Growth Text"] = chart_data.apply(
        lambda r: f"{growth_rates[r['Brand Family']][r['PRI Year']]:.1f}%" if r['PRI Year'] != 'A23' else "",
        axis=1
    )
    
    # Sort families by total NS
    family_totals = chart_data.groupby("Brand Family")["NS M INR"].sum().reset_index()
    family_totals.columns = ["Brand Family", "Total"]
    family_totals = family_totals.sort_values("Total", ascending=False)
    family_order = family_totals["Brand Family"].tolist()
    
    # Green color scheme
    color_map = {
        "A23": "#90EE90",
        "A24": "#4CAF50",
        "A25": "#1B5E20"
    }
    
    # Create multi-bar chart
    fig = px.bar(
        chart_data,
        x="Brand Family",
        y="NS M INR",
        color="PRI Year",
        barmode="group",
        text="Growth Text",
        height=500,
        color_discrete_map=color_map,
        category_orders={"PRI Year": ["A23", "A24", "A25"], "Brand Family": family_order}
    )
    
    # Format growth rate text on top of bars
    fig.update_traces(textposition='outside', textfont=dict(size=11, family="Arial Black", color="#2E7D32"))
    
    # Get max Y value for positioning CAGR boxes
    max_y = chart_data["NS M INR"].max()
    
    # Add CAGR boxes above each brand family
    annotations = []
    for family in family_order:
        cagr = cagr_values[family]
        
        annotations.append(dict(
            x=family,
            y=max_y * 1.15,
            text=f"<b>2yr CAGR: {cagr:.1f}%</b>",
            showarrow=False,
            font=dict(size=10, color="white", family="Arial"),
            bgcolor="#607D8B",
            bordercolor="#FFFFFF",
            borderwidth=1,
            borderpad=6,
            xanchor='center',
            yanchor='bottom',
            opacity=0.95
        ))
    
    fig.update_layout(
        xaxis_title="Brand Family",
        yaxis_title="NS M INR",
        legend_title="PRI Year",
        annotations=annotations,
        yaxis=dict(range=[0, max_y * 1.25])
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Show comment below the chart
    comment = chart_row["comment"] if chart_row["comment"] else ""
    if comment:
        st.markdown(f"<div class='comment-box'>{format_comment(comment)}</div>", unsafe_allow_html=True)
    
    # Delete button for editors
    if is_editor:
        if st.button("Delete Brand Family Chart", key=f"del_family_chart_{chart_row['id']}"):
            delete_chart(chart_row["id"])
            st.success("Brand Family chart removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_zonal_pivot_dashboard(table_row: Dict, segment: Dict, is_editor: bool) -> None:
    """Render the zonal pivot table with Brand Family x Zone"""
    # Get custom title from config
    filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
    custom_title = filter_config.get("title", "NS Zonal View") if isinstance(filter_config, dict) else "NS Zonal View"
    
    st.markdown(f"### {custom_title}")
    
    # Load data and apply filters
    df = load_dataset(table_row["dataset_id"])
    if df is None or df.empty:
        st.warning("Dataset not found.")
        return
    
    # Filter by segment
    df = filter_df_by_segment(df, segment)
    
    # Get filters from config
    filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
    selected_families = filter_config.get("brand_families", []) if isinstance(filter_config, dict) else []
    selected_brands = filter_config.get("brands", []) if isinstance(filter_config, dict) else []
    excluded_states = filter_config.get("excluded_states", []) if isinstance(filter_config, dict) else []
    
    # Apply state exclusion filter
    if excluded_states and "State" in df.columns:
        df = df[~df["State"].isin(excluded_states)]
        st.caption(f"🚫 Excluding {len(excluded_states)} state(s): {', '.join(excluded_states)}")
    
    # Filter for A24 and A25 (needed for growth calculations)
    df = df[df["PRI Year"].isin(["A24", "A25"])]
    df = df[df["Brand Family"].isin(selected_families)]
    df = df[df["Brand"].isin(selected_brands)]
    
    if df.empty:
        st.warning("No data available for selected filters.")

        return
    
    # Check if Zone column exists
    if "Zone" not in df.columns:
        st.warning("Zone column not found in dataset.")

        return
    
    # Use the same function as preview
    from app_ui.data_studio import create_zonal_pivot
    result = create_zonal_pivot(df, selected_families, selected_brands)
    
    if result is None or result.empty:
        st.warning("Unable to create zonal pivot.")

        return
    
    # Get zones
    zones_unsorted = result.attrs.get('zones', [])
    segment_growth = result.attrs.get('segment_growth', {})
    pw_salience = result.attrs.get('pw_salience', {})
    
    # Sort zones by salience (highest first)
    zones = sorted(zones_unsorted, key=lambda z: pw_salience.get(z, 0), reverse=True)
    
    # Display in 4 columns
    if len(zones) == 4:
        cols = st.columns(4)
    elif len(zones) >= 2:
        cols = st.columns(len(zones))
    else:
        cols = [st.container()]
    
    # Define colors for brand families
    family_colors = {
        0: "#E8F5E9",  # Light Green
        1: "#E3F2FD",  # Light Blue
        2: "#FFF3E0",  # Light Orange
        3: "#F3E5F5",  # Light Purple
        4: "#FCE4EC",  # Light Pink
    }
    
    for idx, zone in enumerate(zones):
        with cols[idx] if idx < len(cols) else cols[-1]:
            # Big centered zone header
            st.markdown(f"""
                <div style='text-align: center; padding: 0.5rem; background-color: #f0f2f6; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                    <h2 style='margin: 0; font-size: 1.8rem;'>{zone}</h2>
                    <p style='margin: 0; font-size: 1.3rem; font-weight: bold; color: #1976D2;'>
                        {pw_salience.get(zone, 0):.0f}% Salience
                    </p>
                    <p style='margin: 0; font-size: 1.1rem; font-weight: bold;'>
                        {segment_growth.get(zone, 0):+.1f}% Gr in A25
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            # Filter rows for this zone
            zone_df = result[["Brand", "Type", f"{zone}_MS", f"{zone}_Gr", f"{zone}_BTM"]].copy()
            
            # Apply styling to highlight brand families and color negatives
            def highlight_families(row):
                row_type = zone_df.loc[row.name, 'Type']
                if row_type == 'family':
                    family_idx = len([i for i in zone_df.index[:row.name+1] if zone_df.loc[i, 'Type'] == 'family']) - 1
                    color = family_colors[family_idx % len(family_colors)]
                    return [f'background-color: {color}; font-weight: bold'] * len(row)
                return [''] * len(row)
            
            def color_negatives(val):
                """Color negative numbers red"""
                if isinstance(val, str):
                    # Check if string contains negative number
                    if '-' in val or val.startswith('−'):
                        return 'color: #D32F2F; font-weight: bold'
                return ''
            
            # Drop Type column and rename
            display_df = zone_df.drop(columns=['Type'])
            display_df.columns = ["Brand", "MS|Sal", "A25 Gr", "BTM"]
            
            styled_df = display_df.style.apply(highlight_families, axis=1).applymap(color_negatives)
            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
    
    # Show comment box BELOW the zone tables
    comment = table_row["comment"] if table_row["comment"] else ""
    if comment:
        st.markdown(f"""
            <div style='
                background: linear-gradient(to right, #FFFBF0 0%, #FFF9E6 100%);
                border: 1px solid #E8D7A0;
                border-left: 5px solid #D4A017;
                padding: 1.2rem 1.5rem;
                margin: 1.5rem 0 1rem 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            '>
                <div style='
                    font-size: 0.95rem;
                    line-height: 1.7;
                    color: #2C2C2C;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                '>
                    {format_comment(comment)}
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Delete button for editors
    if is_editor:
        if st.button("Delete Zonal Table", key=f"del_zonal_{table_row['id']}"):
            delete_table(table_row["id"])
            st.success("Zonal table removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    



def render_segment_truths_dashboard(segment: Dict, tables: List, is_editor: bool) -> None:
    """Render Segment Truths section"""
    # Filter for Segment Truths content
    seg_truth_table = next((t for t in tables if t["section"] == "Segment Truths" and t["name"] == "Segment Truth"), None)
    
    if not seg_truth_table:
        st.info("No content published for Segment Truths yet. Editors can configure it in Data Studio.")
        return
    
    # Display first image at the very top (if exists)
    from app_core.media import get_media_for_segment
    media_items = get_media_for_segment(segment["id"])
    first_image = next((m for m in media_items if m.get("section") == "Segment Truths" and m.get("name") == "First Image"), None)
    
    if first_image:
        file_path = first_image.get("file_path")
        title = first_image.get("title", "")
        comment = first_image.get("comment", "")
        
        if file_path and os.path.exists(file_path):
            # Display title first (outside columns)
            if title:
                st.markdown(f"### {title}")
            
            # Image on left, comment on right
            col_img, col_comment = st.columns([1, 1])
            
            with col_img:
                st.image(file_path, use_container_width=True)
            
            with col_comment:
                if comment:
                    st.markdown(f"""
                        <div style='
                            background: linear-gradient(to right, #F0F8FF 0%, #E6F3FF 100%);
                            border: 1px solid #B0D4F1;
                            border-left: 5px solid #2196F3;
                            padding: 1.5rem 1.8rem;
                            border-radius: 8px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                            min-height: 300px;
                        '>
                            <div style='
                                font-size: 0.95rem;
                                line-height: 1.8;
                                color: #2C2C2C;
                                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                            '>
                                {format_comment(comment)}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("---")
    
    # Parse configuration
    try:
        config = json.loads(seg_truth_table["filter_json"]) if seg_truth_table["filter_json"] else {}
        title = config.get("title", "")
        comment = config.get("comment", "")
    except:
        title = ""
        comment = seg_truth_table.get("comment", "")
    
    # Display title
    if title:
        st.markdown(f"### {title}")
    
    # Comment box and table side by side
    col1, col2 = st.columns(2)
    
    with col1:
        if comment:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(to right, #F0F8FF 0%, #E6F3FF 100%);
                    border: 1px solid #B0D4F1;
                    border-left: 5px solid #2196F3;
                    padding: 1.5rem 1.8rem;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    min-height: 500px;
                '>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #2C2C2C;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    '>
                        {format_comment(comment)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    with col2:
        # Profile data table in expander
        with st.expander("📊 P3M Segment Profile Data", expanded=False):
            # Load P3M profile data from database
            from app_core.tables import get_tables_for_segment
            existing_tables = get_tables_for_segment(segment["id"])
            saved_p3m_profile = next((t for t in existing_tables if t["section"] == "Segment Truths" and t["name"] == "P3M Segment Profile"), None)
            
            if saved_p3m_profile and saved_p3m_profile["filter_json"]:
                try:
                    # Load saved CSV data
                    profile_dict = json.loads(saved_p3m_profile["filter_json"])
                    df_profile = pd.DataFrame(profile_dict)
                    
                    # Replace None/NaN values with empty strings for display
                    df_profile = df_profile.fillna("")
                    
                    # Calculate index for conditional formatting
                    def calculate_index(row):
                        """Calculate index from TBA and Premium Whisky values"""
                        try:
                            tba_val = str(row["TBA"]).replace("%", "").strip()
                            pw_val = str(row["Premium Whisky"]).replace("%", "").strip()
                            
                            if not tba_val or not pw_val or tba_val == "" or pw_val == "":
                                return None
                            
                            tba_num = float(tba_val)
                            pw_num = float(pw_val)
                            
                            if tba_num == 0:
                                return None
                            
                            return (pw_num / tba_num) * 100
                        except:
                            return None
                    
                    # Add index column
                    df_profile["_index"] = df_profile.apply(calculate_index, axis=1)
                    
                    # Function to apply conditional formatting
                    def color_premium_whisky(row):
                        """Apply background color to Premium Whisky column based on index value"""
                        idx_val = row["_index"]
                        
                        if idx_val is None:
                            return [""] * len(row)
                        
                        try:
                            if idx_val > 110:
                                color = "background-color: #90EE90; font-weight: bold;"
                            elif idx_val >= 105:
                                color = "background-color: #D4EDDA; font-weight: bold;"
                            elif idx_val < 75:
                                color = "background-color: #FFB380; font-weight: bold;"
                            else:
                                color = ""
                            
                            # Apply color only to Premium Whisky column (index 2)
                            return ["", "", color, ""]
                        except:
                            return [""] * len(row)
                    
                    # Apply styling
                    styled_df = df_profile.style.apply(color_premium_whisky, axis=1)
                    
                    # Display only first 3 columns (hide _index)
                    display_df = df_profile[["Metric", "TBA", "Premium Whisky"]].copy()
                    
                    st.dataframe(
                        styled_df, 
                        use_container_width=True, 
                        hide_index=True,
                        height=450,
                        column_order=["Metric", "TBA", "Premium Whisky"]
                    )
                except Exception as e:
                    st.error(f"Error loading P3M profile data: {str(e)}")
            else:
                st.info("No P3M Segment Profile data uploaded yet. Please upload CSV in Data Studio.")
    
    # Display Carousel 1
    carousel1_images = [m for m in media_items if m.get("section") == "Segment Truths" and m.get("name") == "Carousel 1"]
    carousel1_images = sorted(carousel1_images, key=lambda x: x.get("id", 0))
    
    if carousel1_images:
        st.markdown("---")
        
        if len(carousel1_images) > 1:
            # Tabs for carousel 1
            tab_labels = [media.get("title", f"Page {i+1}") or f"Page {i+1}" for i, media in enumerate(carousel1_images)]
            carousel1_tabs = st.tabs(tab_labels)
            
            for idx, (tab, media) in enumerate(zip(carousel1_tabs, carousel1_images)):
                with tab:
                    file_path = media.get("file_path")
                    combined_comment = media.get("comment", "")
                    
                    # Parse page_title and comment
                    page_title = ""
                    comment = ""
                    if combined_comment and "##PAGE_TITLE##" in combined_comment:
                        parts = combined_comment.split("##PAGE_TITLE##")
                        if len(parts) > 1:
                            remaining = parts[1]
                            if "##COMMENT##" in remaining:
                                page_parts = remaining.split("##COMMENT##")
                                page_title = page_parts[0]
                                comment = page_parts[1] if len(page_parts) > 1 else ""
                            else:
                                page_title = remaining
                    else:
                        comment = combined_comment
                    
                    if file_path and os.path.exists(file_path):
                        if page_title:
                            st.markdown(f"### {page_title}")
                        
                        if comment:
                            col_img, col_comment = st.columns([1, 1])
                            
                            with col_img:
                                st.image(file_path, use_container_width=True)
                            
                            with col_comment:
                                st.markdown(f"""
                                    <div style='
                                        background: #F8F9FA;
                                        border-left: 4px solid #f5b400;
                                        padding: 1.5rem;
                                        margin: 1.5rem 0 1rem 0;
                                        border-radius: 8px;
                                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                    '>
                                        <div style='
                                            font-size: 0.95rem;
                                            line-height: 1.7;
                                            color: #2C2C2C;
                                        '>
                                            {format_comment(comment)}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            col1, col2, col3 = st.columns([0.5, 2, 0.5])
                            with col2:
                                st.image(file_path, use_container_width=True)
        else:
            # Single image in carousel 1
            media = carousel1_images[0]
            file_path = media.get("file_path")
            combined_comment = media.get("comment", "")
            
            # Parse page_title and comment
            page_title = ""
            comment = ""
            if combined_comment and "##PAGE_TITLE##" in combined_comment:
                parts = combined_comment.split("##PAGE_TITLE##")
                if len(parts) > 1:
                    remaining = parts[1]
                    if "##COMMENT##" in remaining:
                        page_parts = remaining.split("##COMMENT##")
                        page_title = page_parts[0]
                        comment = page_parts[1] if len(page_parts) > 1 else ""
                    else:
                        page_title = remaining
            else:
                comment = combined_comment
            
            if file_path and os.path.exists(file_path):
                if page_title:
                    st.markdown(f"### {page_title}")
                
                if comment:
                    col_img, col_comment = st.columns([1, 1])
                    
                    with col_img:
                        st.image(file_path, use_container_width=True)
                    
                    with col_comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    col1, col2, col3 = st.columns([0.5, 2, 0.5])
                    with col2:
                        st.image(file_path, use_container_width=True)
    
    # Display Carousel 2
    carousel2_images = [m for m in media_items if m.get("section") == "Segment Truths" and m.get("name") == "Carousel 2"]
    carousel2_images = sorted(carousel2_images, key=lambda x: x.get("id", 0))
    
    if carousel2_images:
        st.markdown("---")
        
        if len(carousel2_images) > 1:
            # Tabs for carousel 2
            tab_labels = [media.get("title", f"Page {i+1}") or f"Page {i+1}" for i, media in enumerate(carousel2_images)]
            carousel2_tabs = st.tabs(tab_labels)
            
            for idx, (tab, media) in enumerate(zip(carousel2_tabs, carousel2_images)):
                with tab:
                    file_path = media.get("file_path")
                    combined_comment = media.get("comment", "")
                    
                    # Parse page_title and comment
                    page_title = ""
                    comment = ""
                    if combined_comment and "##PAGE_TITLE##" in combined_comment:
                        parts = combined_comment.split("##PAGE_TITLE##")
                        if len(parts) > 1:
                            remaining = parts[1]
                            if "##COMMENT##" in remaining:
                                page_parts = remaining.split("##COMMENT##")
                                page_title = page_parts[0]
                                comment = page_parts[1] if len(page_parts) > 1 else ""
                            else:
                                page_title = remaining
                    else:
                        comment = combined_comment
                    
                    if file_path and os.path.exists(file_path):
                        if page_title:
                            st.markdown(f"### {page_title}")
                        
                        if comment:
                            col_img, col_comment = st.columns([1, 1])
                            
                            with col_img:
                                st.image(file_path, use_container_width=True)
                            
                            with col_comment:
                                st.markdown(f"""
                                    <div style='
                                        background: #F8F9FA;
                                        border-left: 4px solid #f5b400;
                                        padding: 1.5rem;
                                        margin: 1.5rem 0 1rem 0;
                                        border-radius: 8px;
                                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                    '>
                                        <div style='
                                            font-size: 0.95rem;
                                            line-height: 1.7;
                                            color: #2C2C2C;
                                        '>
                                            {format_comment(comment)}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            col1, col2, col3 = st.columns([0.5, 2, 0.5])
                            with col2:
                                st.image(file_path, use_container_width=True)
        else:
            # Single image in carousel 2
            media = carousel2_images[0]
            file_path = media.get("file_path")
            combined_comment = media.get("comment", "")
            
            # Parse page_title and comment
            page_title = ""
            comment = ""
            if combined_comment and "##PAGE_TITLE##" in combined_comment:
                parts = combined_comment.split("##PAGE_TITLE##")
                if len(parts) > 1:
                    remaining = parts[1]
                    if "##COMMENT##" in remaining:
                        page_parts = remaining.split("##COMMENT##")
                        page_title = page_parts[0]
                        comment = page_parts[1] if len(page_parts) > 1 else ""
                    else:
                        page_title = remaining
            else:
                comment = combined_comment
            
            if file_path and os.path.exists(file_path):
                if page_title:
                    st.markdown(f"### {page_title}")
                
                if comment:
                    col_img, col_comment = st.columns([1, 1])
                    
                    with col_img:
                        st.image(file_path, use_container_width=True)
                    
                    with col_comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    col1, col2, col3 = st.columns([0.5, 2, 0.5])
                    with col2:
                        st.image(file_path, use_container_width=True)
    
    # Display images one below the other
    seg_truth_images = [m for m in media_items if m.get("section") == "Segment Truths" and m.get("name") == "Segment Truth Images"]
    # Sort by ID to maintain upload order (Image 1, 2, 3, 4, 5)
    seg_truth_images = sorted(seg_truth_images, key=lambda x: x.get("id", 0))
    
    if seg_truth_images:
        st.markdown("---")
        
        # Display images with title and comment
        for idx, media in enumerate(seg_truth_images):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                # Display title first (outside columns)
                if title:
                    st.markdown(f"### {title}")
                
                # Image on left, comment on right
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: linear-gradient(to right, #F0F8FF 0%, #E6F3FF 100%);
                                border: 1px solid #B0D4F1;
                                border-left: 5px solid #2196F3;
                                padding: 1.5rem 1.8rem;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.8;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                # Add spacing between images
                if idx < len(seg_truth_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
    
    # Delete button for editors
    if is_editor:
        if st.button("Delete Segment Truths", key=f"del_seg_truth_{seg_truth_table['id']}"):
            delete_table(seg_truth_table["id"])
            # Also delete associated images
            from app_core.media import delete_media_for_section
            delete_media_for_section(segment["id"], "Segment Truths", "Segment Truth Images")
            st.success("Segment Truths removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_zone_drilldown_dashboard(table_row: Dict, segment: Dict, is_editor: bool, zone_name: str) -> None:
    """Render zone state drill-down with state summary and brand deep-dive"""
    # Get custom title from config
    filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
    zone_display = zone_name.replace(" Zone", "").replace("+", "+")
    default_title = f"Battleground in {zone_display}"
    custom_title = filter_config.get("title", default_title) if isinstance(filter_config, dict) else default_title
    
    st.markdown(f"### {custom_title}")
    
    # Load data and apply filters
    df = load_dataset(table_row["dataset_id"])
    if df is None or df.empty:
        st.warning("Dataset not found.")
        return
    
    # Filter by segment
    df = filter_df_by_segment(df, segment)
    
    # Get filters from config
    filter_config = json.loads(table_row["filter_json"] if table_row["filter_json"] else "{}")
    selected_families = filter_config.get("brand_families", []) if isinstance(filter_config, dict) else []
    selected_brands = filter_config.get("brands", []) if isinstance(filter_config, dict) else []
    selected_states = filter_config.get("states", []) if isinstance(filter_config, dict) else []
    excluded_states = filter_config.get("excluded_states", []) if isinstance(filter_config, dict) else []
    
    # Apply state exclusion filter
    if excluded_states and "State" in df.columns:
        df = df[~df["State"].isin(excluded_states)]
        st.caption(f"🚫 Excluding {len(excluded_states)} state(s): {', '.join(excluded_states)}")
    
    # Filter for A24 and A25 (needed for growth calculations)
    df = df[df["PRI Year"].isin(["A24", "A25"])]
    
    if df.empty:
        st.warning("No data available for selected filters.")

        return
    
    # Check required columns
    if "Zone" not in df.columns or "State" not in df.columns:
        st.warning("Zone or State column not found in dataset.")

        return
    
    # Get all states in zone for summary
    df_zone = df[df["Zone"] == zone_name]
    states_in_zone = sorted(df_zone[df_zone["PRI Year"] == "A25"]["State"].dropna().unique().tolist())
    
    # Use the same function as preview - first get ALL states summary
    from app_ui.data_studio import create_zone_state_drilldown
    result_all = create_zone_state_drilldown(df, selected_families, selected_brands, states_in_zone, zone_name)
    
    if result_all is None:
        st.warning("Unable to create state drill-down.")

        return
    
    # Define colors for brand families
    family_colors = {
        0: "#E8F5E9",  # Light Green
        1: "#E3F2FD",  # Light Blue
        2: "#FFF3E0",  # Light Orange
        3: "#F3E5F5",  # Light Purple
        4: "#FCE4EC",  # Light Pink
    }
    
    # Show state summary for ALL states
    def highlight_zone_row(row):
        """Highlight the zone row"""
        state_val = result_all['state_summary'].loc[row.name, 'State']
        if state_val in ['NORTH', 'WEST+CSD', 'EAST', 'SOUTH']:
            return ['background-color: #E3F2FD; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    def color_negatives_summary(val):
        """Color negative numbers red"""
        if isinstance(val, str):
            if '-' in val or val.startswith('−'):
                return 'color: #D32F2F; font-weight: bold'
        return ''
    
    # Parse comments (could be JSON with top/bottom or just a string)
    comment_text = table_row["comment"] if table_row["comment"] else ""
    try:
        comments = json.loads(comment_text) if comment_text else {}
        top_comment = comments.get("top", "") if isinstance(comments, dict) else comment_text
        bottom_comment = comments.get("bottom", "") if isinstance(comments, dict) else ""
    except:
        top_comment = comment_text
        bottom_comment = ""
    
    # Show state summary and top comment side by side
    if top_comment:
        col1, col2 = st.columns([2, 1])
        with col1:
            summary_styled = result_all['state_summary'].style.apply(highlight_zone_row, axis=1).applymap(color_negatives_summary)
            st.dataframe(summary_styled, use_container_width=True, hide_index=True)
        with col2:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(to right, #F0F8FF 0%, #E6F3FF 100%);
                    border: 1px solid #B0D4F1;
                    border-left: 5px solid #2196F3;
                    padding: 1rem 1.2rem;
                    margin-top: 0;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                    height: 100%;
                '>
                    <div style='
                        font-size: 0.9rem;
                        line-height: 1.6;
                        color: #2C2C2C;
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    '>
                        {format_comment(top_comment)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    else:
        summary_styled = result_all['state_summary'].style.apply(highlight_zone_row, axis=1).applymap(color_negatives_summary)
        st.dataframe(summary_styled, use_container_width=True, hide_index=True)
    
    # Show state deep-dives for SELECTED states only
    if selected_states:
        result = create_zone_state_drilldown(df, selected_families, selected_brands, selected_states, zone_name)
        
        if result and result['state_details']:
            st.markdown("---")
            
            # Get states in the order they appear in state_summary (which is already sorted by salience for non-North zones)
            state_summary_df = result['state_summary']
            # Filter out the zone row (NORTH, WEST+CSD, etc.) to get just state names
            states_ordered = [s for s in state_summary_df['State'].tolist() if s not in ['NORTH', 'WEST+CSD', 'EAST', 'SOUTH']]
            
            # Display states in rows of 4
            states_per_row = 4
            for row_start in range(0, len(states_ordered), states_per_row):
                row_states = states_ordered[row_start:row_start + states_per_row]
                # Always create 4 columns for consistent alignment
                cols = st.columns(states_per_row)
                
                for idx, state in enumerate(row_states):
                    with cols[idx]:
                        if state in result['state_details']:
                            state_df = result['state_details'][state]
                            
                            # State header
                            st.markdown(f"""
                                <div style='text-align: center; padding: 0.5rem; background-color: #f0f2f6; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                                    <h3 style='margin: 0; font-size: 1.4rem;'>{state}</h3>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            # Apply styling
                            def highlight_families(row):
                                row_type = state_df.loc[row.name, 'Type']
                                if row_type == 'family':
                                    family_idx = len([i for i in state_df.index[:row.name+1] if state_df.loc[i, 'Type'] == 'family']) - 1
                                    color = family_colors[family_idx % len(family_colors)]
                                    return [f'background-color: {color}; font-weight: bold'] * len(row)
                                return [''] * len(row)
                            
                            def color_negatives(val):
                                if isinstance(val, str):
                                    if '-' in val or val.startswith('−'):
                                        return 'color: #D32F2F; font-weight: bold'
                                return ''
                            
                            # Drop Type column for display
                            display_df = state_df.drop(columns=['Type'])
                            styled_df = display_df.style.apply(highlight_families, axis=1).applymap(color_negatives)
                            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350)
                
                # Add spacing between rows if there are more states
                if row_start + states_per_row < len(selected_states):
                    st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    
    # Show bottom comment box BELOW the deep-dive tables
    if bottom_comment:
        st.markdown(f"""
            <div style='
                background: linear-gradient(to right, #FFFBF0 0%, #FFF9E6 100%);
                border: 1px solid #E8D7A0;
                border-left: 5px solid #D4A017;
                padding: 1.2rem 1.5rem;
                margin: 1.5rem 0 1rem 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            '>
                <div style='
                    font-size: 0.95rem;
                    line-height: 1.7;
                    color: #2C2C2C;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                '>
                    {format_comment(bottom_comment)}
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Delete button for editors
    if is_editor:
        if st.button(f"Delete {zone_display} Drill-Down", key=f"del_zone_{table_row['id']}"):
            delete_table(table_row["id"])
            st.success(f"{zone_display} zone drill-down removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    


def render_custom_trends_dashboard(table_row: Dict, segment: Dict, is_editor: bool) -> None:
    """Render custom trends view with title, description, and numbered sections"""
    # Parse configuration
    filter_config = json.loads(table_row["filter_json"]) if table_row["filter_json"] else {}
    trends_title = filter_config.get("title", "")
    trends_description = filter_config.get("description", "")
    sections_data = filter_config.get("sections", [])
    
    if not trends_title and not trends_description and not sections_data:
        return
    
    # Display title
    if trends_title:
        st.markdown(f"### {trends_title}")
    
    # Display main description
    if trends_description:
        formatted_desc = format_comment(trends_description)
        st.markdown(f"""
            <div style='
                background: linear-gradient(to right, #F5F5F5 0%, #EEEEEE 100%);
                border: 1px solid #CCCCCC;
                padding: 1rem 1.5rem;
                margin: 1rem 0;
                border-radius: 8px;
                text-align: center;
            '>
                <div style='font-size: 1rem; line-height: 1.6; color: #2C2C2C;'>
                    {formatted_desc}
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Display sections
    for section in sections_data:
        if section.get("left") or section.get("right"):
            cols = st.columns([0.3, 3, 3])
            
            with cols[0]:
                st.markdown(f"""
                    <div style='
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        background-color: #FFFFFF;
                        border: 3px solid #666666;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.5rem;
                        font-weight: bold;
                        color: #666666;
                        margin-top: 1rem;
                    '>
                        {section.get("number", "")}
                    </div>
                """, unsafe_allow_html=True)
            
            with cols[1]:
                if section.get("left"):
                    formatted_left = format_comment(section["left"])
                    st.markdown(f"""
                        <div style='
                            background: #E3F2FD;
                            border: 1px solid #90CAF9;
                            padding: 1rem;
                            margin: 0.5rem 0;
                            border-radius: 8px;
                        '>
                            <div style='font-size: 0.95rem; line-height: 1.6; color: #1565C0;'>
                                {formatted_left}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            
            with cols[2]:
                if section.get("right"):
                    formatted_right = format_comment(section["right"])
                    st.markdown(f"""
                        <div style='
                            background: #FFF3E0;
                            border: 1px solid #FFB74D;
                            padding: 1rem;
                            margin: 0.5rem 0;
                            border-radius: 8px;
                        '>
                            <div style='font-size: 0.95rem; line-height: 1.6; color: #E65100;'>
                                {formatted_right}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
    
    # Delete button for editors
    if is_editor:
        if st.button("Delete Custom Trends View", key=f"del_ns_custom_trends_{table_row['id']}"):
            delete_table(table_row["id"])
            st.success("Custom Trends View removed")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_segment_trends_dashboard(segment: Dict, is_editor: bool) -> None:
    """Render Segment Trends section with images and custom view"""
    from app_core.media import get_media_for_segment, delete_media_for_section
    from app_core.tables import get_tables_for_segment
    
    # Get images for this section
    media_items = get_media_for_segment(segment["id"])
    
    # Get all images (now just "Additional Images" - no more carousel)
    trend_images = [m for m in media_items if m.get("section") == "Segment Trends" and m.get("name") == "Additional Images"]
    trend_images = sorted(trend_images, key=lambda x: x.get("id", 0))
    
    # Get placeholder images
    placeholder_images = [m for m in media_items if m.get("section") == "Segment Trends" and m.get("name") == "Placeholder Images"]
    placeholder_images = sorted(placeholder_images, key=lambda x: x.get("id", 0))
    
    # Get custom trends view
    tables = get_tables_for_segment(segment["id"])
    custom_view = next((t for t in tables if t["section"] == "Segment Trends" and t["name"] == "Custom Trends View"), None)
    
    if not trend_images and not placeholder_images and not custom_view:
        st.info("No content published for Segment Trends yet. Editors can configure it in Data Studio.")
        return
    
    st.markdown("### Segment Trends")
    
    # Display all images
    if trend_images:
        for idx, media in enumerate(trend_images):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                # Display title first (outside columns)
                if title:
                    st.markdown(f"### {title}")
                
                # Image on left, comment on right
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                # Add spacing between images
                if idx < len(trend_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for images
        if is_editor:
            if st.button("Delete Segment Trends Images", key=f"del_seg_trends_{segment['id']}"):
                delete_media_for_section(segment["id"], "Segment Trends", "Additional Images")
                st.success("Segment Trends images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        
        # Add separator if there are placeholders or custom view
        if placeholder_images or custom_view:
            st.markdown("---")
    
    # Display placeholder images
    if placeholder_images:
        
        for idx, media in enumerate(placeholder_images):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                # Display title first (outside columns)
                if title:
                    st.markdown(f"### {title}")
                
                # Image on left, comment on right
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                # Add spacing between images
                if idx < len(placeholder_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for placeholder images
        if is_editor:
            if st.button("Delete Placeholder Images", key=f"del_seg_trends_placeholder_{segment['id']}"):
                delete_media_for_section(segment["id"], "Segment Trends", "Placeholder Images")
                st.success("Placeholder images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Render custom trends view if exists
    
    # Render custom trends view if exists
    if custom_view:
        st.markdown("---")
        try:
            config = json.loads(custom_view["filter_json"]) if custom_view["filter_json"] else {}
            title = config.get("title", "")
            description = config.get("description", "")
            sections = config.get("sections", [])
            
            if title:
                st.markdown(f"### {title}")
            
            if description:
                # Escape HTML and preserve line breaks
                import html
                escaped_desc = html.escape(description).replace('\n', '<br>')
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(to right, #F5F5F5 0%, #EEEEEE 100%);
                        border: 1px solid #CCCCCC;
                        padding: 1rem 1.5rem;
                        margin: 1rem 0;
                        border-radius: 8px;
                        text-align: center;
                        font-size: 1rem;
                        line-height: 1.6;
                        color: #2C2C2C;
                    '>
                        {escaped_desc}
                    </div>
                """, unsafe_allow_html=True)
            
            # Display sections
            for section in sections:
                if section.get("left") or section.get("right"):
                    cols = st.columns([0.3, 3, 3])
                    
                    with cols[0]:
                        st.markdown(f"""
                            <div style='
                                width: 60px;
                                height: 60px;
                                border-radius: 50%;
                                background-color: #FFFFFF;
                                border: 3px solid #666666;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                font-size: 1.5rem;
                                font-weight: bold;
                                color: #666666;
                                margin-top: 1rem;
                            '>
                                {section.get("number", "")}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        if section.get("left"):
                            import html
                            escaped_left = html.escape(section.get("left", "")).replace('\n', '<br>')
                            st.markdown(f"""
                                <div style='
                                    background: #E3F2FD;
                                    border: 1px solid #90CAF9;
                                    padding: 1rem;
                                    margin: 0.5rem 0;
                                    border-radius: 8px;
                                    min-height: 100px;
                                    font-size: 0.95rem;
                                    line-height: 1.6;
                                    color: #1A1A1A;
                                    font-weight: 500;
                                '>
                                    {escaped_left}
                                </div>
                            """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        if section.get("right"):
                            import html
                            escaped_right = html.escape(section.get("right", "")).replace('\n', '<br>')
                            st.markdown(f"""
                                <div style='
                                    background: #F3E5F5;
                                    border: 1px solid #CE93D8;
                                    padding: 1rem;
                                    margin: 0.5rem 0;
                                    border-radius: 8px;
                                    min-height: 100px;
                                    font-size: 0.95rem;
                                    line-height: 1.6;
                                    color: #1A1A1A;
                                    font-weight: 500;
                                '>
                                    {escaped_right}
                                </div>
                            """, unsafe_allow_html=True)
            
            # Delete button for custom view
            if is_editor:
                if st.button("Delete Custom Trends View", key=f"del_custom_trends_{segment['id']}"):
                    delete_table(custom_view["id"])
                    st.success("Custom Trends View removed")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
        except Exception as e:
            st.error(f"Error rendering custom view: {str(e)}")



def render_brand_truths_dashboard(segment: Dict, tables: List, is_editor: bool) -> None:
    """Render Brand Truths section"""
    # Get brand truths views
    brand_view = next((t for t in tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
    brand_profile_table = next((t for t in tables if t["section"] == "Brand Truths" and t["name"] == "Brand Profile Comparison"), None)
    
    # Render Brand Profile Comparison Table first (if exists)
    if brand_profile_table:
        try:
            profile_config = json.loads(brand_profile_table["filter_json"]) if brand_profile_table["filter_json"] else {}
            profile_title = profile_config.get("title", "Brand Profile Comparison")
            profile_data = profile_config.get("data", {})
            base_column = profile_config.get("base_column", "")
            
            if profile_title:
                st.markdown(f"### {profile_title}")
            
            if profile_data:
                df_profile = pd.DataFrame(profile_data)
                
                # Get all brand columns (all columns after base column)
                base_col_idx = df_profile.columns.get_loc(base_column) if base_column in df_profile.columns else 1
                brand_columns = df_profile.columns[base_col_idx + 1:].tolist()
                
                # Calculate index for ALL brand columns
                for brand_col in brand_columns:
                    def calculate_brand_index(row, base_col, compare_col):
                        """Calculate index comparing brand column to base column"""
                        try:
                            base_val = str(row[base_col]).replace("%", "").strip()
                            compare_val = str(row[compare_col]).replace("%", "").strip()
                            
                            if not base_val or not compare_val or base_val == "" or compare_val == "":
                                return None
                            
                            base_num = float(base_val)
                            compare_num = float(compare_val)
                            
                            if base_num == 0:
                                return None
                            
                            return (compare_num / base_num) * 100
                        except:
                            return None
                    
                    df_profile[f"_index_{brand_col}"] = df_profile.apply(
                        lambda row, bc=brand_col: calculate_brand_index(row, base_column, bc), 
                        axis=1
                    )
                
                # Function to apply conditional formatting to all brand columns
                def color_all_brand_columns(row):
                    """Apply background color to all brand columns based on index value"""
                    styles = [""] * len(row)
                    
                    for brand_col in brand_columns:
                        idx_val = row[f"_index_{brand_col}"]
                        
                        if idx_val is None:
                            continue
                        
                        try:
                            if idx_val > 110:
                                color = "background-color: #90EE90; font-weight: bold;"
                            elif idx_val >= 105:
                                color = "background-color: #D4EDDA; font-weight: bold;"
                            elif idx_val < 75:
                                color = "background-color: #FFB380; font-weight: bold;"
                            else:
                                color = ""
                            
                            # Apply color to the brand column
                            brand_col_idx = df_profile.columns.get_loc(brand_col)
                            styles[brand_col_idx] = color
                        except:
                            pass
                    
                    return styles
                
                # Apply styling to dataframe
                styled_df = df_profile.style.apply(color_all_brand_columns, axis=1)
                
                # Create column config to hide _index columns
                column_config = {col: None for col in df_profile.columns if col.startswith("_index_")}
                
                # Display dataframe
                st.dataframe(
                    styled_df, 
                    use_container_width=True, 
                    hide_index=True,
                    height=600,
                    column_config=column_config
                )
                
                # Delete button for editors
                if is_editor:
                    if st.button("Delete Brand Profile Table", key=f"del_brand_profile_{segment['id']}"):
                        delete_table(brand_profile_table["id"])
                        st.success("Brand Profile table removed")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
            
            st.markdown("---")
        except Exception as e:
            st.error(f"Error rendering Brand Profile table: {str(e)}")
    
    if not brand_view and not brand_profile_table:
        st.info("No content published for Brand Truths yet. Editors can configure it in Data Studio.")
        return
    
    # Render first section (without S&V)
    if brand_view:
        render_brand_truths_section(brand_view, is_editor, segment, "1", show_sv=False)
    
    # Display carousel images (BEFORE S&V and SWOT)
    from app_core.media import get_media_for_segment, delete_media_for_section
    media_items = get_media_for_segment(segment["id"])
    brand_carousel_images = [m for m in media_items if m.get("section") == "Brand Truths" and m.get("name") == "Brand Carousel"]
    brand_carousel_images = sorted(brand_carousel_images, key=lambda x: x.get("id", 0))
    
    if brand_carousel_images:
        st.markdown("---")
        
        if len(brand_carousel_images) > 1:
            # Tabs for navigation
            tab_labels = [media.get("title", f"Page {i+1}") or f"Page {i+1}" for i, media in enumerate(brand_carousel_images)]
            image_tabs = st.tabs(tab_labels)
            
            for idx, (tab, media) in enumerate(zip(image_tabs, brand_carousel_images)):
                with tab:
                    file_path = media.get("file_path")
                    combined_comment = media.get("comment", "")
                    
                    # Parse page_title and comment
                    page_title = ""
                    comment = ""
                    if combined_comment and "##PAGE_TITLE##" in combined_comment:
                        parts = combined_comment.split("##PAGE_TITLE##")
                        if len(parts) > 1:
                            remaining = parts[1]
                            if "##COMMENT##" in remaining:
                                page_parts = remaining.split("##COMMENT##")
                                page_title = page_parts[0]
                                comment = page_parts[1] if len(page_parts) > 1 else ""
                            else:
                                page_title = remaining
                    else:
                        comment = combined_comment
                    
                    if file_path and os.path.exists(file_path):
                        if page_title:
                            st.markdown(f"### {page_title}")
                        
                        if comment:
                            col_img, col_comment = st.columns([1, 1])
                            with col_img:
                                st.image(file_path, use_container_width=True)
                            with col_comment:
                                st.markdown(f"""
                                    <div style='
                                        background: #F8F9FA;
                                        border-left: 4px solid #f5b400;
                                        padding: 1.5rem;
                                        margin: 1.5rem 0 1rem 0;
                                        border-radius: 8px;
                                        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        min-height: 300px;
                                        max-height: 300px;
                                        overflow-y: auto;
                                    '>
                                        <div style='
                                            font-size: 0.95rem;
                                            line-height: 1.7;
                                            color: #2C2C2C;
                                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                        '>
                                            {format_comment(comment)}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                        else:
                            col1, col2, col3 = st.columns([0.5, 2, 0.5])
                            with col2:
                                st.image(file_path, use_container_width=True)
        elif len(brand_carousel_images) == 1:
            # Single image
            media = brand_carousel_images[0]
            file_path = media.get("file_path")
            combined_comment = media.get("comment", "")
            
            # Parse page_title and comment
            page_title = ""
            comment = ""
            if combined_comment and "##PAGE_TITLE##" in combined_comment:
                parts = combined_comment.split("##PAGE_TITLE##")
                if len(parts) > 1:
                    remaining = parts[1]
                    if "##COMMENT##" in remaining:
                        page_parts = remaining.split("##COMMENT##")
                        page_title = page_parts[0]
                        comment = page_parts[1] if len(page_parts) > 1 else ""
                    else:
                        page_title = remaining
            else:
                comment = combined_comment
            
            if file_path and os.path.exists(file_path):
                if page_title:
                    st.markdown(f"### {page_title}")
                
                if comment:
                    col_img, col_comment = st.columns([1, 1])
                    with col_img:
                        st.image(file_path, use_container_width=True)
                    with col_comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                else:
                    col1, col2, col3 = st.columns([0.5, 2, 0.5])
                    with col2:
                        st.image(file_path, use_container_width=True)
        
        # Delete button for carousel
        if is_editor:
            if st.button("Delete Carousel Images", key=f"del_brand_carousel_{segment['id']}"):
                delete_media_for_section(segment["id"], "Brand Truths", "Brand Carousel")
                st.success("Carousel images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Display standalone images (BEFORE S&V and SWOT)
    brand_standalone_images = [m for m in media_items if m.get("section") == "Brand Truths" and m.get("name") == "Standalone Images"]
    brand_standalone_images = sorted(brand_standalone_images, key=lambda x: x.get("id", 0))
    
    if brand_standalone_images:
        st.markdown("---")
        
        for idx, media in enumerate(brand_standalone_images):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                if title:
                    st.markdown(f"### {title}")
                
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                if idx < len(brand_standalone_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for standalone images
        if is_editor:
            if st.button("Delete Standalone Images", key=f"del_brand_standalone_{segment['id']}"):
                delete_media_for_section(segment["id"], "Brand Truths", "Standalone Images")
                st.success("Standalone images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Display placeholder images
    brand_placeholder_images = [m for m in media_items if m.get("section") == "Brand Truths" and m.get("name") == "Placeholder Images"]
    brand_placeholder_images = sorted(brand_placeholder_images, key=lambda x: x.get("id", 0))
    
    if brand_placeholder_images:
        st.markdown("---")
        
        for idx, media in enumerate(brand_placeholder_images):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                if title:
                    st.markdown(f"### {title}")
                
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                if idx < len(brand_placeholder_images) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for placeholder images
        if is_editor:
            if st.button("Delete Placeholder Images", key=f"del_brand_placeholder_{segment['id']}"):
                delete_media_for_section(segment["id"], "Brand Truths", "Placeholder Images")
                st.success("Placeholder images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Render S&V section at the very end (only from Section 1 config)
    if brand_view:
        try:
            config = json.loads(brand_view["filter_json"]) if brand_view["filter_json"] else {}
            sv_data = config.get("strengths_vulnerabilities", {})
            if sv_data and (sv_data.get("strength_content") or sv_data.get("vuln_content")):
                st.markdown("---")
                render_sv_section(sv_data)
            
            # Render SWOT section after S&V
            swot_data = config.get("swot_analysis", {})
            if swot_data and (swot_data.get("strengths") or swot_data.get("weaknesses") or swot_data.get("opportunities") or swot_data.get("threats")):
                st.markdown("---")
                render_swot_section(swot_data)
        except Exception as e:
            st.error(f"Error rendering S&V/SWOT: {str(e)}")


def render_brand_truths_section(brand_view: Dict, is_editor: bool, segment: Dict, section_num: str, show_sv: bool = True) -> None:
    """Render a single brand truths section"""
    
    try:
        config = json.loads(brand_view["filter_json"]) if brand_view["filter_json"] else {}
        title = config.get("title", "")
        description = config.get("description", "")
        brands = config.get("brands", [])
        
        if title:
            st.markdown(f"### {title}")
        
        if description:
            import html
            escaped_desc = html.escape(description).replace('\n', '<br>')
            st.markdown(f"""
                <div style='
                    background: linear-gradient(to right, #FFF9E6 0%, #FFF3D6 100%);
                    border: 1px solid #E8D7A0;
                    padding: 1rem 1.5rem;
                    margin: 1rem 0;
                    border-radius: 8px;
                    text-align: center;
                '>
                    <div style='font-size: 1rem; line-height: 1.6; color: #2C2C2C;'>
                        {escaped_desc}
                    </div>
                </div>
            """, unsafe_allow_html=True)
        
        # Display brand sections with intelligent layout
        total_brands = len(brands)
        
        # Only display if there are brands
        if total_brands == 0:
            st.info("No brand sections configured yet.")
        else:
            # Determine layout based on number of brands
            if total_brands <= 4:
                # 1-4: Show all in one row
                layout = [total_brands]
            elif total_brands == 5:
                # 5: 3 + 2
                layout = [3, 2]
            elif total_brands == 6:
                # 6: 3 + 3
                layout = [3, 3]
            elif total_brands == 7:
                # 7: 4 + 3
                layout = [4, 3]
            else:  # 8
                # 8: 4 + 4
                layout = [4, 4]
            
            # Display brands according to layout
            brand_idx = 0
            for row_size in layout:
                if row_size > 0:  # Safety check
                    row_brands = brands[brand_idx:brand_idx + row_size]
                    cols = st.columns(row_size)
                    brand_idx += row_size
                    
                    for idx, (col, brand) in enumerate(zip(cols, row_brands)):
                        with col:
                            # Display brand name as header
                            if brand.get("name"):
                                st.markdown(f"### {brand['name']}")
                            
                            # Display brand content
                            if brand.get("content"):
                                import html
                                escaped_content = html.escape(brand["content"]).replace('\n', '<br>')
                                st.markdown(f"""
                                    <div style='
                                        background: #F5F5F5;
                                        border: 1px solid #CCCCCC;
                                        padding: 1rem;
                                        margin: 0.5rem 0;
                                        border-radius: 8px;
                                        height: 300px;
                                        overflow-y: auto;
                                    '>
                                        <div style='font-size: 0.9rem; line-height: 1.6; color: #1A1A1A;'>
                                            {escaped_content}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
            
            # Add spacing between rows
            st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for editors
        if is_editor:
            if st.button("Delete Brand Truths", key=f"del_brand_truths_{segment['id']}_{section_num}"):
                delete_table(brand_view["id"])
                st.success("Brand Truths removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    except Exception as e:
        st.error(f"Error rendering Brand Truths: {str(e)}")


def render_sv_section(sv_data: Dict) -> None:
    """Render Strengths & Vulnerabilities section"""
    # Main title
    sv_main_title = sv_data.get("main_title", "PRI Strengths & Vulnerabilities:")
    st.markdown(f"### {sv_main_title}")
    
    # Two columns for strengths and vulnerabilities
    col_strength, col_vuln = st.columns(2)
    
    with col_strength:
        strength_title = sv_data.get("strength_title", "Brand Strengths")
        strength_content = sv_data.get("strength_content", "")
        
        if strength_content:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #E8F5E9 0%, #F1F8F4 100%);
                    border: 2px dashed #4CAF50;
                    border-radius: 15px;
                    padding: 1.5rem;
                    min-height: 300px;
                '>
                    <div style='
                        text-align: center;
                        font-size: 1.2rem;
                        font-weight: 600;
                        color: #2E7D32;
                        margin-bottom: 1rem;
                    '>{strength_title}</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #1B5E20;
                    '>{format_comment(strength_content)}</div>
                </div>
            """, unsafe_allow_html=True)
    
    with col_vuln:
        vuln_title = sv_data.get("vuln_title", "Brand Vulnerabilities")
        vuln_content = sv_data.get("vuln_content", "")
        
        if vuln_content:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #FCE4EC 0%, #F8E8EE 100%);
                    border: 2px dashed #E91E63;
                    border-radius: 15px;
                    padding: 1.5rem;
                    min-height: 300px;
                '>
                    <div style='
                        text-align: center;
                        font-size: 1.2rem;
                        font-weight: 600;
                        color: #C2185B;
                        margin-bottom: 1rem;
                    '>{vuln_title}</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #880E4F;
                    '>{format_comment(vuln_content)}</div>
                </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)


def render_swot_section(swot_data: Dict) -> None:
    """Render SWOT Analysis section with 4 quadrants"""
    # Main title
    swot_main_title = swot_data.get("main_title", "PRI Portfolio SWOT")
    st.markdown(f"### {swot_main_title}")
    
    # Container for SWOT with centered letters
    st.markdown("""
        <div style='position: relative; padding: 2rem 0;'>
    """, unsafe_allow_html=True)
    
    # Top row: Strengths and Weaknesses
    col_s, col_w = st.columns(2)
    
    with col_s:
        strengths = swot_data.get("strengths", "")
        if strengths:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #E3F2FD 0%, #BBDEFB 100%);
                    border: 3px solid #2196F3;
                    border-radius: 15px;
                    padding: 2rem;
                    height: 400px;
                    box-shadow: 0 4px 6px rgba(33, 150, 243, 0.2);
                    position: relative;
                    display: flex;
                    flex-direction: column;
                '>
                    <div style='
                        position: absolute;
                        bottom: 15px;
                        right: 15px;
                        background: #2196F3;
                        color: white;
                        width: 50px;
                        height: 50px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.8rem;
                        font-weight: 900;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                        z-index: 10;
                    '>S</div>
                    <div style='
                        text-align: center;
                        font-size: 1.5rem;
                        font-weight: 700;
                        color: #1565C0;
                        margin-bottom: 1rem;
                        letter-spacing: 1px;
                        flex-shrink: 0;
                    '>STRENGTHS</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #0D47A1;
                        overflow-y: auto;
                        flex-grow: 1;
                        padding-right: 0.5rem;
                        padding-bottom: 3rem;
                    '>
                        {format_comment(strengths)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    with col_w:
        weaknesses = swot_data.get("weaknesses", "")
        if weaknesses:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #FFF3E0 0%, #FFE0B2 100%);
                    border: 3px solid #FF9800;
                    border-radius: 15px;
                    padding: 2rem;
                    height: 400px;
                    box-shadow: 0 4px 6px rgba(255, 152, 0, 0.2);
                    position: relative;
                    display: flex;
                    flex-direction: column;
                '>
                    <div style='
                        position: absolute;
                        bottom: 15px;
                        left: 15px;
                        background: #FF9800;
                        color: white;
                        width: 50px;
                        height: 50px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.8rem;
                        font-weight: 900;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                        z-index: 10;
                    '>W</div>
                    <div style='
                        text-align: center;
                        font-size: 1.5rem;
                        font-weight: 700;
                        color: #E65100;
                        margin-bottom: 1rem;
                        letter-spacing: 1px;
                        flex-shrink: 0;
                    '>WEAKNESS</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #BF360C;
                        overflow-y: auto;
                        flex-grow: 1;
                        padding-right: 0.5rem;
                        padding-bottom: 3rem;
                    '>
                        {format_comment(weaknesses)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
    
    # Bottom row: Opportunities and Threats
    col_o, col_t = st.columns(2)
    
    with col_o:
        opportunities = swot_data.get("opportunities", "")
        if opportunities:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
                    border: 3px solid #4CAF50;
                    border-radius: 15px;
                    padding: 2rem;
                    height: 400px;
                    box-shadow: 0 4px 6px rgba(76, 175, 80, 0.2);
                    position: relative;
                    display: flex;
                    flex-direction: column;
                '>
                    <div style='
                        position: absolute;
                        bottom: 15px;
                        right: 15px;
                        background: #4CAF50;
                        color: white;
                        width: 50px;
                        height: 50px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.8rem;
                        font-weight: 900;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                        z-index: 10;
                    '>O</div>
                    <div style='
                        text-align: center;
                        font-size: 1.5rem;
                        font-weight: 700;
                        color: #2E7D32;
                        margin-bottom: 1rem;
                        letter-spacing: 1px;
                        flex-shrink: 0;
                    '>OPPORTUNITIES</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #1B5E20;
                        overflow-y: auto;
                        flex-grow: 1;
                        padding-right: 0.5rem;
                        padding-bottom: 3rem;
                    '>
                        {format_comment(opportunities)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    with col_t:
        threats = swot_data.get("threats", "")
        if threats:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(135deg, #FFEBEE 0%, #FFCDD2 100%);
                    border: 3px solid #F44336;
                    border-radius: 15px;
                    padding: 2rem;
                    height: 400px;
                    box-shadow: 0 4px 6px rgba(244, 67, 54, 0.2);
                    position: relative;
                    display: flex;
                    flex-direction: column;
                '>
                    <div style='
                        position: absolute;
                        bottom: 15px;
                        left: 15px;
                        background: #F44336;
                        color: white;
                        width: 50px;
                        height: 50px;
                        border-radius: 50%;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 1.8rem;
                        font-weight: 900;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
                        z-index: 10;
                    '>T</div>
                    <div style='
                        text-align: center;
                        font-size: 1.5rem;
                        font-weight: 700;
                        color: #C62828;
                        margin-bottom: 1rem;
                        letter-spacing: 1px;
                        flex-shrink: 0;
                    '>THREATS</div>
                    <div style='
                        font-size: 0.95rem;
                        line-height: 1.8;
                        color: #B71C1C;
                        overflow-y: auto;
                        flex-grow: 1;
                        padding-right: 0.5rem;
                        padding-bottom: 3rem;
                    '>
                        {format_comment(threats)}
                    </div>
                </div>
            """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)



def render_battlegrounds_jtbd_dashboard(segment: Dict, tables: List, is_editor: bool) -> None:
    """Render Battlegrounds JTBD section"""
    # Get JTBD view
    jtbd_view = next((t for t in tables if t["section"] == "Battlegrounds" and t["name"] == "JTBD View"), None)
    
    if not jtbd_view:
        return  # No JTBD configured
    
    try:
        config = json.loads(jtbd_view["filter_json"]) if jtbd_view["filter_json"] else {}
        title = config.get("title", "")
        tabs_data = config.get("tabs", [])
        
        # Fallback for old format (single sections array with global headers)
        if not tabs_data and config.get("sections"):
            tabs_data = [{
                "tab_name": "JTBD",
                "description": config.get("description", ""),
                "left_header": config.get("left_header", ""),
                "right_header": config.get("right_header", ""),
                "sections": config.get("sections", [])
            }]
        
        if title:
            st.markdown(f"### {title}")
        
        # Display JTBD tabs
        if len(tabs_data) > 1:
            # Multiple tabs - use tab interface
            tab_names = [tab.get("tab_name", f"Tab {i+1}") for i, tab in enumerate(tabs_data)]
            dashboard_tabs = st.tabs(tab_names)
            
            for tab_idx, dashboard_tab in enumerate(dashboard_tabs):
                with dashboard_tab:
                    tab = tabs_data[tab_idx]
                    
                    # Show tab description if exists
                    if tab.get("description"):
                        import html
                        escaped_desc = html.escape(tab["description"]).replace('\n', '<br>')
                        st.markdown(f"""
                            <div style='
                                background: #F5F5F5;
                                border: 1px solid #CCCCCC;
                                padding: 1rem 1.5rem;
                                margin: 1rem 0;
                                border-radius: 8px;
                                font-size: 1rem;
                                line-height: 1.6;
                                color: #2C2C2C;
                            '>
                                {escaped_desc}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Get headers for this tab
                    left_header = tab.get("left_header", "")
                    right_header = tab.get("right_header", "")
                    tab_sections = tab.get("sections", [])
                    
                    for section in tab_sections:
                        if section.get("left") or section.get("right"):
                            # Create a container div to hold the entire row
                            st.markdown('<div style="display: flex; gap: 0.5rem; margin-bottom: 2rem;">', unsafe_allow_html=True)
                            
                            # Create columns for label and content - wider label column
                            cols = st.columns([0.5, 4.75, 4.75])
                            
                            with cols[0]:
                                # Vertical label that stretches full height
                                st.markdown(f"""
                                    <div style='
                                        background: linear-gradient(135deg, #E8E8E8 0%, #D0D0D0 100%);
                                        border: 2px solid #999999;
                                        padding: 1rem 0.5rem;
                                        border-radius: 8px;
                                        display: flex;
                                        align-items: center;
                                        justify-content: center;
                                        writing-mode: vertical-rl;
                                        transform: rotate(180deg);
                                        font-size: 0.95rem;
                                        font-weight: 700;
                                        color: #333333;
                                        text-align: center;
                                        letter-spacing: 0.5px;
                                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                        height: 100%;
                                        min-width: 50px;
                                    '>
                                        {section.get("label", "")}
                                    </div>
                                """, unsafe_allow_html=True)
                            
                            with cols[1]:
                                # Left section with header
                                content_html = ""
                                if left_header:
                                    content_html += f"""
                                        <div style='
                                            background: linear-gradient(to right, #D0D0D0 0%, #C0C0C0 100%);
                                            padding: 0.6rem 1rem;
                                            border-radius: 8px 8px 0 0;
                                            font-weight: 700;
                                            font-size: 0.95rem;
                                            color: #1A1A1A;
                                            text-align: center;
                                            border: 1px solid #B0B0B0;
                                            border-bottom: none;
                                        '>
                                            {left_header}
                                        </div>
                                    """
                                
                                if section.get("left"):
                                    import html
                                    escaped_left = html.escape(section.get("left", "")).replace('\n', '<br>')
                                    border_radius = "0 0 8px 8px" if left_header else "8px"
                                    content_html += f"""
                                        <div style='
                                            background: #FFFFFF;
                                            border: 1px solid #CCCCCC;
                                            padding: 1.2rem;
                                            border-radius: {border_radius};
                                            min-height: 280px;
                                            font-size: 0.9rem;
                                            line-height: 1.7;
                                            color: #1A1A1A;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            {escaped_left}
                                        </div>
                                    """
                                
                                if content_html:
                                    st.markdown(content_html, unsafe_allow_html=True)
                            
                            with cols[2]:
                                # Right section with header
                                content_html = ""
                                if right_header:
                                    content_html += f"""
                                        <div style='
                                            background: linear-gradient(to right, #D0D0D0 0%, #C0C0C0 100%);
                                            padding: 0.6rem 1rem;
                                            border-radius: 8px 8px 0 0;
                                            font-weight: 700;
                                            font-size: 0.95rem;
                                            color: #1A1A1A;
                                            text-align: center;
                                            border: 1px solid #B0B0B0;
                                            border-bottom: none;
                                        '>
                                            {right_header}
                                        </div>
                                    """
                                
                                if section.get("right"):
                                    import html
                                    escaped_right = html.escape(section.get("right", "")).replace('\n', '<br>')
                                    border_radius = "0 0 8px 8px" if right_header else "8px"
                                    content_html += f"""
                                        <div style='
                                            background: #FFFFFF;
                                            border: 1px solid #CCCCCC;
                                            padding: 1.2rem;
                                            border-radius: {border_radius};
                                            min-height: 280px;
                                            font-size: 0.9rem;
                                            line-height: 1.7;
                                            color: #1A1A1A;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            {escaped_right}
                                        </div>
                                    """
                                
                                if content_html:
                                    st.markdown(content_html, unsafe_allow_html=True)
                            
                            st.markdown('</div>', unsafe_allow_html=True)
        else:
            # Single tab - display without tab interface
            tab = tabs_data[0] if tabs_data else {}
            
            # Show tab description if exists
            if tab.get("description"):
                import html
                escaped_desc = html.escape(tab["description"]).replace('\n', '<br>')
                st.markdown(f"""
                    <div style='
                        background: #F5F5F5;
                        border: 1px solid #CCCCCC;
                        padding: 1rem 1.5rem;
                        margin: 1rem 0;
                        border-radius: 8px;
                        font-size: 1rem;
                        line-height: 1.6;
                        color: #2C2C2C;
                    '>
                        {escaped_desc}
                    </div>
                """, unsafe_allow_html=True)
            
            # Get headers for this tab
            left_header = tab.get("left_header", "")
            right_header = tab.get("right_header", "")
            tab_sections = tab.get("sections", [])
            
            for section in tab_sections:
                if section.get("left") or section.get("right"):
                    # Create row with label and content - give more space to label
                    cols = st.columns([0.5, 4.75, 4.75])
                    
                    with cols[0]:
                        # Vertical label that matches content height
                        st.markdown(f"""
                            <div style='
                                background: linear-gradient(135deg, #E8E8E8 0%, #D0D0D0 100%);
                                border: 2px solid #999999;
                                padding: 1rem 0.5rem;
                                border-radius: 8px;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                writing-mode: vertical-rl;
                                transform: rotate(180deg);
                                font-size: 0.95rem;
                                font-weight: 700;
                                color: #333333;
                                text-align: center;
                                letter-spacing: 0.5px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                                min-height: 320px;
                                margin-right: 0.5rem;
                            '>
                                {section.get("label", "")}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        # Left section with header
                        if left_header:
                            st.markdown(f"""
                                <div style='
                                    background: linear-gradient(to right, #D0D0D0 0%, #C0C0C0 100%);
                                    padding: 0.6rem 1rem;
                                    border-radius: 8px 8px 0 0;
                                    font-weight: 700;
                                    font-size: 0.95rem;
                                    color: #1A1A1A;
                                    text-align: center;
                                    border: 1px solid #B0B0B0;
                                    border-bottom: none;
                                '>
                                    {left_header}
                                </div>
                            """, unsafe_allow_html=True)
                        
                        if section.get("left"):
                            import html
                            escaped_left = html.escape(section.get("left", "")).replace('\n', '<br>')
                            border_top = "0 0 8px 8px" if left_header else "8px"
                            st.markdown(f"""
                                <div style='
                                    background: #FFFFFF;
                                    border: 1px solid #CCCCCC;
                                    padding: 1.2rem;
                                    border-radius: {border_top};
                                    min-height: 280px;
                                    font-size: 0.9rem;
                                    line-height: 1.7;
                                    color: #1A1A1A;
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                '>
                                    {escaped_left}
                                </div>
                            """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        # Right section with header
                        if right_header:
                            st.markdown(f"""
                                <div style='
                                    background: linear-gradient(to right, #D0D0D0 0%, #C0C0C0 100%);
                                    padding: 0.6rem 1rem;
                                    border-radius: 8px 8px 0 0;
                                    font-weight: 700;
                                    font-size: 0.95rem;
                                    color: #1A1A1A;
                                    text-align: center;
                                    border: 1px solid #B0B0B0;
                                    border-bottom: none;
                                '>
                                    {right_header}
                                </div>
                            """, unsafe_allow_html=True)
                        
                        if section.get("right"):
                            import html
                            escaped_right = html.escape(section.get("right", "")).replace('\n', '<br>')
                            border_top = "0 0 8px 8px" if right_header else "8px"
                            st.markdown(f"""
                                <div style='
                                    background: #FFFFFF;
                                    border: 1px solid #CCCCCC;
                                    padding: 1.2rem;
                                    border-radius: {border_top};
                                    min-height: 280px;
                                    font-size: 0.9rem;
                                    line-height: 1.7;
                                    color: #1A1A1A;
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                '>
                                    {escaped_right}
                                </div>
                            """, unsafe_allow_html=True)
                    
                    # Add spacing between sections
                    st.markdown("<div style='height:1.5rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for editors
        if is_editor:
            if st.button("Delete Battlegrounds JTBD", key=f"del_jtbd_{segment['id']}"):
                delete_table(jtbd_view["id"])
                st.success("Battlegrounds JTBD removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    except Exception as e:
        st.error(f"Error rendering JTBD view: {str(e)}")


def render_brand_trends_dashboard(segment: Dict, tables: List, is_editor: bool) -> None:
    """Render Brand Trends - Multiple Custom Trends Views"""
    
    # Get media items
    from app_core.media import get_media_for_segment, delete_media_for_section
    media_items = get_media_for_segment(segment["id"])
    
    # Get standalone images
    brand_trends_standalone = [m for m in media_items if m.get("section") == "Brand Trends" and m.get("name") == "Standalone Images"]
    brand_trends_standalone = sorted(brand_trends_standalone, key=lambda x: x.get("id", 0))
    
    # Get placeholder images
    brand_trends_placeholders = [m for m in media_items if m.get("section") == "Brand Trends" and m.get("name") == "Placeholder Images"]
    brand_trends_placeholders = sorted(brand_trends_placeholders, key=lambda x: x.get("id", 0))
    
    # Get all custom trends views (View 1, View 2, etc.)
    custom_trends_views = [t for t in tables if t["section"] == "Brand Trends" and t["name"].startswith("Custom Trends View")]
    
    if not brand_trends_standalone and not brand_trends_placeholders and not custom_trends_views:
        st.info("No content published for Brand Trends yet. Editors can configure it in Data Studio.")
        return
    
    st.markdown("### Brand Trends")
    
    # Display standalone images
    if brand_trends_standalone:
        for idx, media in enumerate(brand_trends_standalone):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                if title:
                    st.markdown(f"### {title}")
                
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                if idx < len(brand_trends_standalone) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for standalone images
        if is_editor:
            if st.button("Delete Standalone Images", key=f"del_bt_standalone_{segment['id']}"):
                delete_media_for_section(segment["id"], "Brand Trends", "Standalone Images")
                st.success("Standalone images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        
        st.markdown("---")
    
    # Display placeholder images
    if brand_trends_placeholders:
        for idx, media in enumerate(brand_trends_placeholders):
            file_path = media.get("file_path")
            title = media.get("title", "")
            comment = media.get("comment", "")
            
            if file_path and os.path.exists(file_path):
                if title:
                    st.markdown(f"### {title}")
                
                col_img, col_comment = st.columns([1, 1])
                
                with col_img:
                    st.image(file_path, use_container_width=True)
                
                with col_comment:
                    if comment:
                        st.markdown(f"""
                            <div style='
                                background: #F8F9FA;
                                border-left: 4px solid #f5b400;
                                padding: 1.5rem;
                                margin: 1.5rem 0 1rem 0;
                                border-radius: 8px;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                min-height: 300px;
                                max-height: 300px;
                                overflow-y: auto;
                            '>
                                <div style='
                                    font-size: 0.95rem;
                                    line-height: 1.7;
                                    color: #2C2C2C;
                                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                '>
                                    {format_comment(comment)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                if idx < len(brand_trends_placeholders) - 1:
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        
        # Delete button for placeholder images
        if is_editor:
            if st.button("Delete Placeholder Images", key=f"del_bt_placeholder_{segment['id']}"):
                delete_media_for_section(segment["id"], "Brand Trends", "Placeholder Images")
                st.success("Placeholder images removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        
        st.markdown("---")
    
    # Display custom trends views
    if not custom_trends_views:
        return
    
    # Sort views by number (View 1, View 2, etc.)
    custom_trends_views.sort(key=lambda x: int(x["name"].replace("Custom Trends View ", "")) if x["name"].replace("Custom Trends View ", "").isdigit() else 0)
    
    # Create tabs for multiple views
    if len(custom_trends_views) == 1:
        # Single view - no tabs needed
        view = custom_trends_views[0]
        try:
            config = json.loads(view["filter_json"]) if view["filter_json"] else {}
            title = config.get("title", "")
            description = config.get("description", "")
            sections = config.get("sections", [])
            
            if title:
                st.markdown(f"### {title}")
            
            if description:
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(to right, #F5F5F5 0%, #EEEEEE 100%);
                        border: 1px solid #CCCCCC;
                        padding: 1rem 1.5rem;
                        margin: 1rem 0;
                        border-radius: 8px;
                        text-align: center;
                    '>
                        <div style='font-size: 1rem; line-height: 1.6; color: #2C2C2C;'>
                            {format_comment(description)}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            
            # Display sections
            for section in sections:
                if section.get("left") or section.get("right"):
                    cols = st.columns([0.3, 3, 3])
                    
                    with cols[0]:
                        st.markdown(f"""
                            <div style='
                                width: 60px;
                                height: 60px;
                                border-radius: 50%;
                                background-color: #FFFFFF;
                                border: 3px solid #666666;
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                font-size: 1.5rem;
                                font-weight: bold;
                                color: #666666;
                                margin-top: 1rem;
                            '>
                                {section.get("number", "")}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        if section.get("left"):
                            st.markdown(f"""
                                <div style='
                                    background: #E3F2FD;
                                    border: 1px solid #90CAF9;
                                    padding: 1rem;
                                    margin: 0.5rem 0;
                                    border-radius: 8px;
                                    min-height: 100px;
                                '>
                                    <div style='font-size: 0.95rem; line-height: 1.6; color: #1A1A1A; font-weight: 500;'>
                                        {format_comment(section["left"])}
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        if section.get("right"):
                            st.markdown(f"""
                                <div style='
                                    background: #F3E5F5;
                                    border: 1px solid #CE93D8;
                                    padding: 1rem;
                                    margin: 0.5rem 0;
                                    border-radius: 8px;
                                    min-height: 100px;
                                '>
                                    <div style='font-size: 0.95rem; line-height: 1.6; color: #1A1A1A; font-weight: 500;'>
                                        {format_comment(section["right"])}
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
            
            # Delete button for editors
            if is_editor:
                if st.button(f"Delete {view['name']}", key=f"del_brand_trends_{view['id']}_{segment['id']}"):
                    delete_table(view["id"])
                    st.success(f"{view['name']} removed")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
        except Exception as e:
            st.error(f"Error rendering {view['name']}: {str(e)}")
    else:
        # Multiple views - use tabs with custom tab titles
        tab_names = []
        for i, view in enumerate(custom_trends_views):
            config = json.loads(view["filter_json"]) if view["filter_json"] else {}
            tab_title = config.get("tab_title", f"View {i+1}")
            tab_names.append(tab_title)
        
        tabs = st.tabs(tab_names)
        
        for tab_idx, (tab, view) in enumerate(zip(tabs, custom_trends_views)):
            with tab:
                try:
                    config = json.loads(view["filter_json"]) if view["filter_json"] else {}
                    title = config.get("title", "")
                    description = config.get("description", "")
                    sections = config.get("sections", [])
                    
                    if title:
                        st.markdown(f"### {title}")
                    
                    if description:
                        st.markdown(f"""
                            <div style='
                                background: linear-gradient(to right, #F5F5F5 0%, #EEEEEE 100%);
                                border: 1px solid #CCCCCC;
                                padding: 1rem 1.5rem;
                                margin: 1rem 0;
                                border-radius: 8px;
                                text-align: center;
                            '>
                                <div style='font-size: 1rem; line-height: 1.6; color: #2C2C2C;'>
                                    {format_comment(description)}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Display sections
                    for section in sections:
                        if section.get("left") or section.get("right"):
                            cols = st.columns([0.3, 3, 3])
                            
                            with cols[0]:
                                st.markdown(f"""
                                    <div style='
                                        width: 60px;
                                        height: 60px;
                                        border-radius: 50%;
                                        background-color: #FFFFFF;
                                        border: 3px solid #666666;
                                        display: flex;
                                        align-items: center;
                                        justify-content: center;
                                        font-size: 1.5rem;
                                        font-weight: bold;
                                        color: #666666;
                                        margin-top: 1rem;
                                    '>
                                        {section.get("number", "")}
                                    </div>
                                """, unsafe_allow_html=True)
                            
                            with cols[1]:
                                if section.get("left"):
                                    st.markdown(f"""
                                        <div style='
                                            background: #E3F2FD;
                                            border: 1px solid #90CAF9;
                                            padding: 1rem;
                                            margin: 0.5rem 0;
                                            border-radius: 8px;
                                            min-height: 100px;
                                        '>
                                            <div style='font-size: 0.95rem; line-height: 1.6; color: #1A1A1A; font-weight: 500;'>
                                                {format_comment(section["left"])}
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
                            
                            with cols[2]:
                                if section.get("right"):
                                    st.markdown(f"""
                                        <div style='
                                            background: #F3E5F5;
                                            border: 1px solid #CE93D8;
                                            padding: 1rem;
                                            margin: 0.5rem 0;
                                            border-radius: 8px;
                                            min-height: 100px;
                                        '>
                                            <div style='font-size: 0.95rem; line-height: 1.6; color: #1A1A1A; font-weight: 500;'>
                                                {format_comment(section["right"])}
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
                    
                    # Delete button for editors (for each view)
                    if is_editor:
                        view_name = view["name"]
                        if st.button(f"Delete {view_name}", key=f"del_brand_trends_{view['id']}_{segment['id']}"):
                            delete_table(view["id"])
                            st.success(f"{view_name} removed")
                            if hasattr(st, "rerun"):
                                st.rerun()
                            else:
                                st.experimental_rerun()
                except Exception as e:
                    st.error(f"Error rendering {view['name']}: {str(e)}")



def get_india_geojson_url():
    """Return URL to India states GeoJSON from a public source"""
    return "https://gist.githubusercontent.com/jbrobst/56c13bbbf9d97d187fea01ca62ea5112/raw/e388c4cae20aa53cb5090210a42ebb9b765c0a36/india_states.geojson"


def normalize_state_name(state_name: str) -> str:
    """Normalize state names to match GeoJSON format"""
    state_mapping = {
        "andaman & nicobar": "Andaman & Nicobar Island",
        "andaman and nicobar": "Andaman & Nicobar Island",
        "a & n islands": "Andaman & Nicobar Island",
        "andhra pradesh": "Andhra Pradesh",
        "arunachal pradesh": "Arunanchal Pradesh",
        "assam": "Assam",
        "bihar": "Bihar",
        "chandigarh": "Chandigarh",
        "chhattisgarh": "Chhattisgarh",
        "dadra & nagar haveli": "Dadara & Nagar Havelli",
        "daman & diu": "Daman & Diu",
        "delhi": "Delhi",
        "goa": "Goa",
        "gujarat": "Gujarat",
        "haryana": "Haryana",
        "himachal pradesh": "Himachal Pradesh",
        "jammu & kashmir": "Jammu & Kashmir",
        "jammu and kashmir": "Jammu & Kashmir",
        "jharkhand": "Jharkhand",
        "karnataka": "Karnataka",
        "kerala": "Kerala",
        "ladakh": "Ladakh",
        "lakshadweep": "Lakshadweep",
        "madhya pradesh": "Madhya Pradesh",
        "maharashtra": "Maharashtra",
        "manipur": "Manipur",
        "meghalaya": "Meghalaya",
        "mizoram": "Mizoram",
        "nagaland": "Nagaland",
        "odisha": "Odisha",
        "puducherry": "Puducherry",
        "punjab": "Punjab",
        "rajasthan": "Rajasthan",
        "sikkim": "Sikkim",
        "tamil nadu": "Tamil Nadu",
        "telangana": "Telangana",
        "tripura": "Tripura",
        "uttar pradesh": "Uttar Pradesh",
        "uttarakhand": "Uttarakhand",
        "west bengal": "West Bengal",
    }
    normalized = state_name.strip().lower()
    return state_mapping.get(normalized, state_name)


def render_battlegrounds_calculations(segment: Dict, tab_config: Dict, segment_id: int, tab_idx: int = 0, is_editor: bool = False) -> None:
    """Render state performance calculations for a Battlegrounds tab"""
    
    # Get the data
    from app_core.uploads import get_uploads, load_dataset
    from app_core.tables import get_tables_for_segment
    
    uploads = get_uploads(segment_id=segment_id)
    if not uploads:
        uploads = get_uploads()
    
    if not uploads:
        return
    
    latest = sorted(uploads, key=lambda r: r["uploaded_at"], reverse=True)[0]
    df = load_dataset(latest["id"])
    
    if df is None or df.empty:
        return
    
    # Get battlegrounds config table for saving updates
    tables = get_tables_for_segment(segment_id)
    bg_config_table = next((t for t in tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
    
    # Filter by segment
    df_segment = filter_df_by_segment(df, segment)
    
    # Get states and brands from config
    selected_states = tab_config.get("states", [])
    selected_brands = tab_config.get("brands", [])
    calc_comment = tab_config.get("calc_comment", "")
    
    if not selected_states or not selected_brands:
        return
    
    # Filter for A24 and A25
    df_calc = df_segment[df_segment["PRI Year"].isin(["A24", "A25"])].copy()
    
    if df_calc.empty:
        return
    
    # Calculate All India segment metrics
    all_india_a24 = df_calc[df_calc["PRI Year"] == "A24"]["NS M INR"].sum()
    all_india_a25 = df_calc[df_calc["PRI Year"] == "A25"]["NS M INR"].sum()
    all_india_growth = ((all_india_a25 - all_india_a24) / all_india_a24 * 100) if all_india_a24 > 0 else 0
    
    # Show comment if exists
    if calc_comment:
        st.markdown(f"<div class='comment-box'>{format_comment(calc_comment)}</div>", unsafe_allow_html=True)
    
    st.markdown(f"**All India Segment Growth (A25):** {all_india_growth:+.1f}%")
    st.markdown("---")
    
    # Get custom section headers (with defaults)
    state_perf_header = tab_config.get("state_perf_header", "State Performance")
    strategic_insights_header = tab_config.get("strategic_insights_header", "Strategic Insights")
    
    # Get state-specific columns configuration
    state_columns = tab_config.get("state_columns", {})
    
    # Get custom column headings (with defaults)
    col1_heading = tab_config.get("col1_heading", "SOG")
    col2_heading = tab_config.get("col2_heading", "5Cs")
    col3_heading = tab_config.get("col3_heading", "Imagery")
    
    # Display headers
    col_states_header, col_insights_header = st.columns([1.2, 2])
    with col_states_header:
        st.markdown(f"### {state_perf_header}")
    with col_insights_header:
        st.markdown(f"### {strategic_insights_header}")
    
    # Process each state - display performance and insights side by side
    for state_idx, state in enumerate(selected_states):
        # Filter data for this state
        df_state = df_calc[df_calc["State"] == state].copy()
        
        if df_state.empty:
            continue
        
        # SEGMENT-LEVEL CALCULATIONS
        state_segment_a24 = df_state[df_state["PRI Year"] == "A24"]["NS M INR"].sum()
        state_segment_a25 = df_state[df_state["PRI Year"] == "A25"]["NS M INR"].sum()
        
        segment_ms = (state_segment_a25 / all_india_a25 * 100) if all_india_a25 > 0 else 0
        segment_growth = ((state_segment_a25 - state_segment_a24) / state_segment_a24 * 100) if state_segment_a24 > 0 else 0
        btm_status = segment_growth - all_india_growth
        
        # State card with BTM status and brand performance
        btm_color = "#4CAF50" if btm_status >= 0 else "#F44336"
        btm_bg_color = "#E8F5E9" if btm_status >= 0 else "#FFEBEE"
        
        # Create row for this state
        col_states, col_insights = st.columns([1.2, 2])
        
        with col_states:
            # State header with BTM
            st.markdown(f"""
                <div style='background-color: {btm_bg_color}; padding: 0.8rem; border-radius: 0.4rem; margin-bottom: 0.5rem; border-left: 4px solid {btm_color};'>
                    <h4 style='margin: 0; color: #333;'>{state}</h4>
                    <div style='margin-top: 0.3rem;'>
                        <span style='font-size: 0.8rem; color: #666;'>BTM vs AI: </span>
                        <span style='color: {btm_color}; font-weight: bold; font-size: 1.1rem;'>{btm_status:+.1f}%</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Build table data
            table_data = []
            
            # Segment row
            segment_growth_color = "🟢" if segment_growth >= 0 else "🔴"
            table_data.append({
                "Brand": "SEGMENT",
                "MS & Growth": f"{segment_ms:.1f}% {segment_growth_color}({segment_growth:+.1f}%)"
            })
            
            # Brand rows (up to 5)
            brand_count = 0
            for brand in selected_brands:
                if brand_count >= 5:
                    break
                    
                df_brand = df_state[df_state["Brand"] == brand].copy()
                
                if df_brand.empty:
                    continue
                
                brand_a24 = df_brand[df_brand["PRI Year"] == "A24"]["NS M INR"].sum()
                brand_a25 = df_brand[df_brand["PRI Year"] == "A25"]["NS M INR"].sum()
                
                brand_ms = (brand_a25 / state_segment_a25 * 100) if state_segment_a25 > 0 else 0
                brand_growth = ((brand_a25 - brand_a24) / brand_a24 * 100) if brand_a24 > 0 else 0
                
                brand_growth_icon = "🟢" if brand_growth >= 0 else "🔴"
                
                table_data.append({
                    "Brand": brand,
                    "MS & Growth": f"{brand_ms:.1f}% {brand_growth_icon}({brand_growth:+.1f}%)"
                })
                brand_count += 1
            
            # Display table with styling
            if table_data:
                df_display = pd.DataFrame(table_data)
                
                # Style the dataframe - highlight segment row
                def highlight_segment(row):
                    if row['Brand'] == 'SEGMENT':
                        return ['background-color: #FFF9C4; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                styled_df = df_display.style.apply(highlight_segment, axis=1)
                st.dataframe(styled_df, use_container_width=True, hide_index=True, height=min(250, (len(table_data) + 1) * 35))
        
        with col_insights:
            # Display insights for this state
            state_data = state_columns.get(state, {})
            
            if any(state_data.values()):  # If any content exists for this state
                # Create 3 columns for custom headings
                col_sog, col_5cs, col_imagery = st.columns(3)
                
                with col_sog:
                    st.markdown(f"**{col1_heading}**")
                    sog_content = state_data.get("SOG", "")
                    edited_sog = st.text_area(
                        f"{col1_heading} content",
                        value=sog_content,
                        placeholder=f"{col1_heading} insights for {state}...",
                        height=150,
                        key=f"edit_sog_{state}_{state_idx}_{tab_idx}_{segment['id']}",
                        label_visibility="collapsed"
                    )
                    
                    # Update button for SOG
                    if edited_sog != sog_content and is_editor:
                        if st.button(f"Update {col1_heading}", key=f"update_sog_{state}_{state_idx}_{tab_idx}_{segment['id']}"):
                            # Get the full config
                            from app_core.tables import get_tables_for_segment
                            existing_tables = get_tables_for_segment(segment["id"])
                            bg_config_table = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
                            
                            if bg_config_table:
                                # Load full config
                                full_config = json.loads(bg_config_table["filter_json"]) if bg_config_table["filter_json"] else {}
                                all_tabs = full_config.get("tabs", [])
                                
                                # Update this specific tab
                                if tab_idx < len(all_tabs):
                                    if "state_columns" not in all_tabs[tab_idx]:
                                        all_tabs[tab_idx]["state_columns"] = {}
                                    if state not in all_tabs[tab_idx]["state_columns"]:
                                        all_tabs[tab_idx]["state_columns"][state] = {}
                                    all_tabs[tab_idx]["state_columns"][state]["SOG"] = edited_sog
                                    
                                    # Save back to database
                                    delete_tables_for_section(segment["id"], "Battlegrounds", "Battlegrounds Config")
                                    save_table(
                                        name="Battlegrounds Config",
                                        dataset_id=bg_config_table["dataset_id"],
                                        columns=["Config"],
                                        created_by=bg_config_table["created_by"],
                                        segment_id=segment["id"],
                                        section="Battlegrounds",
                                        filter_json=json.dumps({"tabs": all_tabs}),
                                        comment=""
                                    )
                                    st.success(f"{col1_heading} updated!")
                                    if hasattr(st, "rerun"):
                                        st.rerun()
                                    else:
                                        st.experimental_rerun()
                
                with col_5cs:
                    st.markdown(f"**{col2_heading}**")
                    fivecs_content = state_data.get("5Cs", "")
                    edited_5cs = st.text_area(
                        f"{col2_heading} content",
                        value=fivecs_content,
                        placeholder=f"{col2_heading} insights for {state}...",
                        height=150,
                        key=f"edit_5cs_{state}_{state_idx}_{tab_idx}_{segment['id']}",
                        label_visibility="collapsed"
                    )
                    
                    # Update button for 5Cs
                    if edited_5cs != fivecs_content and is_editor:
                        if st.button(f"Update {col2_heading}", key=f"update_5cs_{state}_{state_idx}_{tab_idx}_{segment['id']}"):
                            from app_core.tables import get_tables_for_segment
                            existing_tables = get_tables_for_segment(segment["id"])
                            bg_config_table = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
                            
                            if bg_config_table:
                                full_config = json.loads(bg_config_table["filter_json"]) if bg_config_table["filter_json"] else {}
                                all_tabs = full_config.get("tabs", [])
                                
                                if tab_idx < len(all_tabs):
                                    if "state_columns" not in all_tabs[tab_idx]:
                                        all_tabs[tab_idx]["state_columns"] = {}
                                    if state not in all_tabs[tab_idx]["state_columns"]:
                                        all_tabs[tab_idx]["state_columns"][state] = {}
                                    all_tabs[tab_idx]["state_columns"][state]["5Cs"] = edited_5cs
                                    
                                    delete_tables_for_section(segment["id"], "Battlegrounds", "Battlegrounds Config")
                                    save_table(
                                        name="Battlegrounds Config",
                                        dataset_id=bg_config_table["dataset_id"],
                                        columns=["Config"],
                                        created_by=bg_config_table["created_by"],
                                        segment_id=segment["id"],
                                        section="Battlegrounds",
                                        filter_json=json.dumps({"tabs": all_tabs}),
                                        comment=""
                                    )
                                    st.success(f"{col2_heading} updated!")
                                    if hasattr(st, "rerun"):
                                        st.rerun()
                                    else:
                                        st.experimental_rerun()
                
                with col_imagery:
                    st.markdown(f"**{col3_heading}**")
                    imagery_content = state_data.get("Imagery", "")
                    edited_imagery = st.text_area(
                        f"{col3_heading} content",
                        value=imagery_content,
                        placeholder=f"{col3_heading} insights for {state}...",
                        height=150,
                        key=f"edit_imagery_{state}_{state_idx}_{tab_idx}_{segment['id']}",
                        label_visibility="collapsed"
                    )
                    
                    # Update button for Imagery
                    if edited_imagery != imagery_content and is_editor:
                        if st.button(f"Update {col3_heading}", key=f"update_imagery_{state}_{state_idx}_{tab_idx}_{segment['id']}"):
                            from app_core.tables import get_tables_for_segment
                            existing_tables = get_tables_for_segment(segment["id"])
                            bg_config_table = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
                            
                            if bg_config_table:
                                full_config = json.loads(bg_config_table["filter_json"]) if bg_config_table["filter_json"] else {}
                                all_tabs = full_config.get("tabs", [])
                                
                                if tab_idx < len(all_tabs):
                                    if "state_columns" not in all_tabs[tab_idx]:
                                        all_tabs[tab_idx]["state_columns"] = {}
                                    if state not in all_tabs[tab_idx]["state_columns"]:
                                        all_tabs[tab_idx]["state_columns"][state] = {}
                                    all_tabs[tab_idx]["state_columns"][state]["Imagery"] = edited_imagery
                                    
                                    delete_tables_for_section(segment["id"], "Battlegrounds", "Battlegrounds Config")
                                    save_table(
                                        name="Battlegrounds Config",
                                        dataset_id=bg_config_table["dataset_id"],
                                        columns=["Config"],
                                        created_by=bg_config_table["created_by"],
                                        segment_id=segment["id"],
                                        section="Battlegrounds",
                                        filter_json=json.dumps({"tabs": all_tabs}),
                                        comment=""
                                    )
                                    st.success(f"{col3_heading} updated!")
                                    if hasattr(st, "rerun"):
                                        st.rerun()
                                    else:
                                        st.experimental_rerun()
            else:
                st.info(f"No insights configured for {state}")
        
        # Add spacing between states
        if state_idx < len(selected_states) - 1:
            st.markdown("<div style='height: 2rem;'></div>", unsafe_allow_html=True)


def render_india_map_dashboard(tabs_config: List[Dict]) -> None:
    """Render India map showing state assignments across tabs in dashboard"""
    import plotly.graph_objects as go
    import requests
    
    # Map states to their tab assignments
    state_to_tab = {}
    
    for idx, tab in enumerate(tabs_config):
        tab_name = tab.get("name", f"Tab {idx+1}")
        states = tab.get("states", [])
        
        for state in states:
            normalized_state = normalize_state_name(state)
            state_to_tab[normalized_state] = {"tab_index": idx, "tab_name": tab_name, "original_name": state}
    
    # Create color mapping from tab configs (use custom colors if available)
    default_colors = ["#4CAF50", "#FFC107", "#F44336"]  # Green, Yellow, Red
    tab_colors = {}
    for idx, tab in enumerate(tabs_config):
        tab_colors[idx] = tab.get("color", default_colors[idx] if idx < len(default_colors) else "#808080")
    tab_colors[-1] = "#E0E0E0"  # Gray - Unassigned
    
    try:
        # Fetch GeoJSON data
        geojson_url = get_india_geojson_url()
        response = requests.get(geojson_url, timeout=5)
        india_geojson = response.json()
        
        # Prepare data for choropleth
        states_data = []
        colors_data = []
        hover_text = []
        
        for feature in india_geojson['features']:
            state_name = feature['properties'].get('ST_NM', '')
            
            if state_name in state_to_tab:
                info = state_to_tab[state_name]
                tab_idx = info['tab_index']
                tab_name = info['tab_name']
                original_name = info['original_name']
                
                states_data.append(state_name)
                colors_data.append(tab_idx)
                hover_text.append(f"{original_name}<br>Assigned to: {tab_name}")
            else:
                states_data.append(state_name)
                colors_data.append(-1)
                hover_text.append(f"{state_name}<br>Unassigned")
        
        # Create choropleth map
        fig = go.Figure(go.Choroplethmapbox(
            geojson=india_geojson,
            locations=states_data,
            z=colors_data,
            featureidkey="properties.ST_NM",
            colorscale=[
                [0, tab_colors[-1]],      # Unassigned - Gray
                [0.33, tab_colors[0]],    # Tab 1 - Green
                [0.66, tab_colors[1]],    # Tab 2 - Yellow
                [1, tab_colors[2]]        # Tab 3 - Red
            ],
            marker_opacity=0.8,
            marker_line_width=2,
            marker_line_color='white',
            text=hover_text,
            hovertemplate='%{text}<extra></extra>',
            showscale=False
        ))
        
        fig.update_layout(
            mapbox_style="carto-positron",
            mapbox_zoom=3.5,
            mapbox_center={"lat": 22, "lon": 82},
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=700,
            uirevision='constant',  # Prevents zoom changes
            mapbox=dict(
                bearing=0,
                pitch=0
            )
        )
        
        # Disable zoom and pan to keep map stable
        fig.update_layout(
            dragmode=False,
            mapbox_accesstoken=None
        )
        
        # Group states by tab for the side panel
        tab_0_states = []
        tab_1_states = []
        tab_2_states = []
        
        for idx, tab in enumerate(tabs_config):
            states = tab.get("states", [])
            if idx == 0:
                tab_0_states = states
            elif idx == 1:
                tab_1_states = states
            elif idx == 2:
                tab_2_states = states
        
        # Create two columns: map on left, state list on right
        map_col, states_col = st.columns([1.6, 1])
        
        with map_col:
            st.plotly_chart(fig, use_container_width=True)
        
        with states_col:
            st.markdown("### State Assignments")
            
            # Helper function to lighten color for background
            def lighten_color(hex_color, amount=0.9):
                """Lighten a hex color by mixing with white"""
                hex_color = hex_color.lstrip('#')
                r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
                r = int(r + (255 - r) * amount)
                g = int(g + (255 - g) * amount)
                b = int(b + (255 - b) * amount)
                return f'#{r:02x}{g:02x}{b:02x}'
            
            # Tab 1
            tab_name = tabs_config[0].get("name", "Tab 1") if len(tabs_config) > 0 else "Tab 1"
            tab_bg_color = lighten_color(tab_colors[0])
            st.markdown(f"""
                <div style='background-color: {tab_colors[0]}; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                    <h4 style='color: white; margin: 0;'>{tab_name}</h4>
                    <p style='color: white; margin: 0; font-size: 0.9rem;'>{len(tab_0_states)} states</p>
                </div>
            """, unsafe_allow_html=True)
            
            if tab_0_states:
                # Display states in 2 columns
                states_html = "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; margin-bottom: 0.5rem;'>"
                for state in sorted(tab_0_states):
                    states_html += f"<div style='background-color: {tab_bg_color}; padding: 0.3rem 0.5rem; border-radius: 0.3rem; font-size: 0.85rem; border-left: 3px solid {tab_colors[0]};'>• {state}</div>"
                states_html += "</div>"
                st.markdown(states_html, unsafe_allow_html=True)
            else:
                st.caption("No states assigned")
            
            st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
            
            # Tab 2
            tab_name = tabs_config[1].get("name", "Tab 2") if len(tabs_config) > 1 else "Tab 2"
            tab_bg_color = lighten_color(tab_colors[1])
            st.markdown(f"""
                <div style='background-color: {tab_colors[1]}; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                    <h4 style='color: white; margin: 0;'>{tab_name}</h4>
                    <p style='color: white; margin: 0; font-size: 0.9rem;'>{len(tab_1_states)} states</p>
                </div>
            """, unsafe_allow_html=True)
            
            if tab_1_states:
                # Display states in 2 columns
                states_html = "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; margin-bottom: 0.5rem;'>"
                for state in sorted(tab_1_states):
                    states_html += f"<div style='background-color: {tab_bg_color}; padding: 0.3rem 0.5rem; border-radius: 0.3rem; font-size: 0.85rem; border-left: 3px solid {tab_colors[1]};'>• {state}</div>"
                states_html += "</div>"
                st.markdown(states_html, unsafe_allow_html=True)
            else:
                st.caption("No states assigned")
            
            st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
            
            # Tab 3
            tab_name = tabs_config[2].get("name", "Tab 3") if len(tabs_config) > 2 else "Tab 3"
            tab_bg_color = lighten_color(tab_colors[2])
            st.markdown(f"""
                <div style='background-color: {tab_colors[2]}; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                    <h4 style='color: white; margin: 0;'>{tab_name}</h4>
                    <p style='color: white; margin: 0; font-size: 0.9rem;'>{len(tab_2_states)} states</p>
                </div>
            """, unsafe_allow_html=True)
            
            if tab_2_states:
                # Display states in 2 columns
                states_html = "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; margin-bottom: 0.5rem;'>"
                for state in sorted(tab_2_states):
                    states_html += f"<div style='background-color: {tab_bg_color}; padding: 0.3rem 0.5rem; border-radius: 0.3rem; font-size: 0.85rem; border-left: 3px solid {tab_colors[2]};'>• {state}</div>"
                states_html += "</div>"
                st.markdown(states_html, unsafe_allow_html=True)
            else:
                st.caption("No states assigned")
        
    except Exception as e:
        st.warning(f"Could not load India map visualization: {str(e)}")


def render_battlegrounds_dashboard(segment: Dict, tables: List, is_editor: bool) -> None:
    """Render Battlegrounds section with 3 tabs"""
    # Get battlegrounds config
    bg_config_table = next((t for t in tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
    
    if not bg_config_table:
        st.info("No content published for Battlegrounds yet. Editors can configure it in Data Studio.")
        return
    
    try:
        config = json.loads(bg_config_table["filter_json"]) if bg_config_table["filter_json"] else {}
        tabs_config = config.get("tabs", [])
        
        if not tabs_config:
            st.info("No battleground tabs configured yet.")
            return
        
        # Show India Map at the top
        st.markdown("### 📍 India Map - Battlegrounds Overview")
        render_india_map_dashboard(tabs_config)
        st.markdown("---")
        
        # Get all media for Battlegrounds
        from app_core.media import get_media_for_segment
        media_items = get_media_for_segment(segment["id"])
        bg_media = [m for m in media_items if m.get("section") == "Battlegrounds"]
        
        # Create tabs with custom names
        tab_names = [tab.get("name", f"Tab {i+1}") for i, tab in enumerate(tabs_config)]
        dashboard_tabs = st.tabs(tab_names)
        
        for idx, (tab, tab_config) in enumerate(zip(dashboard_tabs, tabs_config)):
            with tab:
                # Get images for this tab - check 'name' field (which stores the label)
                tab_images = [m for m in bg_media if m.get("name") == f"Tab {idx+1} Images"]
                
                # Find images by comment
                image_1 = None
                image_2 = None
                for img in tab_images:
                    comment = img.get("comment", "")
                    if f"Tab {idx+1} - Image 1" in comment:
                        image_1 = img
                    elif f"Tab {idx+1} - Image 2" in comment:
                        image_2 = img
                # Display Image 1 (Top) with title and comment
                if image_1:
                    file_path = image_1.get("file_path")
                    title = image_1.get("title", "")
                    # Extract actual comment (remove the "Tab X - Image 1" prefix)
                    raw_comment = image_1.get("comment", "")
                    comment = raw_comment.replace(f"Tab {idx+1} - Image 1", "").strip()
                    
                    if file_path and os.path.exists(file_path):
                        if str(file_path).lower().endswith((".ppt", ".pptx")):
                            st.caption("📄 PPT File - Download to view")
                            with open(file_path, "rb") as f:
                                st.download_button(
                                    "Download PPT",
                                    data=f.read(),
                                    file_name=os.path.basename(file_path),
                                    key=f"dl_bg_img1_{segment['id']}_{idx}",
                                )
                        else:
                            # Show title if exists
                            if title:
                                st.markdown(f"### {title}")
                            
                            # Display image and comment side by side if comment exists
                            if comment:
                                col_img, col_comment = st.columns([1, 1])
                                
                                with col_img:
                                    st.image(file_path, use_container_width=True)
                                
                                with col_comment:
                                    st.markdown(f"""
                                        <div style='
                                            background: #F8F9FA;
                                            border-left: 4px solid #f5b400;
                                            padding: 1.5rem;
                                            margin: 1.5rem 0 1rem 0;
                                            border-radius: 8px;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            <div style='
                                                font-size: 0.95rem;
                                                line-height: 1.7;
                                                color: #2C2C2C;
                                                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                            '>
                                                {format_comment(comment)}
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
                            else:
                                # No comment, center the image
                                col1, col2, col3 = st.columns([0.5, 2, 0.5])
                                with col2:
                                    st.image(file_path, use_container_width=True)
                    else:
                        st.warning("Image 1 file not found")
                
                st.markdown("---")
                
                # STATE PERFORMANCE CALCULATIONS (Between Images)
                st.markdown("### 📊 State Performance Analysis")
                render_battlegrounds_calculations(segment, tab_config, segment["id"], idx, is_editor)
                
                st.markdown("---")
                
                # Display Image 2 (Bottom) with title and comment
                if image_2:
                    file_path = image_2.get("file_path")
                    title = image_2.get("title", "")
                    # Extract actual comment (remove the "Tab X - Image 2" prefix)
                    raw_comment = image_2.get("comment", "")
                    comment = raw_comment.replace(f"Tab {idx+1} - Image 2", "").strip()
                    
                    if file_path and os.path.exists(file_path):
                        if str(file_path).lower().endswith((".ppt", ".pptx")):
                            st.caption("📄 PPT File - Download to view")
                            with open(file_path, "rb") as f:
                                st.download_button(
                                    "Download PPT",
                                    data=f.read(),
                                    file_name=os.path.basename(file_path),
                                    key=f"dl_bg_img2_{segment['id']}_{idx}",
                                )
                        else:
                            # Show title if exists
                            if title:
                                st.markdown(f"### {title}")
                            
                            # Display image and comment side by side if comment exists
                            if comment:
                                col_img, col_comment = st.columns([1, 1])
                                
                                with col_img:
                                    st.image(file_path, use_container_width=True)
                                
                                with col_comment:
                                    st.markdown(f"""
                                        <div style='
                                            background: #F8F9FA;
                                            border-left: 4px solid #f5b400;
                                            padding: 1.5rem;
                                            margin: 1.5rem 0 1rem 0;
                                            border-radius: 8px;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            <div style='
                                                font-size: 0.95rem;
                                                line-height: 1.7;
                                                color: #2C2C2C;
                                                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                                            '>
                                                {format_comment(comment)}
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
                            else:
                                # No comment, center the image
                                col1, col2, col3 = st.columns([0.5, 2, 0.5])
                                with col2:
                                    st.image(file_path, use_container_width=True)
                    else:
                        st.warning("Image 2 file not found")
        
        # JTBD Section at the end
        st.markdown("---")
        st.markdown("---")
        render_battlegrounds_jtbd_dashboard(segment, tables, is_editor)
        
        # Delete button for editors
        if is_editor:
            st.markdown("---")
            if st.button("Delete Battlegrounds Configuration", key=f"del_battlegrounds_{segment['id']}"):
                from app_core.tables import delete_table
                from app_core.media import delete_media_for_section
                
                delete_table(bg_config_table["id"])
                # Delete all battlegrounds media
                for i in range(3):
                    delete_media_for_section(segment["id"], "Battlegrounds", f"Tab {i+1} Images")
                
                st.success("Battlegrounds configuration removed")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    except Exception as e:
        st.error(f"Error rendering Battlegrounds: {str(e)}")
