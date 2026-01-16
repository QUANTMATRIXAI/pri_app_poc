import json
import os
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app_core.charts import delete_charts_for_section, get_charts_for_segment, save_chart
from app_core.constants import SECTIONS
from app_core.database import get_connection
from app_core.filters import apply_filters
from app_core.media import delete_media_for_section, save_media_upload
from app_core.tables import delete_tables_for_section, get_tables_for_segment, save_table
from app_ui.battlegrounds import render_battleground_notes_editor
from app_core.uploads import (
    delete_upload,
    get_dataset_usage,
    get_sample_dataset,
    get_upload_history,
    get_uploads,
    load_dataset,
    query_segment_filtered,
    save_upload_for_segment,
)

from .charts import plot_chart


def clean_numeric_column(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """
    Clean and convert a numeric column, handling accounting format negatives like (123.45).
    
    Args:
        df: DataFrame containing the column
        column_name: Name of the column to clean
        
    Returns:
        DataFrame with cleaned numeric column
    """
    def clean_value(val):
        """Clean individual numeric value"""
        if pd.isna(val):
            return 0
        
        # Convert to string and strip whitespace
        val_str = str(val).strip()
        
        # Handle accounting format negatives: (123.45) -> -123.45
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1].strip()
        
        # Remove currency symbols and commas
        val_str = val_str.replace('₹', '').replace('$', '').replace(',', '').strip()
        
        # Try to convert to float
        try:
            return float(val_str)
        except (ValueError, TypeError):
            return 0
    
    # Apply cleaning function
    df[column_name] = df[column_name].apply(clean_value)
    return df


def format_comment_preview(text: str) -> str:
    """Format comment text with bold, underline, italic, headings, and bullets for preview"""
    import re
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    lines = safe.splitlines()
    rendered = []
    for line in lines:
        if line.startswith("##"):
            # Heading - apply formatting to the heading text
            heading_text = line.lstrip('#').strip()
            heading_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", heading_text)
            heading_text = re.sub(r"__(.+?)__", r"<u>\1</u>", heading_text)
            heading_text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", heading_text)
            rendered.append(f"<div style='font-size:1.08rem;font-weight:700'>{heading_text}</div>")
        elif line.startswith("•") or line.strip().startswith("-"):
            # Bullet - apply formatting to the bullet content
            text_content = line.lstrip('•').lstrip('-').strip()
            text_content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text_content)
            text_content = re.sub(r"__(.+?)__", r"<u>\1</u>", text_content)
            text_content = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text_content)
            rendered.append(f"<div style='margin-left:0.6rem;'>• {text_content}</div>")
        else:
            # Regular text - apply formatting
            line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
            line = re.sub(r"__(.+?)__", r"<u>\1</u>", line)
            line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", line)
            rendered.append(line)
    return "<br>".join(rendered)


def show_formatting_tips(key_suffix: str = "") -> None:
    """Display formatting tips expander with preview"""
    with st.expander("💡 Formatting Tips", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("""
            **How to format:**
            
            - `**text**` for bold
            - `__text__` for underline
            - `*text*` for italic
            - `## text` for heading
            - `- text` for bullet
            
            **Example Input:**
            ```
            ## Key Insights
            - **PRI** growth at __15%__
            - Focus on *premium* brands
            - __Bold__ and *italic* work in bullets
            ```
            """)
        
        with col2:
            st.markdown("**Result:**")
            st.markdown("""
            <div style='background-color: #fff8df; border-left: 3px solid #f5b400; padding: 0.5rem 0.8rem; border-radius: 8px;'>
                <div style='font-size:1.08rem;font-weight:700'>Key Insights</div>
                <div style='margin-left:0.6rem;'>• <b>PRI</b> growth at <u>15%</u></div>
                <div style='margin-left:0.6rem;'>• Focus on <i>premium</i> brands</div>
                <div style='margin-left:0.6rem;'>• <u>Bold</u> and <i>italic</i> work in bullets</div>
            </div>
            """, unsafe_allow_html=True)


def normalize_dataset_year(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a numeric 'year' column exists for datasets that have 'Cal Year' or 'PRI Year' values."""
    if "year" in df.columns:
        return df
    df = df.copy()
    if "Cal Year" in df.columns:
        df["year"] = pd.to_numeric(df["Cal Year"], errors="coerce")
        return df
    if "PRI Year" in df.columns:
        pri_year_map = {"A23": 2023, "A24": 2024, "A25": 2025}
        df["year"] = df["PRI Year"].map(pri_year_map)
        return df
    return df


def render_data_upload(current_user: Dict, segment: Dict) -> None:
    st.subheader(f"Data Studio · {segment['name']}")
    st.caption(
        "Configure and publish content for this segment. Upload data using the sidebar uploader."
    )

    # Get uploaded data
    uploads = get_uploads(segment_id=segment["id"])
    using_global = False
    if not uploads:
        # fallback to latest global upload
        uploads = get_uploads()
        using_global = bool(uploads)
    
    if not uploads:
        st.info("Upload data first using the sidebar uploader to get started.")
        return

    latest = sorted(uploads, key=lambda r: r["uploaded_at"], reverse=True)[0]
    
    # Get upload path for DuckDB filtering
    upload_path = None
    with get_connection() as conn:
        row = conn.execute("SELECT data_path FROM uploads WHERE id = ?", (latest["id"],)).fetchone()
        if row:
            upload_path = row["data_path"]
    
    if not upload_path:
        st.warning("Dataset path not found.")
        return
    
    # Filter data by segment using DuckDB (much faster than loading entire dataset)
    excel_name = segment.get("excel_name", segment["name"])
    filter_column = segment.get("filter_column", "Segment_Col_1")
    years_with_a26 = ["A23", "A24", "A25", "A26"]  # Include A26 for Manufacturing Pivot
    years_without_a26 = ["A23", "A24", "A25"]  # Exclude A26 for other sections
    
    # Load data with A26 included
    df_filtered_all = query_segment_filtered(upload_path, excel_name, filter_column, years_with_a26)
    
    if df_filtered_all is None or df_filtered_all.empty:
        st.warning("Selected dataset is empty.")
        return
    
    df_filtered_all = normalize_dataset_year(df_filtered_all)
    
    # Create filtered version without A26 for other sections
    df_filtered = df_filtered_all[df_filtered_all["PRI Year"].isin(years_without_a26)].copy()
    
    # Load full dataset only when needed (for All Spirits calculations)
    df = load_dataset(latest["id"])
    if df is None or df.empty:
        df = df_filtered  # Fallback to filtered data
    else:
        df = normalize_dataset_year(df)

    # Show data info
    note = f"Using latest {'global' if using_global else 'segment'} upload: **{latest['filename']}**"
    st.info(f"{note} | Segment rows: {len(df_filtered)} | Filter: {filter_column} = '{excel_name}' | Years: {', '.join(years_without_a26)}")

    # Data preview in expander (closed by default)
    with st.expander("📊 Segment Data Preview", expanded=False):
        if df_filtered.empty:
            st.warning(f"No rows found for segment '{segment['name']}' (Excel: '{excel_name}', Column: '{filter_column}') in the uploaded data.")
        else:
            st.dataframe(df_filtered.head(200), use_container_width=True)
    
    # Show formatting tips once for all sections
    show_formatting_tips()

    # Section tabs for configuration
    st.markdown("---")
    st.markdown("### Configure Dashboard Sections")
    tabs = st.tabs(["NS Landscape", "Segment Truths", "Brand Truths", "Segment Trends", "Brand Trends", "Battlegrounds"])
    
    with tabs[0]:
        # Pass df_filtered_all (with A26) to NS Landscape for Manufacturing Pivot
        render_ns_landscape_config(segment, df_filtered_all, latest["id"], current_user)
    
    with tabs[1]:
        render_segment_truths_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[2]:
        render_brand_truths_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[3]:
        render_segment_trends_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[4]:
        render_brand_trends_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[5]:
        render_battlegrounds_config(segment, df_filtered, latest["id"], current_user)



def render_ns_landscape_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure NS Landscape: Manufacturing Pivot Table + Brand Multi-Bar Chart
    
    Note: df_filtered includes A26 data, but we filter it out for sections after Manufacturing Pivot
    """

    
    if df_filtered.empty:
        st.warning("No data available for this segment.")
        return
    
    # Check required columns
    required_cols = ["PRI Year", "Mfg Com", "Revised NS", "Brand Family", "Brand"]
    missing_cols = [col for col in required_cols if col not in df_filtered.columns]
    if missing_cols:
        st.error(f"Missing required columns: {', '.join(missing_cols)}")
        return
    
    # Load existing saved configurations
    existing_tables = get_tables_for_segment(segment["id"])
    existing_charts = get_charts_for_segment(segment["id"])
    
    # Get saved configs for each component
    saved_pivot = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "Manufacturing Pivot"), None)
    saved_chart = next((c for c in existing_charts if c["section"] == "NS Landscape" and c["name"] == "Brand Performance"), None)
    saved_zonal = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "Zonal Pivot"), None)
    saved_north = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "NORTH State Drill-Down"), None)
    saved_west = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "WEST+CSD State Drill-Down"), None)
    saved_east = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "EAST State Drill-Down"), None)
    saved_south = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "SOUTH State Drill-Down"), None)
    
    # Parse saved pivot config
    pivot_config = json.loads(saved_pivot["filter_json"]) if saved_pivot and saved_pivot["filter_json"] else {}
    saved_pivot_title = pivot_config.get("title", "NS Overview")
    saved_pivot_comment = saved_pivot["comment"] if saved_pivot else ""
    
    st.markdown("---")
    
    # 1. Manufacturing Pivot Table Configuration (uses A26 if available)
    st.markdown("### Manufacturing Co. View")
    st.caption("NS YoY Growth and CAGR by Manufacturing Company")
    
    # Editable title - pre-populated with saved value
    pivot_title = st.text_input(
        "Slide Title",
        value=saved_pivot_title,
        key=f"ns_pivot_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Year filter - automatically use all available years (including A26 for Manufacturing Pivot)
    available_years = ["A23", "A24", "A25", "A26"]
    years_in_data = [y for y in available_years if y in df_filtered["PRI Year"].unique()]
    selected_years_pivot = years_in_data  # Use all available years by default
    
    # Preview pivot
    if selected_years_pivot:
        preview_pivot = create_manufacturing_pivot(df_filtered, selected_years_pivot)
        if preview_pivot is not None:
            st.markdown("**Preview:**")
            
            # Apply styling to highlight Segment Total row
            def highlight_segment_total(row):
                """Highlight the Segment Total row with golden background"""
                mfg_com = preview_pivot.loc[row.name, 'Mfg Com']
                if mfg_com == "Segment Total":
                    return ['background-color: #FFF3CD; font-weight: bold; border-top: 3px solid #f5b400; border-bottom: 3px solid #f5b400; color: #856404'] * len(row)
                return [''] * len(row)
            
            styled_preview = preview_pivot.style.apply(highlight_segment_total, axis=1)
            st.dataframe(styled_preview, use_container_width=True, hide_index=True)
            
            # Info message below table
            st.info("📌 Data for all brands within the manufacturing company")
    
    # Comment box AFTER preview - pre-populated with saved value
    pivot_comment = st.text_area(
        "Add Comment",
        value=saved_pivot_comment,
        key=f"ns_pivot_comment_{segment['id']}",
        placeholder="Add insights or notes about the manufacturing view...",
        height=120
    )
    
    if st.button("Save Manufacturing Pivot to Dashboard", key=f"save_ns_pivot_{segment['id']}"):
        if not selected_years_pivot:
            st.error("Please select at least one year.")
        else:
            # Delete existing pivot for this section
            delete_tables_for_section(segment["id"], "NS Landscape", "Manufacturing Pivot")
            
            # Save configuration with title
            filter_config = json.dumps({
                "years": selected_years_pivot,
                "title": pivot_title
            })
            save_table(
                name="Manufacturing Pivot",
                dataset_id=dataset_id,
                columns=["Mfg Com", "PRI Year", "Revised NS"],  # Will be pivoted
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=pivot_comment
            )
            st.success("Manufacturing Pivot saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Delete button next to save
    if saved_pivot:
        if st.button("🗑️ Delete Manufacturing Pivot", key=f"delete_ns_pivot_{segment['id']}", type="secondary"):
            delete_tables_for_section(segment["id"], "NS Landscape", "Manufacturing Pivot")
            st.success("Manufacturing Pivot deleted!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    st.markdown("---")
    
    # Keep A26 data for Brand Chart, but filter it out for sections below
    df_filtered_with_a26 = df_filtered.copy()  # Keep A26 for Brand Chart
    df_filtered_no_a26 = df_filtered[df_filtered["PRI Year"] != "A26"].copy()  # Remove A26 for other sections
    
    # 2. Brand Multi-Bar Chart Configuration (uses A26 YTD)
    st.markdown("### Brand View")
    st.caption("NS YoY Growth and CAGR by Brands (includes A26 YTD)")
    
    # Parse saved chart config
    chart_config = json.loads(saved_chart["filter_json"]) if saved_chart and saved_chart["filter_json"] else {}
    saved_families = chart_config.get("brand_families", [])
    saved_brands = chart_config.get("brands", [])
    saved_excluded_states = chart_config.get("excluded_states", [])
    saved_chart_title = chart_config.get("title", "Brand Performance")
    saved_chart_comment = saved_chart["comment"] if saved_chart else ""
    
    # Editable title - pre-populated with saved value
    chart_title = st.text_input(
        "Chart Title (editable)",
        value=saved_chart_title,
        key=f"ns_chart_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Filters in 3 columns
    brand_families = sorted(df_filtered_with_a26["Brand Family"].dropna().unique().tolist())
    
    # Get all states for exclusion filter
    all_states = sorted(df_filtered_with_a26["State"].dropna().unique().tolist()) if "State" in df_filtered_with_a26.columns else []
    
    # Use saved families if available, otherwise default
    default_families = saved_families if saved_families else (brand_families[:2] if len(brand_families) > 2 else brand_families)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        selected_families = st.multiselect(
            "Select Brand Families",
            options=brand_families,
            default=default_families,
            key=f"ns_chart_families_{segment['id']}"
        )
    
    with col2:
        if selected_families:
            brands_in_families = sorted(
                df_filtered_with_a26[df_filtered_with_a26["Brand Family"].isin(selected_families)]["Brand"].dropna().unique().tolist()
            )
            # Use saved brands if available, otherwise default to all brands in selected families
            default_brands = [b for b in saved_brands if b in brands_in_families] if saved_brands else brands_in_families
            selected_brands = st.multiselect(
                "Select Brands",
                options=brands_in_families,
                default=default_brands,
                key=f"ns_chart_brands_{segment['id']}"
            )
        else:
            selected_brands = []
            st.info("Select Brand Family first")
    
    with col3:
        # Filter saved excluded states to only include those still available
        valid_excluded_states = [s for s in saved_excluded_states if s in all_states] if saved_excluded_states else []
        excluded_states = st.multiselect(
            "Select States to Exclude from Analysis",
            options=all_states,
            default=valid_excluded_states,
            key=f"ns_excluded_states_{segment['id']}",
            help="These states will be excluded from all sections below"
        )
    
    # Apply state exclusion filter
    if excluded_states and "State" in df_filtered_with_a26.columns:
        df_filtered_with_a26 = df_filtered_with_a26[~df_filtered_with_a26["State"].isin(excluded_states)].copy()
        df_filtered_no_a26 = df_filtered_no_a26[~df_filtered_no_a26["State"].isin(excluded_states)].copy()
        st.info(f"🚫 Excluding {len(excluded_states)} state(s) from all sections: {', '.join(excluded_states)}")
    
    # Keep a copy of the full segment data (all brands, after state exclusion) for MS denominator calculations
    df_full_segment = df_filtered_no_a26.copy()
    
    # Available years for Brand Chart (includes A26)
    available_years_chart = ["A23", "A24", "A25", "A26"]
    years_in_data_chart = [y for y in available_years_chart if y in df_filtered_with_a26["PRI Year"].unique()]
    has_month_col = "Month" in df_filtered_with_a26.columns
    ytd_months = ["July", "August", "September", "October"]
    
    # Preview chart
    if selected_brands:
        df_chart = df_filtered_with_a26[df_filtered_with_a26["Brand"].isin(selected_brands)]
        
        # For A26, filter to July-Oct only
        if "A26" in years_in_data_chart and has_month_col:
            df_chart_a26_ytd = df_chart[(df_chart["PRI Year"] == "A26") & (df_chart["Month"].isin(ytd_months))]
            df_chart_full_years = df_chart[df_chart["PRI Year"].isin(["A23", "A24", "A25"])]
            df_chart = pd.concat([df_chart_full_years, df_chart_a26_ytd], ignore_index=True)
        else:
            df_chart = df_chart[df_chart["PRI Year"].isin(["A23", "A24", "A25"])]
        
        if not df_chart.empty:
            st.markdown("**Preview:**")
            # Ensure Revised NS is numeric
            df_chart = clean_numeric_column(df_chart, "Revised NS")
            
            # Create data for chart - aggregate NS by Brand and Year
            chart_data = df_chart.groupby(["Brand", "Brand Family", "PRI Year"])["Revised NS"].sum().reset_index()
            
            # Create pivot to calculate growth rates
            pivot_wide = chart_data.pivot_table(
                index=["Brand", "Brand Family"],
                columns="PRI Year",
                values="Revised NS",
                aggfunc="sum"
            ).reset_index()
            
            # Calculate growth rates and CAGR for each brand
            growth_rates = {}
            cagr_values = {}
            a26_ytd_growth_rates = {}
            
            for _, row in pivot_wide.iterrows():
                brand = row["Brand"]
                ns_a23 = row.get("A23", 0) or 0
                ns_a24 = row.get("A24", 0) or 0
                ns_a25 = row.get("A25", 0) or 0
                ns_a26_ytd = row.get("A26", 0) or 0  # This is YTD (July-Oct)
                
                # A24 Growth % (YoY from A23)
                a24_growth = ((ns_a24 - ns_a23) / ns_a23 * 100) if ns_a23 != 0 else 0
                
                # A25 Growth % (YoY from A24)
                a25_growth = ((ns_a25 - ns_a24) / ns_a24 * 100) if ns_a24 != 0 else 0
                
                # 2-Year CAGR (A23 to A25)
                cagr_2yr = (((ns_a25 / ns_a23) ** 0.5) - 1) * 100 if ns_a23 != 0 else 0
                
                # A26 YTD Growth % (July-Oct A26 vs July-Oct A25)
                if "A26" in years_in_data_chart and has_month_col:
                    # Get A25 YTD (July-Oct) for comparison
                    a25_ytd_data = df_chart[(df_chart["Brand"] == brand) & (df_chart["PRI Year"] == "A25") & (df_chart["Month"].isin(ytd_months))]
                    ns_a25_ytd = a25_ytd_data["Revised NS"].sum() if not a25_ytd_data.empty else 0
                    
                    a26_ytd_growth = ((ns_a26_ytd - ns_a25_ytd) / ns_a25_ytd * 100) if ns_a25_ytd != 0 else 0
                    a26_ytd_growth_rates[brand] = round(a26_ytd_growth, 1)
                
                growth_rates[brand] = {
                    "A23": None,  # No growth for base year - don't show anything
                    "A24": round(a24_growth, 1),
                    "A25": round(a25_growth, 1),
                    "A26": a26_ytd_growth_rates.get(brand, None)  # YTD growth
                }
                cagr_values[brand] = round(cagr_2yr, 1)
            
            # Add growth rate text - empty for A23 (no growth rate for base year)
            chart_data["Growth Text"] = chart_data.apply(
                lambda r: f"{growth_rates[r['Brand']][r['PRI Year']]:.1f}%" if r['PRI Year'] != 'A23' and growth_rates[r['Brand']][r['PRI Year']] is not None else "",
                axis=1
            )
            
            # Sort brands by Brand Family total NS, then by brand total NS (excluding A26 from sorting)
            chart_data_no_a26 = chart_data[chart_data["PRI Year"] != "A26"].copy()
            brand_totals = chart_data_no_a26.groupby(["Brand", "Brand Family"])["Revised NS"].sum().reset_index()
            brand_totals.columns = ["Brand", "Brand Family", "Total"]
            
            family_totals = brand_totals.groupby("Brand Family")["Total"].sum().reset_index()
            family_totals.columns = ["Brand Family", "Family Total"]
            family_totals = family_totals.sort_values("Family Total", ascending=False)
            
            brand_totals = brand_totals.merge(family_totals, on="Brand Family")
            brand_totals = brand_totals.sort_values(["Family Total", "Total"], ascending=[False, False])
            
            # Create ordered brand list
            brand_order = brand_totals["Brand"].tolist()
            
            # Use Plotly Graph Objects for pattern control
            import plotly.graph_objects as go
            
            # Green color scheme + Gray for A26
            color_map = {
                "A23": "#90EE90",  # Light Green
                "A24": "#4CAF50",  # Medium Green
                "A25": "#1B5E20",  # Dark Green
                "A26": "#9E9E9E"   # Gray for A26 YTD
            }
            
            # Year order for chart (includes A26)
            year_order = ["A23", "A24", "A25", "A26"]
            
            # Create figure with Graph Objects
            fig = go.Figure()
            
            # Add bars for each year
            for year in year_order:
                year_data = chart_data[chart_data["PRI Year"] == year]
                
                # Create growth text for this year
                growth_text = []
                for _, row in year_data.iterrows():
                    brand = row["Brand"]
                    growth = growth_rates.get(brand, {}).get(year)
                    if growth is not None:
                        growth_text.append(f"{growth:.1f}%")
                    else:
                        growth_text.append("")
                
                # Add pattern for A26 (diagonal stripes)
                if year == "A26":
                    fig.add_trace(go.Bar(
                        name="A26 YTD",
                        x=[brand_order.index(b) if b in brand_order else len(brand_order) for b in year_data["Brand"]],
                        y=year_data["Revised NS"],
                        text=growth_text,
                        textposition='outside',
                        textfont=dict(size=11, family="Arial Black", color="#2E7D32"),
                        marker=dict(
                            color=color_map[year],
                            pattern=dict(
                                shape="/",
                                bgcolor=color_map[year],
                                fgcolor="white",
                                size=8,
                                solidity=0.3
                            )
                        ),
                        customdata=year_data["Brand"]
                    ))
                else:
                    fig.add_trace(go.Bar(
                        name=year,
                        x=[brand_order.index(b) if b in brand_order else len(brand_order) for b in year_data["Brand"]],
                        y=year_data["Revised NS"],
                        text=growth_text,
                        textposition='outside',
                        textfont=dict(size=11, family="Arial Black", color="#2E7D32"),
                        marker=dict(color=color_map[year]),
                        customdata=year_data["Brand"]
                    ))
            
            # Get max Y value for positioning CAGR boxes
            max_y = chart_data["Revised NS"].max()
            
            # Add CAGR boxes above each brand with neutral styling
            annotations = []
            for i, brand in enumerate(brand_order):
                cagr = cagr_values[brand]
                
                annotations.append(dict(
                    x=i,
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
                barmode='group',
                xaxis=dict(
                    title="Brand",
                    tickmode='array',
                    tickvals=list(range(len(brand_order))),
                    ticktext=brand_order
                ),
                yaxis=dict(
                    title="NS",
                    range=[0, max_y * 1.25]  # Extend Y-axis to fit CAGR boxes
                ),
                legend_title="PRI Year",
                annotations=annotations,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Show data table with growth rates in expander (same as dashboard)
            with st.expander("📊 View Data"):
                st.info("📌 Data for selected brands only")
                
                # Calculate All India growth rates for BTM calculation
                ai_a23 = df_chart[df_chart["PRI Year"] == "A23"]["Revised NS"].sum()
                ai_a24 = df_chart[df_chart["PRI Year"] == "A24"]["Revised NS"].sum()
                ai_a25 = df_chart[df_chart["PRI Year"] == "A25"]["Revised NS"].sum()
                
                ai_a25_growth = ((ai_a25 - ai_a24) / ai_a24 * 100) if ai_a24 > 0 else 0
                
                # Calculate All India A26 YTD growth if available
                if "A26" in years_in_data_chart and has_month_col:
                    ai_a25_ytd = df_chart[(df_chart["PRI Year"] == "A25") & (df_chart["Month"].isin(ytd_months))]["Revised NS"].sum()
                    ai_a26_ytd = df_chart[(df_chart["PRI Year"] == "A26") & (df_chart["Month"].isin(ytd_months))]["Revised NS"].sum()
                    ai_a26_ytd_growth = ((ai_a26_ytd - ai_a25_ytd) / ai_a25_ytd * 100) if ai_a25_ytd > 0 else 0
                else:
                    ai_a26_ytd_growth = 0
                
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
                
                # Add A25 BTM
                summary_df["A25 BTM"] = summary_df.apply(
                    lambda r: round(r["A25 Growth %"] - ai_a25_growth, 1),
                    axis=1
                )
                
                # Add A26 YTD Growth %* if A26 data exists
                if "A26" in years_in_data_chart and has_month_col:
                    summary_df["A26 YTD Growth %*"] = summary_df.apply(
                        lambda r: a26_ytd_growth_rates.get(r["Brand"], 0.0),
                        axis=1
                    )
                    # Add A26 YTD BTM
                    summary_df["A26 YTD BTM*"] = summary_df.apply(
                        lambda r: round(a26_ytd_growth_rates.get(r["Brand"], 0.0) - ai_a26_ytd_growth, 1),
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
                    a26_ytd_total = family_data["A26"].sum() if "A26" in family_data.columns else 0
                    
                    # Calculate family-level growth rates
                    a24_growth = ((a24_total - a23_total) / a23_total * 100) if a23_total != 0 else 0
                    a25_growth = ((a25_total - a24_total) / a24_total * 100) if a24_total != 0 else 0
                    cagr_2yr = (((a25_total / a23_total) ** 0.5 - 1) * 100) if a23_total != 0 else 0
                    
                    # A26 YTD Growth for family
                    if "A26" in years_in_data_chart and has_month_col:
                        # Get A25 YTD for family
                        family_brands = family_data["Brand"].tolist()
                        a25_ytd_family = df_chart[(df_chart["Brand"].isin(family_brands)) & (df_chart["PRI Year"] == "A25") & (df_chart["Month"].isin(ytd_months))]["Revised NS"].sum()
                        a26_ytd_growth_family = ((a26_ytd_total - a25_ytd_family) / a25_ytd_family * 100) if a25_ytd_family != 0 else 0
                    else:
                        a26_ytd_growth_family = 0.0
                    
                    family_row = {
                        "Brand Family": family,
                        "Brand": f"📊 {family} Total",
                        "A23": a23_total,
                        "A24": a24_total,
                        "A25": a25_total,
                        "A24 Growth %": round(a24_growth, 1),
                        "A25 Growth %": round(a25_growth, 1),
                        "2-Yr CAGR %": round(cagr_2yr, 1),
                        "A25 BTM": round(a25_growth - ai_a25_growth, 1),
                        "is_family_total": True
                    }
                    
                    if "A26" in years_in_data_chart and has_month_col:
                        family_row["A26"] = a26_ytd_total
                        family_row["A26 YTD Growth %*"] = round(a26_ytd_growth_family, 1)
                        family_row["A26 YTD BTM*"] = round(a26_ytd_growth_family - ai_a26_ytd_growth, 1)
                    
                    family_summary.append(family_row)
                
                # Add is_family_total flag to brand rows
                summary_df["is_family_total"] = False
                
                # Combine family totals with brand data
                family_df = pd.DataFrame(family_summary)
                combined_df = pd.concat([family_df, summary_df], ignore_index=True)
                
                # Sort brand families by A25 NS (biggest first), then by is_family_total (True first), then by Brand
                # First, create a family order based on A25 totals
                family_order = family_df.sort_values("A25", ascending=False)["Brand Family"].tolist()
                combined_df["family_order"] = combined_df["Brand Family"].map({fam: idx for idx, fam in enumerate(family_order)})
                
                combined_df = combined_df.sort_values(
                    by=["family_order", "is_family_total", "Brand"],
                    ascending=[True, False, True]
                ).reset_index(drop=True)
                
                # Drop the helper column
                combined_df = combined_df.drop(columns=["family_order"])
                
                # Rename NS columns to include "NS M INR"
                rename_map = {}
                if "A23" in combined_df.columns:
                    rename_map["A23"] = "A23 NS"
                if "A24" in combined_df.columns:
                    rename_map["A24"] = "A24 NS"
                if "A25" in combined_df.columns:
                    rename_map["A25"] = "A25 NS"
                
                combined_df = combined_df.rename(columns=rename_map)
                
                # Add A26 YTD columns if available
                if "A26" in combined_df.columns:
                    combined_df = combined_df.rename(columns={"A26": "A26 YTD NS"})
                
                # Reorder columns - specific order requested
                column_order = ["Brand Family", "Brand"]
                if "A23 NS" in combined_df.columns:
                    column_order.append("A23 NS")
                if "A24 NS" in combined_df.columns:
                    column_order.append("A24 NS")
                if "A25 NS" in combined_df.columns:
                    column_order.append("A25 NS")
                if "A26 YTD NS" in combined_df.columns:
                    column_order.append("A26 YTD NS")
                if "A24 Growth %" in combined_df.columns:
                    column_order.append("A24 Growth %")
                if "A25 Growth %" in combined_df.columns:
                    column_order.append("A25 Growth %")
                if "A26 YTD Growth %*" in combined_df.columns:
                    column_order.append("A26 YTD Growth %*")
                column_order.append("2-Yr CAGR %")
                if "A25 BTM" in combined_df.columns:
                    column_order.append("A25 BTM")
                if "A26 YTD BTM*" in combined_df.columns:
                    column_order.append("A26 YTD BTM*")
                
                # Select and display columns
                display_df = combined_df[column_order].copy()
                
                # Format NS columns with commas
                for col in ["A23 NS", "A24 NS", "A25 NS", "A26 YTD NS"]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(lambda x: f"{int(x):,}" if pd.notna(x) and x > 0 else "0")
                
                # Format growth and BTM columns with % symbol
                for col in ["A24 Growth %", "A25 Growth %", "2-Yr CAGR %", "A25 BTM", "A26 YTD Growth %*", "A26 YTD BTM*"]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) and "BTM" in col else f"{x:.1f}%" if pd.notna(x) else "0.0%")
                
                # Apply styling to highlight family totals
                def highlight_family_totals(row):
                    if combined_df.loc[row.name, "is_family_total"]:
                        return ['background-color: #E8F5E9; font-weight: bold; border-top: 2px solid #4CAF50; border-bottom: 1px solid #4CAF50'] * len(row)
                    return [''] * len(row)
                
                styled_table = display_df.style.apply(highlight_family_totals, axis=1)
                st.dataframe(styled_table, use_container_width=True, hide_index=True, height=400)
    
    # Comment box AFTER chart preview - pre-populated with saved value
    chart_comment = st.text_area(
        "Add Comment",
        value=saved_chart_comment,
        key=f"ns_chart_comment_{segment['id']}",
        placeholder="Add insights about brand performance...",
        height=120
    )
    
    if st.button("Save Chart to Dashboard", key=f"save_ns_chart_{segment['id']}"):
        if not selected_families or not selected_brands:
            st.error("Please select Brand Families and at least one Brand.")
        else:
            # Delete existing chart for this section
            delete_charts_for_section(segment["id"], "NS Landscape", "Brand Performance")
            
            # Save configuration with title
            filter_config = json.dumps({
                "brand_families": selected_families,
                "brands": selected_brands,
                "excluded_states": excluded_states,
                "years": years_in_data,
                "title": chart_title
            })
            save_chart(
                name="Brand Performance",
                chart_type="bar",
                x_col="Brand",
                y_cols=["Revised NS"],
                dataset_id=dataset_id,
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=chart_comment
            )
            st.success("Brand Performance Chart saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Delete button next to save
    if saved_chart:
        if st.button("🗑️ Delete Brand Performance Chart", key=f"delete_ns_chart_{segment['id']}", type="secondary"):
            delete_charts_for_section(segment["id"], "NS Landscape", "Brand Performance")
            st.success("Brand Performance Chart deleted!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    st.markdown("---")
    
    # From this point forward, all sections use df_filtered without A26
    df_filtered = df_filtered_no_a26
    
    # Brand View: Key Competitors Configuration
    st.markdown("### Brand View: Key Competitors")
    st.caption("NS YoY Growth and CAGR for Key Competitor Brand Families")
    
    # Load existing saved chart
    existing_charts = get_charts_for_segment(segment["id"])
    saved_family_chart = next((c for c in existing_charts if c["section"] == "NS Landscape" and c["name"] == "Brand Family Performance"), None)
    saved_family_comment = saved_family_chart["comment"] if saved_family_chart else ""
    
    # Parse saved config
    if saved_family_chart and saved_family_chart["filter_json"]:
        family_config = json.loads(saved_family_chart["filter_json"])
        saved_family_families = family_config.get("brand_families", [])
        saved_family_brands = family_config.get("brands", [])
        saved_family_title = family_config.get("title", "Brand Performance: Key Competitors")
    else:
        saved_family_families = []
        saved_family_brands = []
        saved_family_title = "Brand Performance: Key Competitors"
    
    # Editable title - pre-populated with saved value
    family_chart_title = st.text_input(
        "Chart Title (editable)",
        value=saved_family_title,
        key=f"ns_family_chart_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Show available options from Section 2
    if not selected_families or not selected_brands:
        st.warning("⚠️ Please configure Section 2 (Brand Performance Chart) first to select Brand Families and Brands.")
        selected_families_family = []
        selected_brands_family = []
    else:
        st.info(f"📌 Available from Section 2: {len(selected_families)} Brand Families, {len(selected_brands)} Brands")
        
        # Brand Family filter (only show families from Section 2)
        st.markdown("**Select Key Competitor Brand Families**")
        selected_families_family = st.multiselect(
            "Brand Families",
            options=sorted(selected_families),
            default=[f for f in saved_family_families if f in selected_families] if saved_family_families else selected_families,
            key=f"family_chart_families_{segment['id']}",
            label_visibility="collapsed"
        )
        
        # Brand filter (only show brands from Section 2, filtered by selected families)
        if selected_families_family:
            # Filter brands that belong to selected families
            df_temp = df_filtered_no_a26[df_filtered_no_a26["Brand Family"].isin(selected_families_family)]
            available_brands_family = [b for b in selected_brands if b in df_temp["Brand"].unique()]
            
            st.markdown("**Select Brands to include:**")
            selected_brands_family = st.multiselect(
                "Brands",
                options=sorted(available_brands_family),
                default=[b for b in saved_family_brands if b in available_brands_family] if saved_family_brands else available_brands_family,
                key=f"family_chart_brands_{segment['id']}",
                label_visibility="collapsed"
            )
        else:
            selected_brands_family = []
            st.warning("Please select at least one Brand Family first.")
    
    # Preview chart if brands are selected
    if selected_brands_family:
        # Include A26 data for Brand Family chart
        df_family_chart_with_a26 = df_filtered_with_a26[df_filtered_with_a26["Brand"].isin(selected_brands_family)]
        
        # For A26, filter to July-Oct only
        if "A26" in years_in_data_chart and has_month_col:
            df_family_a26_ytd = df_family_chart_with_a26[(df_family_chart_with_a26["PRI Year"] == "A26") & (df_family_chart_with_a26["Month"].isin(ytd_months))]
            df_family_full_years = df_family_chart_with_a26[df_family_chart_with_a26["PRI Year"].isin(["A23", "A24", "A25"])]
            df_family_chart = pd.concat([df_family_full_years, df_family_a26_ytd], ignore_index=True)
        else:
            df_family_chart = df_family_chart_with_a26[df_family_chart_with_a26["PRI Year"].isin(["A23", "A24", "A25"])]
        
        # Apply state exclusion from Section 2
        if excluded_states and "State" in df_family_chart.columns:
            df_family_chart = df_family_chart[~df_family_chart["State"].isin(excluded_states)]
            st.caption(f"🚫 Using Section 2 state exclusions: {len(excluded_states)} state(s)")
        
        if not df_family_chart.empty:
            st.markdown("**Preview:**")
            # Ensure Revised NS is numeric
            df_family_chart = clean_numeric_column(df_family_chart, "Revised NS")
            
            # Aggregate by Brand Family and Year
            family_chart_data = df_family_chart.groupby(["Brand Family", "PRI Year"])["Revised NS"].sum().reset_index()
            
            # Create pivot to calculate growth rates and CAGR
            family_pivot = family_chart_data.pivot_table(
                index="Brand Family",
                columns="PRI Year",
                values="Revised NS",
                aggfunc="sum"
            ).reset_index()
            
            # Calculate growth rates and CAGR for each family
            family_growth_rates = {}
            family_cagr_values = {}
            for _, row in family_pivot.iterrows():
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
                
                family_growth_rates[family] = {
                    "A23": None,
                    "A24": round(a24_growth, 1),
                    "A25": round(a25_growth, 1),
                    "A26": None  # No growth text for A26
                }
                family_cagr_values[family] = round(cagr_2yr, 1)
            
            # Sort families by total NS (A23-A25 only for sorting)
            family_chart_no_a26 = family_chart_data[family_chart_data["PRI Year"] != "A26"].copy()
            family_totals = family_chart_no_a26.groupby("Brand Family")["Revised NS"].sum().reset_index()
            family_totals.columns = ["Brand Family", "Total"]
            family_totals = family_totals.sort_values("Total", ascending=False)
            family_order = family_totals["Brand Family"].tolist()
            
            # Green color scheme + Gray for A26
            color_map = {
                "A23": "#90EE90",
                "A24": "#4CAF50",
                "A25": "#1B5E20",
                "A26": "#9E9E9E"
            }
            
            # Use Plotly Graph Objects for pattern control
            import plotly.graph_objects as go
            
            # Create figure
            fig = go.Figure()
            
            # Add bars for each year
            year_order = ["A23", "A24", "A25", "A26"]
            for year in year_order:
                year_data = family_chart_data[family_chart_data["PRI Year"] == year]
                
                # Create growth text for this year
                growth_text = []
                for _, row in year_data.iterrows():
                    family = row["Brand Family"]
                    growth = family_growth_rates.get(family, {}).get(year)
                    if growth is not None:
                        growth_text.append(f"{growth:.1f}%")
                    else:
                        growth_text.append("")
                
                # Add pattern for A26 (diagonal stripes)
                if year == "A26":
                    fig.add_trace(go.Bar(
                        name="A26 YTD",
                        x=[family_order.index(f) if f in family_order else len(family_order) for f in year_data["Brand Family"]],
                        y=year_data["Revised NS"],
                        text=growth_text,
                        textposition='outside',
                        textfont=dict(size=11, family="Arial Black", color="#2E7D32"),
                        marker=dict(
                            color=color_map[year],
                            pattern=dict(
                                shape="/",
                                bgcolor=color_map[year],
                                fgcolor="white",
                                size=8,
                                solidity=0.3
                            )
                        ),
                        customdata=year_data["Brand Family"]
                    ))
                else:
                    fig.add_trace(go.Bar(
                        name=year,
                        x=[family_order.index(f) if f in family_order else len(family_order) for f in year_data["Brand Family"]],
                        y=year_data["Revised NS"],
                        text=growth_text,
                        textposition='outside',
                        textfont=dict(size=11, family="Arial Black", color="#2E7D32"),
                        marker=dict(color=color_map[year]),
                        customdata=year_data["Brand Family"]
                    ))
            
            # Get max Y value for positioning CAGR boxes
            max_y = family_chart_data["Revised NS"].max()
            
            # Add CAGR boxes above each brand family
            annotations = []
            for i, family in enumerate(family_order):
                cagr = family_cagr_values[family]
                
                annotations.append(dict(
                    x=i,
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
                barmode='group',
                xaxis=dict(
                    title="Brand Family",
                    tickmode='array',
                    tickvals=list(range(len(family_order))),
                    ticktext=family_order
                ),
                yaxis=dict(
                    title="NS",
                    range=[0, max_y * 1.25]
                ),
                legend_title="PRI Year",
                annotations=annotations,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Comment box for family chart
    family_chart_comment = st.text_area(
        "Add comment for Brand Family chart (optional)",
        value=saved_family_comment,
        key=f"ns_family_chart_comment_{segment['id']}",
        placeholder="Add insights about brand family performance...",
        height=120
    )
    
    if st.button("Save Chart to Dashboard", key=f"save_family_chart_{segment['id']}"):
        if not selected_families_family or not selected_brands_family:
            st.error("Please select Brand Families and Brands.")
        else:
            # Delete existing chart
            delete_charts_for_section(segment["id"], "NS Landscape", "Brand Family Performance")
            
            # Save configuration with Section 2.5 filters (use Section 2 state exclusions)
            filter_config = json.dumps({
                "brand_families": selected_families_family,
                "brands": selected_brands_family,
                "excluded_states": excluded_states,  # Use Section 2 state exclusions
                "years": years_in_data,
                "title": family_chart_title
            })
            save_chart(
                name="Brand Family Performance",
                chart_type="bar",
                x_col="Brand Family",
                y_cols=["Revised NS"],
                dataset_id=dataset_id,
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=family_chart_comment
            )
            st.success("Brand Family Performance Chart saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Delete button next to save
    if saved_family_chart:
        if st.button("🗑️ Delete Brand Family Performance Chart", key=f"delete_ns_family_chart_{segment['id']}", type="secondary"):
            delete_charts_for_section(segment["id"], "NS Landscape", "Brand Family Performance")
            st.success("Brand Family Performance Chart deleted!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    st.markdown("---")
    # 3. Zonal Pivot Table Configuration
    st.markdown("### Zonal View")
    st.caption("Market share, salience, growth rates and BTM for each zone")
    
    # Parse saved zonal config
    zonal_config = json.loads(saved_zonal["filter_json"]) if saved_zonal and saved_zonal["filter_json"] else {}
    saved_zonal_title = zonal_config.get("title", "NS Zonal View")
    saved_zonal_comment = saved_zonal["comment"] if saved_zonal else ""
    
    # Editable title - pre-populated with saved value
    zonal_title = st.text_input(
        "Slide Title",
        value=saved_zonal_title,
        key=f"ns_zonal_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Use same brand families and brands from chart
    if selected_families and selected_brands:
        # Check if Zone column exists
        if "Zone" not in df_filtered.columns:
            st.warning("Zone column not found in dataset. This table requires a 'Zone' column.")
        else:
            # Filter data for A24, A25, and A26 (needed for growth calculations)
            # Use df_filtered_with_a26 which has A26 data
            # IMPORTANT: Pass ALL brands in segment (don't filter yet) so MS calculation is correct
            df_zonal = df_filtered_with_a26[df_filtered_with_a26["PRI Year"].isin(["A24", "A25", "A26"])].copy()
            
            if not df_zonal.empty:
                # Preview zonal table (function will filter to selected brands internally)
                preview_zonal = create_zonal_pivot(df_zonal, selected_families, selected_brands)
                if preview_zonal is not None:
                    st.markdown("**Preview:**")
                    
                    # Get zones
                    zones_unsorted = preview_zonal.attrs.get('zones', [])
                    segment_growth = preview_zonal.attrs.get('segment_growth', {})
                    pw_salience = preview_zonal.attrs.get('pw_salience', {})
                    
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
                            
                            # Filter rows for this zone - reorder columns: MS|Sal, A25 Gr, A26 YTD Gr*, A25 BTM, A26 YTD BTM*
                            zone_df = preview_zonal[["Brand", "Type", f"{zone}_MS", f"{zone}_Gr", f"{zone}_A26YTD", f"{zone}_BTM", f"{zone}_A26YTD_BTM"]].copy()
                            
                            # Apply styling to highlight brand families and mfg companies
                            def highlight_families(row):
                                row_type = zone_df.loc[row.name, 'Type']
                                if row_type == 'mfg_com':
                                    # Manufacturing Company - bold with golden background
                                    return ['background-color: #FFF3CD; font-weight: bold; border-top: 2px solid #f5b400; border-bottom: 1px solid #f5b400; color: #856404'] * len(row)
                                elif row_type == 'family':
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
                            
                            # Drop Type column and rename - new order: MS|Sal, A25 Gr, A26 YTD Gr*, A25 BTM, A26 YTD BTM*
                            display_df = zone_df.drop(columns=['Type'])
                            display_df.columns = ["Brand", "MS|Sal", "A25 Gr", "A26 YTD Gr*", "A25 BTM", "A26 YTD BTM*"]
                            
                            styled_df = display_df.style.apply(highlight_families, axis=1).applymap(color_negatives)
                            st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
                
                # Comment box AFTER zonal preview - pre-populated with saved value
                zonal_comment = st.text_area(
                    "Add Comment",
                    value=saved_zonal_comment,
                    key=f"ns_zonal_comment_{segment['id']}",
                    placeholder="Add insights about zonal performance...",
                    height=120
                )
                
                if st.button("Save Zonal Table to Dashboard", key=f"save_ns_zonal_{segment['id']}"):
                    # Delete existing zonal table
                    delete_tables_for_section(segment["id"], "NS Landscape", "Zonal Pivot")
                    
                    # Save configuration with title
                    filter_config = json.dumps({
                        "brand_families": selected_families,
                        "brands": selected_brands,
                        "excluded_states": excluded_states,
                        "year": "A25",
                        "title": zonal_title
                    })
                    save_table(
                        name="Zonal Pivot",
                        dataset_id=dataset_id,
                        columns=["Brand Family", "Brand", "Zone", "Revised NS"],
                        created_by=current_user["username"],
                        segment_id=segment["id"],
                        section="NS Landscape",
                        filter_json=filter_config,
                        comment=zonal_comment
                    )
                    st.success("Zonal Pivot Table saved to dashboard!")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
                
                # Delete button next to save
                if saved_zonal:
                    if st.button("🗑️ Delete Zonal Pivot", key=f"delete_ns_zonal_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "Zonal Pivot")
                        st.success("Zonal Pivot deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
            else:
                st.info("No data available for A25 with selected brands.")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    st.markdown("---")
    # 4. NORTH Zone State Drill-Down
    st.markdown("### North Zone")
    st.caption("Performance of key states within the zone")
    
    # Parse saved NORTH config
    north_config = json.loads(saved_north["filter_json"]) if saved_north and saved_north["filter_json"] else {}
    saved_north_title = north_config.get("title", "Battleground in North")
    saved_north_states = north_config.get("states", [])
    saved_north_comments = json.loads(saved_north["comment"]) if saved_north and saved_north["comment"] else {}
    saved_north_comment_top = saved_north_comments.get("top", "") if isinstance(saved_north_comments, dict) else ""
    saved_north_comment_bottom = saved_north_comments.get("bottom", "") if isinstance(saved_north_comments, dict) else ""
    
    # Editable title - pre-populated with saved value
    north_title = st.text_input(
        "Slide Title",
        value=saved_north_title,
        key=f"ns_north_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    if selected_families and selected_brands:
        # Check if State column exists
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset. This feature requires a 'State' column.")
        else:
            # Filter data for NORTH zone only (use df_filtered_with_a26 for A26 YTD support)
            df_north = df_filtered_with_a26[df_filtered_with_a26["Zone"] == "North Zone"].copy()
            
            if df_north.empty:
                st.info("No data available for NORTH zone.")
            else:
                # Get all states in NORTH zone
                states_in_north = sorted(df_north["State"].dropna().unique().tolist())
                
                # First show state summary for ALL states in North Zone

                preview_all_states = create_north_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, states_in_north, df_filtered_with_a26)
                
                if preview_all_states:
                    # Define colors for styling
                    def highlight_zone_row(row):
                        """Highlight the NORTH zone row"""
                        state_val = preview_all_states['state_summary'].loc[row.name, 'State']
                        if state_val == 'NORTH':
                            return ['background-color: #E3F2FD; font-weight: bold'] * len(row)
                        return [''] * len(row)
                    
                    def color_negatives_summary(val):
                        """Color negative numbers red"""
                        if isinstance(val, str):
                            if '-' in val or val.startswith('−'):
                                return 'color: #D32F2F; font-weight: bold'
                        return ''
                    
                    summary_styled = preview_all_states['state_summary'].style.apply(highlight_zone_row, axis=1).applymap(color_negatives_summary)
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding NORTH zone row)
                    sorted_states = preview_all_states['state_summary'][preview_all_states['state_summary']['State'] != 'NORTH']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table - pre-populated with saved value
                north_comment_top = st.text_area(
                    "Add Comment",
                    value=saved_north_comment_top,
                    key=f"ns_north_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                # Then let user select states for deep-dive - use saved states if available
                available_states = sorted_states if preview_all_states else states_in_north
                # Filter saved states to only include those still available (after exclusion)
                valid_saved_states = [s for s in saved_north_states if s in available_states] if saved_north_states else []
                default_north_states = valid_saved_states if valid_saved_states else (available_states[:4] if len(available_states) > 4 else available_states)
                selected_states = st.multiselect(
                    "Select Key States",
                    options=available_states,
                    default=default_north_states,
                    key=f"ns_north_states_{segment['id']}"
                )
                
                if selected_states:
                    # Preview deep-dive
                    st.markdown("**Retrieving data. Wait a few seconds and try to cut or copy again.**")
                    preview_north = create_north_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, selected_states, df_filtered_with_a26)
                    
                    if preview_north and preview_north['state_details']:
                        # Define colors for brand families
                        family_colors = {
                            0: "#E8F5E9",  # Light Green
                            1: "#E3F2FD",  # Light Blue
                            2: "#FFF3E0",  # Light Orange
                            3: "#F3E5F5",  # Light Purple
                            4: "#FCE4EC",  # Light Pink
                        }
                        
                        # Display states in rows of 4
                        states_per_row = 4
                        for row_start in range(0, len(selected_states), states_per_row):
                            row_states = selected_states[row_start:row_start + states_per_row]
                            # Always create 4 columns for consistent alignment
                            cols = st.columns(states_per_row)
                            
                            for idx, state in enumerate(row_states):
                                with cols[idx]:
                                    if state in preview_north['state_details']:
                                        state_df = preview_north['state_details'][state]
                                        
                                        # State header
                                        st.markdown(f"""
                                            <div style='text-align: center; padding: 0.5rem; background-color: #f0f2f6; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                                                <h3 style='margin: 0; font-size: 1.4rem;'>{state}</h3>
                                            </div>
                                        """, unsafe_allow_html=True)
                                        
                                        # Apply styling
                                        def highlight_families(row):
                                            row_type = state_df.loc[row.name, 'Type']
                                            if row_type == 'mfg_com':
                                                # Manufacturing Company - bold with golden background
                                                return ['background-color: #FFF3CD; font-weight: bold; border-top: 2px solid #f5b400; border-bottom: 1px solid #f5b400; color: #856404'] * len(row)
                                            elif row_type == 'family':
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
                                        
                                        # Info message below table
                                        st.info("📌 Data for all brands within the manufacturing company")
                            
                            # Add spacing between rows if there are more states
                            if row_start + states_per_row < len(selected_states):
                                st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
                
                # Comment for brand deep-dive AFTER preview - pre-populated with saved value
                st.markdown("---")
                north_comment_bottom = st.text_area(
                    "Add Comment",
                    value=saved_north_comment_bottom,
                    key=f"ns_north_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save North Zone to Dashboard", key=f"save_ns_north_{segment['id']}"):
                    if not selected_states:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        # Delete existing
                        delete_tables_for_section(segment["id"], "NS Landscape", "NORTH State Drill-Down")
                        
                        # Combine both comments into a JSON structure
                        comments_json = json.dumps({
                            "top": north_comment_top,
                            "bottom": north_comment_bottom
                        })
                        
                        # Save configuration with title
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "excluded_states": excluded_states,
                            "states": selected_states,
                            "zone": "North Zone",
                            "title": north_title
                        })
                        save_table(
                            name="NORTH State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "Revised NS"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("NORTH Zone Drill-Down saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_north:
                    if st.button("🗑️ Delete NORTH Zone Drill-Down", key=f"delete_ns_north_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "NORTH State Drill-Down")
                        st.success("NORTH Zone Drill-Down deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 5. WEST+CSD Zone State Drill-Down
    st.markdown("### West + CSD Zone")
    st.caption("Performance of key states within the zone")
    
    # Parse saved WEST config
    west_config = json.loads(saved_west["filter_json"]) if saved_west and saved_west["filter_json"] else {}
    saved_west_title = west_config.get("title", "Battleground in West+CSD")
    saved_west_states = west_config.get("states", [])
    saved_west_comments = json.loads(saved_west["comment"]) if saved_west and saved_west["comment"] else {}
    saved_west_comment_top = saved_west_comments.get("top", "") if isinstance(saved_west_comments, dict) else ""
    saved_west_comment_bottom = saved_west_comments.get("bottom", "") if isinstance(saved_west_comments, dict) else ""
    
    # Editable title - pre-populated with saved value
    west_title = st.text_input(
        "Slide Title",
        value=saved_west_title,
        key=f"ns_west_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_west = df_filtered_with_a26[df_filtered_with_a26["Zone"] == "West+CSD Zone"].copy()
            
            if df_west.empty:
                st.info("No data available for WEST+CSD zone.")
            else:
                states_in_west = sorted(df_west["State"].dropna().unique().tolist())
                

                preview_all_west = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, states_in_west, "West+CSD Zone", df_full_segment)
                
                if preview_all_west:
                    summary_styled = style_state_summary(preview_all_west['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_west = preview_all_west['state_summary'][preview_all_west['state_summary']['State'] != 'WEST+CSD']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table - pre-populated with saved value
                west_comment_top = st.text_area(
                    "Add Comment",
                    value=saved_west_comment_top,
                    key=f"ns_west_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                # Use saved states if available
                available_states_west = sorted_states_west if preview_all_west else states_in_west
                # Filter saved states to only include those still available (after exclusion)
                valid_saved_west = [s for s in saved_west_states if s in available_states_west] if saved_west_states else []
                default_west_states = valid_saved_west if valid_saved_west else (available_states_west[:4] if len(available_states_west) > 4 else available_states_west)
                selected_states_west = st.multiselect(
                    "Select Key States",
                    options=available_states_west,
                    default=default_west_states,
                    key=f"ns_west_states_{segment['id']}"
                )
                
                if selected_states_west:
                    st.markdown("**Select Key States**")
                    preview_west = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, selected_states_west, "West+CSD Zone", df_filtered_with_a26)
                    
                    if preview_west and preview_west['state_details']:
                        render_state_drilldown_preview(preview_west, selected_states_west)
                
                # Comment for brand deep-dive AFTER preview - pre-populated with saved value
                st.markdown("---")
                west_comment_bottom = st.text_area(
                    "Add Comment",
                    value=saved_west_comment_bottom,
                    key=f"ns_west_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save West + CSD Zone to Dashboard", key=f"save_ns_west_{segment['id']}"):
                    if not selected_states_west:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "WEST+CSD State Drill-Down")
                        
                        comments_json = json.dumps({"top": west_comment_top, "bottom": west_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "excluded_states": excluded_states,
                            "states": selected_states_west,
                            "zone": "West+CSD Zone",
                            "title": west_title
                        })
                        save_table(
                            name="WEST+CSD State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "Revised NS"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("WEST+CSD Zone Drill-Down saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_west:
                    if st.button("🗑️ Delete WEST+CSD Zone Drill-Down", key=f"delete_ns_west_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "WEST+CSD State Drill-Down")
                        st.success("WEST+CSD Zone Drill-Down deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 6. EAST Zone State Drill-Down
    st.markdown("### East Zone")
    st.caption("Performance of key states within the zone")
    
    # Parse saved EAST config
    east_config = json.loads(saved_east["filter_json"]) if saved_east and saved_east["filter_json"] else {}
    saved_east_title = east_config.get("title", "Battleground in East")
    saved_east_states = east_config.get("states", [])
    saved_east_comments = json.loads(saved_east["comment"]) if saved_east and saved_east["comment"] else {}
    saved_east_comment_top = saved_east_comments.get("top", "") if isinstance(saved_east_comments, dict) else ""
    saved_east_comment_bottom = saved_east_comments.get("bottom", "") if isinstance(saved_east_comments, dict) else ""
    
    # Editable title - pre-populated with saved value
    east_title = st.text_input(
        "Slide Title",
        value=saved_east_title,
        key=f"ns_east_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_east = df_filtered_with_a26[df_filtered_with_a26["Zone"] == "East Zone"].copy()
            
            if df_east.empty:
                st.info("No data available for EAST zone.")
            else:
                states_in_east = sorted(df_east["State"].dropna().unique().tolist())
                

                preview_all_east = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, states_in_east, "East Zone", df_filtered_with_a26)
                
                if preview_all_east:
                    summary_styled = style_state_summary(preview_all_east['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_east = preview_all_east['state_summary'][preview_all_east['state_summary']['State'] != 'EAST']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table - pre-populated with saved value
                east_comment_top = st.text_area(
                    "Add Comment",
                    value=saved_east_comment_top,
                    key=f"ns_east_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                # Use saved states if available
                available_states_east = sorted_states_east if preview_all_east else states_in_east
                # Filter saved states to only include those still available (after exclusion)
                valid_saved_east = [s for s in saved_east_states if s in available_states_east] if saved_east_states else []
                default_east_states = valid_saved_east if valid_saved_east else (available_states_east[:4] if len(available_states_east) > 4 else available_states_east)
                selected_states_east = st.multiselect(
                    "Select Key States",
                    options=available_states_east,
                    default=default_east_states,
                    key=f"ns_east_states_{segment['id']}"
                )
                
                if selected_states_east:
                    st.markdown("**Retrieving data. Wait a few seconds and try to cut or copy again.**")
                    preview_east = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, selected_states_east, "East Zone", df_filtered_with_a26)
                    
                    if preview_east and preview_east['state_details']:
                        render_state_drilldown_preview(preview_east, selected_states_east)
                
                # Comment for brand deep-dive AFTER preview - pre-populated with saved value
                st.markdown("---")
                east_comment_bottom = st.text_area(
                    "Add Comment",
                    value=saved_east_comment_bottom,
                    key=f"ns_east_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save East Zone to Dashboard", key=f"save_ns_east_{segment['id']}"):
                    if not selected_states_east:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "EAST State Drill-Down")
                        
                        comments_json = json.dumps({"top": east_comment_top, "bottom": east_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "excluded_states": excluded_states,
                            "states": selected_states_east,
                            "zone": "East Zone",
                            "title": east_title
                        })
                        save_table(
                            name="EAST State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "Revised NS"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("EAST Zone Drill-Down saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_east:
                    if st.button("🗑️ Delete EAST Zone Drill-Down", key=f"delete_ns_east_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "EAST State Drill-Down")
                        st.success("EAST Zone Drill-Down deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 7. SOUTH Zone State Drill-Down
    st.markdown("### South Zone")
    st.caption("Performance of key states within the zone")
    
    # Parse saved SOUTH config
    south_config = json.loads(saved_south["filter_json"]) if saved_south and saved_south["filter_json"] else {}
    saved_south_title = south_config.get("title", "Battleground in South")
    saved_south_states = south_config.get("states", [])
    saved_south_comments = json.loads(saved_south["comment"]) if saved_south and saved_south["comment"] else {}
    saved_south_comment_top = saved_south_comments.get("top", "") if isinstance(saved_south_comments, dict) else ""
    saved_south_comment_bottom = saved_south_comments.get("bottom", "") if isinstance(saved_south_comments, dict) else ""
    
    # Editable title - pre-populated with saved value
    south_title = st.text_input(
        "Slide Title",
        value=saved_south_title,
        key=f"ns_south_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_south = df_filtered_with_a26[df_filtered_with_a26["Zone"] == "South Zone"].copy()
            
            if df_south.empty:
                st.info("No data available for SOUTH zone.")
            else:
                states_in_south = sorted(df_south["State"].dropna().unique().tolist())
                

                preview_all_south = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, states_in_south, "South Zone", df_filtered_with_a26)
                
                if preview_all_south:
                    summary_styled = style_state_summary(preview_all_south['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_south = preview_all_south['state_summary'][preview_all_south['state_summary']['State'] != 'SOUTH']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table - pre-populated with saved value
                south_comment_top = st.text_area(
                    "Add Comment",
                    value=saved_south_comment_top,
                    key=f"ns_south_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                # Use saved states if available
                available_states_south = sorted_states_south if preview_all_south else states_in_south
                # Filter saved states to only include those still available (after exclusion)
                valid_saved_south = [s for s in saved_south_states if s in available_states_south] if saved_south_states else []
                default_south_states = valid_saved_south if valid_saved_south else (available_states_south[:4] if len(available_states_south) > 4 else available_states_south)
                selected_states_south = st.multiselect(
                    "Select Key States",
                    options=available_states_south,
                    default=default_south_states,
                    key=f"ns_south_states_{segment['id']}"
                )
                
                if selected_states_south:
                    st.markdown("**Retrieving data. Wait a few seconds and try to cut or copy again.**")
                    preview_south = create_zone_state_drilldown(df_filtered_with_a26, selected_families, selected_brands, selected_states_south, "South Zone", df_filtered_with_a26)
                    
                    if preview_south and preview_south['state_details']:
                        render_state_drilldown_preview(preview_south, selected_states_south)
                
                # Comment for brand deep-dive AFTER preview - pre-populated with saved value
                st.markdown("---")
                south_comment_bottom = st.text_area(
                    "Add Comment",
                    value=saved_south_comment_bottom,
                    key=f"ns_south_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save South Zone to Dashboard", key=f"save_ns_south_{segment['id']}"):
                    if not selected_states_south:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "SOUTH State Drill-Down")
                        
                        comments_json = json.dumps({"top": south_comment_top, "bottom": south_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "excluded_states": excluded_states,
                            "states": selected_states_south,
                            "zone": "South Zone",
                            "title": south_title
                        })
                        save_table(
                            name="SOUTH State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "Revised NS"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("SOUTH Zone Drill-Down saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_south:
                    if st.button("🗑️ Delete SOUTH Zone Drill-Down", key=f"delete_ns_south_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "SOUTH State Drill-Down")
                        st.success("SOUTH Zone Drill-Down deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    st.markdown("---")
    # BTM Detailed Analysis
    st.markdown("### BTM Detailed Analysis")
    st.caption("Select states and brand family to view detailed performance metrics")
    
    # Load existing saved configuration
    saved_state_perf = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "State Performance Analysis"), None)
    
    state_perf_config = json.loads(saved_state_perf["filter_json"]) if saved_state_perf and saved_state_perf["filter_json"] else {}
    saved_state_perf_title = state_perf_config.get("title", "BTM Detailed Analysis")
    saved_state_perf_states = state_perf_config.get("states", [])
    saved_state_perf_family = state_perf_config.get("brand_family", "")
    saved_state_colors = state_perf_config.get("state_colors", {})  # Load saved colors
    saved_state_perf_comment = saved_state_perf["comment"] if saved_state_perf else ""
    
    # Editable title
    state_perf_title = st.text_input(
        "Slide Title",
        value=saved_state_perf_title,
        key=f"ns_state_perf_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Check required columns
    if "State" not in df_filtered.columns or "Brand Family" not in df_filtered.columns:
        st.warning("State and Brand Family columns required for this analysis.")
    else:
        # Get available states and brand families (INDEPENDENT from Section 2)
        all_states = sorted(df_filtered["State"].dropna().unique().tolist())
        all_brand_families = sorted(df_filtered["Brand Family"].dropna().unique().tolist())
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Multiselect for states
            selected_states_perf = st.multiselect(
                "Select States",
                options=all_states,
                default=saved_state_perf_states if saved_state_perf_states else all_states[:5],  # Default to first 5 states
                key=f"ns_state_perf_states_{segment['id']}"
            )
        
        with col2:
            # Independent brand family selection
            selected_family = st.selectbox(
                "Select Brand Family (select one PRI brand)",
                options=all_brand_families,
                index=all_brand_families.index(saved_state_perf_family) if saved_state_perf_family in all_brand_families else 0,
                key=f"ns_state_perf_family_{segment['id']}"
            )
        
        # Calculate and show table preview RIGHT AFTER selection
        if selected_states_perf and selected_family:
            # Calculate the table - need to pass original df for All Spirits calculation
            # Load the full dataset (unfiltered by segment)
            from app_core.uploads import load_dataset
            df_full = load_dataset(dataset_id)
            
            state_perf_df = calculate_state_performance_table(df_filtered, df_full, selected_states_perf, selected_family, segment)
            
            if state_perf_df is not None and not state_perf_df.empty:
                st.markdown("---")
                st.markdown("**Table Preview:**")
                
                # Display the styled table using Streamlit dataframe with custom styling
                display_state_performance_table(state_perf_df)
        
        # 3 Color Groups for state assignment (AFTER table preview)
        if selected_states_perf:
            st.markdown("---")
            st.markdown("**Assign States to Color Groups (for bubble chart):**")
            st.caption("Organize states into 3 color groups to visualize different categories")
            
            # Load saved color groups
            saved_color_groups = saved_state_colors.get("color_groups", {
                "group1": {"color": "#E74C3C", "states": []},  # Red
                "group2": {"color": "#4A90E2", "states": []},  # Blue
                "group3": {"color": "#2ECC71", "states": []}   # Green
            })
            
            # Create 3 color group sections
            color_groups = {}
            state_colors = {}  # Map state -> color
            
            # First pass: collect all currently selected states from session state
            currently_assigned = {}
            for group_num in range(1, 4):
                group_key = f"group{group_num}"
                session_key = f"states_group_{group_num}_{segment['id']}"
                if session_key in st.session_state:
                    currently_assigned[group_key] = st.session_state[session_key]
                else:
                    currently_assigned[group_key] = saved_color_groups.get(group_key, {}).get("states", [])
            
            for group_num in range(1, 4):
                group_key = f"group{group_num}"
                saved_group = saved_color_groups.get(group_key, {"color": ["#E74C3C", "#4A90E2", "#2ECC71"][group_num-1], "states": []})
                
                st.markdown(f"**Color Group {group_num}:**")
                
                col_color, col_states = st.columns([1, 3])
                
                with col_color:
                    group_color = st.color_picker(
                        f"Color {group_num}",
                        value=saved_group.get("color", ["#E74C3C", "#4A90E2", "#2ECC71"][group_num-1]),
                        key=f"color_group_{group_num}_{segment['id']}"
                    )
                
                with col_states:
                    # Get states already assigned to OTHER groups (from current session)
                    assigned_to_others = []
                    for other_group_num in range(1, 4):
                        if other_group_num != group_num:
                            other_key = f"group{other_group_num}"
                            assigned_to_others.extend(currently_assigned.get(other_key, []))
                    
                    # Available states = all selected states minus those assigned to other groups
                    # But include states currently in THIS group
                    current_group_states = currently_assigned.get(group_key, [])
                    available_for_group = [s for s in selected_states_perf 
                                          if s not in assigned_to_others or s in current_group_states]
                    
                    group_states = st.multiselect(
                        f"States for Color {group_num}",
                        options=available_for_group,
                        default=[s for s in current_group_states if s in selected_states_perf],
                        key=f"states_group_{group_num}_{segment['id']}",
                        help=f"Assign states to Color Group {group_num}"
                    )
                
                # Store group configuration
                color_groups[group_key] = {
                    "color": group_color,
                    "states": group_states
                }
                
                # Map each state to its color
                for state in group_states:
                    state_colors[state] = group_color
                
                st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
            
            # Show unassigned states warning
            assigned_all = []
            for group in color_groups.values():
                assigned_all.extend(group["states"])
            unassigned = [s for s in selected_states_perf if s not in assigned_all]
            
            if unassigned:
                st.warning(f"⚠️ Unassigned states: {', '.join(unassigned)}. These will use default color.")
                # Assign default color to unassigned states
                for state in unassigned:
                    state_colors[state] = "#95A5A6"  # Gray for unassigned
        
        # Show bubble chart preview (AFTER color assignment)
        if selected_states_perf and selected_family:
                # Reuse the already calculated state_perf_df from above
                if 'state_perf_df' in locals() and state_perf_df is not None and not state_perf_df.empty:
                    st.markdown("---")
                    st.markdown("**Chart Preview:**")
                    
                    # Create bubble chart
                    import plotly.graph_objects as go
                    
                    # Extract data
                    ai_row = state_perf_df[state_perf_df["State"] == "All India"]
                    state_rows = state_perf_df[state_perf_df["State"] != "All India"]
                    
                    if not ai_row.empty and not state_rows.empty:
                        # Get All India values
                        ai_ms = float(ai_row["Brand FAM\nA25 MS"].iloc[0])
                        ai_salience = float(ai_row["Segment\nSalience to\nAll Spirits"].iloc[0])
                        
                        # Prepare state data
                        states = []
                        x_values = []
                        y_values = []
                        sizes = []
                        contribution_values = []
                        colors = []  # Add colors list
                        
                        for _, row in state_rows.iterrows():
                            contribution = float(row["State\nContribution\nto AI"])
                            state_name = row["State"]
                            states.append(state_name)
                            x_values.append(float(row["Brand FAM\nA25 MS"]))
                            y_values.append(float(row["Segment\nSalience to\nAll Spirits"]))
                            contribution_values.append(contribution)
                            # Use square root so area is proportional to contribution, not diameter
                            sizes.append((contribution ** 0.5) * 20)  # 2x scale for better visibility
                            # Get assigned color for this state
                            colors.append(state_colors.get(state_name, '#4A90E2'))
                        
                        # Create figure
                        fig = go.Figure()
                        
                        fig.add_trace(go.Scatter(
                            x=x_values,
                            y=y_values,
                            mode='markers+text',
                            marker=dict(
                                size=sizes,
                                color=colors,  # Use assigned colors
                                opacity=0.7,
                                line=dict(width=2, color='white')
                            ),
                            text=states,
                            textposition='middle center',
                            textfont=dict(size=10, color='black', family='Arial Black'),
                            customdata=contribution_values,
                            hovertemplate='<b>%{text}</b><br>Brand FAM MS: %{x:.0f}%<br>Segment Salience: %{y:.0f}%<br>State Contribution: %{customdata:.0f}%<extra></extra>',
                            name='States'
                        ))
                        
                        # Add reference lines (without annotation_text, we'll add them separately)
                        fig.add_hline(y=ai_salience, line_dash="dash", line_color="#9B59B6", line_width=2)
                        fig.add_vline(x=ai_ms, line_dash="dash", line_color="#E74C3C", line_width=2)
                        
                        fig.update_layout(
                            xaxis_title="X-Axis: Brand Fam A25 MS",
                            yaxis_title="Y-Axis: Segment Salience to TBA A25",
                            height=600,
                            showlegend=False,
                            hovermode='closest',
                            plot_bgcolor='#F8F9FA',
                            paper_bgcolor='white',
                            xaxis=dict(
                                showgrid=True, 
                                gridcolor='#E0E0E0',
                                gridwidth=1,
                                zeroline=False,
                                title_font=dict(size=13, color='#2C3E50')
                            ),
                            yaxis=dict(
                                showgrid=True, 
                                gridcolor='#E0E0E0',
                                gridwidth=1,
                                zeroline=False,
                                title_font=dict(size=13, color='#2C3E50')
                            ),
                            font=dict(family="Arial, sans-serif", size=12, color='#2C3E50')
                        )
                        
                        # Add all annotations together
                        fig.add_annotation(
                            text=f"A25 Seg. Sal. ({ai_salience:.1f}%) All India",
                            xref="paper",
                            yref="y",
                            x=0.98,
                            y=ai_salience,
                            showarrow=False,
                            font=dict(size=11, color="#9B59B6", family="Arial"),
                            xanchor='right',
                            yanchor='bottom'
                        )
                        
                        fig.add_annotation(
                            text=f"A25 Brand Fam MS ({ai_ms:.1f}%) All India",
                            xref="x", yref="paper",
                            x=ai_ms, y=1.02,
                            showarrow=False,
                            font=dict(size=11, color="#E74C3C", family="Arial"),
                            xanchor='center',
                            yanchor='bottom'
                        )
                        
                        fig.add_annotation(
                            text="Bubble Size: Segment Contribution to All India",
                            xref="paper",
                            yref="paper",
                            x=0.01,
                            y=-0.15,
                            showarrow=False,
                            font=dict(size=12, color='#2C3E50'),
                            xanchor='left'
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No data available for selected states and brand family.")
                
                # Comment box
                state_perf_comment = st.text_area(
                    "Add comment for state performance table (optional)",
                    value=saved_state_perf_comment,
                    key=f"ns_state_perf_comment_{segment['id']}",
                    placeholder="Add insights about state performance metrics...",
                    height=120
                )
                
                if st.button("Save Table and Chart to Dashboard", key=f"save_ns_state_perf_{segment['id']}"):
                    # Delete existing table
                    delete_tables_for_section(segment["id"], "NS Landscape", "State Performance Analysis")
                    
                    # Save configuration with color groups
                    filter_config = json.dumps({
                        "states": selected_states_perf,
                        "brand_family": selected_family,
                        "title": state_perf_title,
                        "state_colors": {
                            "color_groups": color_groups,  # Save color groups
                            "state_map": state_colors  # Save state->color mapping for easy lookup
                        }
                    })
                    save_table(
                        name="State Performance Analysis",
                        dataset_id=dataset_id,
                        columns=["State", "Brand Family", "Metrics"],
                        created_by=current_user["username"],
                        segment_id=segment["id"],
                        section="NS Landscape",
                        filter_json=filter_config,
                        comment=state_perf_comment
                    )
                    st.success("State Performance Analysis saved to dashboard!")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
                
                # Delete button next to save
                if saved_state_perf:
                    if st.button("🗑️ Delete State Performance Analysis", key=f"delete_ns_state_perf_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "State Performance Analysis")
                        st.success("State Performance Analysis deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                st.markdown("---")
                st.markdown("### Battleground Summary Slide")
                st.caption("Cluster states and add Battleground Summary")
                
                # Load existing grid data
                saved_grid = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "Strategic Insights Grid"), None)
                
                grid_config = json.loads(saved_grid["filter_json"]) if saved_grid and saved_grid["filter_json"] else {}
                saved_grid_title = grid_config.get("title", "Battleground Summary")
                saved_grid_data = grid_config.get("grid_data", {})
                
                # Title for the grid
                grid_title = st.text_input(
                    "Slide Title",
                    value=saved_grid_title,
                    key=f"ns_grid_title_{segment['id']}",
                    placeholder="e.g., Battleground Summary"
                )
                
                # 3 rows with titles and 3 columns
                grid_data = {}
                
                for row_idx in range(3):
                    st.markdown(f"**Row {row_idx + 1}:**")
                    
                    # Row title
                    row_title = st.text_input(
                        f"Row {row_idx + 1} Title",
                        value=saved_grid_data.get(f"row_{row_idx}_title", ""),
                        key=f"ns_grid_row_{row_idx}_title_{segment['id']}",
                        placeholder=f"e.g., Category {row_idx + 1}"
                    )
                    grid_data[f"row_{row_idx}_title"] = row_title
                    
                    # 3 columns for this row
                    cols = st.columns(3)
                    for col_idx in range(3):
                        with cols[col_idx]:
                            cell_value = st.text_area(
                                f"Column {col_idx + 1}",
                                value=saved_grid_data.get(f"row_{row_idx}_col_{col_idx}", ""),
                                key=f"ns_grid_r{row_idx}_c{col_idx}_{segment['id']}",
                                placeholder="Enter content...",
                                height=100
                            )
                            grid_data[f"row_{row_idx}_col_{col_idx}"] = cell_value
                    
                    st.markdown("---")
                
                # Preview the grid
                if grid_title:
                    st.markdown("**Preview:**")
                    st.markdown(f"### {grid_title}")
                    
                    # Define colors for each row
                    row_colors = [
                        {"bg": "#E8F5E9", "border": "#81C784", "text": "#2E7D32"},  # Row 1: Light green
                        {"bg": "#E3F2FD", "border": "#90CAF9", "text": "#1565C0"},  # Row 2: Light blue
                        {"bg": "#FFEBEE", "border": "#EF9A9A", "text": "#C62828"}   # Row 3: Red
                    ]
                    
                    # Display 3x3 grid preview with row titles as first column
                    for row_idx in range(3):
                        row_title = grid_data.get(f"row_{row_idx}_title", "")
                        row_color = row_colors[row_idx]
                        
                        # 4 columns: row title + 3 content columns
                        cols = st.columns([1, 2, 2, 2])
                        
                        # Row title in first column
                        with cols[0]:
                            if row_title:
                                st.markdown(f"""
                                    <div style='
                                        background: {row_color["bg"]};
                                        border: 1px solid {row_color["border"]};
                                        padding: 1rem;
                                        margin: 0.5rem 0;
                                        border-radius: 6px;
                                        min-height: 100px;
                                        display: flex;
                                        align-items: center;
                                        justify-content: center;
                                    '>
                                        <div style='
                                            font-size: 0.95rem;
                                            font-weight: 600;
                                            color: {row_color["text"]};
                                            text-align: center;
                                        '>
                                            {row_title}
                                        </div>
                                    </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.markdown("""
                                    <div style='
                                        background: #FAFAFA;
                                        border: 1px dashed #CCCCCC;
                                        padding: 1rem;
                                        margin: 0.5rem 0;
                                        border-radius: 6px;
                                        min-height: 100px;
                                        display: flex;
                                        align-items: center;
                                        justify-content: center;
                                        color: #999;
                                    '>
                                        Row Title
                                    </div>
                                """, unsafe_allow_html=True)
                        
                        # 3 content columns
                        for col_idx in range(3):
                            cell_value = grid_data.get(f"row_{row_idx}_col_{col_idx}", "")
                            
                            with cols[col_idx + 1]:
                                if cell_value:
                                    formatted_content = cell_value.replace('\n', '<br>')
                                    st.markdown(f"""
                                        <div style='
                                            background: #F8F9FA;
                                            border: 1px solid #E0E0E0;
                                            padding: 1rem;
                                            margin: 0.5rem 0;
                                            border-radius: 6px;
                                            min-height: 100px;
                                        '>
                                            <div style='
                                                font-size: 0.9rem;
                                                line-height: 1.6;
                                                color: #2C3E50;
                                            '>
                                                {formatted_content}
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)
                                else:
                                    st.markdown("""
                                        <div style='
                                            background: #FAFAFA;
                                            border: 1px dashed #CCCCCC;
                                            padding: 1rem;
                                            margin: 0.5rem 0;
                                            border-radius: 6px;
                                            min-height: 100px;
                                            display: flex;
                                            align-items: center;
                                            justify-content: center;
                                            color: #999;
                                        '>
                                            Empty
                                        </div>
                                    """, unsafe_allow_html=True)
                        
                        if row_idx < 2:
                            st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
                
                # Save button for grid
                if st.button("Save Battleground Summary Slide to Dashboard", key=f"save_ns_grid_{segment['id']}"):
                    if not grid_title:
                        st.error("Please provide a Slide Title.")
                    else:
                        # Delete existing grid
                        delete_tables_for_section(segment["id"], "NS Landscape", "Strategic Insights Grid")
                        
                        # Save configuration
                        filter_config = json.dumps({
                            "title": grid_title,
                            "grid_data": grid_data
                        })
                        save_table(
                            name="Strategic Insights Grid",
                            dataset_id=dataset_id,
                            columns=["Grid"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=""
                        )
                        st.success("Battleground Summary Slide saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_grid:
                    if st.button("🗑️ Delete Strategic Insights Grid", key=f"delete_ns_grid_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "NS Landscape", "Strategic Insights Grid")
                        st.success("Strategic Insights Grid deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
    
    st.markdown("---")
    
    # Placeholder Slides (5 images)
    st.markdown("### Placeholder Slides")
    
    with st.expander("📸 Upload Placeholder Slides (optional)", expanded=False):
        st.caption("Upload up to 5 images with titles and comments")
        
        # Load existing placeholder images
        from app_core.media import get_media_for_segment, delete_media, update_media_metadata
        existing_media = get_media_for_segment(segment["id"])
        placeholder_images = [m for m in existing_media if m.get("section") == "NS Landscape" and m.get("name") == "Placeholder Images"]
        placeholder_images = sorted(placeholder_images, key=lambda x: x.get("id", 0))
        
        # Placeholder Image 1
        st.markdown("**Placeholder Image 1:**")
        existing_p1 = placeholder_images[0] if len(placeholder_images) > 0 else None
        
        if existing_p1:
            # Show existing image with edit/delete buttons
            file_path_p1 = existing_p1.get("file_path")
            if file_path_p1 and os.path.exists(file_path_p1):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p1, caption="Current Image", use_container_width=True)
                with col_info:
                    title_p1 = st.text_input("Title", value=existing_p1.get("title", ""), key=f"ns_p1_title_edit_{segment['id']}")
                    comment_p1 = st.text_area("Comment", value=existing_p1.get("comment", ""), key=f"ns_p1_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_ns_p1_{segment['id']}", type="primary"):
                            update_media_metadata(existing_p1["id"], title_p1, comment_p1)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_ns_p1_{segment['id']}", type="secondary"):
                            delete_media(existing_p1["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            # Show upload form
            uploaded_p1 = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "ppt", "pptx"], key=f"ns_placeholder_1_{segment['id']}")
            title_p1 = st.text_input("Title", key=f"ns_p_title_1_{segment['id']}")
            comment_p1 = st.text_area("Comment", key=f"ns_p_comment_1_{segment['id']}", height=150)
            
            if st.button("Save Image", key=f"save_ns_p1_{segment['id']}"):
                if not uploaded_p1:
                    st.error("Please upload an image.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p1,
                        segment_id=segment["id"],
                        section="NS Landscape",
                        created_by=current_user["username"],
                        comment=comment_p1,
                        title=title_p1,
                        label="Placeholder Images"
                    )
                    st.success("Image saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 2
        st.markdown("**Placeholder Image 2:**")
        existing_p2 = placeholder_images[1] if len(placeholder_images) > 1 else None
        
        if existing_p2:
            file_path_p2 = existing_p2.get("file_path")
            if file_path_p2 and os.path.exists(file_path_p2):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p2, caption="Current Image", use_container_width=True)
                with col_info:
                    title_p2 = st.text_input("Title", value=existing_p2.get("title", ""), key=f"ns_p2_title_edit_{segment['id']}")
                    comment_p2 = st.text_area("Comment", value=existing_p2.get("comment", ""), key=f"ns_p2_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_ns_p2_{segment['id']}", type="primary"):
                            update_media_metadata(existing_p2["id"], title_p2, comment_p2)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_ns_p2_{segment['id']}", type="secondary"):
                            delete_media(existing_p2["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p2 = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "ppt", "pptx"], key=f"ns_placeholder_2_{segment['id']}")
            title_p2 = st.text_input("Title", key=f"ns_p_title_2_{segment['id']}")
            comment_p2 = st.text_area("Comment", key=f"ns_p_comment_2_{segment['id']}", height=150)
            
            if st.button("Save Image", key=f"save_ns_p2_{segment['id']}"):
                if not uploaded_p2:
                    st.error("Please upload an image.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p2,
                        segment_id=segment["id"],
                        section="NS Landscape",
                        created_by=current_user["username"],
                        comment=comment_p2,
                        title=title_p2,
                        label="Placeholder Images"
                    )
                    st.success("Image saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 3
        st.markdown("**Placeholder Image 3:**")
        existing_p3 = placeholder_images[2] if len(placeholder_images) > 2 else None
        
        if existing_p3:
            file_path_p3 = existing_p3.get("file_path")
            if file_path_p3 and os.path.exists(file_path_p3):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p3, caption="Current Image", use_container_width=True)
                with col_info:
                    title_p3 = st.text_input("Title", value=existing_p3.get("title", ""), key=f"ns_p3_title_edit_{segment['id']}")
                    comment_p3 = st.text_area("Comment", value=existing_p3.get("comment", ""), key=f"ns_p3_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_ns_p3_{segment['id']}", type="primary"):
                            update_media_metadata(existing_p3["id"], title_p3, comment_p3)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_ns_p3_{segment['id']}", type="secondary"):
                            delete_media(existing_p3["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p3 = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "ppt", "pptx"], key=f"ns_placeholder_3_{segment['id']}")
            title_p3 = st.text_input("Title", key=f"ns_p_title_3_{segment['id']}")
            comment_p3 = st.text_area("Comment", key=f"ns_p_comment_3_{segment['id']}", height=150)
            
            if st.button("Save Image", key=f"save_ns_p3_{segment['id']}"):
                if not uploaded_p3:
                    st.error("Please upload an image.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p3,
                        segment_id=segment["id"],
                        section="NS Landscape",
                        created_by=current_user["username"],
                        comment=comment_p3,
                        title=title_p3,
                        label="Placeholder Images"
                    )
                    st.success("Image saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 4
        st.markdown("**Placeholder Image 4:**")
        existing_p4 = placeholder_images[3] if len(placeholder_images) > 3 else None
        
        if existing_p4:
            file_path_p4 = existing_p4.get("file_path")
            if file_path_p4 and os.path.exists(file_path_p4):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p4, caption="Current Image", use_container_width=True)
                with col_info:
                    title_p4 = st.text_input("Title", value=existing_p4.get("title", ""), key=f"ns_p4_title_edit_{segment['id']}")
                    comment_p4 = st.text_area("Comment", value=existing_p4.get("comment", ""), key=f"ns_p4_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_ns_p4_{segment['id']}", type="primary"):
                            update_media_metadata(existing_p4["id"], title_p4, comment_p4)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_ns_p4_{segment['id']}", type="secondary"):
                            delete_media(existing_p4["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p4 = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "ppt", "pptx"], key=f"ns_placeholder_4_{segment['id']}")
            title_p4 = st.text_input("Title", key=f"ns_p_title_4_{segment['id']}")
            comment_p4 = st.text_area("Comment", key=f"ns_p_comment_4_{segment['id']}", height=150)
            
            if st.button("Save Image", key=f"save_ns_p4_{segment['id']}"):
                if not uploaded_p4:
                    st.error("Please upload an image.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p4,
                        segment_id=segment["id"],
                        section="NS Landscape",
                        created_by=current_user["username"],
                        comment=comment_p4,
                        title=title_p4,
                        label="Placeholder Images"
                    )
                    st.success("Image saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 5
        st.markdown("**Placeholder Image 5:**")
        existing_p5 = placeholder_images[4] if len(placeholder_images) > 4 else None
        
        if existing_p5:
            file_path_p5 = existing_p5.get("file_path")
            if file_path_p5 and os.path.exists(file_path_p5):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p5, caption="Current Image", use_container_width=True)
                with col_info:
                    title_p5 = st.text_input("Title", value=existing_p5.get("title", ""), key=f"ns_p5_title_edit_{segment['id']}")
                    comment_p5 = st.text_area("Comment", value=existing_p5.get("comment", ""), key=f"ns_p5_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_ns_p5_{segment['id']}", type="primary"):
                            update_media_metadata(existing_p5["id"], title_p5, comment_p5)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_ns_p5_{segment['id']}", type="secondary"):
                            delete_media(existing_p5["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p5 = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "ppt", "pptx"], key=f"ns_placeholder_5_{segment['id']}")
            title_p5 = st.text_input("Title", key=f"ns_p_title_5_{segment['id']}")
            comment_p5 = st.text_area("Comment", key=f"ns_p_comment_5_{segment['id']}", height=150)
            
            if st.button("Save Image", key=f"save_ns_p5_{segment['id']}"):
                if not uploaded_p5:
                    st.error("Please upload an image.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p5,
                        segment_id=segment["id"],
                        section="NS Landscape",
                        created_by=current_user["username"],
                        comment=comment_p5,
                        title=title_p5,
                        label="Placeholder Images"
                    )
                    st.success("Image saved!")
                    st.rerun()
    
    st.markdown("---")
    
    # NS Landscape Summary Slide
    st.markdown("### NS Landscape Summary Slide")
    st.caption("Add content for NS Landscape summary slide")
    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    saved_custom_trends = next((t for t in existing_tables if t["section"] == "NS Landscape" and t["name"] == "Custom Trends View"), None)
    
    # Parse saved config
    custom_trends_config = json.loads(saved_custom_trends["filter_json"]) if saved_custom_trends and saved_custom_trends["filter_json"] else {}
    saved_trends_title = custom_trends_config.get("title", "")
    saved_trends_description = custom_trends_config.get("description", "")
    saved_trends_sections = custom_trends_config.get("sections", [])
    
    # Title and main description - pre-populated with saved values
    trends_title = st.text_input(
        "Slide Title",
        value=saved_trends_title,
        placeholder="e.g., NS Landscape Key Insights",
        key=f"ns_trends_title_{segment['id']}"
    )
    
    trends_description = st.text_area(
        "Overall Comment",
        value=saved_trends_description,
        placeholder="e.g., Key insights from NS performance analysis...",
        height=100,
        key=f"ns_trends_desc_{segment['id']}"
    )
    
    # Number of sections
    num_sections = st.number_input(
        "Number of Sections (1-8)",
        min_value=1,
        max_value=8,
        value=4,
        key=f"ns_trends_num_sections_{segment['id']}"
    )
    
    # Section inputs
    sections_data = []
    for i in range(num_sections):
        st.markdown(f"**Section {i+1}:**")
        
        # Get saved section data if available
        saved_section = saved_trends_sections[i] if i < len(saved_trends_sections) else {}
        saved_left = saved_section.get("left", "")
        saved_right = saved_section.get("right", "")
        
        # Two columns for left and right content (no label field)
        col_left, col_right = st.columns(2)
        
        with col_left:
            left_content = st.text_area(
                f"Left content",
                value=saved_left,
                placeholder="Enter content for left side...",
                height=100,
                key=f"ns_trends_sec{i}_left_{segment['id']}"
            )
        
        with col_right:
            right_content = st.text_area(
                f"Right content",
                value=saved_right,
                placeholder="Enter content for right side...",
                height=100,
                key=f"ns_trends_sec{i}_right_{segment['id']}"
            )
        
        sections_data.append({
            "number": str(i + 1),  # Just use the section number
            "left": left_content,
            "right": right_content
        })
    
    # Preview
    if trends_title or trends_description or any(s["left"] or s["right"] for s in sections_data):
        st.markdown("---")
        st.markdown("**Preview:**")
        
        if trends_title:
            st.markdown(f"### {trends_title}")
        
        if trends_description:
            # Format with bold, underline, etc.
            formatted_desc = format_comment_preview(trends_description)
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
            if section["left"] or section["right"]:
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
                            {section["number"]}
                        </div>
                    """, unsafe_allow_html=True)
                
                with cols[1]:
                    if section["left"]:
                        formatted_left = format_comment_preview(section["left"])
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
                    if section["right"]:
                        formatted_right = format_comment_preview(section["right"])
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
    
    # Save button
    if st.button("Save Summary to Dashboard", key=f"save_ns_trends_{segment['id']}"):
        if not trends_title:
            st.error("Please provide a title for the custom trends view.")
        else:
            # Delete existing custom trends view
            delete_tables_for_section(segment["id"], "NS Landscape", "Custom Trends View")
            
            # Save configuration
            filter_config = json.dumps({
                "title": trends_title,
                "description": trends_description,
                "sections": sections_data
            })
            save_table(
                name="Custom Trends View",
                dataset_id=dataset_id,
                columns=["Custom"],
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=""
            )
            st.success("Custom Trends View saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Delete button next to save
    if saved_custom_trends:
        if st.button("🗑️ Delete Custom Trends View", key=f"delete_ns_trends_{segment['id']}", type="secondary"):
            delete_tables_for_section(segment["id"], "NS Landscape", "Custom Trends View")
            st.success("Custom Trends View deleted!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_segment_truths_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Segment Truths: Title, Image, Comment, and Profile Data"""
    # Removed "Segment Truths Configuration" header
    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    saved_seg_truth = next((t for t in existing_tables if t["section"] == "Segment Truths" and t["name"] == "Segment Truth"), None)
    
    # SECTION 1: First Image Upload (appears before title)
    st.markdown("### Consumer Preference and Behavior Slide")
    st.caption("Upload a slide that will appear at the very top of Segment Truths")
    
    # Get existing first image
    from app_core.media import get_media_for_segment
    existing_media = get_media_for_segment(segment["id"])
    first_image = next((m for m in existing_media if m.get("section") == "Segment Truths" and m.get("name") == "First Image"), None)
    
    if first_image:
        file_path = first_image.get("file_path")
        if file_path and os.path.exists(file_path):
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path, caption="Current Slide", use_container_width=True)
            with col_info:
                first_image_title = st.text_input("Title", value=first_image.get("title", ""), key=f"seg_first_image_title_edit_{segment['id']}")
                first_image_comment = st.text_area("Comment", value=first_image.get("comment", ""), key=f"seg_first_image_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_first_image_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        update_media_metadata(first_image["id"], first_image_title, first_image_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_first_image_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(first_image["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        first_image_title = st.text_input(
            "Slide title",
            key=f"seg_first_image_title_{segment['id']}",
            placeholder="e.g., Segment Overview"
        )
        
        first_image_comment = st.text_area(
            "Slide comment",
            key=f"seg_first_image_comment_{segment['id']}",
            placeholder="Add insights about this image...",
            height=150
        )
        
        uploaded_first_image = st.file_uploader(
            "Upload slide",
            type=["png", "jpg", "jpeg"],
            key=f"seg_truth_first_image_{segment['id']}",
            help="This image will appear at the top before the title"
        )
        
        if uploaded_first_image:
            st.image(uploaded_first_image, caption="Preview", use_container_width=True)
            
            if st.button("Save slide", key=f"save_first_image_{segment['id']}"):
                from app_core.media import save_media_upload
                save_media_upload(
                    uploaded_file=uploaded_first_image,
                    segment_id=segment["id"],
                    section="Segment Truths",
                    created_by=current_user["username"],
                    comment=first_image_comment,
                    label="First Image",
                    title=first_image_title
                )
                st.success("Opening image saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Section header to guide users (non-editable, only visible in Data Studio)
    st.markdown("### Segment Profile Summary")
    st.caption("Configure the segment profile information below")
    
    # Parse saved config
    seg_truth_config = json.loads(saved_seg_truth["filter_json"]) if saved_seg_truth and saved_seg_truth["filter_json"] else {}
    saved_seg_title = seg_truth_config.get("title", "Segment Profile Summary")
    saved_seg_comment = seg_truth_config.get("comment", "")
    
    # Title input - pre-populated with saved value
    segment_title = st.text_input(
        "**Title**",
        value=saved_seg_title,
        placeholder="e.g., Younger (LDA-35yo); Singles & Nuclear Families...",
        key=f"seg_truth_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    # Big comment box - pre-populated with saved value
    st.markdown("**Summary Insights:**")
    segment_comment = st.text_area(
        "Add detailed insights about the segment",
        value=saved_seg_comment,
        placeholder="• 60% Young (LDA-35) consumers; 88% Graduates\n• 57% Urban & 26% Semi-urban\n• Segment over-indexing on SEC A...",
        height=200,
        key=f"seg_truth_comment_{segment['id']}"
    )
    
    # P3M Segment Profile CSV Upload - BEFORE PREVIEW
    st.markdown("---")
    st.markdown("**Segment Profile Data**")
    st.caption("Upload a CSV file with: Column 1 = Metric names, Column 2 = Baseline values, Column 3+ = Comparison values (any number of columns)")
    
    # Load existing P3M profile data
    saved_p3m_profile = next((t for t in existing_tables if t["section"] == "Segment Truths" and t["name"] == "P3M Segment Profile"), None)
    
    if saved_p3m_profile and saved_p3m_profile["filter_json"]:
        st.info("✅ Segment Profile data already uploaded. Upload a new CSV to replace it.")
    
    # CSV file uploader
    uploaded_csv = st.file_uploader(
        "Upload CSV File",
        type=["csv"],
        key=f"p3m_profile_csv_{segment['id']}",
        help="CSV should have at least 3 columns: Metric, Baseline, and one or more comparison columns"
    )
    
    # Variable to hold the CSV data for preview
    df_csv_for_preview = None
    
    if uploaded_csv:
        try:
            # Read CSV
            df_csv = pd.read_csv(uploaded_csv)
            
            # Validate columns
            if len(df_csv.columns) < 3:
                st.error("CSV must have at least 3 columns: Metric, Baseline, and at least one comparison column")
            else:
                # Keep all columns with their original names
                st.success(f"✅ CSV loaded successfully! {len(df_csv)} rows, {len(df_csv.columns)} columns found.")
                
                # Calculate index for each comparison column (columns 3+)
                baseline_col = df_csv.columns[1]  # Column 2 is the baseline
                
                for col_idx in range(2, len(df_csv.columns)):
                    col_name = df_csv.columns[col_idx]
                    index_col_name = f"{col_name}_Index"
                    
                    def calculate_index(row):
                        """Calculate index from baseline and comparison value"""
                        try:
                            baseline_val = str(row[baseline_col]).replace("%", "").replace(",", "").strip()
                            comp_val = str(row[col_name]).replace("%", "").replace(",", "").strip()
                            
                            if not baseline_val or not comp_val or baseline_val == "" or comp_val == "":
                                return None
                            
                            baseline_num = float(baseline_val)
                            comp_num = float(comp_val)
                            
                            if baseline_num == 0:
                                return None
                            
                            return (comp_num / baseline_num) * 100
                        except:
                            return None
                    
                    # Add index column for this comparison column
                    df_csv[index_col_name] = df_csv.apply(calculate_index, axis=1).round(0).astype('Int64')
                
                df_csv_for_preview = df_csv
                
                # Save button for profile
                if st.button("Save Segment Profile", key=f"save_p3m_profile_{segment['id']}"):
                    # Delete existing
                    delete_tables_for_section(segment["id"], "Segment Truths", "P3M Segment Profile")
                    
                    # Save all original columns (without index columns)
                    original_cols = [col for col in df_csv.columns if not col.endswith("_Index")]
                    df_to_save = df_csv[original_cols].copy()
                    profile_dict = df_to_save.to_dict('list')
                    
                    save_table(
                        name="P3M Segment Profile",
                        dataset_id=dataset_id,
                        columns=["Config"],
                        created_by=current_user["username"],
                        segment_id=segment["id"],
                        section="Segment Truths",
                        filter_json=json.dumps(profile_dict),
                        comment=""
                    )
                    st.success("P3M Segment Profile saved to dashboard!")
        
        except Exception as e:
            st.error(f"Error reading CSV: {str(e)}")
            st.info("Please ensure your CSV has 3 columns: Metric, TBA, Premium Whisky")
    elif saved_p3m_profile and saved_p3m_profile["filter_json"]:
        # Load existing data for preview
        try:
            saved_profile_data = json.loads(saved_p3m_profile["filter_json"])
            df_csv = pd.DataFrame(saved_profile_data)
            
            # Calculate index for existing data
            def calculate_index(row):
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
            
            df_csv["_index"] = df_csv.apply(calculate_index, axis=1).round(0).astype('Int64')
            df_csv_for_preview = df_csv
        except:
            pass
    
    # Preview section - NOW SHOWS COMMENT AND TABLE SIDE BY SIDE
    st.markdown("---")
    st.markdown("**Preview:**")
    
    if segment_title:
        st.markdown(f"### {segment_title}")
    
    # Comment box and table side by side
    col1, col2 = st.columns(2)
    
    with col1:
        if segment_comment:
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
                        {segment_comment.replace(chr(10), '<br>')}
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Comment will appear here")
    
    with col2:
        if df_csv_for_preview is not None:
            # Create display dataframe - convert to string and replace NaN with empty strings
            df_display = df_csv_for_preview.copy()
            
            # Get all comparison columns (columns 2 onwards, excluding _index columns)
            comparison_cols = [col for col in df_display.columns if not col.endswith("_Index") and df_display.columns.get_loc(col) >= 2]
            
            # Convert all non-index columns to object type to allow empty strings
            for col in df_display.columns:
                if not col.endswith("_Index"):
                    df_display[col] = df_display[col].astype(str).replace('nan', '').replace('None', '')
            
            # Show table with conditional formatting
            def color_comparison_columns(row):
                """Apply background color to comparison columns based on their index values"""
                styles = [""] * len(row)
                
                for col_idx, col_name in enumerate(df_display.columns):
                    # Check if this is a comparison column (not metric name, not baseline)
                    if col_idx >= 2 and not col_name.endswith("_Index"):
                        # Find corresponding index column
                        index_col_name = f"{col_name}_Index"
                        if index_col_name in df_csv_for_preview.columns:
                            idx_val = df_csv_for_preview.loc[row.name, index_col_name]
                            
                            if not pd.isna(idx_val):
                                try:
                                    if idx_val > 110:
                                        styles[col_idx] = "background-color: #90EE90; font-weight: bold;"
                                    elif idx_val >= 105:
                                        styles[col_idx] = "background-color: #D4EDDA; font-weight: bold;"
                                    elif idx_val < 75:
                                        styles[col_idx] = "background-color: #FFB380; font-weight: bold;"
                                except:
                                    pass
                
                return styles
            
            styled_preview = df_display.style.apply(color_comparison_columns, axis=1)
            
            # Display table (hide all _Index columns)
            column_config = {col: None for col in df_display.columns if col.endswith("_Index")}
            
            st.dataframe(
                styled_preview,
                use_container_width=True,
                hide_index=True,
                height=500,
                column_config=column_config
            )
            
            st.caption("""
                **Color Legend:**
                🟢 Dark Green: Index > 110 | 🟢 Light Green: 105-110 | 🟠 Orange: < 75 | ⚪ White: 75-105
            """)
        else:
            st.info("Segment Profile table will appear here after uploading CSV")
    
    # Save button for title and comment
    if st.button("Save Summary Insights to Dashboard", key=f"save_seg_insights_{segment['id']}"):
        if not segment_title:
            st.error("Please provide a segment title.")
        else:
            # Save configuration as a table entry
            delete_tables_for_section(segment["id"], "Segment Truths", "Segment Truth")
            
            config_data = json.dumps({
                "title": segment_title,
                "comment": segment_comment
            })
            
            save_table(
                name="Segment Truth",
                dataset_id=dataset_id,
                columns=["Config"],
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="Segment Truths",
                filter_json=config_data,
                comment=segment_comment
            )
            st.success("Segment Insights saved to dashboard!")
    
    # CAROUSEL 1: First set of tabbed images
    st.markdown("---")
    st.markdown("### Segment Fit Scores by Needs")
    st.caption("Multiple slides will be displayed as tabs")
    
    # Get existing carousel 1 images
    carousel1_media = [m for m in existing_media if m.get("section") == "Segment Truths" and m.get("name") == "Carousel 1"]
    carousel1_media = sorted(carousel1_media, key=lambda x: x.get("id", 0))
    
    # Show existing carousel images with edit/delete options
    if carousel1_media:
        st.markdown("#### Existing Carousel Slides")
        for idx, media in enumerate(carousel1_media):
            st.markdown(f"**Slide {idx+1}:**")
            file_path = media.get("file_path")
            if file_path and os.path.exists(file_path):
                # Parse existing data
                combined_comment = media.get("comment", "")
                existing_page_title = ""
                existing_comment = ""
                
                if combined_comment and "##PAGE_TITLE##" in combined_comment:
                    parts = combined_comment.split("##PAGE_TITLE##")
                    if len(parts) > 1:
                        remaining = parts[1]
                        if "##COMMENT##" in remaining:
                            page_parts = remaining.split("##COMMENT##")
                            existing_page_title = page_parts[0]
                            existing_comment = page_parts[1] if len(page_parts) > 1 else ""
                        else:
                            existing_page_title = remaining
                else:
                    existing_comment = combined_comment
                
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path, caption=f"Slide {idx+1}", use_container_width=True)
                with col_info:
                    tab_title = st.text_input("Tab Title", value=media.get("title", ""), key=f"carousel1_tab_edit_{media['id']}")
                    page_title = st.text_input("Slide Title", value=existing_page_title, key=f"carousel1_page_edit_{media['id']}")
                    comment = st.text_area("Comment", value=existing_comment, key=f"carousel1_comment_edit_{media['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_carousel1_{media['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            combined_new = f"##PAGE_TITLE##{page_title}##COMMENT##" + comment
                            update_media_metadata(media["id"], tab_title, combined_new)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_carousel1_{media['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(media["id"])
                            st.success("Deleted!")
                            st.rerun()
            
            if idx < len(carousel1_media) - 1:
                st.markdown("---")
        
        st.markdown("---")
    
    # Upload new carousel images section
    st.markdown("#### Upload New Carousel Slides")
    st.caption("Upload multiple slides at once (will be added to existing slides)")
    
    # Use session state to track upload counter for clearing file uploader
    if f"carousel1_upload_counter_{segment['id']}" not in st.session_state:
        st.session_state[f"carousel1_upload_counter_{segment['id']}"] = 0
    
    uploaded_carousel1 = st.file_uploader(
        "Upload Slides (multiple allowed)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"seg_carousel1_{segment['id']}_{st.session_state[f'carousel1_upload_counter_{segment['id']}']}"
    )
    
    carousel1_configs = []
    if uploaded_carousel1:
        st.markdown("**Configure each new carousel image:**")
        
        for idx, img in enumerate(uploaded_carousel1):
            st.markdown(f"**New Carousel Image {idx+1}:**")
            
            col_img, col_inputs = st.columns([1, 1])
            
            with col_img:
                st.image(img, use_container_width=True)
            
            with col_inputs:
                tab_title = st.text_input(
                    "Tab Title (short name)",
                    value=f"Page {len(carousel1_media) + idx+1}",
                    key=f"carousel1_tab_{segment['id']}_{idx}",
                    placeholder=f"e.g., Page {len(carousel1_media) + idx+1}"
                )
                
                page_title = st.text_input(
                    "Slide title",
                    value="",
                    key=f"carousel1_page_{segment['id']}_{idx}",
                    placeholder="e.g., Consumer Demographics"
                )
                
                comment = st.text_area(
                    "Comment (optional)",
                    value="",
                    key=f"carousel1_comment_{segment['id']}_{idx}",
                    placeholder="Add insights...",
                    height=120
                )
            
            carousel1_configs.append({"tab_title": tab_title, "page_title": page_title, "comment": comment})
            
            if idx < len(uploaded_carousel1) - 1:
                st.markdown("---")
    
    # Save button for new carousel images
    if uploaded_carousel1:
        if st.button("Save New Slides", key=f"save_carousel1_{segment['id']}"):
            try:
                from app_core.media import save_media_upload
                
                saved_count = 0
                for idx, uploaded_img in enumerate(uploaded_carousel1):
                    config = carousel1_configs[idx] if idx < len(carousel1_configs) else {"tab_title": f"Page {len(carousel1_media) + idx+1}", "page_title": "", "comment": ""}
                    combined_comment = f"##PAGE_TITLE##{config['page_title']}##COMMENT##" + config["comment"]
                    
                    save_media_upload(
                        uploaded_file=uploaded_img,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=combined_comment,
                        label="Carousel 1",
                        title=config["tab_title"]
                    )
                    saved_count += 1
                
                # Increment counter to clear file uploader on next render
                st.session_state[f"carousel1_upload_counter_{segment['id']}"] += 1
                
                st.success(f"{saved_count} new carousel image(s) saved!")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving carousel images: {str(e)}")
    
    # CAROUSEL 2: Second set of tabbed images
    st.markdown("---")
    st.markdown("### Consumer Taste Preferences")
    st.caption("Multiple slides will be displayed as tabs")
    
    # Get existing carousel 2 images
    carousel2_media = [m for m in existing_media if m.get("section") == "Segment Truths" and m.get("name") == "Carousel 2"]
    carousel2_media = sorted(carousel2_media, key=lambda x: x.get("id", 0))
    
    # Show existing carousel images with edit/delete options
    if carousel2_media:
        st.markdown("#### Existing Carousel Slides")
        for idx, media in enumerate(carousel2_media):
            st.markdown(f"**Slide {idx+1}:**")
            file_path = media.get("file_path")
            if file_path and os.path.exists(file_path):
                # Parse existing data
                combined_comment = media.get("comment", "")
                existing_page_title = ""
                existing_comment = ""
                
                if combined_comment and "##PAGE_TITLE##" in combined_comment:
                    parts = combined_comment.split("##PAGE_TITLE##")
                    if len(parts) > 1:
                        remaining = parts[1]
                        if "##COMMENT##" in remaining:
                            page_parts = remaining.split("##COMMENT##")
                            existing_page_title = page_parts[0]
                            existing_comment = page_parts[1] if len(page_parts) > 1 else ""
                        else:
                            existing_page_title = remaining
                else:
                    existing_comment = combined_comment
                
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path, caption=f"Slide {idx+1}", use_container_width=True)
                with col_info:
                    tab_title = st.text_input("Tab Title", value=media.get("title", ""), key=f"carousel2_tab_edit_{media['id']}")
                    page_title = st.text_input("Slide Title", value=existing_page_title, key=f"carousel2_page_edit_{media['id']}")
                    comment = st.text_area("Comment", value=existing_comment, key=f"carousel2_comment_edit_{media['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_carousel2_{media['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            combined_new = f"##PAGE_TITLE##{page_title}##COMMENT##" + comment
                            update_media_metadata(media["id"], tab_title, combined_new)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_carousel2_{media['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(media["id"])
                            st.success("Deleted!")
                            st.rerun()
            
            if idx < len(carousel2_media) - 1:
                st.markdown("---")
        
        st.markdown("---")
    
    # Upload new carousel images section
    st.markdown("#### Upload New Carousel Slides")
    st.caption("Upload multiple slides at once (will be added to existing slides)")
    
    # Use session state to track upload counter for clearing file uploader
    if f"carousel2_upload_counter_{segment['id']}" not in st.session_state:
        st.session_state[f"carousel2_upload_counter_{segment['id']}"] = 0
    
    uploaded_carousel2 = st.file_uploader(
        "Upload Images for Carousel 2 (multiple allowed)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"seg_carousel2_{segment['id']}_{st.session_state[f'carousel2_upload_counter_{segment['id']}']}"
    )
    
    carousel2_configs = []
    if uploaded_carousel2:
        st.markdown("**Configure each new carousel image:**")
        
        for idx, img in enumerate(uploaded_carousel2):
            st.markdown(f"**New Carousel Image {idx+1}:**")
            
            col_img, col_inputs = st.columns([1, 1])
            
            with col_img:
                st.image(img, use_container_width=True)
            
            with col_inputs:
                tab_title = st.text_input(
                    "Tab Title (short name)",
                    value=f"Page {len(carousel2_media) + idx+1}",
                    key=f"carousel2_tab_{segment['id']}_{idx}",
                    placeholder=f"e.g., Page {len(carousel2_media) + idx+1}"
                )
                
                page_title = st.text_input(
                    "Page Title (full title)",
                    value="",
                    key=f"carousel2_page_{segment['id']}_{idx}",
                    placeholder="e.g., Consumption Patterns"
                )
                
                comment = st.text_area(
                    "Comment (optional)",
                    value="",
                    key=f"carousel2_comment_{segment['id']}_{idx}",
                    placeholder="Add insights...",
                    height=120
                )
            
            carousel2_configs.append({"tab_title": tab_title, "page_title": page_title, "comment": comment})
            
            if idx < len(uploaded_carousel2) - 1:
                st.markdown("---")
    
    # Save button for new carousel 2 images
    if uploaded_carousel2:
        if st.button("Save New Carousel 2 Images", key=f"save_carousel2_{segment['id']}"):
            try:
                from app_core.media import save_media_upload
                
                saved_count = 0
                for idx, uploaded_img in enumerate(uploaded_carousel2):
                    config = carousel2_configs[idx] if idx < len(carousel2_configs) else {"tab_title": f"Page {len(carousel2_media) + idx+1}", "page_title": "", "comment": ""}
                    combined_comment = f"##PAGE_TITLE##{config['page_title']}##COMMENT##" + config["comment"]
                    
                    save_media_upload(
                        uploaded_file=uploaded_img,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=combined_comment,
                        label="Carousel 2",
                        title=config["tab_title"]
                    )
                    saved_count += 1
                
                # Increment counter to clear file uploader on next render
                st.session_state[f"carousel2_upload_counter_{segment['id']}"] += 1
                
                st.success(f"{saved_count} new carousel 2 image(s) saved!")
                st.rerun()
            except Exception as e:
                st.error(f"Error saving carousel 2 images: {str(e)}")
    
    # Image uploads section - SEPARATE
    st.markdown("---")
    st.markdown("### Placeholder Slides")
    
    with st.expander("📸 Upload Placeholder Slides (optional)", expanded=False):
        st.caption("Upload up to 5 images with titles and comments")
        
        # Show existing images if any
        from app_core.media import get_media_for_segment
        existing_media = get_media_for_segment(segment["id"])
        seg_truth_media = [m for m in existing_media if m.get("section") == "Segment Truths" and m.get("name") == "Segment Truth Images"]
        seg_truth_media = sorted(seg_truth_media, key=lambda x: x.get("id", 0))
        
        if seg_truth_media:
            st.info(f"✅ {len(seg_truth_media)} image(s) already uploaded.")
        
        # Image 1
        st.markdown("**Image 1:**")
        existing_1 = seg_truth_media[0] if len(seg_truth_media) > 0 else None
        
        if existing_1:
            file_path_1 = existing_1.get("file_path")
            if file_path_1 and os.path.exists(file_path_1):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_1, caption="Current Image 1", use_container_width=True)
                with col_info:
                    title_1 = st.text_input("Title", value=existing_1.get("title", ""), key=f"seg_truth_1_title_edit_{segment['id']}")
                    comment_1 = st.text_area("Comment", value=existing_1.get("comment", ""), key=f"seg_truth_1_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_truth_1_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_1["id"], title_1, comment_1)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_truth_1_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_1["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_image_1 = st.file_uploader("Upload Image 1", type=["png", "jpg", "jpeg"], key=f"seg_truth_img1_{segment['id']}")
            title_1 = st.text_input("Title for Image 1", key=f"seg_truth_title1_{segment['id']}", placeholder="e.g., Consumer Profile")
            comment_1 = st.text_area("Comment for Image 1", key=f"seg_truth_comment1_{segment['id']}", placeholder="Add description or insights...", height=100)
            
            if st.button("💾 Save Image 1", key=f"save_seg_img1_{segment['id']}"):
                if not uploaded_image_1:
                    st.error("Please upload Image 1.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_image_1,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=comment_1,
                        title=title_1,
                        label="Segment Truth Images"
                    )
                    st.success("Image 1 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Image 2
        st.markdown("**Image 2:**")
        existing_2 = seg_truth_media[1] if len(seg_truth_media) > 1 else None
        
        if existing_2:
            file_path_2 = existing_2.get("file_path")
            if file_path_2 and os.path.exists(file_path_2):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_2, caption="Current Image 2", use_container_width=True)
                with col_info:
                    title_2 = st.text_input("Title", value=existing_2.get("title", ""), key=f"seg_truth_2_title_edit_{segment['id']}")
                    comment_2 = st.text_area("Comment", value=existing_2.get("comment", ""), key=f"seg_truth_2_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_truth_2_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_2["id"], title_2, comment_2)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_truth_2_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_2["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_image_2 = st.file_uploader("Upload Image 2", type=["png", "jpg", "jpeg"], key=f"seg_truth_img2_{segment['id']}")
            title_2 = st.text_input("Title for Image 2", key=f"seg_truth_title2_{segment['id']}", placeholder="e.g., Market Insights")
            comment_2 = st.text_area("Comment for Image 2", key=f"seg_truth_comment2_{segment['id']}", placeholder="Add description or insights...", height=100)
            
            if st.button("💾 Save Image 2", key=f"save_seg_img2_{segment['id']}"):
                if not uploaded_image_2:
                    st.error("Please upload Image 2.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_image_2,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=comment_2,
                        title=title_2,
                        label="Segment Truth Images"
                    )
                    st.success("Image 2 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Image 3
        st.markdown("**Image 3:**")
        existing_3 = seg_truth_media[2] if len(seg_truth_media) > 2 else None
        
        if existing_3:
            file_path_3 = existing_3.get("file_path")
            if file_path_3 and os.path.exists(file_path_3):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_3, caption="Current Image 3", use_container_width=True)
                with col_info:
                    title_3 = st.text_input("Title", value=existing_3.get("title", ""), key=f"seg_truth_3_title_edit_{segment['id']}")
                    comment_3 = st.text_area("Comment", value=existing_3.get("comment", ""), key=f"seg_truth_3_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_truth_3_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_3["id"], title_3, comment_3)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_truth_3_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_3["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_image_3 = st.file_uploader("Upload Image 3", type=["png", "jpg", "jpeg"], key=f"seg_truth_img3_{segment['id']}")
            title_3 = st.text_input("Title for Image 3", key=f"seg_truth_title3_{segment['id']}", placeholder="e.g., Trends Analysis")
            comment_3 = st.text_area("Comment for Image 3", key=f"seg_truth_comment3_{segment['id']}", placeholder="Add description or insights...", height=100)
            
            if st.button("💾 Save Image 3", key=f"save_seg_img3_{segment['id']}"):
                if not uploaded_image_3:
                    st.error("Please upload Image 3.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_image_3,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=comment_3,
                        title=title_3,
                        label="Segment Truth Images"
                    )
                    st.success("Image 3 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Image 4
        st.markdown("**Image 4:**")
        existing_4 = seg_truth_media[3] if len(seg_truth_media) > 3 else None
        col_img4, col_meta4 = st.columns([1, 1])
        # Image 4
        st.markdown("**Image 4:**")
        existing_4 = seg_truth_media[3] if len(seg_truth_media) > 3 else None
        
        if existing_4:
            file_path_4 = existing_4.get("file_path")
            if file_path_4 and os.path.exists(file_path_4):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_4, caption="Current Image 4", use_container_width=True)
                with col_info:
                    title_4 = st.text_input("Title", value=existing_4.get("title", ""), key=f"seg_truth_4_title_edit_{segment['id']}")
                    comment_4 = st.text_area("Comment", value=existing_4.get("comment", ""), key=f"seg_truth_4_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_truth_4_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_4["id"], title_4, comment_4)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_truth_4_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_4["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_image_4 = st.file_uploader("Upload Image 4", type=["png", "jpg", "jpeg"], key=f"seg_truth_img4_{segment['id']}")
            title_4 = st.text_input("Title for Image 4", key=f"seg_truth_title4_{segment['id']}", placeholder="e.g., Additional Insights")
            comment_4 = st.text_area("Comment for Image 4", key=f"seg_truth_comment4_{segment['id']}", placeholder="Add description or insights...", height=100)
            
            if st.button("💾 Save Image 4", key=f"save_seg_img4_{segment['id']}"):
                if not uploaded_image_4:
                    st.error("Please upload Image 4.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_image_4,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=comment_4,
                        title=title_4,
                        label="Segment Truth Images"
                    )
                    st.success("Image 4 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Image 5
        st.markdown("**Image 5:**")
        existing_5 = seg_truth_media[4] if len(seg_truth_media) > 4 else None
        
        if existing_5:
            file_path_5 = existing_5.get("file_path")
            if file_path_5 and os.path.exists(file_path_5):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_5, caption="Current Image 5", use_container_width=True)
                with col_info:
                    title_5 = st.text_input("Title", value=existing_5.get("title", ""), key=f"seg_truth_5_title_edit_{segment['id']}")
                    comment_5 = st.text_area("Comment", value=existing_5.get("comment", ""), key=f"seg_truth_5_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_truth_5_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_5["id"], title_5, comment_5)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_truth_5_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_5["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_image_5 = st.file_uploader("Upload Image 5", type=["png", "jpg", "jpeg"], key=f"seg_truth_img5_{segment['id']}")
            title_5 = st.text_input("Title for Image 5", key=f"seg_truth_title5_{segment['id']}", placeholder="e.g., Summary")
            comment_5 = st.text_area("Comment for Image 5", key=f"seg_truth_comment5_{segment['id']}", placeholder="Add description or insights...", height=100)
            
            if st.button("💾 Save Image 5", key=f"save_seg_img5_{segment['id']}"):
                if not uploaded_image_5:
                    st.error("Please upload Image 5.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_image_5,
                        segment_id=segment["id"],
                        section="Segment Truths",
                        created_by=current_user["username"],
                        comment=comment_5,
                        title=title_5,
                        label="Segment Truth Images"
                    )
                    st.success("Image 5 saved!")
                    st.rerun()


def style_state_summary(state_summary: pd.DataFrame) -> pd.DataFrame:
    """Apply styling to state summary table"""
    def highlight_zone_row(row):
        """Highlight the zone row"""
        state_val = state_summary.loc[row.name, 'State']
        if state_val in ['NORTH', 'WEST+CSD', 'EAST', 'SOUTH']:
            return ['background-color: #E3F2FD; font-weight: bold'] * len(row)
        return [''] * len(row)
    
    def color_negatives_summary(val):
        """Color negative numbers red"""
        if isinstance(val, str):
            if '-' in val or val.startswith('−'):
                return 'color: #D32F2F; font-weight: bold'
        return ''
    
    return state_summary.style.apply(highlight_zone_row, axis=1).applymap(color_negatives_summary)


def render_state_drilldown_preview(preview_data: Dict, selected_states: List[str]) -> None:
    """Render state deep-dive preview with styling"""
    family_colors = {
        0: "#E8F5E9",  # Light Green
        1: "#E3F2FD",  # Light Blue
        2: "#FFF3E0",  # Light Orange
        3: "#F3E5F5",  # Light Purple
        4: "#FCE4EC",  # Light Pink
    }
    
    num_states = min(len(selected_states), 4)
    cols = st.columns(num_states)
    
    for idx, state in enumerate(selected_states[:4]):
        with cols[idx]:
            if state in preview_data['state_details']:
                state_df = preview_data['state_details'][state]
                
                st.markdown(f"""
                    <div style='text-align: center; padding: 0.5rem; background-color: #f0f2f6; border-radius: 0.5rem; margin-bottom: 0.5rem;'>
                        <h3 style='margin: 0; font-size: 1.4rem;'>{state}</h3>
                    </div>
                """, unsafe_allow_html=True)
                
                def highlight_families(row):
                    row_type = state_df.loc[row.name, 'Type']
                    if row_type == 'mfg_com':
                        # Manufacturing Company - bold with golden background
                        return ['background-color: #FFF3CD; font-weight: bold; border-top: 2px solid #f5b400; border-bottom: 1px solid #f5b400; color: #856404'] * len(row)
                    elif row_type == 'family':
                        family_idx = len([i for i in state_df.index[:row.name+1] if state_df.loc[i, 'Type'] == 'family']) - 1
                        color = family_colors[family_idx % len(family_colors)]
                        return [f'background-color: {color}; font-weight: bold'] * len(row)
                    return [''] * len(row)
                
                def color_negatives(val):
                    if isinstance(val, str):
                        if '-' in val or val.startswith('−'):
                            return 'color: #D32F2F; font-weight: bold'
                    return ''
                
                display_df = state_df.drop(columns=['Type'])
                styled_df = display_df.style.apply(highlight_families, axis=1).applymap(color_negatives)
                st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350)
                
                # Info message below table
                st.info("📌 Data for all brands within the manufacturing company")


def calculate_state_performance_table(df_segment: pd.DataFrame, df_full: pd.DataFrame, selected_states: List[str], selected_family: str, segment: Dict) -> pd.DataFrame | None:
    """Calculate state performance analysis table with 12 columns for selected states and brand family
    
    Args:
        df_segment: DataFrame filtered by current segment
        df_full: Full unfiltered DataFrame (all segments) for All Spirits calculation
        selected_states: List of states to include
        selected_family: Brand family to analyze
        segment: Segment dictionary
    """
    
    if df_segment.empty:
        return None
    
    # Ensure Revised NS is numeric
    df_segment = clean_numeric_column(df_segment, "Revised NS")
    
    # Filter for A24 and A25 data
    df_calc = df_segment[df_segment["PRI Year"].isin(["A24", "A25"])].copy()
    df_full_calc = df_full[df_full["PRI Year"].isin(["A24", "A25"])].copy() if df_full is not None and not df_full.empty else df_calc
    
    # Ensure Revised NS is numeric in df_full_calc
    if df_full_calc is not df_calc:
        df_full_calc = clean_numeric_column(df_full_calc, "Revised NS")
    
    if df_calc.empty:
        return None
    
    # Get segment name
    segment_name = segment.get("name", "")
    
    # Calculate ACTUAL All India (AI) values from ALL STATES (not affected by selected states)
    ai_segment_a24 = df_calc[df_calc["PRI Year"] == "A24"]["Revised NS"].sum()
    ai_segment_a25 = df_calc[df_calc["PRI Year"] == "A25"]["Revised NS"].sum()
    
    ai_family_a24 = df_calc[(df_calc["PRI Year"] == "A24") & (df_calc["Brand Family"] == selected_family)]["Revised NS"].sum()
    ai_family_a25 = df_calc[(df_calc["PRI Year"] == "A25") & (df_calc["Brand Family"] == selected_family)]["Revised NS"].sum()
    
    # Calculate All Spirits from ALL STATES (all segments from unfiltered data)
    ai_all_spirits_a24 = df_full_calc[df_full_calc["PRI Year"] == "A24"]["Revised NS"].sum()
    ai_all_spirits_a25 = df_full_calc[df_full_calc["PRI Year"] == "A25"]["Revised NS"].sum()
    
    # AI Growth rates (based on actual All India, not selected states)
    ai_segment_gr = ((ai_segment_a25 - ai_segment_a24) / ai_segment_a24 * 100) if ai_segment_a24 > 0 else 0
    ai_family_gr = ((ai_family_a25 - ai_family_a24) / ai_family_a24 * 100) if ai_family_a24 > 0 else 0
    
    # Calculate metrics for each selected state
    rows = []
    
    for state in selected_states:
        df_state = df_calc[df_calc["State"] == state].copy()
        df_state_full = df_full_calc[df_full_calc["State"] == state].copy() if df_full is not None and not df_full.empty else df_state
        
        if df_state.empty:
            continue
        
        # State-level segment values (current segment only)
        state_segment_a24 = df_state[df_state["PRI Year"] == "A24"]["Revised NS"].sum()
        state_segment_a25 = df_state[df_state["PRI Year"] == "A25"]["Revised NS"].sum()
        
        # State-level brand family values
        state_family_a24 = df_state[(df_state["PRI Year"] == "A24") & (df_state["Brand Family"] == selected_family)]["Revised NS"].sum()
        state_family_a25 = df_state[(df_state["PRI Year"] == "A25") & (df_state["Brand Family"] == selected_family)]["Revised NS"].sum()
        
        # State all spirits (all segments in this state from unfiltered data)
        state_all_spirits_a25 = df_state_full[df_state_full["PRI Year"] == "A25"]["Revised NS"].sum()
        
        # 1. Brand FAM A25 MS (State Level) - Brand Family Market Share within Segment
        bp_fam_ms = (state_family_a25 / state_segment_a25 * 100) if state_segment_a25 > 0 else 0
        
        # 2. Segment Salience to All Spirits A25 - Segment NS / All Spirits NS
        segment_salience = (state_segment_a25 / state_all_spirits_a25 * 100) if state_all_spirits_a25 > 0 else 0
        
        # 3. State Contribution to AI A25 - State Segment NS / AI Segment NS (all states)
        state_contribution = (state_segment_a25 / ai_segment_a25 * 100) if ai_segment_a25 > 0 else 0
        
        # 4. PW A25 NS Gr - Segment Growth Rate (Delta in PW Consumption)
        pw_gr = ((state_segment_a25 - state_segment_a24) / state_segment_a24 * 100) if state_segment_a24 > 0 else 0
        
        # 5. Brand FAM A25 NS Gr - Brand Family Growth Rate (Delta in BP Consumption)
        bp_fam_gr = ((state_family_a25 - state_family_a24) / state_family_a24 * 100) if state_family_a24 > 0 else 0
        
        # 6. Brand FAM BTM - Beat the Market (BP Growth - All India Segment Growth)
        btm = bp_fam_gr - ai_segment_gr
        
        # 7. PW A25 NS Gr (States Indexed to All India) - State Segment Growth / AI Segment Growth * 100
        pw_gr_index = (pw_gr / ai_segment_gr * 100) if ai_segment_gr != 0 else 0
        
        # 8. Brand FAM A25 NS Gr (States Indexed to All India) - State BP Growth / AI BP Growth * 100
        bp_fam_gr_index = (bp_fam_gr / ai_family_gr * 100) if ai_family_gr != 0 else 0
        
        # 8. Brand FAM A25 NS Gr (Indexed to All India BP Fam Gr) - BP Growth / PW Growth (efficiency)
        bp_fam_efficiency = (bp_fam_gr / pw_gr * 100) if pw_gr != 0 else 0
        
        rows.append({
            "State": state,
            "Brand FAM\nA25 MS": bp_fam_ms,
            "Segment\nSalience to\nAll Spirits": segment_salience,
            "State\nContribution\nto AI": state_contribution,
            "Seg A25\nNS Gr": pw_gr,
            "Brand FAM\nA25 NS Gr": bp_fam_gr,
            "Brand FAM\nBTM": btm,
            "Seg Gr\nIndexed\nto AI": pw_gr_index,
            "BP Gr\nIndexed\nto AI": bp_fam_gr_index,
            "BP Gr\nIndexed to\nAI BP Gr": bp_fam_efficiency,
            "MS\nRANK": 0,
            "Salience\nRANK": 0,
            "Contribution\nRANK": 0
        })
    
    if not rows:
        return None
    
    # Create DataFrame
    result_df = pd.DataFrame(rows)
    
    # Add ranking columns
    result_df["MS\nRANK"] = result_df["Brand FAM\nA25 MS"].rank(ascending=False, method='min').astype(int)
    result_df["Salience\nRANK"] = result_df["Segment\nSalience to\nAll Spirits"].rank(ascending=False, method='min').astype(int)
    result_df["Contribution\nRANK"] = result_df["State\nContribution\nto AI"].rank(ascending=False, method='min').astype(int)
    
    # Add AI row at the TOP
    ai_row = {
        "State": "All India",
        "Brand FAM\nA25 MS": (ai_family_a25 / ai_segment_a25 * 100) if ai_segment_a25 > 0 else 0,
        "Segment\nSalience to\nAll Spirits": (ai_segment_a25 / ai_all_spirits_a25 * 100) if ai_all_spirits_a25 > 0 else 0,
        "State\nContribution\nto AI": 100.0,
        "Seg A25\nNS Gr": ai_segment_gr,
        "Brand FAM\nA25 NS Gr": ai_family_gr,
        "Brand FAM\nBTM": ai_family_gr - ai_segment_gr,
        "Seg Gr\nIndexed\nto AI": 100.0,
        "BP Gr\nIndexed\nto AI": 100.0,
        "BP Gr\nIndexed to\nAI BP Gr": (ai_family_gr / ai_segment_gr * 100) if ai_segment_gr != 0 else 0,
        "MS\nRANK": "",
        "Salience\nRANK": "",
        "Contribution\nRANK": ""
    }
    
    # Insert AI row at the beginning (index 0)
    result_df = pd.concat([pd.DataFrame([ai_row]), result_df], ignore_index=True)
    
    return result_df


def render_state_performance_table_html(df: pd.DataFrame) -> str:
    """Render state performance table with colored column groups"""
    
    if df.empty:
        return ""
    
    # Define column groups with colors
    column_groups = [
        {
            "name": "State",
            "columns": ["State"],
            "color": "#E8F5E9",  # Light Green
            "text_color": "#1B5E20"
        },
        {
            "name": "State aggregated to AI",
            "columns": ["Brand FAM A25 MS", "Segment Salience", "State Contribution"],
            "color": "#E8F5E9",  # Light Green
            "text_color": "#1B5E20"
        },
        {
            "name": "NS Growth Data",
            "columns": ["PW A25 NS Gr", "Brand FAM A25 NS Gr"],
            "color": "#FFF3E0",  # Light Orange
            "text_color": "#E65100"
        },
        {
            "name": "Growth Indexation",
            "columns": ["PW Gr Index (AI)", "BP Gr Index (AI)", "BP Efficiency"],
            "color": "#F3E5F5",  # Light Purple
            "text_color": "#4A148C"
        },
        {
            "name": "Salience & Contribution RANKS",
            "columns": ["MS Rank", "Salience Rank", "Contribution Rank"],
            "color": "#FCE4EC",  # Light Pink
            "text_color": "#880E4F"
        }
    ]
    
    # Build HTML table
    html = """
    <div style='overflow-x: auto; margin: 1rem 0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>
        <table style='width: 100%; border-collapse: collapse; font-size: 0.9rem; background: white;'>
            <thead>
    """
    
    # Header row with column group names
    html += "<tr>"
    for group in column_groups:
        colspan = len(group["columns"])
        html += f"""+
            <th colspan='{colspan}' style='
                background: {group["color"]};
                color: {group["text_color"]};
                padding: 1rem 0.5rem;
                text-align: center;
                font-weight: 700;
                font-size: 1rem;
                border: 2px solid white;
            '>{group["name"]}</th>
        """
    html += "</tr>"
    
    # Column names row
    html += "<tr>"
    for group in column_groups:
        for col in group["columns"]:
            # Shorten column names for display
            display_name = col.replace("Brand FAM ", "").replace(" (AI)", "").replace("A25 ", "")
            html += f"""
                <th style='
                    background: {group["color"]};
                    color: {group["text_color"]};
                    padding: 0.7rem 0.5rem;
                    text-align: center;
                    font-weight: 600;
                    font-size: 0.85rem;
                    border: 2px solid white;
                    white-space: nowrap;
                '>{display_name}</th>
            """
    html += "</tr></thead><tbody>"
    
    # Data rows
    for idx, row in df.iterrows():
        is_ai_row = row["State"] == "All India"
        row_bg = "#FFFDE7" if is_ai_row else ("white" if idx % 2 == 0 else "#FAFAFA")
        
        html += "<tr>"
        
        for group in column_groups:
            for col in group["columns"]:
                value = row[col]
                
                # Format values
                if col == "State":
                    display_value = value
                    align = "left"
                    text_style = "font-weight: 600;" if is_ai_row else ""
                elif col in ["MS Rank", "Salience Rank", "Contribution Rank"]:
                    display_value = str(int(value)) if value != "" and value != "-" else "-"
                    align = "center"
                    text_style = "font-weight: 600;" if is_ai_row else ""
                elif isinstance(value, (int, float)):
                    if col in ["Brand FAM A25 MS", "Segment Salience", "State Contribution"]:
                        display_value = f"{value:.1f}%"
                        align = "center"
                        text_style = "font-weight: 600;" if is_ai_row else ""
                    elif col in ["PW A25 NS Gr", "Brand FAM A25 NS Gr"]:
                        display_value = f"{value:+.1f}%"
                        align = "center"
                        # Color negative values red, positive green
                        if value < 0:
                            text_style = "color: #D32F2F; font-weight: 700;"
                        elif value > 0:
                            text_style = "color: #2E7D32; font-weight: 600;"
                        else:
                            text_style = "font-weight: 600;" if is_ai_row else ""
                    elif col in ["PW Gr Index (AI)", "BP Gr Index (AI)", "BP Efficiency"]:
                        display_value = f"{value:.0f}%"
                        align = "center"
                        text_style = "font-weight: 600;" if is_ai_row else ""
                    else:
                        display_value = f"{value:.1f}"
                        align = "center"
                        text_style = "font-weight: 600;" if is_ai_row else ""
                else:
                    display_value = str(value)
                    align = "center"
                    text_style = "font-weight: 600;" if is_ai_row else ""
                
                html += f"""
                    <td style='
                        padding: 0.7rem 0.5rem;
                        text-align: {align};
                        border: 1px solid #E0E0E0;
                        background: {row_bg};
                        font-size: 0.9rem;
                        {text_style}
                    '>{display_value}</td>
                """
        
        html += "</tr>"
    
    html += "</tbody></table></div>"
    
    return html


def display_state_performance_table(df: pd.DataFrame) -> None:
    """Display state performance table as downloadable Streamlit table (without last 6 columns)"""
    
    if df.empty:
        return
    
    # Remove the last 6 columns (Growth Indexation and Ranks)
    columns_to_remove = [
        "Seg Gr\nIndexed\nto AI",
        "Brand Gr\nIndexed\nto AI", 
        "Brand Gr\nIndexed to\nAI Brand Gr",
        "MS\nRANK",
        "Salience\nRANK",
        "Contribution\nRANK"
    ]
    
    # Create a copy and remove unwanted columns
    df_display = df.copy()
    for col in columns_to_remove:
        if col in df_display.columns:
            df_display = df_display.drop(columns=[col])
    
    # Clean up column names (remove \n for better display)
    df_display.columns = [col.replace('\n', ' ') for col in df_display.columns]
    
    # Display as normal Streamlit dataframe (downloadable)
    st.dataframe(df_display, use_container_width=True, hide_index=True)


def create_zone_state_drilldown(df: pd.DataFrame, selected_families: List[str], selected_brands: List[str], selected_states: List[str], zone_name: str, df_full_segment: pd.DataFrame = None) -> Dict | None:
    """Generic function to create state drill-down for any zone
    
    Args:
        df: DataFrame filtered by selected brands
        selected_families: List of brand families to show
        selected_brands: List of brands to show
        selected_states: List of states to include
        zone_name: Name of the zone (e.g., "West+CSD Zone")
        df_full_segment: Full segment data (all brands) for MS denominator calculation
    """
    
    if df.empty:
        return None
    
    # Ensure Revised NS is numeric
    df = clean_numeric_column(df, "Revised NS")
    
    # Use full segment data if provided, otherwise fall back to filtered data
    df_for_denominator = df_full_segment if df_full_segment is not None and not df_full_segment.empty else df
    if df_for_denominator is not df:
        df_for_denominator = clean_numeric_column(df_for_denominator, "Revised NS")
    
    # Filter for specified zone and selected brands/families
    df_zone = df[df["Zone"] == zone_name].copy()
    df_zone = df_zone[df_zone["Brand Family"].isin(selected_families)]
    df_zone = df_zone[df_zone["Brand"].isin(selected_brands)]
    
    if df_zone.empty:
        return None
    
    # Separate A24, A25, and A26 data
    df_a25 = df_zone[df_zone["PRI Year"] == "A25"].copy()
    df_a24 = df_zone[df_zone["PRI Year"] == "A24"].copy()
    
    # A26 YTD data (July-Oct only)
    df_a26_ytd = df_zone[df_zone["PRI Year"] == "A26"].copy()
    if "Month" in df_a26_ytd.columns:
        df_a26_ytd = df_a26_ytd[df_a26_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # A25 YTD data (July-Oct only) for A26 YTD growth comparison
    df_a25_ytd = df_zone[df_zone["PRI Year"] == "A25"].copy()
    if "Month" in df_a25_ytd.columns:
        df_a25_ytd = df_a25_ytd[df_a25_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # Calculate All India totals (for the segment with selected brands)
    df_all = df[df["Brand Family"].isin(selected_families) & df["Brand"].isin(selected_brands)].copy()
    ai_a25_total = df_all[df_all["PRI Year"] == "A25"]["Revised NS"].sum()
    ai_a24_total = df_all[df_all["PRI Year"] == "A24"]["Revised NS"].sum()
    ai_growth = ((ai_a25_total / ai_a24_total) - 1) * 100 if ai_a24_total > 0 else 0
    
    # Calculate All India A26 YTD growth for BTM calculation
    ai_a26_ytd_total = df_all[
        (df_all["PRI Year"] == "A26") & 
        (df_all["Month"].isin(["July", "August", "September", "October"]))
    ]["Revised NS"].sum() if "Month" in df_all.columns else 0
    
    ai_a25_ytd_total = df_all[
        (df_all["PRI Year"] == "A25") & 
        (df_all["Month"].isin(["July", "August", "September", "October"]))
    ]["Revised NS"].sum() if "Month" in df_all.columns else 0
    
    ai_a26_ytd_growth = ((ai_a26_ytd_total / ai_a25_ytd_total) - 1) * 100 if ai_a25_ytd_total > 0 else 0
    
    # ===== STATE SUMMARY TABLE =====
    state_a25 = df_a25.groupby("State")["Revised NS"].sum().to_dict()
    state_a24 = df_a24.groupby("State")["Revised NS"].sum().to_dict()
    state_a26_ytd = df_a26_ytd.groupby("State")["Revised NS"].sum().to_dict()
    state_a25_ytd = df_a25_ytd.groupby("State")["Revised NS"].sum().to_dict()
    
    # Calculate segment totals for ALL brands in each state (for MS denominator)
    df_segment_full = df_for_denominator[df_for_denominator["Zone"] == zone_name].copy()  # All brands in segment in this zone
    segment_state_a25_full = df_segment_full[df_segment_full["PRI Year"] == "A25"].groupby("State")["Revised NS"].sum().to_dict()
    segment_state_a24_full = df_segment_full[df_segment_full["PRI Year"] == "A24"].groupby("State")["Revised NS"].sum().to_dict()
    
    # Calculate zone totals
    zone_a25 = sum(state_a25.values())
    zone_a24 = sum(state_a24.values())
    zone_a26_ytd = sum(state_a26_ytd.values())
    zone_a25_ytd = sum(state_a25_ytd.values())
    zone_sal = (zone_a25 / ai_a25_total * 100) if ai_a25_total > 0 else 0
    zone_growth = ((zone_a25 / zone_a24) - 1) * 100 if zone_a24 > 0 else 0
    zone_a26_ytd_growth = ((zone_a26_ytd / zone_a25_ytd) - 1) * 100 if zone_a25_ytd > 0 else 0
    zone_btm = zone_growth - ai_growth
    zone_a26_ytd_btm = zone_a26_ytd_growth - ai_a26_ytd_growth
    
    # Get zone display name
    zone_display = zone_name.replace(" Zone", "").replace("+", "+").upper()
    
    summary_rows = []
    
    # First row: Zone summary - reordered columns
    summary_rows.append({
        "State": zone_display,
        "A25 Sal % Contribution to AI": f"{zone_sal:.0f}%",
        "A25 Gr": f"{zone_growth:+.1f}%",
        "A26 YTD Gr*": f"{zone_a26_ytd_growth:+.1f}%",
        "A25 BTM": f"{zone_btm:+.1f}%",
        "A26 YTD BTM*": f"{zone_a26_ytd_btm:+.1f}%"
    })
    
    # Then individual states - collect with numeric salience for sorting
    state_rows_with_sal = []
    for state in selected_states:
        a25_ns = state_a25.get(state, 0)
        a24_ns = state_a24.get(state, 0)
        a26_ytd_ns = state_a26_ytd.get(state, 0)
        a25_ytd_ns = state_a25_ytd.get(state, 0)
        
        sal_contribution = (a25_ns / ai_a25_total * 100) if ai_a25_total > 0 else 0
        state_growth = ((a25_ns / a24_ns) - 1) * 100 if a24_ns > 0 else 0
        state_a26_ytd_growth = ((a26_ytd_ns / a25_ytd_ns) - 1) * 100 if a25_ytd_ns > 0 else 0
        btm = state_growth - ai_growth
        a26_ytd_btm = state_a26_ytd_growth - ai_a26_ytd_growth
        
        state_rows_with_sal.append({
            "State": state,
            "A25 Sal % Contribution to AI": f"{sal_contribution:.0f}%",
            "A25 Gr": f"{state_growth:+.1f}%",
            "A26 YTD Gr*": f"{state_a26_ytd_growth:+.1f}%",
            "A25 BTM": f"{btm:+.1f}%",
            "A26 YTD BTM*": f"{a26_ytd_btm:+.1f}%",
            "_sal_numeric": sal_contribution  # For sorting
        })
    
    # Sort states by salience (highest first)
    state_rows_with_sal.sort(key=lambda x: x["_sal_numeric"], reverse=True)
    
    # Remove the numeric sorting column and add to summary_rows
    for row in state_rows_with_sal:
        del row["_sal_numeric"]
        summary_rows.append(row)
    
    state_summary = pd.DataFrame(summary_rows)
    
    # ===== STATE DEEP-DIVE TABLES =====
    # Brand-level data by state (SELECTED brands only)
    brand_state_a25 = df_a25.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a24 = df_a24.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a26_ytd = df_a26_ytd.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a25_ytd = df_a25_ytd.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    
    # Family-level data by state (ALL brands - for Mfg Com calculations)
    df_zone_all = df[df["Zone"] == zone_name].copy()
    df_a25_all = df_zone_all[df_zone_all["PRI Year"] == "A25"].copy()
    df_a24_all = df_zone_all[df_zone_all["PRI Year"] == "A24"].copy()
    df_a26_ytd_all = df_zone_all[df_zone_all["PRI Year"] == "A26"].copy()
    df_a25_ytd_all = df_zone_all[df_zone_all["PRI Year"] == "A25"].copy()
    
    if "Month" in df_a26_ytd_all.columns:
        df_a26_ytd_all = df_a26_ytd_all[df_a26_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    if "Month" in df_a25_ytd_all.columns:
        df_a25_ytd_all = df_a25_ytd_all[df_a25_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    
    family_state_a25_all = df_a25_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a24_all = df_a24_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a26_ytd_all = df_a26_ytd_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a25_ytd_all = df_a25_ytd_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    
    state_details = {}
    
    for state in selected_states:
        # Get segment total for this state (ALL brands, not just selected - for MS calculation)
        segment_state_a25 = segment_state_a25_full.get(state, 0)
        segment_state_a24 = segment_state_a24_full.get(state, 0)
        segment_state_growth = ((segment_state_a25 / segment_state_a24) - 1) * 100 if segment_state_a24 > 0 else 0
        
        # Calculate segment A26 YTD growth for this state (for BTM calculation)
        segment_state_a26_ytd = df_segment_full[
            (df_segment_full["PRI Year"] == "A26") & 
            (df_segment_full["State"] == state) & 
            (df_segment_full["Month"].isin(["July", "August", "September", "October"]))
        ]["Revised NS"].sum() if "Month" in df_segment_full.columns else 0
        
        segment_state_a25_ytd = df_segment_full[
            (df_segment_full["PRI Year"] == "A25") & 
            (df_segment_full["State"] == state) & 
            (df_segment_full["Month"].isin(["July", "August", "September", "October"]))
        ]["Revised NS"].sum() if "Month" in df_segment_full.columns else 0
        
        segment_state_a26_ytd_growth = ((segment_state_a26_ytd / segment_state_a25_ytd) - 1) * 100 if segment_state_a25_ytd > 0 else 0
        
        detail_rows = []
        
        # Group ALL families by Manufacturing Company (not just selected)
        all_families_in_data = df_a25_all["Brand Family"].unique().tolist() if "Brand Family" in df_a25_all.columns else []
        family_to_mfg_all = {}
        for family in all_families_in_data:
            family_data = df_a25_all[df_a25_all["Brand Family"] == family]
            if not family_data.empty and "Mfg Com" in family_data.columns:
                mfg_com = family_data["Mfg Com"].iloc[0]
                family_to_mfg_all[family] = mfg_com
            else:
                family_to_mfg_all[family] = "Unknown"
        
        mfg_to_all_families = {}
        for family, mfg in family_to_mfg_all.items():
            if mfg not in mfg_to_all_families:
                mfg_to_all_families[mfg] = []
            mfg_to_all_families[mfg].append(family)
        
        # Group SELECTED families by Manufacturing Company
        family_to_mfg = {}
        for family in selected_families:
            family_data = df_a25[df_a25["Brand Family"] == family]
            if not family_data.empty and "Mfg Com" in family_data.columns:
                mfg_com = family_data["Mfg Com"].iloc[0]
                family_to_mfg[family] = mfg_com
            else:
                family_to_mfg[family] = "Unknown"
        
        mfg_to_families = {}
        for family, mfg in family_to_mfg.items():
            if mfg not in mfg_to_families:
                mfg_to_families[mfg] = []
            mfg_to_families[mfg].append(family)
        
        # Sort Mfg Companies
        mfg_order = []
        for mfg_name in ["PRI", "Diageo", "Others", "Unknown"]:
            if mfg_name in mfg_to_families:
                mfg_order.append(mfg_name)
        
        for mfg_com in mfg_order:
            families_in_mfg_selected = mfg_to_families[mfg_com]
            families_in_mfg_all = mfg_to_all_families.get(mfg_com, [])
            
            # Add Manufacturing Company header row (using ALL brands in ALL families)
            mfg_a25 = 0
            mfg_a24 = 0
            mfg_a26_ytd = 0
            mfg_a25_ytd = 0
            
            for family in families_in_mfg_all:
                mfg_a25 += family_state_a25_all[
                    (family_state_a25_all["State"] == state) & (family_state_a25_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a24 += family_state_a24_all[
                    (family_state_a24_all["State"] == state) & (family_state_a24_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a26_ytd += family_state_a26_ytd_all[
                    (family_state_a26_ytd_all["State"] == state) & (family_state_a26_ytd_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a25_ytd += family_state_a25_ytd_all[
                    (family_state_a25_ytd_all["State"] == state) & (family_state_a25_ytd_all["Brand Family"] == family)
                ]["Revised NS"].sum()
            
            if mfg_a25 == 0 and mfg_a24 == 0:
                detail_rows.append({
                    "Brand": f"📊 {mfg_com}",
                    "MS": "-",
                    "A25 Gr": "-",
                    "A25 BTM": "-",
                    "A26 YTD Gr*": "-",
                    "A26 YTD BTM*": "-",
                    "Type": "mfg_com"
                })
            else:
                mfg_ms = (mfg_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                mfg_growth = ((mfg_a25 / mfg_a24) - 1) * 100 if mfg_a24 > 0 else 0
                mfg_a26_ytd_growth = ((mfg_a26_ytd / mfg_a25_ytd) - 1) * 100 if mfg_a25_ytd > 0 else 0
                mfg_btm = mfg_growth - ai_growth  # Use All India growth as benchmark
                mfg_a26_ytd_btm = mfg_a26_ytd_growth - ai_a26_ytd_growth  # Use All India A26 YTD growth as benchmark
                
                detail_rows.append({
                    "Brand": f"📊 {mfg_com}",
                    "MS": f"{mfg_ms:.0f}%",
                    "A25 Gr": f"{mfg_growth:+.1f}%",
                    "A25 BTM": f"{mfg_btm:+.0f}%",
                    "A26 YTD Gr*": f"{mfg_a26_ytd_growth:+.1f}%",
                    "A26 YTD BTM*": f"{mfg_a26_ytd_btm:+.0f}%",
                    "Type": "mfg_com"
                })
            
            # Now add SELECTED families under this Mfg Com
            for family in families_in_mfg_selected:
                family_brands_all = []
                for brand in selected_brands:
                    if not brand_state_a25[
                        (brand_state_a25["Brand Family"] == family) & 
                        (brand_state_a25["Brand"] == brand)
                    ].empty:
                        family_brands_all.append(brand)
                
                if not family_brands_all:
                    continue
                
                # Family total row
                family_a25 = brand_state_a25[
                    (brand_state_a25["State"] == state) & (brand_state_a25["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a24 = brand_state_a24[
                (brand_state_a24["State"] == state) & (brand_state_a24["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a26_ytd = brand_state_a26_ytd[
                (brand_state_a26_ytd["State"] == state) & (brand_state_a26_ytd["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a25_ytd = brand_state_a25_ytd[
                (brand_state_a25_ytd["State"] == state) & (brand_state_a25_ytd["Brand Family"] == family)
            ]["Revised NS"].sum()
            
            if family_a25 == 0 and family_a24 == 0:
                detail_rows.append({
                    "Brand": f"  {family} FAM",
                    "MS": "-",
                    "A25 Gr": "-",
                    "A26 YTD Gr*": "-",
                    "A25 BTM": "-",
                    "A26 YTD BTM*": "-",
                    "Type": "family"
                })
            else:
                family_ms = (family_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                family_growth = ((family_a25 / family_a24) - 1) * 100 if family_a24 > 0 else 0
                family_a26_ytd_growth = ((family_a26_ytd / family_a25_ytd) - 1) * 100 if family_a25_ytd > 0 else 0
                family_btm = family_growth - segment_state_growth
                family_a26_ytd_btm = family_a26_ytd_growth - segment_state_a26_ytd_growth
                
                detail_rows.append({
                    "Brand": f"  {family} FAM",
                    "MS": f"{family_ms:.0f}%",
                    "A25 Gr": f"{family_growth:+.1f}%",
                    "A26 YTD Gr*": f"{family_a26_ytd_growth:+.1f}%",
                    "A25 BTM": f"{family_btm:+.0f}%",
                    "A26 YTD BTM*": f"{family_a26_ytd_btm:+.0f}%",
                    "Type": "family"
                })
            
            # Individual brand rows
            for brand in family_brands_all:
                brand_data_a25 = brand_state_a25[
                    (brand_state_a25["State"] == state) & 
                    (brand_state_a25["Brand Family"] == family) & 
                    (brand_state_a25["Brand"] == brand)
                ]
                brand_data_a24 = brand_state_a24[
                    (brand_state_a24["State"] == state) & 
                    (brand_state_a24["Brand Family"] == family) & 
                    (brand_state_a24["Brand"] == brand)
                ]
                brand_data_a26_ytd = brand_state_a26_ytd[
                    (brand_state_a26_ytd["State"] == state) & 
                    (brand_state_a26_ytd["Brand Family"] == family) & 
                    (brand_state_a26_ytd["Brand"] == brand)
                ]
                brand_data_a25_ytd = brand_state_a25_ytd[
                    (brand_state_a25_ytd["State"] == state) & 
                    (brand_state_a25_ytd["Brand Family"] == family) & 
                    (brand_state_a25_ytd["Brand"] == brand)
                ]
                
                brand_a25 = brand_data_a25["Revised NS"].sum() if not brand_data_a25.empty else 0
                brand_a24 = brand_data_a24["Revised NS"].sum() if not brand_data_a24.empty else 0
                brand_a26_ytd = brand_data_a26_ytd["Revised NS"].sum() if not brand_data_a26_ytd.empty else 0
                brand_a25_ytd = brand_data_a25_ytd["Revised NS"].sum() if not brand_data_a25_ytd.empty else 0
                
                if brand_a25 == 0 and brand_a24 == 0:
                    detail_rows.append({
                        "Brand": f"    {brand}",
                        "MS": "-",
                        "A25 Gr": "-",
                        "A26 YTD Gr*": "-",
                        "A25 BTM": "-",
                        "A26 YTD BTM*": "-",
                        "Type": "brand"
                    })
                else:
                    brand_ms = (brand_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 and brand_a25 > 0 else 0
                    brand_growth = ((brand_a25 / brand_a24) - 1) * 100 if brand_a24 > 0 else 0
                    brand_a26_ytd_growth = ((brand_a26_ytd / brand_a25_ytd) - 1) * 100 if brand_a25_ytd > 0 else 0
                    brand_btm = brand_growth - segment_state_growth
                    brand_a26_ytd_btm = brand_a26_ytd_growth - segment_state_a26_ytd_growth
                    
                    detail_rows.append({
                        "Brand": f"    {brand}",
                        "MS": f"{brand_ms:.0f}%",
                        "A25 Gr": f"{brand_growth:+.1f}%",
                        "A26 YTD Gr*": f"{brand_a26_ytd_growth:+.1f}%",
                        "A25 BTM": f"{brand_btm:+.0f}%",
                        "A26 YTD BTM*": f"{brand_a26_ytd_btm:+.0f}%",
                        "Type": "brand"
                    })
        
        if detail_rows:
            state_details[state] = pd.DataFrame(detail_rows)
    
    return {
        "state_summary": state_summary,
        "state_details": state_details,
        "ai_growth": ai_growth
    }


def create_zonal_pivot(df: pd.DataFrame, selected_families: List[str], selected_brands: List[str]) -> pd.DataFrame | None:
    """Create unified zonal pivot table with all zones as columns"""
    
    if df.empty:
        return None
    
    # Ensure Revised NS is numeric
    df = clean_numeric_column(df, "Revised NS")
    
    # Need A24, A25, and A26 data for growth calculation
    df_all = df.copy()
    
    # CRITICAL: Calculate segment totals from ALL brands (not just selected ones)
    # This ensures MS shows true market share vs entire segment
    df_a25_all_brands = df_all[df_all["PRI Year"] == "A25"].copy()
    df_a24_all_brands = df_all[df_all["PRI Year"] == "A24"].copy()
    
    # Get all zones
    zones = sorted(df_a25_all_brands["Zone"].unique().tolist())
    
    # Level 3: Zone only (segment totals per zone) - FROM ALL BRANDS
    segment_zone_a25 = df_a25_all_brands.groupby("Zone")["Revised NS"].sum().to_dict()
    segment_zone_a24 = df_a24_all_brands.groupby("Zone")["Revised NS"].sum().to_dict()
    
    # Calculate segment growth for each zone (from ALL brands) - ONLY FOR DISPLAY, NOT FOR BTM
    segment_growth = {}
    for zone in zones:
        a25_total = segment_zone_a25.get(zone, 0)
        a24_total = segment_zone_a24.get(zone, 0)
        segment_growth[zone] = ((a25_total / a24_total) - 1) * 100 if a24_total > 0 else 0
    
    # Calculate ALL INDIA growth for BTM benchmark (sum across all zones)
    ai_a25_total = sum(segment_zone_a25.values())
    ai_a24_total = sum(segment_zone_a24.values())
    ai_growth = ((ai_a25_total / ai_a24_total) - 1) * 100 if ai_a24_total > 0 else 0
    
    # Calculate ALL INDIA A26 YTD growth for BTM benchmark
    df_a26_ytd_all_brands = df_all[df_all["PRI Year"] == "A26"].copy()
    df_a25_ytd_all_brands = df_all[df_all["PRI Year"] == "A25"].copy()
    
    if "Month" in df_a26_ytd_all_brands.columns:
        df_a26_ytd_all_brands = df_a26_ytd_all_brands[df_a26_ytd_all_brands["Month"].isin(["July", "August", "September", "October"])]
    if "Month" in df_a25_ytd_all_brands.columns:
        df_a25_ytd_all_brands = df_a25_ytd_all_brands[df_a25_ytd_all_brands["Month"].isin(["July", "August", "September", "October"])]
    
    ai_a26_ytd_total = df_a26_ytd_all_brands["Revised NS"].sum()
    ai_a25_ytd_total = df_a25_ytd_all_brands["Revised NS"].sum()
    ai_a26_ytd_growth = ((ai_a26_ytd_total / ai_a25_ytd_total) - 1) * 100 if ai_a25_ytd_total > 0 else 0
    
    # NOW filter to selected brands and families for the table rows
    df_a25 = df_all[(df_all["PRI Year"] == "A25") & 
                    (df_all["Brand Family"].isin(selected_families)) & 
                    (df_all["Brand"].isin(selected_brands))].copy()
    
    df_a24 = df_all[(df_all["PRI Year"] == "A24") & 
                    (df_all["Brand Family"].isin(selected_families)) & 
                    (df_all["Brand"].isin(selected_brands))].copy()
    
    # A26 YTD data (July-Oct only)
    df_a26_ytd = df_all[(df_all["PRI Year"] == "A26") & 
                        (df_all["Brand Family"].isin(selected_families)) & 
                        (df_all["Brand"].isin(selected_brands))].copy()
    if "Month" in df_a26_ytd.columns:
        df_a26_ytd = df_a26_ytd[df_a26_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # A25 YTD data (July-Oct only) for A26 YTD growth comparison
    df_a25_ytd = df_all[(df_all["PRI Year"] == "A25") & 
                        (df_all["Brand Family"].isin(selected_families)) & 
                        (df_all["Brand"].isin(selected_brands))].copy()
    if "Month" in df_a25_ytd.columns:
        df_a25_ytd = df_a25_ytd[df_a25_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # THREE LEVELS OF AGGREGATION FOR SELECTED BRANDS:
    
    # Level 1: Zone × Brand Family × Brand (most granular)
    brand_zone_a25 = df_a25.groupby(["Zone", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_zone_a24 = df_a24.groupby(["Zone", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_zone_a26_ytd = df_a26_ytd.groupby(["Zone", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_zone_a25_ytd = df_a25_ytd.groupby(["Zone", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    
    # Level 2: Zone × Brand Family (family totals per zone)
    family_zone_a25 = df_a25.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a24 = df_a24.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a26_ytd = df_a26_ytd.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a25_ytd = df_a25_ytd.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    
    # Level 2b: Zone × Brand Family (ALL brands - unfiltered, for Mfg Com calculations)
    df_a25_all = df_all[df_all["PRI Year"] == "A25"].copy()
    df_a24_all = df_all[df_all["PRI Year"] == "A24"].copy()
    df_a26_ytd_all = df_all[df_all["PRI Year"] == "A26"].copy()
    df_a25_ytd_all = df_all[df_all["PRI Year"] == "A25"].copy()
    
    if "Month" in df_a26_ytd_all.columns:
        df_a26_ytd_all = df_a26_ytd_all[df_a26_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    if "Month" in df_a25_ytd_all.columns:
        df_a25_ytd_all = df_a25_ytd_all[df_a25_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    
    family_zone_a25_all = df_a25_all.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a24_all = df_a24_all.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a26_ytd_all = df_a26_ytd_all.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    family_zone_a25_ytd_all = df_a25_ytd_all.groupby(["Zone", "Brand Family"])["Revised NS"].sum().reset_index()
    
    # Build unified table
    rows = []
    
    # Group ALL families by Manufacturing Company (not just selected ones)
    # Get all unique families from the unfiltered data
    all_families_in_data = df_a25_all["Brand Family"].unique().tolist() if "Brand Family" in df_a25_all.columns else []
    
    family_to_mfg_all = {}
    for family in all_families_in_data:
        # Get the manufacturing company for this family from the unfiltered data
        family_data = df_a25_all[df_a25_all["Brand Family"] == family]
        if not family_data.empty and "Mfg Com" in family_data.columns:
            mfg_com = family_data["Mfg Com"].iloc[0]
            family_to_mfg_all[family] = mfg_com
        else:
            family_to_mfg_all[family] = "Unknown"
    
    # Group ALL families by Mfg Com
    mfg_to_all_families = {}
    for family, mfg in family_to_mfg_all.items():
        if mfg not in mfg_to_all_families:
            mfg_to_all_families[mfg] = []
        mfg_to_all_families[mfg].append(family)
    
    # Also track which selected families belong to which Mfg Com
    family_to_mfg = {}
    for family in selected_families:
        # Get the manufacturing company for this family from the data
        family_data = df_a25[df_a25["Brand Family"] == family]
        if not family_data.empty and "Mfg Com" in family_data.columns:
            mfg_com = family_data["Mfg Com"].iloc[0]
            family_to_mfg[family] = mfg_com
        else:
            family_to_mfg[family] = "Unknown"
    
    # Group selected families by Mfg Com
    mfg_to_families = {}
    for family, mfg in family_to_mfg.items():
        if mfg not in mfg_to_families:
            mfg_to_families[mfg] = []
        mfg_to_families[mfg].append(family)
    
    # Sort Mfg Companies: PRI, Diageo, Others, Unknown
    mfg_order = []
    for mfg_name in ["PRI", "Diageo", "Others", "Unknown"]:
        if mfg_name in mfg_to_families:
            mfg_order.append(mfg_name)
    
    for mfg_com in mfg_order:
        families_in_mfg_selected = mfg_to_families[mfg_com]  # Selected families for display
        families_in_mfg_all = mfg_to_all_families.get(mfg_com, [])  # ALL families for Mfg Com calculation
        
        # Add Manufacturing Company header row (aggregated from ALL brands in ALL families of this Mfg Com)
        mfg_row = {"Brand": f"📊 {mfg_com}", "Type": "mfg_com"}
        
        # Calculate Mfg Com totals across all zones for salience (ALL brands in ALL families)
        mfg_total_all_zones = 0
        for family in families_in_mfg_all:
            family_total = family_zone_a25_all[family_zone_a25_all["Brand Family"] == family]["Revised NS"].sum()
            mfg_total_all_zones += family_total
        
        for zone in zones:
            # Aggregate all families in this Mfg Com for this zone (ALL brands)
            mfg_sum_a25 = 0
            mfg_sum_a24 = 0
            mfg_sum_a26_ytd = 0
            mfg_sum_a25_ytd = 0
            
            for family in families_in_mfg_all:
                family_zone_data_a25 = family_zone_a25_all[(family_zone_a25_all["Zone"] == zone) & (family_zone_a25_all["Brand Family"] == family)]
                mfg_sum_a25 += family_zone_data_a25["Revised NS"].sum() if not family_zone_data_a25.empty else 0
                
                family_zone_data_a24 = family_zone_a24_all[(family_zone_a24_all["Zone"] == zone) & (family_zone_a24_all["Brand Family"] == family)]
                mfg_sum_a24 += family_zone_data_a24["Revised NS"].sum() if not family_zone_data_a24.empty else 0
                
                family_zone_data_a26_ytd = family_zone_a26_ytd_all[(family_zone_a26_ytd_all["Zone"] == zone) & (family_zone_a26_ytd_all["Brand Family"] == family)]
                mfg_sum_a26_ytd += family_zone_data_a26_ytd["Revised NS"].sum() if not family_zone_data_a26_ytd.empty else 0
                
                family_zone_data_a25_ytd = family_zone_a25_ytd_all[(family_zone_a25_ytd_all["Zone"] == zone) & (family_zone_a25_ytd_all["Brand Family"] == family)]
                mfg_sum_a25_ytd += family_zone_data_a25_ytd["Revised NS"].sum() if not family_zone_data_a25_ytd.empty else 0
                        
            # MS = Mfg Com share in this zone (vs segment total in zone)
            segment_total_zone = segment_zone_a25.get(zone, 0)
            mfg_ms = (mfg_sum_a25 / segment_total_zone * 100) if segment_total_zone > 0 else 0
            
            # Salience = This zone's share of Mfg Com's total across all zones
            mfg_salience = (mfg_sum_a25 / mfg_total_all_zones * 100) if mfg_total_all_zones > 0 else 0
            
            # Growth = Mfg Com growth in this zone
            mfg_growth = ((mfg_sum_a25 / mfg_sum_a24) - 1) * 100 if mfg_sum_a24 > 0 else 0
            
            # A26 YTD Growth
            mfg_a26_ytd_growth = ((mfg_sum_a26_ytd / mfg_sum_a25_ytd) - 1) * 100 if mfg_sum_a25_ytd > 0 else 0
            
            # BTM = Mfg Com growth - ALL INDIA growth (not zone-specific)
            mfg_btm = mfg_growth - ai_growth
            
            # A26 YTD BTM = Mfg Com A26 YTD growth - ALL INDIA A26 YTD growth (not zone-specific)
            mfg_a26_ytd_btm = mfg_a26_ytd_growth - ai_a26_ytd_growth
            
            mfg_row[f"{zone}_MS"] = f"{mfg_ms:.0f}% | {mfg_salience:.0f}%"
            mfg_row[f"{zone}_Gr"] = f"{mfg_growth:.1f}%"
            mfg_row[f"{zone}_BTM"] = f"{mfg_btm:+.0f}%"
            mfg_row[f"{zone}_A26YTD"] = f"{mfg_a26_ytd_growth:.1f}%"
            mfg_row[f"{zone}_A26YTD_BTM"] = f"{mfg_a26_ytd_btm:+.0f}%"
        
        rows.append(mfg_row)
        
        # Now add SELECTED families under this Mfg Com
        for family in families_in_mfg_selected:
            # Get brands in this family from the data
            family_brands_in_data = brand_zone_a25[brand_zone_a25["Brand Family"] == family]["Brand"].unique().tolist()
            family_brands = [b for b in selected_brands if b in family_brands_in_data]
            
            if not family_brands:
                continue
            
            # Add Brand Family header row (indented under Mfg Com)
            family_row = {"Brand": f"  {family} FAM", "Type": "family"}
            
            # Calculate family total across all zones for salience
            family_total_all_zones = family_zone_a25[family_zone_a25["Brand Family"] == family]["Revised NS"].sum()
            
            for zone in zones:
                # Get family totals for this zone
                family_zone_data_a25 = family_zone_a25[(family_zone_a25["Zone"] == zone) & (family_zone_a25["Brand Family"] == family)]
                family_sum_a25 = family_zone_data_a25["Revised NS"].sum() if not family_zone_data_a25.empty else 0
                
                family_zone_data_a24 = family_zone_a24[(family_zone_a24["Zone"] == zone) & (family_zone_a24["Brand Family"] == family)]
                family_sum_a24 = family_zone_data_a24["Revised NS"].sum() if not family_zone_data_a24.empty else 0
                
                # MS = Family share in this zone (vs segment total in zone)
                segment_total_zone = segment_zone_a25.get(zone, 0)
                family_ms = (family_sum_a25 / segment_total_zone * 100) if segment_total_zone > 0 else 0
                
                # Salience = This zone's share of family's total across all zones
                family_salience = (family_sum_a25 / family_total_all_zones * 100) if family_total_all_zones > 0 else 0
                
                # Growth = Family growth in this zone
                family_growth = ((family_sum_a25 / family_sum_a24) - 1) * 100 if family_sum_a24 > 0 else 0
                
                # A26 YTD Growth = (July-Oct A26 - July-Oct A25) / July-Oct A25
                family_zone_data_a26_ytd = family_zone_a26_ytd[(family_zone_a26_ytd["Zone"] == zone) & (family_zone_a26_ytd["Brand Family"] == family)]
                family_sum_a26_ytd = family_zone_data_a26_ytd["Revised NS"].sum() if not family_zone_data_a26_ytd.empty else 0
                
                family_zone_data_a25_ytd = family_zone_a25_ytd[(family_zone_a25_ytd["Zone"] == zone) & (family_zone_a25_ytd["Brand Family"] == family)]
                family_sum_a25_ytd = family_zone_data_a25_ytd["Revised NS"].sum() if not family_zone_data_a25_ytd.empty else 0
                
                family_a26_ytd_growth = ((family_sum_a26_ytd / family_sum_a25_ytd) - 1) * 100 if family_sum_a25_ytd > 0 else 0
                
                # BTM = Family growth - ALL INDIA growth (not zone-specific)
                family_btm = family_growth - ai_growth
                
                # A26 YTD BTM = Family A26 YTD growth - ALL INDIA A26 YTD growth (not zone-specific)
                family_a26_ytd_btm = family_a26_ytd_growth - ai_a26_ytd_growth
                
                family_row[f"{zone}_MS"] = f"{family_ms:.0f}% | {family_salience:.0f}%"
                family_row[f"{zone}_Gr"] = f"{family_growth:.1f}%"
                family_row[f"{zone}_BTM"] = f"{family_btm:+.0f}%"
                family_row[f"{zone}_A26YTD"] = f"{family_a26_ytd_growth:.1f}%"
                family_row[f"{zone}_A26YTD_BTM"] = f"{family_a26_ytd_btm:+.0f}%"
            
            rows.append(family_row)
            
            # Add individual brand rows (further indented)
            for brand in family_brands:
                brand_row = {"Brand": f"    {brand}", "Type": "brand"}
            
            # Calculate brand total across all zones for salience
            brand_total_all_zones = brand_zone_a25[(brand_zone_a25["Brand Family"] == family) & 
                                                     (brand_zone_a25["Brand"] == brand)]["Revised NS"].sum()
            
            for zone in zones:
                # Get brand data for this zone
                brand_zone_data_a25 = brand_zone_a25[(brand_zone_a25["Zone"] == zone) & 
                                                       (brand_zone_a25["Brand Family"] == family) & 
                                                       (brand_zone_a25["Brand"] == brand)]
                a25_val = brand_zone_data_a25["Revised NS"].sum() if not brand_zone_data_a25.empty else 0
                
                brand_zone_data_a24 = brand_zone_a24[(brand_zone_a24["Zone"] == zone) & 
                                                       (brand_zone_a24["Brand Family"] == family) & 
                                                       (brand_zone_a24["Brand"] == brand)]
                a24_val = brand_zone_data_a24["Revised NS"].sum() if not brand_zone_data_a24.empty else 0
                
                # MS = Brand share in this zone (vs segment total in zone)
                segment_total_zone = segment_zone_a25.get(zone, 0)
                ms = (a25_val / segment_total_zone * 100) if segment_total_zone > 0 else 0
                
                # Salience = This zone's share of brand's total across all zones
                salience = (a25_val / brand_total_all_zones * 100) if brand_total_all_zones > 0 else 0
                
                # Growth = Brand growth in this zone
                growth = ((a25_val / a24_val) - 1) * 100 if a24_val > 0 else 0
                
                # A26 YTD Growth = (July-Oct A26 - July-Oct A25) / July-Oct A25
                brand_zone_data_a26_ytd = brand_zone_a26_ytd[(brand_zone_a26_ytd["Zone"] == zone) & 
                                                               (brand_zone_a26_ytd["Brand Family"] == family) & 
                                                               (brand_zone_a26_ytd["Brand"] == brand)]
                a26_ytd_val = brand_zone_data_a26_ytd["Revised NS"].sum() if not brand_zone_data_a26_ytd.empty else 0
                
                brand_zone_data_a25_ytd = brand_zone_a25_ytd[(brand_zone_a25_ytd["Zone"] == zone) & 
                                                               (brand_zone_a25_ytd["Brand Family"] == family) & 
                                                               (brand_zone_a25_ytd["Brand"] == brand)]
                a25_ytd_val = brand_zone_data_a25_ytd["Revised NS"].sum() if not brand_zone_data_a25_ytd.empty else 0
                
                a26_ytd_growth = ((a26_ytd_val / a25_ytd_val) - 1) * 100 if a25_ytd_val > 0 else 0
                
                # BTM = Brand growth - ALL INDIA growth (not zone-specific)
                btm = growth - ai_growth
                
                # A26 YTD BTM = Brand A26 YTD growth - ALL INDIA A26 YTD growth (not zone-specific)
                a26_ytd_btm = a26_ytd_growth - ai_a26_ytd_growth
                
                brand_row[f"{zone}_MS"] = f"{ms:.0f}% | {salience:.0f}%"
                brand_row[f"{zone}_Gr"] = f"{growth:.1f}%"
                brand_row[f"{zone}_BTM"] = f"{btm:+.0f}%"
                brand_row[f"{zone}_A26YTD"] = f"{a26_ytd_growth:.1f}%"
                brand_row[f"{zone}_A26YTD_BTM"] = f"{a26_ytd_btm:+.0f}%"
            
            rows.append(brand_row)
    
    # Create DataFrame
    result = pd.DataFrame(rows)
    
    # Calculate PW Salience for each zone (zone's share of total segment)
    total_segment_a25 = sum(segment_zone_a25.values())
    pw_salience = {}
    for zone in zones:
        pw_salience[zone] = (segment_zone_a25.get(zone, 0) / total_segment_a25 * 100) if total_segment_a25 > 0 else 0
    
    # Store zone info for headers
    result.attrs['zones'] = zones
    result.attrs['segment_growth'] = segment_growth
    result.attrs['segment_totals'] = segment_zone_a25
    result.attrs['pw_salience'] = pw_salience
    
    return result


def create_manufacturing_pivot(df: pd.DataFrame, selected_years: List[str]) -> pd.DataFrame | None:
    """Create manufacturing pivot table with YoY growth and CAGR
    
    For A26: Calculate YTD growth (July-Oct A26 vs July-Oct A25)
    """
    
    # Filter to selected years
    df_years = df[df["PRI Year"].isin(selected_years)].copy()
    
    if df_years.empty:
        return None
    
    # Ensure Revised NS is numeric
    # Clean and convert Revised NS column
    def clean_numeric_value(val):
        """Clean numeric values including accounting format negatives like (123.45)"""
        if pd.isna(val):
            return 0
        
        # Convert to string and strip whitespace
        val_str = str(val).strip()
        
        # Handle accounting format negatives: (123.45) -> -123.45
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1].strip()
        
        # Remove currency symbols and commas
        val_str = val_str.replace('₹', '').replace('$', '').replace(',', '').strip()
        
        # Try to convert to float
        try:
            return float(val_str)
        except (ValueError, TypeError):
            return 0
    
    # Apply cleaning function
    df_years["Revised NS"] = df_years["Revised NS"].apply(clean_numeric_value)
    
    # Check if Month column exists for A26 YTD calculation
    has_month_col = "Month" in df_years.columns
    
    # Month names for July-Oct YTD
    ytd_months = ["July", "August", "September", "October"]
    
    # For A26 YTD calculation, we need July-Oct data from both A25 and A26
    # But we should NOT mix them with full year data to avoid double counting
    if "A26" in selected_years and has_month_col:
        # Keep full year data for A23, A24, A25 ONLY
        df_combined = df_years[df_years["PRI Year"].isin(["A23", "A24", "A25"])].copy()
    else:
        # No Month column or no A26 data - use full year data
        df_combined = df_years.copy()
    
    # Create pivot for full year data
    pivot = pd.pivot_table(
        df_combined[df_combined["PRI Year"].isin(["A23", "A24", "A25"])],
        index="Mfg Com",
        columns="PRI Year",
        values="Revised NS",
        aggfunc="sum",
        fill_value=0
    )
    
    # Reindex to ensure year order (A23, A24, A25 only for now)
    years_for_pivot = [y for y in ["A23", "A24", "A25"] if y in selected_years]
    pivot = pivot.reindex(columns=years_for_pivot, fill_value=0)
    
    # Add Segment Total row
    segment_total = pivot.sum(axis=0).to_frame().T
    segment_total.index = ["Segment Total"]
    pivot = pd.concat([pivot, segment_total], axis=0)
    
    # Keep only growth columns (no base year)
    columns_to_keep = ["Mfg Com"]
    
    # Calculate YoY Growth % for A24 and A25
    for i in range(1, len(years_for_pivot)):
        prev_year = years_for_pivot[i-1]
        curr_year = years_for_pivot[i]
        if prev_year in pivot.columns and curr_year in pivot.columns:
            col_name = f"{curr_year} Growth %"
            pivot[col_name] = ((pivot[curr_year] - pivot[prev_year]) / pivot[prev_year] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)
            columns_to_keep.append(col_name)
    
    # Calculate 2-Year CAGR (A23 to A25)
    if "A23" in selected_years and "A25" in selected_years:
        start = pivot["A23"]
        end = pivot["A25"]
        pivot["2 Yr CAGR % (A23-A25)"] = np.where(
            start > 0,
            ((end / start) ** 0.5 - 1) * 100,
            0
        ).round(1)
        columns_to_keep.append("2 Yr CAGR % (A23-A25)")
    
    # Calculate A26 YTD Growth % (July-Oct A26 vs July-Oct A25)
    if "A26" in selected_years and has_month_col:
        # Month names for July-Oct
        ytd_months = ["July", "August", "September", "October"]
        
        # Calculate A26 YTD (July-Oct) - use df_years, not df_combined
        a26_ytd = df_years[(df_years["PRI Year"] == "A26") & (df_years["Month"].isin(ytd_months))]
        a26_ytd_pivot = pd.pivot_table(
            a26_ytd,
            index="Mfg Com",
            values="Revised NS",
            aggfunc="sum",
            fill_value=0
        )
        
        # Calculate A25 YTD (July-Oct) for comparison - use df_years, not df_combined
        a25_ytd = df_years[(df_years["PRI Year"] == "A25") & (df_years["Month"].isin(ytd_months))]
        a25_ytd_pivot = pd.pivot_table(
            a25_ytd,
            index="Mfg Com",
            values="Revised NS",
            aggfunc="sum",
            fill_value=0
        )
        
        # Add Segment Total for YTD calculations
        a26_ytd_total = a26_ytd_pivot.sum().item() if not a26_ytd_pivot.empty else 0.0
        a25_ytd_total = a25_ytd_pivot.sum().item() if not a25_ytd_pivot.empty else 0.0
        
        # Calculate A26 YTD Growth %* for each Mfg Com
        pivot["A26 YTD Growth %*"] = 0.0
        for mfg_com in pivot.index:
            if mfg_com == "Segment Total":
                # Use totals for Segment Total
                a26_val = a26_ytd_total
                a25_val = a25_ytd_total
            else:
                # Use individual Mfg Com values - extract scalar value
                if mfg_com in a26_ytd_pivot.index:
                    a26_series = a26_ytd_pivot.loc[mfg_com]
                    a26_val = a26_series.item() if hasattr(a26_series, 'item') else float(a26_series)
                else:
                    a26_val = 0.0
                
                if mfg_com in a25_ytd_pivot.index:
                    a25_series = a25_ytd_pivot.loc[mfg_com]
                    a25_val = a25_series.item() if hasattr(a25_series, 'item') else float(a25_series)
                else:
                    a25_val = 0.0
            
            # Calculate growth
            if a25_val > 0:
                growth = ((a26_val - a25_val) / a25_val * 100)
                pivot.loc[mfg_com, "A26 YTD Growth %*"] = round(growth, 1)
            else:
                pivot.loc[mfg_com, "A26 YTD Growth %*"] = 0.0
        
        columns_to_keep.append("A26 YTD Growth %*")
    
    # Reset index to make Mfg Com a column FIRST
    pivot = pivot.reset_index()
    pivot = pivot.rename(columns={"index": "Mfg Com"})
    
    # Sort: Segment Total first, then others
    custom_order = ["Segment Total", "PRI", "Diageo", "Others"]
    pivot["sort_key"] = pivot["Mfg Com"].apply(lambda x: custom_order.index(x) if x in custom_order else 999)
    pivot = pivot.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)
    
    # Calculate A25 BTM (Beat The Market) - Company A25 Growth vs Segment Total A25 Growth
    if "A25 Growth %" in pivot.columns:
        # Get Segment Total A25 Growth (All India benchmark) - it's the first row after sorting
        segment_row = pivot[pivot["Mfg Com"] == "Segment Total"]
        if not segment_row.empty:
            segment_a25_growth = segment_row["A25 Growth %"].iloc[0]
        else:
            segment_a25_growth = 0.0
        
        # Calculate BTM for each Mfg Com
        pivot["A25 BTM"] = 0.0
        for idx in range(len(pivot)):
            mfg_com = pivot.loc[idx, "Mfg Com"]
            if mfg_com == "Segment Total":
                # Segment Total BTM is 0 (comparing to itself)
                pivot.loc[idx, "A25 BTM"] = 0.0
            else:
                # BTM = Company Growth - Segment Growth
                company_growth = pivot.loc[idx, "A25 Growth %"]
                btm = company_growth - segment_a25_growth
                pivot.loc[idx, "A25 BTM"] = round(btm, 1)
        
        columns_to_keep.append("A25 BTM")
    
    # Calculate A26 YTD BTM - Company A26 YTD Growth vs Segment Total A26 YTD Growth
    if "A26 YTD Growth %*" in pivot.columns:
        # Get Segment Total A26 YTD Growth (All India benchmark)
        segment_row = pivot[pivot["Mfg Com"] == "Segment Total"]
        if not segment_row.empty:
            segment_a26_ytd_growth = segment_row["A26 YTD Growth %*"].iloc[0]
        else:
            segment_a26_ytd_growth = 0.0
        
        # Calculate BTM for each Mfg Com
        pivot["A26 YTD BTM*"] = 0.0
        for idx in range(len(pivot)):
            mfg_com = pivot.loc[idx, "Mfg Com"]
            if mfg_com == "Segment Total":
                # Segment Total BTM is 0 (comparing to itself)
                pivot.loc[idx, "A26 YTD BTM*"] = 0.0
            else:
                # BTM = Company Growth - Segment Growth
                company_growth = pivot.loc[idx, "A26 YTD Growth %*"]
                btm = company_growth - segment_a26_ytd_growth
                pivot.loc[idx, "A26 YTD BTM*"] = round(btm, 1)
        
        columns_to_keep.append("A26 YTD BTM*")
    
    # Reorder columns: Mfg Com, Growth columns, CAGR, BTM columns
    column_order = ["Mfg Com"]
    if "A24 Growth %" in pivot.columns:
        column_order.append("A24 Growth %")
    if "A25 Growth %" in pivot.columns:
        column_order.append("A25 Growth %")
    if "A26 YTD Growth %*" in pivot.columns:
        column_order.append("A26 YTD Growth %*")
    if "2 Yr CAGR % (A23-A25)" in pivot.columns:
        column_order.append("2 Yr CAGR % (A23-A25)")
    if "A25 BTM" in pivot.columns:
        column_order.append("A25 BTM")
    if "A26 YTD BTM*" in pivot.columns:
        column_order.append("A26 YTD BTM*")
    
    # Select only required columns in the new order
    final_columns = [col for col in column_order if col in pivot.columns]
    pivot_display = pivot[final_columns].copy()
    
    # Format growth, CAGR, and BTM columns to show % symbol
    for col in pivot_display.columns:
        if 'Growth %' in col or 'CAGR %' in col or 'BTM' in col:
            pivot_display[col] = pivot_display[col].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) and ('BTM' in col) else f"{x:.1f}%" if pd.notna(x) else "0.0%")
    
    return pivot_display


def create_north_state_drilldown(df: pd.DataFrame, selected_families: List[str], selected_brands: List[str], selected_states: List[str], df_full_segment: pd.DataFrame = None) -> Dict | None:
    """Create NORTH zone state drill-down with state summary and brand deep-dive
    
    Formulas:
    - A25 Sal % Contribution to AI = State A25 NS / All India A25 NS × 100
    - A25 Gr (Segment) = (State A25 Seg NS - State A24 Seg NS) / State A24 Seg NS × 100
    - BTM (State vs AI) = State Growth - All India Growth
    - MS (in state) = Brand A25 NS in State / ALL Brands in Segment in State × 100
    - A25 Gr (Brand in state) = (Brand A25 NS - Brand A24 NS) / Brand A24 NS × 100
    - BTM (Brand vs Segment in state) = Brand Growth in State - Segment Growth in State
    
    Args:
        df: DataFrame filtered by selected brands
        selected_families: List of brand families to show
        selected_brands: List of brands to show
        selected_states: List of states to include
        df_full_segment: Full segment data (all brands) for MS denominator calculation
    """
    
    if df.empty:
        return None
    
    # Ensure Revised NS is numeric
    df = clean_numeric_column(df, "Revised NS")
    
    # Use full segment data if provided, otherwise fall back to filtered data
    df_for_denominator = df_full_segment if df_full_segment is not None and not df_full_segment.empty else df
    if df_for_denominator is not df:
        df_for_denominator = clean_numeric_column(df_for_denominator, "Revised NS")
    
    # Filter for NORTH zone and selected brands/families
    df_north = df[df["Zone"] == "North Zone"].copy()
    df_north = df_north[df_north["Brand Family"].isin(selected_families)]
    df_north = df_north[df_north["Brand"].isin(selected_brands)]
    
    if df_north.empty:
        return None
    
    # Separate A24, A25, and A26 data
    df_a25 = df_north[df_north["PRI Year"] == "A25"].copy()
    df_a24 = df_north[df_north["PRI Year"] == "A24"].copy()
    
    # A26 YTD data (July-Oct only)
    df_a26_ytd = df_north[df_north["PRI Year"] == "A26"].copy()
    if "Month" in df_a26_ytd.columns:
        df_a26_ytd = df_a26_ytd[df_a26_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # A25 YTD data (July-Oct only) for A26 YTD growth comparison
    df_a25_ytd = df_north[df_north["PRI Year"] == "A25"].copy()
    if "Month" in df_a25_ytd.columns:
        df_a25_ytd = df_a25_ytd[df_a25_ytd["Month"].isin(["July", "August", "September", "October"])]
    
    # Calculate All India totals (for the segment with selected brands)
    df_all = df[df["Brand Family"].isin(selected_families) & df["Brand"].isin(selected_brands)].copy()
    ai_a25_total = df_all[df_all["PRI Year"] == "A25"]["Revised NS"].sum()
    ai_a24_total = df_all[df_all["PRI Year"] == "A24"]["Revised NS"].sum()
    ai_growth = ((ai_a25_total / ai_a24_total) - 1) * 100 if ai_a24_total > 0 else 0
    
    # Calculate All India A26 YTD growth for BTM calculation
    ai_a26_ytd_total = df_all[
        (df_all["PRI Year"] == "A26") & 
        (df_all["Month"].isin(["July", "August", "September", "October"]))
    ]["Revised NS"].sum() if "Month" in df_all.columns else 0
    
    ai_a25_ytd_total = df_all[
        (df_all["PRI Year"] == "A25") & 
        (df_all["Month"].isin(["July", "August", "September", "October"]))
    ]["Revised NS"].sum() if "Month" in df_all.columns else 0
    
    ai_a26_ytd_growth = ((ai_a26_ytd_total / ai_a25_ytd_total) - 1) * 100 if ai_a25_ytd_total > 0 else 0
    
    # ===== STATE SUMMARY TABLE =====
    # Aggregate by state for segment totals (selected brands only for summary)
    state_a25 = df_a25.groupby("State")["Revised NS"].sum().to_dict()
    state_a24 = df_a24.groupby("State")["Revised NS"].sum().to_dict()
    state_a26_ytd = df_a26_ytd.groupby("State")["Revised NS"].sum().to_dict()
    state_a25_ytd = df_a25_ytd.groupby("State")["Revised NS"].sum().to_dict()
    
    # Calculate segment totals for ALL brands in each state (for MS denominator)
    df_segment_full = df_for_denominator[df_for_denominator["Zone"] == "North Zone"].copy()  # All brands in segment in North Zone
    segment_state_a25_full = df_segment_full[df_segment_full["PRI Year"] == "A25"].groupby("State")["Revised NS"].sum().to_dict()
    segment_state_a24_full = df_segment_full[df_segment_full["PRI Year"] == "A24"].groupby("State")["Revised NS"].sum().to_dict()
    
    # Calculate NORTH zone totals (sum of all states in North Zone)
    north_zone_a25 = sum(state_a25.values())
    north_zone_a24 = sum(state_a24.values())
    north_zone_a26_ytd = sum(state_a26_ytd.values())
    north_zone_a25_ytd = sum(state_a25_ytd.values())
    north_zone_sal = (north_zone_a25 / ai_a25_total * 100) if ai_a25_total > 0 else 0
    north_zone_growth = ((north_zone_a25 / north_zone_a24) - 1) * 100 if north_zone_a24 > 0 else 0
    north_zone_a26_ytd_growth = ((north_zone_a26_ytd / north_zone_a25_ytd) - 1) * 100 if north_zone_a25_ytd > 0 else 0
    north_zone_btm = north_zone_growth - ai_growth
    north_zone_a26_ytd_btm = north_zone_a26_ytd_growth - ai_a26_ytd_growth
    
    summary_rows = []
    
    # First row: NORTH zone summary - reordered columns
    summary_rows.append({
        "State": "NORTH",
        "A25 Sal % Contribution to AI": f"{north_zone_sal:.0f}%",
        "A25 Gr": f"{north_zone_growth:+.1f}%",
        "A26 YTD Gr*": f"{north_zone_a26_ytd_growth:+.1f}%",
        "A25 BTM": f"{north_zone_btm:+.1f}%",
        "A26 YTD BTM*": f"{north_zone_a26_ytd_btm:+.1f}%"
    })
    
    # Then individual states - collect with numeric salience for sorting
    state_rows_with_sal = []
    for state in selected_states:
        a25_ns = state_a25.get(state, 0)
        a24_ns = state_a24.get(state, 0)
        a26_ytd_ns = state_a26_ytd.get(state, 0)
        a25_ytd_ns = state_a25_ytd.get(state, 0)
        
        # A25 Sal % Contribution to AI
        sal_contribution = (a25_ns / ai_a25_total * 100) if ai_a25_total > 0 else 0
        
        # A25 Growth (Segment in state)
        state_growth = ((a25_ns / a24_ns) - 1) * 100 if a24_ns > 0 else 0
        
        # A26 YTD Growth
        state_a26_ytd_growth = ((a26_ytd_ns / a25_ytd_ns) - 1) * 100 if a25_ytd_ns > 0 else 0
        
        # BTM (State vs AI)
        btm = state_growth - ai_growth
        
        # A26 YTD BTM (State vs AI)
        a26_ytd_btm = state_a26_ytd_growth - ai_a26_ytd_growth
        
        state_rows_with_sal.append({
            "State": state,
            "A25 Sal % Contribution to AI": f"{sal_contribution:.0f}%",
            "A25 Gr": f"{state_growth:+.1f}%",
            "A26 YTD Gr*": f"{state_a26_ytd_growth:+.1f}%",
            "A25 BTM": f"{btm:+.1f}%",
            "A26 YTD BTM*": f"{a26_ytd_btm:+.1f}%",
            "_sal_numeric": sal_contribution  # Store numeric value for sorting
        })
    
    # Sort states by salience (highest first)
    state_rows_with_sal.sort(key=lambda x: x["_sal_numeric"], reverse=True)
    
    # Remove the numeric salience field before creating DataFrame
    for row in state_rows_with_sal:
        row.pop("_sal_numeric", None)
    
    # Combine zone row + sorted state rows
    summary_rows.extend(state_rows_with_sal)
    
    state_summary = pd.DataFrame(summary_rows)
    
    # ===== STATE DEEP-DIVE TABLES =====
    # Brand-level data by state (SELECTED brands only)
    brand_state_a25 = df_a25.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a24 = df_a24.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a26_ytd = df_a26_ytd.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    brand_state_a25_ytd = df_a25_ytd.groupby(["State", "Brand Family", "Brand"])["Revised NS"].sum().reset_index()
    
    # Family-level data by state (ALL brands - for Mfg Com calculations)
    df_north_all = df[df["Zone"] == "North Zone"].copy()
    df_a25_all = df_north_all[df_north_all["PRI Year"] == "A25"].copy()
    df_a24_all = df_north_all[df_north_all["PRI Year"] == "A24"].copy()
    df_a26_ytd_all = df_north_all[df_north_all["PRI Year"] == "A26"].copy()
    df_a25_ytd_all = df_north_all[df_north_all["PRI Year"] == "A25"].copy()
    
    if "Month" in df_a26_ytd_all.columns:
        df_a26_ytd_all = df_a26_ytd_all[df_a26_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    if "Month" in df_a25_ytd_all.columns:
        df_a25_ytd_all = df_a25_ytd_all[df_a25_ytd_all["Month"].isin(["July", "August", "September", "October"])]
    
    family_state_a25_all = df_a25_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a24_all = df_a24_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a26_ytd_all = df_a26_ytd_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    family_state_a25_ytd_all = df_a25_ytd_all.groupby(["State", "Brand Family"])["Revised NS"].sum().reset_index()
    
    state_details = {}
    
    for state in selected_states:
        # Get segment total for this state (ALL brands, not just selected - for MS calculation)
        segment_state_a25 = segment_state_a25_full.get(state, 0)
        segment_state_a24 = segment_state_a24_full.get(state, 0)
        segment_state_growth = ((segment_state_a25 / segment_state_a24) - 1) * 100 if segment_state_a24 > 0 else 0
        
        # Calculate segment A26 YTD growth for this state (for BTM calculation)
        segment_state_a26_ytd = df_segment_full[
            (df_segment_full["PRI Year"] == "A26") & 
            (df_segment_full["State"] == state) & 
            (df_segment_full["Month"].isin(["July", "August", "September", "October"]))
        ]["Revised NS"].sum() if "Month" in df_segment_full.columns else 0
        
        segment_state_a25_ytd = df_segment_full[
            (df_segment_full["PRI Year"] == "A25") & 
            (df_segment_full["State"] == state) & 
            (df_segment_full["Month"].isin(["July", "August", "September", "October"]))
        ]["Revised NS"].sum() if "Month" in df_segment_full.columns else 0
        
        segment_state_a26_ytd_growth = ((segment_state_a26_ytd / segment_state_a25_ytd) - 1) * 100 if segment_state_a25_ytd > 0 else 0
        
        detail_rows = []
        
        # Group ALL families by Manufacturing Company (not just selected)
        all_families_in_data = df_a25_all["Brand Family"].unique().tolist() if "Brand Family" in df_a25_all.columns else []
        family_to_mfg_all = {}
        for family in all_families_in_data:
            family_data = df_a25_all[df_a25_all["Brand Family"] == family]
            if not family_data.empty and "Mfg Com" in family_data.columns:
                mfg_com = family_data["Mfg Com"].iloc[0]
                family_to_mfg_all[family] = mfg_com
            else:
                family_to_mfg_all[family] = "Unknown"
        
        mfg_to_all_families = {}
        for family, mfg in family_to_mfg_all.items():
            if mfg not in mfg_to_all_families:
                mfg_to_all_families[mfg] = []
            mfg_to_all_families[mfg].append(family)
        
        # Group SELECTED families by Manufacturing Company
        family_to_mfg = {}
        for family in selected_families:
            family_data = df_a25[df_a25["Brand Family"] == family]
            if not family_data.empty and "Mfg Com" in family_data.columns:
                mfg_com = family_data["Mfg Com"].iloc[0]
                family_to_mfg[family] = mfg_com
            else:
                family_to_mfg[family] = "Unknown"
        
        # Group families by Mfg Com
        mfg_to_families = {}
        for family, mfg in family_to_mfg.items():
            if mfg not in mfg_to_families:
                mfg_to_families[mfg] = []
            mfg_to_families[mfg].append(family)
        
        # Sort Mfg Companies
        mfg_order = []
        for mfg_name in ["PRI", "Diageo", "Others", "Unknown"]:
            if mfg_name in mfg_to_families:
                mfg_order.append(mfg_name)
        
        for mfg_com in mfg_order:
            families_in_mfg_selected = mfg_to_families[mfg_com]  # Selected families for display
            families_in_mfg_all = mfg_to_all_families.get(mfg_com, [])  # ALL families for Mfg Com calculation
            
            # Add Manufacturing Company header row (using ALL brands in ALL families)
            mfg_a25 = 0
            mfg_a24 = 0
            mfg_a26_ytd = 0
            mfg_a25_ytd = 0
            
            for family in families_in_mfg_all:
                mfg_a25 += family_state_a25_all[
                    (family_state_a25_all["State"] == state) & (family_state_a25_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a24 += family_state_a24_all[
                    (family_state_a24_all["State"] == state) & (family_state_a24_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a26_ytd += family_state_a26_ytd_all[
                    (family_state_a26_ytd_all["State"] == state) & (family_state_a26_ytd_all["Brand Family"] == family)
                ]["Revised NS"].sum()
                mfg_a25_ytd += family_state_a25_ytd_all[
                    (family_state_a25_ytd_all["State"] == state) & (family_state_a25_ytd_all["Brand Family"] == family)
                ]["Revised NS"].sum()
            
            if mfg_a25 == 0 and mfg_a24 == 0:
                detail_rows.append({
                    "Brand": f"📊 {mfg_com}",
                    "MS": "-",
                    "A25 Gr": "-",
                    "A26 YTD Gr*": "-",
                    "A25 BTM": "-",
                    "A26 YTD BTM*": "-",
                    "Type": "mfg_com"
                })
            else:
                mfg_ms = (mfg_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                mfg_growth = ((mfg_a25 / mfg_a24) - 1) * 100 if mfg_a24 > 0 else 0
                mfg_a26_ytd_growth = ((mfg_a26_ytd / mfg_a25_ytd) - 1) * 100 if mfg_a25_ytd > 0 else 0
                mfg_btm = mfg_growth - ai_growth  # Use All India growth as benchmark
                mfg_a26_ytd_btm = mfg_a26_ytd_growth - ai_a26_ytd_growth  # Use All India A26 YTD growth as benchmark
                
                detail_rows.append({
                    "Brand": f"📊 {mfg_com}",
                    "MS": f"{mfg_ms:.0f}%",
                    "A25 Gr": f"{mfg_growth:+.1f}%",
                    "A26 YTD Gr*": f"{mfg_a26_ytd_growth:+.1f}%",
                    "A25 BTM": f"{mfg_btm:+.0f}%",
                    "A26 YTD BTM*": f"{mfg_a26_ytd_btm:+.0f}%",
                    "Type": "mfg_com"
                })
            
            # Now add SELECTED families under this Mfg Com
            for family in families_in_mfg_selected:
                # Get ALL brands in this family from selected_brands (show all, even if 0 in this state)
                # First check which brands in selected_brands belong to this family
                family_brands_all = []
            for brand in selected_brands:
                # Check if this brand belongs to this family in ANY state
                if not brand_state_a25[
                    (brand_state_a25["Brand Family"] == family) & 
                    (brand_state_a25["Brand"] == brand)
                ].empty:
                    family_brands_all.append(brand)
            
            if not family_brands_all:
                continue
            
            # Family total row - sum across all brands in family for this state
            family_a25 = brand_state_a25[
                (brand_state_a25["State"] == state) & (brand_state_a25["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a24 = brand_state_a24[
                (brand_state_a24["State"] == state) & (brand_state_a24["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a26_ytd = brand_state_a26_ytd[
                (brand_state_a26_ytd["State"] == state) & (brand_state_a26_ytd["Brand Family"] == family)
            ]["Revised NS"].sum()
            family_a25_ytd = brand_state_a25_ytd[
                (brand_state_a25_ytd["State"] == state) & (brand_state_a25_ytd["Brand Family"] == family)
            ]["Revised NS"].sum()
            
            # If family has no sales in this state, show "-"
            if family_a25 == 0 and family_a24 == 0:
                detail_rows.append({
                    "Brand": f"  {family} FAM",
                    "MS": "-",
                    "A25 Gr": "-",
                    "A26 YTD Gr*": "-",
                    "A25 BTM": "-",
                    "A26 YTD BTM*": "-",
                    "Type": "family"
                })
            else:
                family_ms = (family_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                family_growth = ((family_a25 / family_a24) - 1) * 100 if family_a24 > 0 else 0
                family_a26_ytd_growth = ((family_a26_ytd / family_a25_ytd) - 1) * 100 if family_a25_ytd > 0 else 0
                family_btm = family_growth - ai_growth  # Use All India growth as benchmark
                family_a26_ytd_btm = family_a26_ytd_growth - ai_a26_ytd_growth  # Use All India A26 YTD growth as benchmark
                
                detail_rows.append({
                    "Brand": f"  {family} FAM",
                    "MS": f"{family_ms:.0f}%",
                    "A25 Gr": f"{family_growth:+.1f}%",
                    "A26 YTD Gr*": f"{family_a26_ytd_growth:+.1f}%",
                    "A25 BTM": f"{family_btm:+.0f}%",
                    "A26 YTD BTM*": f"{family_a26_ytd_btm:+.0f}%",
                    "Type": "family"
                })
            
            # Individual brand rows - show ALL brands in family, even if 0 in this state
            for brand in family_brands_all:
                brand_data_a25 = brand_state_a25[
                    (brand_state_a25["State"] == state) & 
                    (brand_state_a25["Brand Family"] == family) & 
                    (brand_state_a25["Brand"] == brand)
                ]
                brand_data_a24 = brand_state_a24[
                    (brand_state_a24["State"] == state) & 
                    (brand_state_a24["Brand Family"] == family) & 
                    (brand_state_a24["Brand"] == brand)
                ]
                brand_data_a26_ytd = brand_state_a26_ytd[
                    (brand_state_a26_ytd["State"] == state) & 
                    (brand_state_a26_ytd["Brand Family"] == family) & 
                    (brand_state_a26_ytd["Brand"] == brand)
                ]
                brand_data_a25_ytd = brand_state_a25_ytd[
                    (brand_state_a25_ytd["State"] == state) & 
                    (brand_state_a25_ytd["Brand Family"] == family) & 
                    (brand_state_a25_ytd["Brand"] == brand)
                ]
                
                # Always show brand, even if 0
                brand_a25 = brand_data_a25["Revised NS"].sum() if not brand_data_a25.empty else 0
                brand_a24 = brand_data_a24["Revised NS"].sum() if not brand_data_a24.empty else 0
                brand_a26_ytd = brand_data_a26_ytd["Revised NS"].sum() if not brand_data_a26_ytd.empty else 0
                brand_a25_ytd = brand_data_a25_ytd["Revised NS"].sum() if not brand_data_a25_ytd.empty else 0
                
                # If brand has no sales in this state (both A25 and A24 are 0), show "-"
                if brand_a25 == 0 and brand_a24 == 0:
                    detail_rows.append({
                        "Brand": f"    {brand}",
                        "MS": "-",
                        "A25 Gr": "-",
                        "A26 YTD Gr*": "-",
                        "A25 BTM": "-",
                        "A26 YTD BTM*": "-",
                        "Type": "brand"
                    })
                else:
                    brand_ms = (brand_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 and brand_a25 > 0 else 0
                    brand_growth = ((brand_a25 / brand_a24) - 1) * 100 if brand_a24 > 0 else 0
                    brand_a26_ytd_growth = ((brand_a26_ytd / brand_a25_ytd) - 1) * 100 if brand_a25_ytd > 0 else 0
                    brand_btm = brand_growth - ai_growth  # Use All India growth as benchmark
                    brand_a26_ytd_btm = brand_a26_ytd_growth - ai_a26_ytd_growth  # Use All India A26 YTD growth as benchmark
                    
                    detail_rows.append({
                        "Brand": f"    {brand}",
                        "MS": f"{brand_ms:.0f}%",
                        "A25 Gr": f"{brand_growth:+.1f}%",
                        "A26 YTD Gr*": f"{brand_a26_ytd_growth:+.1f}%",
                        "A25 BTM": f"{brand_btm:+.0f}%",
                        "A26 YTD BTM*": f"{brand_a26_ytd_btm:+.0f}%",
                        "Type": "brand"
                    })
        
        if detail_rows:
            state_details[state] = pd.DataFrame(detail_rows)
    
    return {
        "state_summary": state_summary,
        "state_details": state_details,
        "ai_growth": ai_growth
    }


def format_extra_comments(extras: list[str] | None) -> str:
    if not extras:
        return ""
    bullet_lines = [f"• {c}" for c in extras]
    return "\n" + "\n".join(bullet_lines)



def render_segment_trends_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Segment Trends: Images and Carousel"""

    
    # Get existing media
    from app_core.media import get_media_for_segment
    existing_media = get_media_for_segment(segment["id"])
    
    # Get existing images
    trend_images = [m for m in existing_media if m.get("section") == "Segment Trends" and m.get("name") == "Additional Images"]
    
    # Create a dictionary mapping slot numbers to images
    slot_map = {}
    for img in trend_images:
        comment = img.get("comment", "")
        if comment.startswith("SLOT:"):
            try:
                slot_num = int(comment.split("##")[0].replace("SLOT:", ""))
                slot_map[slot_num] = img
            except:
                pass
    
    # Section title for image uploads
    st.markdown("---")
    st.markdown("### Analysis Slides")
    st.caption("Upload slides and add title and comment")
    
    # Segment Growth Slide
    st.markdown("**Segment Growth Slide**")
    existing_1 = slot_map.get(1, None)
    
    if existing_1:
        file_path_1 = existing_1.get("file_path")
        if file_path_1 and os.path.exists(file_path_1):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_1.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_1, caption="Current Slide", use_container_width=True)
            with col_info:
                title_add_1 = st.text_input("Title", value=existing_1.get("title", ""), key=f"seg_trends_1_title_edit_{segment['id']}")
                comment_add_1 = st.text_area("Comment", value=actual_comment, key=f"seg_trends_1_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_trends_1_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:1##" + comment_add_1
                        update_media_metadata(existing_1["id"], title_add_1, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_trends_1_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_1["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_add_1 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"seg_trends_add_1_{segment['id']}")
        title_add_1 = st.text_input("Slide Title", key=f"seg_trends_add_title_1_{segment['id']}")
        comment_add_1 = st.text_area("Slide Comment", key=f"seg_trends_add_comment_1_{segment['id']}", height=150)
        
        if st.button("Save Slide 1", key=f"save_seg_trends_1_{segment['id']}"):
            if not uploaded_add_1:
                st.error("Please upload Image 1.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:1##" + comment_add_1
                save_media_upload(
                    uploaded_file=uploaded_add_1,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_add_1,
                    label="Additional Images"
                )
                st.success("Image 1 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # P3M Interactions Slide
    st.markdown("**P3M Interactions Slide**")
    existing_2 = slot_map.get(2, None)
    
    if existing_2:
        file_path_2 = existing_2.get("file_path")
        if file_path_2 and os.path.exists(file_path_2):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_2.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_2, caption="Current Slide", use_container_width=True)
            with col_info:
                title_add_2 = st.text_input("Title", value=existing_2.get("title", ""), key=f"seg_trends_2_title_edit_{segment['id']}")
                comment_add_2 = st.text_area("Comment", value=actual_comment, key=f"seg_trends_2_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_trends_2_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:2##" + comment_add_2
                        update_media_metadata(existing_2["id"], title_add_2, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_trends_2_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_2["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_add_2 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"seg_trends_add_2_{segment['id']}")
        title_add_2 = st.text_input("Slide Title", key=f"seg_trends_add_title_2_{segment['id']}")
        comment_add_2 = st.text_area("Slide Comment", key=f"seg_trends_add_comment_2_{segment['id']}", height=150)
        
        if st.button("Save Slide 2", key=f"save_seg_trends_2_{segment['id']}"):
            if not uploaded_add_2:
                st.error("Please upload Image 2.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:2##" + comment_add_2
                save_media_upload(
                    uploaded_file=uploaded_add_2,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_add_2,
                    label="Additional Images"
                )
                st.success("Image 2 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # P3M Profile Changes Slide
    st.markdown("**P3M Profile Changes Slide**")
    existing_3 = slot_map.get(3, None)
    
    if existing_3:
        file_path_3 = existing_3.get("file_path")
        if file_path_3 and os.path.exists(file_path_3):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_3.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_3, caption="Current Slide", use_container_width=True)
            with col_info:
                title_add_3 = st.text_input("Title", value=existing_3.get("title", ""), key=f"seg_trends_3_title_edit_{segment['id']}")
                comment_add_3 = st.text_area("Comment", value=actual_comment, key=f"seg_trends_3_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_trends_3_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:3##" + comment_add_3
                        update_media_metadata(existing_3["id"], title_add_3, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_trends_3_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_3["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_add_3 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"seg_trends_add_3_{segment['id']}")
        title_add_3 = st.text_input("Slide Title", key=f"seg_trends_add_title_3_{segment['id']}")
        comment_add_3 = st.text_area("Slide Comment", key=f"seg_trends_add_comment_3_{segment['id']}", height=150)
        
        if st.button("Save Slide 3", key=f"save_seg_trends_3_{segment['id']}"):
            if not uploaded_add_3:
                st.error("Please upload Image 3.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:3##" + comment_add_3
                save_media_upload(
                    uploaded_file=uploaded_add_3,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_add_3,
                    label="Additional Images"
                )
                st.success("Image 3 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Upgrades & Downgrades Slide
    st.markdown("**Upgrades & Downgrades Slide**")
    existing_4 = slot_map.get(4, None)
    
    if existing_4:
        file_path_4 = existing_4.get("file_path")
        if file_path_4 and os.path.exists(file_path_4):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_4.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_4, caption="Current Slide", use_container_width=True)
            with col_info:
                title_add_4 = st.text_input("Title", value=existing_4.get("title", ""), key=f"seg_trends_4_title_edit_{segment['id']}")
                comment_add_4 = st.text_area("Comment", value=actual_comment, key=f"seg_trends_4_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_trends_4_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:4##" + comment_add_4
                        update_media_metadata(existing_4["id"], title_add_4, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_trends_4_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_4["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_add_4 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"seg_trends_add_4_{segment['id']}")
        title_add_4 = st.text_input("Slide Title", key=f"seg_trends_add_title_4_{segment['id']}")
        comment_add_4 = st.text_area("Slide Comment", key=f"seg_trends_add_comment_4_{segment['id']}", height=150)
        
        if st.button("Save Slide 4", key=f"save_seg_trends_4_{segment['id']}"):
            if not uploaded_add_4:
                st.error("Please upload Image 4.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:4##" + comment_add_4
                save_media_upload(
                    uploaded_file=uploaded_add_4,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_add_4,
                    label="Additional Images"
                )
                st.success("Image 4 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # KPIs Slide
    st.markdown("**KPIs Slide**")
    existing_5 = slot_map.get(5, None)
    
    if existing_5:
        file_path_5 = existing_5.get("file_path")
        if file_path_5 and os.path.exists(file_path_5):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_5.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_5, caption="Current Slide", use_container_width=True)
            with col_info:
                title_add_5 = st.text_input("Title", value=existing_5.get("title", ""), key=f"seg_trends_5_title_edit_{segment['id']}")
                comment_add_5 = st.text_area("Comment", value=actual_comment, key=f"seg_trends_5_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_seg_trends_5_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:5##" + comment_add_5
                        update_media_metadata(existing_5["id"], title_add_5, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_seg_trends_5_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_5["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_add_5 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"seg_trends_add_5_{segment['id']}")
        title_add_5 = st.text_input("Slide Title", key=f"seg_trends_add_title_5_{segment['id']}")
        comment_add_5 = st.text_area("Slide Comment", key=f"seg_trends_add_comment_5_{segment['id']}", height=150)
        
        if st.button("Save Slide 5", key=f"save_seg_trends_5_{segment['id']}"):
            if not uploaded_add_5:
                st.error("Please upload Image 5.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:5##" + comment_add_5
                save_media_upload(
                    uploaded_file=uploaded_add_5,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_add_5,
                    label="Additional Images"
                )
                st.success("Image 5 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Placeholder Slides section title
    st.markdown("### Placeholder Slides")
    
    # Placeholder Images (in expander)
    with st.expander("📸 Upload Placeholder Slides (optional)", expanded=False):
        # Get existing placeholder images
        placeholder_images = [m for m in existing_media if m.get("section") == "Segment Trends" and m.get("name") == "Placeholder Images"]
        placeholder_images = sorted(placeholder_images, key=lambda x: x.get("id", 0))
        
        # Placeholder Image 1
        st.markdown("**Placeholder Image 1:**")
        existing_p1 = placeholder_images[0] if len(placeholder_images) > 0 else None
        
        if existing_p1:
            file_path_p1 = existing_p1.get("file_path")
            if file_path_p1 and os.path.exists(file_path_p1):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p1, caption="Current Placeholder 1", use_container_width=True)
                with col_info:
                    title_p1 = st.text_input("Title", value=existing_p1.get("title", ""), key=f"seg_trends_p1_title_edit_{segment['id']}")
                    comment_p1 = st.text_area("Comment", value=existing_p1.get("comment", ""), key=f"seg_trends_p1_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_trends_p1_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p1["id"], title_p1, comment_p1)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_trends_p1_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p1["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p1 = st.file_uploader("Upload Placeholder Image 1", type=["png", "jpg", "jpeg"], key=f"seg_trends_p1_{segment['id']}")
            title_p1 = st.text_input("Title for Placeholder 1", key=f"seg_trends_p_title_1_{segment['id']}")
            comment_p1 = st.text_area("Comment for Placeholder 1", key=f"seg_trends_p_comment_1_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 1", key=f"save_seg_trends_p1_{segment['id']}"):
                if not uploaded_p1:
                    st.error("Please upload Placeholder Image 1.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p1,
                        segment_id=segment["id"],
                        section="Segment Trends",
                        created_by=current_user["username"],
                        comment=comment_p1,
                        title=title_p1,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 1 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 2
        st.markdown("**Placeholder Image 2:**")
        existing_p2 = placeholder_images[1] if len(placeholder_images) > 1 else None
        
        if existing_p2:
            file_path_p2 = existing_p2.get("file_path")
            if file_path_p2 and os.path.exists(file_path_p2):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p2, caption="Current Placeholder 2", use_container_width=True)
                with col_info:
                    title_p2 = st.text_input("Title", value=existing_p2.get("title", ""), key=f"seg_trends_p2_title_edit_{segment['id']}")
                    comment_p2 = st.text_area("Comment", value=existing_p2.get("comment", ""), key=f"seg_trends_p2_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_trends_p2_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p2["id"], title_p2, comment_p2)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_trends_p2_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p2["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p2 = st.file_uploader("Upload Placeholder Image 2", type=["png", "jpg", "jpeg"], key=f"seg_trends_p2_{segment['id']}")
            title_p2 = st.text_input("Title for Placeholder 2", key=f"seg_trends_p_title_2_{segment['id']}")
            comment_p2 = st.text_area("Comment for Placeholder 2", key=f"seg_trends_p_comment_2_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 2", key=f"save_seg_trends_p2_{segment['id']}"):
                if not uploaded_p2:
                    st.error("Please upload Placeholder Image 2.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p2,
                        segment_id=segment["id"],
                        section="Segment Trends",
                        created_by=current_user["username"],
                        comment=comment_p2,
                        title=title_p2,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 2 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 3
        st.markdown("**Placeholder Image 3:**")
        existing_p3 = placeholder_images[2] if len(placeholder_images) > 2 else None
        
        if existing_p3:
            file_path_p3 = existing_p3.get("file_path")
            if file_path_p3 and os.path.exists(file_path_p3):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p3, caption="Current Placeholder 3", use_container_width=True)
                with col_info:
                    title_p3 = st.text_input("Title", value=existing_p3.get("title", ""), key=f"seg_trends_p3_title_edit_{segment['id']}")
                    comment_p3 = st.text_area("Comment", value=existing_p3.get("comment", ""), key=f"seg_trends_p3_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_trends_p3_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p3["id"], title_p3, comment_p3)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_trends_p3_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p3["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p3 = st.file_uploader("Upload Placeholder Image 3", type=["png", "jpg", "jpeg"], key=f"seg_trends_p3_{segment['id']}")
            title_p3 = st.text_input("Title for Placeholder 3", key=f"seg_trends_p_title_3_{segment['id']}")
            comment_p3 = st.text_area("Comment for Placeholder 3", key=f"seg_trends_p_comment_3_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 3", key=f"save_seg_trends_p3_{segment['id']}"):
                if not uploaded_p3:
                    st.error("Please upload Placeholder Image 3.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p3,
                        segment_id=segment["id"],
                        section="Segment Trends",
                        created_by=current_user["username"],
                        comment=comment_p3,
                        title=title_p3,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 3 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 4
        st.markdown("**Placeholder Image 4:**")
        existing_p4 = placeholder_images[3] if len(placeholder_images) > 3 else None
        
        if existing_p4:
            file_path_p4 = existing_p4.get("file_path")
            if file_path_p4 and os.path.exists(file_path_p4):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p4, caption="Current Placeholder 4", use_container_width=True)
                with col_info:
                    title_p4 = st.text_input("Title", value=existing_p4.get("title", ""), key=f"seg_trends_p4_title_edit_{segment['id']}")
                    comment_p4 = st.text_area("Comment", value=existing_p4.get("comment", ""), key=f"seg_trends_p4_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_trends_p4_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p4["id"], title_p4, comment_p4)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_trends_p4_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p4["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p4 = st.file_uploader("Upload Placeholder Image 4", type=["png", "jpg", "jpeg"], key=f"seg_trends_p4_{segment['id']}")
            title_p4 = st.text_input("Title for Placeholder 4", key=f"seg_trends_p_title_4_{segment['id']}")
            comment_p4 = st.text_area("Comment for Placeholder 4", key=f"seg_trends_p_comment_4_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 4", key=f"save_seg_trends_p4_{segment['id']}"):
                if not uploaded_p4:
                    st.error("Please upload Placeholder Image 4.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p4,
                        segment_id=segment["id"],
                        section="Segment Trends",
                        created_by=current_user["username"],
                        comment=comment_p4,
                        title=title_p4,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 4 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 5
        st.markdown("**Placeholder Image 5:**")
        existing_p5 = placeholder_images[4] if len(placeholder_images) > 4 else None
        
        if existing_p5:
            file_path_p5 = existing_p5.get("file_path")
            if file_path_p5 and os.path.exists(file_path_p5):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p5, caption="Current Placeholder 5", use_container_width=True)
                with col_info:
                    title_p5 = st.text_input("Title", value=existing_p5.get("title", ""), key=f"seg_trends_p5_title_edit_{segment['id']}")
                    comment_p5 = st.text_area("Comment", value=existing_p5.get("comment", ""), key=f"seg_trends_p5_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_seg_trends_p5_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p5["id"], title_p5, comment_p5)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_seg_trends_p5_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p5["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p5 = st.file_uploader("Upload Placeholder Image 5", type=["png", "jpg", "jpeg"], key=f"seg_trends_p5_{segment['id']}")
            title_p5 = st.text_input("Title for Placeholder 5", key=f"seg_trends_p_title_5_{segment['id']}")
            comment_p5 = st.text_area("Comment for Placeholder 5", key=f"seg_trends_p_comment_5_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 5", key=f"save_seg_trends_p5_{segment['id']}"):
                if not uploaded_p5:
                    st.error("Please upload Placeholder Image 5.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p5,
                        segment_id=segment["id"],
                        section="Segment Trends",
                        created_by=current_user["username"],
                        comment=comment_p5,
                        title=title_p5,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 5 saved!")
                    st.rerun()
    
    st.markdown("---")
    st.markdown("### Segment Trends Summary Slide")
    st.caption("Add content for segment trends summary slide")
    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    saved_custom_trends = next((t for t in existing_tables if t["section"] == "Segment Trends" and t["name"] == "Custom Trends View"), None)
    
    # Parse saved config
    custom_trends_config = json.loads(saved_custom_trends["filter_json"]) if saved_custom_trends and saved_custom_trends["filter_json"] else {}
    saved_trends_title = custom_trends_config.get("title", "Segment Trends in L1Y")
    saved_trends_description = custom_trends_config.get("description", "")
    saved_trends_sections = custom_trends_config.get("sections", [])
    
    # Title and main description - pre-populated with saved values
    trends_title = st.text_input(
        "Slide Title",
        value=saved_trends_title,
        placeholder="e.g., Premium Whisky Trends in L1Y",
        key=f"trends_title_{segment['id']}"
    )
    
    trends_description = st.text_area(
        "Overall Comment",
        value=saved_trends_description,
        placeholder="e.g., Premium whisky consumption in A25 @ 45%, increasing vs LY...",
        height=100,
        key=f"trends_desc_{segment['id']}"
    )
    
    # Number of sections
    num_sections = st.number_input(
        "Number of Sections (1-8)",
        min_value=1,
        max_value=8,
        value=4,
        key=f"trends_num_sections_{segment['id']}"
    )
    
    # Section inputs
    sections_data = []
    for i in range(num_sections):
        st.markdown(f"**Section {i+1}:**")
        
        # Get saved section data if available
        saved_section = saved_trends_sections[i] if i < len(saved_trends_sections) else {}
        saved_left = saved_section.get("left", "")
        saved_right = saved_section.get("right", "")
        
        # Two columns for left and right content (no label field)
        col_left, col_right = st.columns(2)
        
        with col_left:
            left_content = st.text_area(
                f"Left content",
                value=saved_left,
                placeholder="Enter content for left side...",
                height=100,
                key=f"trends_sec{i}_left_{segment['id']}"
            )
        
        with col_right:
            right_content = st.text_area(
                f"Right content",
                value=saved_right,
                placeholder="Enter content for right side...",
                height=100,
                key=f"trends_sec{i}_right_{segment['id']}"
            )
        
        sections_data.append({
            "number": str(i + 1),  # Just use the section number
            "left": left_content,
            "right": right_content
        })
    
    # Preview
    if trends_title or trends_description or any(s["left"] or s["right"] for s in sections_data):
        st.markdown("---")
        st.markdown("**Preview:**")
        
        if trends_title:
            st.markdown(f"### {trends_title}")
        
        if trends_description:
            # Format with bold, underline, etc.
            formatted_desc = format_comment_preview(trends_description)
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
            if section["left"] or section["right"]:
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
                            {section["number"]}
                        </div>
                    """, unsafe_allow_html=True)
                
                with cols[1]:
                    if section["left"]:
                        formatted_left = format_comment_preview(section["left"])
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
                                    {formatted_left}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                with cols[2]:
                    if section["right"]:
                        formatted_right = format_comment_preview(section["right"])
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
                                    {formatted_right}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
    
    # Save button
    if st.button("Save Custom Trends View to Dashboard", key=f"save_trends_view_{segment['id']}"):
        if not trends_title:
            st.error("Please provide a title for the view.")
        else:
            # Save as a table entry with JSON config
            delete_tables_for_section(segment["id"], "Segment Trends", "Custom Trends View")
            
            config_data = json.dumps({
                "title": trends_title,
                "description": trends_description,
                "sections": sections_data
            })
            
            save_table(
                name="Custom Trends View",
                dataset_id=dataset_id,
                columns=["Config"],
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="Segment Trends",
                filter_json=config_data,
                comment=""
            )
            st.success("Custom Trends View saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Delete button next to save
    if saved_custom_trends:
        if st.button("🗑️ Delete Custom Trends View", key=f"delete_trends_view_{segment['id']}", type="secondary"):
            delete_tables_for_section(segment["id"], "Segment Trends", "Custom Trends View")
            st.success("Custom Trends View deleted!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()



def render_brand_trends_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Brand Trends - Custom Trends View Builder with multiple views support"""
    
    # Get existing media
    from app_core.media import get_media_for_segment
    existing_media = get_media_for_segment(segment["id"])
    
    # Standalone Images Section (6 images)
    st.markdown("### Analysis Slides")
    st.caption("Upload slides and add title and comment")
    
    # Get existing standalone images
    brand_trends_standalone = [m for m in existing_media if m.get("section") == "Brand Trends" and m.get("name") == "Standalone Images"]
    
    # Create a dictionary mapping slot numbers to images
    slot_map_bt = {}
    for img in brand_trends_standalone:
        comment = img.get("comment", "")
        if comment.startswith("SLOT:"):
            try:
                slot_num = int(comment.split("##")[0].replace("SLOT:", ""))
                slot_map_bt[slot_num] = img
            except:
                pass
    
    from app_core.media import delete_media
    
    # Image 1: 5Cs Performance Slide
    st.markdown("**5Cs Performance Slide**")
    existing_bt1 = slot_map_bt.get(1, None)
    
    if existing_bt1:
        file_path_bt1 = existing_bt1.get("file_path")
        if file_path_bt1 and os.path.exists(file_path_bt1):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_bt1.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt1, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt1 = st.text_input("Title", value=existing_bt1.get("title", ""), key=f"bt1_title_edit_{segment['id']}")
                comment_bt1 = st.text_area("Comment", value=actual_comment, key=f"bt1_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt1_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:1##" + comment_bt1
                        update_media_metadata(existing_bt1["id"], title_bt1, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt1_{segment['id']}", type="secondary"):
                        delete_media(existing_bt1["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt1 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_1_{segment['id']}")
        title_bt1 = st.text_input("Slide Title", key=f"bt_title_1_{segment['id']}")
        comment_bt1 = st.text_area("Slide Comment", key=f"bt_comment_1_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img1_{segment['id']}"):
            if not uploaded_bt1:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:1##" + comment_bt1
                save_media_upload(
                    uploaded_file=uploaded_bt1,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt1,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 2: 5Cs Data Slide
    st.markdown("**5Cs Data Slide**")
    existing_bt2 = slot_map_bt.get(2, None)
    
    if existing_bt2:
        file_path_bt2 = existing_bt2.get("file_path")
        if file_path_bt2 and os.path.exists(file_path_bt2):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_bt2.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt2, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt2 = st.text_input("Title", value=existing_bt2.get("title", ""), key=f"bt2_title_edit_{segment['id']}")
                comment_bt2 = st.text_area("Comment", value=actual_comment, key=f"bt2_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt2_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:2##" + comment_bt2
                        update_media_metadata(existing_bt2["id"], title_bt2, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt2_{segment['id']}", type="secondary"):
                        delete_media(existing_bt2["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt2 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_2_{segment['id']}")
        title_bt2 = st.text_input("Slide Title", key=f"bt_title_2_{segment['id']}")
        comment_bt2 = st.text_area("Slide Comment", key=f"bt_comment_2_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img2_{segment['id']}"):
            if not uploaded_bt2:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:2##" + comment_bt2
                save_media_upload(
                    uploaded_file=uploaded_bt2,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt2,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 3: Sources of Growth Slide
    st.markdown("**Sources of Growth Slide**")
    existing_bt3 = slot_map_bt.get(3, None)
    
    if existing_bt3:
        file_path_bt3 = existing_bt3.get("file_path")
        if file_path_bt3 and os.path.exists(file_path_bt3):
            # Extract actual comment (remove SLOT:3## prefix)
            raw_comment_bt3 = existing_bt3.get("comment", "")
            actual_comment_bt3 = raw_comment_bt3.split("##", 1)[1] if "##" in raw_comment_bt3 else raw_comment_bt3
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt3, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt3 = st.text_input("Title", value=existing_bt3.get("title", ""), key=f"bt3_title_edit_{segment['id']}")
                comment_bt3 = st.text_area("Comment", value=actual_comment_bt3, key=f"bt3_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt3_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment_bt3 = f"SLOT:3##" + comment_bt3
                        update_media_metadata(existing_bt3["id"], title_bt3, updated_comment_bt3)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt3_{segment['id']}", type="secondary"):
                        delete_media(existing_bt3["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt3 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_3_{segment['id']}")
        title_bt3 = st.text_input("Slide Title", key=f"bt_title_3_{segment['id']}")
        comment_bt3 = st.text_area("Slide Comment", key=f"bt_comment_3_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img3_{segment['id']}"):
            if not uploaded_bt3:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:3##" + comment_bt3
                save_media_upload(
                    uploaded_file=uploaded_bt3,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt3,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 4: P3M Profile Shifts Slide
    st.markdown("**P3M Profile Shifts Slide**")
    existing_bt4 = slot_map_bt.get(4, None)
    
    if existing_bt4:
        file_path_bt4 = existing_bt4.get("file_path")
        if file_path_bt4 and os.path.exists(file_path_bt4):
            # Extract actual comment (remove SLOT:4## prefix)
            raw_comment_bt4 = existing_bt4.get("comment", "")
            actual_comment_bt4 = raw_comment_bt4.split("##", 1)[1] if "##" in raw_comment_bt4 else raw_comment_bt4
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt4, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt4 = st.text_input("Title", value=existing_bt4.get("title", ""), key=f"bt4_title_edit_{segment['id']}")
                comment_bt4 = st.text_area("Comment", value=actual_comment_bt4, key=f"bt4_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt4_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment_bt4 = f"SLOT:4##" + comment_bt4
                        update_media_metadata(existing_bt4["id"], title_bt4, updated_comment_bt4)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt4_{segment['id']}", type="secondary"):
                        delete_media(existing_bt4["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt4 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_4_{segment['id']}")
        title_bt4 = st.text_input("Slide Title", key=f"bt_title_4_{segment['id']}")
        comment_bt4 = st.text_area("Slide Comment", key=f"bt_comment_4_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img4_{segment['id']}"):
            if not uploaded_bt4:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:4##" + comment_bt4
                save_media_upload(
                    uploaded_file=uploaded_bt4,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt4,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 5: Imagery vs LY Slide
    st.markdown("**Imagery vs LY Slide**")
    existing_bt5 = slot_map_bt.get(5, None)
    
    if existing_bt5:
        file_path_bt5 = existing_bt5.get("file_path")
        if file_path_bt5 and os.path.exists(file_path_bt5):
            # Extract actual comment (remove SLOT:5## prefix)
            raw_comment_bt5 = existing_bt5.get("comment", "")
            actual_comment_bt5 = raw_comment_bt5.split("##", 1)[1] if "##" in raw_comment_bt5 else raw_comment_bt5
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt5, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt5 = st.text_input("Title", value=existing_bt5.get("title", ""), key=f"bt5_title_edit_{segment['id']}")
                comment_bt5 = st.text_area("Comment", value=actual_comment_bt5, key=f"bt5_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt5_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment_bt5 = f"SLOT:5##" + comment_bt5
                        update_media_metadata(existing_bt5["id"], title_bt5, updated_comment_bt5)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt5_{segment['id']}", type="secondary"):
                        delete_media(existing_bt5["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt5 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_5_{segment['id']}")
        title_bt5 = st.text_input("Slide Title", key=f"bt_title_5_{segment['id']}")
        comment_bt5 = st.text_area("Slide Comment", key=f"bt_comment_5_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img5_{segment['id']}"):
            if not uploaded_bt5:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:5##" + comment_bt5
                save_media_upload(
                    uploaded_file=uploaded_bt5,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt5,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 6: P3M Interaction x Age Slide
    st.markdown("**P3M Interaction x Age Slide**")
    existing_bt6 = slot_map_bt.get(6, None)
    
    if existing_bt6:
        file_path_bt6 = existing_bt6.get("file_path")
        if file_path_bt6 and os.path.exists(file_path_bt6):
            # Extract actual comment (remove SLOT:6## prefix)
            raw_comment_bt6 = existing_bt6.get("comment", "")
            actual_comment_bt6 = raw_comment_bt6.split("##", 1)[1] if "##" in raw_comment_bt6 else raw_comment_bt6
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_bt6, caption="Current Slide", use_container_width=True)
            with col_info:
                title_bt6 = st.text_input("Title", value=existing_bt6.get("title", ""), key=f"bt6_title_edit_{segment['id']}")
                comment_bt6 = st.text_area("Comment", value=actual_comment_bt6, key=f"bt6_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_bt6_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment_bt6 = f"SLOT:6##" + comment_bt6
                        update_media_metadata(existing_bt6["id"], title_bt6, updated_comment_bt6)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_bt6_{segment['id']}", type="secondary"):
                        delete_media(existing_bt6["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_bt6 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg", "pptx"], key=f"brand_trends_img_6_{segment['id']}")
        title_bt6 = st.text_input("Slide Title", key=f"bt_title_6_{segment['id']}")
        comment_bt6 = st.text_area("Slide Comment", key=f"bt_comment_6_{segment['id']}", height=150)
        
        if st.button("Save Slide", key=f"save_bt_img6_{segment['id']}"):
            if not uploaded_bt6:
                st.error("Please upload a slide.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:6##" + comment_bt6
                save_media_upload(
                    uploaded_file=uploaded_bt6,
                    segment_id=segment["id"],
                    section="Brand Trends",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_bt6,
                    label="Standalone Images"
                )
                st.success("Slide saved!")
                st.rerun()
    
    st.markdown("---")
    
    # Placeholder Images (in expander)
    with st.expander("📸 Upload Placeholder Images (Optional)", expanded=False):
        # Get existing placeholder images
        brand_trends_placeholders = [m for m in existing_media if m.get("section") == "Brand Trends" and m.get("name") == "Placeholder Images"]
        brand_trends_placeholders = sorted(brand_trends_placeholders, key=lambda x: x.get("id", 0))
        
        # Placeholder 1
        st.markdown("**Placeholder 1:**")
        existing_btp1 = brand_trends_placeholders[0] if len(brand_trends_placeholders) > 0 else None
        
        if existing_btp1:
            file_path_btp1 = existing_btp1.get("file_path")
            if file_path_btp1 and os.path.exists(file_path_btp1):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_btp1, caption="Current Placeholder 1", use_container_width=True)
                with col_info:
                    title_btp1 = st.text_input("Title", value=existing_btp1.get("title", ""), key=f"btp1_title_edit_{segment['id']}")
                    comment_btp1 = st.text_area("Comment", value=existing_btp1.get("comment", ""), key=f"btp1_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_btp1_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_btp1["id"], title_btp1, comment_btp1)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_btp1_{segment['id']}", type="secondary"):
                            delete_media(existing_btp1["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_btp1 = st.file_uploader("Upload Placeholder 1", type=["png", "jpg", "jpeg"], key=f"bt_placeholder_1_{segment['id']}")
            title_btp1 = st.text_input("Title for Placeholder 1", key=f"btp_title_1_{segment['id']}")
            comment_btp1 = st.text_area("Comment for Placeholder 1", key=f"btp_comment_1_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 1", key=f"save_btp1_{segment['id']}"):
                if not uploaded_btp1:
                    st.error("Please upload Placeholder 1.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_btp1,
                        segment_id=segment["id"],
                        section="Brand Trends",
                        created_by=current_user["username"],
                        comment=comment_btp1,
                        title=title_btp1,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 1 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder 2
        st.markdown("**Placeholder 2:**")
        existing_btp2 = brand_trends_placeholders[1] if len(brand_trends_placeholders) > 1 else None
        
        if existing_btp2:
            file_path_btp2 = existing_btp2.get("file_path")
            if file_path_btp2 and os.path.exists(file_path_btp2):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_btp2, caption="Current Placeholder 2", use_container_width=True)
                with col_info:
                    title_btp2 = st.text_input("Title", value=existing_btp2.get("title", ""), key=f"btp2_title_edit_{segment['id']}")
                    comment_btp2 = st.text_area("Comment", value=existing_btp2.get("comment", ""), key=f"btp2_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_btp2_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_btp2["id"], title_btp2, comment_btp2)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_btp2_{segment['id']}", type="secondary"):
                            delete_media(existing_btp2["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_btp2 = st.file_uploader("Upload Placeholder 2", type=["png", "jpg", "jpeg"], key=f"bt_placeholder_2_{segment['id']}")
            title_btp2 = st.text_input("Title for Placeholder 2", key=f"btp_title_2_{segment['id']}")
            comment_btp2 = st.text_area("Comment for Placeholder 2", key=f"btp_comment_2_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 2", key=f"save_btp2_{segment['id']}"):
                if not uploaded_btp2:
                    st.error("Please upload Placeholder 2.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_btp2,
                        segment_id=segment["id"],
                        section="Brand Trends",
                        created_by=current_user["username"],
                        comment=comment_btp2,
                        title=title_btp2,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 2 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder 3
        st.markdown("**Placeholder 3:**")
        existing_btp3 = brand_trends_placeholders[2] if len(brand_trends_placeholders) > 2 else None
        
        if existing_btp3:
            file_path_btp3 = existing_btp3.get("file_path")
            if file_path_btp3 and os.path.exists(file_path_btp3):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_btp3, caption="Current Placeholder 3", use_container_width=True)
                with col_info:
                    title_btp3 = st.text_input("Title", value=existing_btp3.get("title", ""), key=f"btp3_title_edit_{segment['id']}")
                    comment_btp3 = st.text_area("Comment", value=existing_btp3.get("comment", ""), key=f"btp3_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_btp3_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_btp3["id"], title_btp3, comment_btp3)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_btp3_{segment['id']}", type="secondary"):
                            delete_media(existing_btp3["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_btp3 = st.file_uploader("Upload Placeholder 3", type=["png", "jpg", "jpeg"], key=f"bt_placeholder_3_{segment['id']}")
            title_btp3 = st.text_input("Title for Placeholder 3", key=f"btp_title_3_{segment['id']}")
            comment_btp3 = st.text_area("Comment for Placeholder 3", key=f"btp_comment_3_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 3", key=f"save_btp3_{segment['id']}"):
                if not uploaded_btp3:
                    st.error("Please upload Placeholder 3.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_btp3,
                        segment_id=segment["id"],
                        section="Brand Trends",
                        created_by=current_user["username"],
                        comment=comment_btp3,
                        title=title_btp3,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 3 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder 4
        st.markdown("**Placeholder 4:**")
        existing_btp4 = brand_trends_placeholders[3] if len(brand_trends_placeholders) > 3 else None
        
        if existing_btp4:
            file_path_btp4 = existing_btp4.get("file_path")
            if file_path_btp4 and os.path.exists(file_path_btp4):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_btp4, caption="Current Placeholder 4", use_container_width=True)
                with col_info:
                    title_btp4 = st.text_input("Title", value=existing_btp4.get("title", ""), key=f"btp4_title_edit_{segment['id']}")
                    comment_btp4 = st.text_area("Comment", value=existing_btp4.get("comment", ""), key=f"btp4_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_btp4_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_btp4["id"], title_btp4, comment_btp4)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_btp4_{segment['id']}", type="secondary"):
                            delete_media(existing_btp4["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_btp4 = st.file_uploader("Upload Placeholder 4", type=["png", "jpg", "jpeg"], key=f"bt_placeholder_4_{segment['id']}")
            title_btp4 = st.text_input("Title for Placeholder 4", key=f"btp_title_4_{segment['id']}")
            comment_btp4 = st.text_area("Comment for Placeholder 4", key=f"btp_comment_4_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 4", key=f"save_btp4_{segment['id']}"):
                if not uploaded_btp4:
                    st.error("Please upload Placeholder 4.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_btp4,
                        segment_id=segment["id"],
                        section="Brand Trends",
                        created_by=current_user["username"],
                        comment=comment_btp4,
                        title=title_btp4,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 4 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder 5
        st.markdown("**Placeholder 5:**")
        existing_btp5 = brand_trends_placeholders[4] if len(brand_trends_placeholders) > 4 else None
        
        if existing_btp5:
            file_path_btp5 = existing_btp5.get("file_path")
            if file_path_btp5 and os.path.exists(file_path_btp5):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_btp5, caption="Current Placeholder 5", use_container_width=True)
                with col_info:
                    title_btp5 = st.text_input("Title", value=existing_btp5.get("title", ""), key=f"btp5_title_edit_{segment['id']}")
                    comment_btp5 = st.text_area("Comment", value=existing_btp5.get("comment", ""), key=f"btp5_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_btp5_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_btp5["id"], title_btp5, comment_btp5)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_btp5_{segment['id']}", type="secondary"):
                            delete_media(existing_btp5["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_btp5 = st.file_uploader("Upload Placeholder 5", type=["png", "jpg", "jpeg"], key=f"bt_placeholder_5_{segment['id']}")
            title_btp5 = st.text_input("Title for Placeholder 5", key=f"btp_title_5_{segment['id']}")
            comment_btp5 = st.text_area("Comment for Placeholder 5", key=f"btp_comment_5_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 5", key=f"save_btp5_{segment['id']}"):
                if not uploaded_btp5:
                    st.error("Please upload Placeholder 5.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_btp5,
                        segment_id=segment["id"],
                        section="Brand Trends",
                        created_by=current_user["username"],
                        comment=comment_btp5,
                        title=title_btp5,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 5 saved!")
                    st.rerun()
    
    st.markdown("---")
    
    st.markdown("### Segment Trends Summary Slide")
    st.caption("Add content for segment trends summary slide")
    
    # Number of views selector
    num_views = st.number_input(
        "Number of Brands (1-6)",
        min_value=1,
        max_value=6,
        value=1,
        key=f"brand_trends_num_views_{segment['id']}",
        help="Create multiple separate views that will display one after another"
    )
    
    # Load existing saved configurations
    existing_tables = get_tables_for_segment(segment["id"])
    
    # Collect all views data
    all_views_data = []
    
    # Create each view
    for view_idx in range(num_views):
        view_num = view_idx + 1
        st.markdown("---")
        st.markdown(f"## Brand {view_num}")
        
        # Load saved config for this view
        saved_view = next((t for t in existing_tables if t["section"] == "Brand Trends" and t["name"] == f"Custom Trends View {view_num}"), None)
        view_config = json.loads(saved_view["filter_json"]) if saved_view and saved_view["filter_json"] else {}
        saved_title = view_config.get("title", "")
        saved_description = view_config.get("description", "")
        saved_sections = view_config.get("sections", [])
        saved_tab_title = view_config.get("tab_title", "")
        
        # Tab title (for display in tabs)
        tab_title = st.text_input(
            f"Brand {view_num} - Tab Title",
            value=saved_tab_title,
            placeholder=f"e.g., Performance Overview, Market Analysis, etc.",
            key=f"brand_trends_tab_title_v{view_num}_{segment['id']}",
            help="This will be the tab name shown in the dashboard"
        )
        
        # Title and main description
        trends_title = st.text_input(
            f"Brand {view_num} - Slide Title",
            value=saved_title,
            placeholder=f"e.g., Brand Performance Trends - Part {view_num}",
            key=f"brand_trends_title_v{view_num}_{segment['id']}"
        )
        
        trends_description = st.text_area(
            f"Brand {view_num} - Overall Comment",
            value=saved_description,
            placeholder="e.g., Key brand trends and insights...",
            height=100,
            key=f"brand_trends_desc_v{view_num}_{segment['id']}"
        )
        
        # Number of sections for this view
        num_sections = st.number_input(
            f"Brand {view_num} - Number of Sections (1-8)",
            min_value=1,
            max_value=8,
            value=4,
            key=f"brand_trends_num_sections_v{view_num}_{segment['id']}"
        )
        
        # Section inputs
        sections_data = []
        for i in range(num_sections):
            st.markdown(f"**Section {i+1}:**")
            
            # Get saved section data if available
            saved_section = saved_sections[i] if i < len(saved_sections) else {}
            saved_left = saved_section.get("left", "")
            saved_right = saved_section.get("right", "")
            
            # Only show left and right content fields (no label input)
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                left_content = st.text_area(
                    f"Left content",
                    value=saved_left,
                    placeholder="Enter content for left side...",
                    height=100,
                    key=f"brand_trends_v{view_num}_sec{i}_left_{segment['id']}"
                )
            
            with col_right:
                right_content = st.text_area(
                    f"Right content",
                    value=saved_right,
                    placeholder="Enter content for right side...",
                    height=100,
                    key=f"brand_trends_v{view_num}_sec{i}_right_{segment['id']}"
                )
            
            sections_data.append({
                "number": str(i + 1),
                "left": left_content,
                "right": right_content
            })
        
        # Add this view's data to all_views_data
        all_views_data.append({
            "view_num": view_num,
            "tab_title": tab_title,
            "title": trends_title,
            "description": trends_description,
            "sections": sections_data
        })
        
        # Preview for this view
        if trends_title or trends_description or any(s["left"] or s["right"] for s in sections_data):
            st.markdown("---")
            st.markdown(f"**Preview Brand {view_num}:**")
            
            if trends_title:
                st.markdown(f"### {trends_title}")
            
            if trends_description:
                formatted_desc = format_comment_preview(trends_description)
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
                if section["left"] or section["right"]:
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
                                {section["number"]}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        if section["left"]:
                            formatted_left = format_comment_preview(section["left"])
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
                                        {formatted_left}
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        if section["right"]:
                            formatted_right = format_comment_preview(section["right"])
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
                                        {formatted_right}
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
        
        # Save button for this view
        if st.button(f"Save Brand {view_num} Summary to Dashboard", key=f"save_brand_trends_view_v{view_num}_{segment['id']}"):
            if not trends_title:
                st.error(f"Please provide a title for Brand {view_num}.")
            else:
                # Delete existing view
                delete_tables_for_section(segment["id"], "Brand Trends", f"Custom Trends View {view_num}")
                
                config_data = json.dumps({
                    "title": trends_title,
                    "description": trends_description,
                    "sections": sections_data,
                    "tab_title": tab_title
                })
                
                save_table(
                    name=f"Custom Trends View {view_num}",
                    dataset_id=dataset_id,
                    columns=["Config"],
                    created_by=current_user["username"],
                    segment_id=segment["id"],
                    section="Brand Trends",
                    filter_json=config_data,
                    comment=""
                )
                st.success(f"Brand {view_num} saved to Brand Trends dashboard!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        
        # Delete button next to save
        if saved_view:
            if st.button(f"🗑️ Delete Brand {view_num} Summary", key=f"delete_brand_trends_view_v{view_num}_{segment['id']}", type="secondary"):
                delete_tables_for_section(segment["id"], "Brand Trends", f"Custom Trends View {view_num}")
                st.success(f"Brand {view_num} Summary deleted!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # Save All Brands button (after all individual views)
    st.markdown("---")
    st.markdown("### 💾 Save All Brands Configuration")
    st.caption("This will save ALL brands based on the current 'Number of Brands' setting and remove any old brands.")
    
    if st.button(f"💾 Save All {num_views} Brand(s) to Dashboard", key=f"save_all_brand_trends_{segment['id']}", type="primary"):
        # Validate that all views have titles
        missing_titles = []
        for view_data in all_views_data:
            if not view_data["title"]:
                missing_titles.append(view_data["view_num"])
        
        if missing_titles:
            st.error(f"Please provide titles for Brand(s): {', '.join(map(str, missing_titles))}")
        else:
            # Delete ALL existing Custom Trends Views for this segment (1-6)
            for i in range(1, 7):
                delete_tables_for_section(segment["id"], "Brand Trends", f"Custom Trends View {i}")
            
            # Save only the current number of views
            for view_data in all_views_data:
                config_data = json.dumps({
                    "title": view_data["title"],
                    "description": view_data["description"],
                    "sections": view_data["sections"],
                    "tab_title": view_data["tab_title"]
                })
                
                save_table(
                    name=f"Custom Trends View {view_data['view_num']}",
                    dataset_id=dataset_id,
                    columns=["Config"],
                    created_by=current_user["username"],
                    segment_id=segment["id"],
                    section="Brand Trends",
                    filter_json=config_data,
                    comment=""
                )
            
            st.success(f"✅ All {num_views} brand(s) saved to Brand Trends dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()


def render_battlegrounds_jtbd_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Battlegrounds JTBD view with rectangular labels and left/right sections"""
    st.markdown("#### Jobs To Be Done (JTBD) Configuration")
    st.caption("Create a Jobs To Be Done view with title, description, and rectangular section labels")
    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    saved_jtbd = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "JTBD View"), None)
    
    # Parse saved config
    jtbd_config = json.loads(saved_jtbd["filter_json"]) if saved_jtbd and saved_jtbd["filter_json"] else {}
    saved_jtbd_tabs = jtbd_config.get("tabs", [])
    
    # Number of Brands
    num_jtbd_tabs = st.number_input(
        "Number of Brands (1-5)",
        min_value=1,
        max_value=5,
        value=len(saved_jtbd_tabs) if saved_jtbd_tabs else 1,
        key=f"jtbd_num_tabs_{segment['id']}"
    )
    
    # Collect data for all tabs
    all_tabs_data = []
    
    for tab_idx in range(num_jtbd_tabs):
        st.markdown("---")
        st.markdown(f"### Brand {tab_idx + 1} Configuration")
        
        # Get saved tab data if available
        saved_tab = saved_jtbd_tabs[tab_idx] if tab_idx < len(saved_jtbd_tabs) else {}
        saved_tab_name = saved_tab.get("tab_name", f"Brand {tab_idx + 1}")
        saved_description = saved_tab.get("description", "")
        saved_left_header = saved_tab.get("left_header", "What's Working & Holding Us Back?")
        saved_right_header = saved_tab.get("right_header", "JTBDs:")
        saved_jtbd_sections = saved_tab.get("sections", [])
        
        # Tab name
        tab_name = st.text_input(
            f"Brand {tab_idx + 1} Name",
            value=saved_tab_name,
            placeholder=f"e.g., Premium Segment, Mass Market",
            key=f"jtbd_tab{tab_idx}_name_{segment['id']}"
        )
        
        # Slide title for this tab
        saved_slide_title = saved_tab.get("slide_title", "")
        slide_title = st.text_input(
            f"Brand {tab_idx + 1} Slide Title",
            value=saved_slide_title,
            placeholder="Enter slide title to display inside the tab...",
            key=f"jtbd_tab{tab_idx}_slide_title_{segment['id']}"
        )
        
        # Main description for this tab
        tab_description = st.text_area(
            f"Brand {tab_idx + 1} Overall Comment",
            value=saved_description,
            placeholder="Enter overview or context for this brand...",
            height=80,
            key=f"jtbd_tab{tab_idx}_desc_{segment['id']}"
        )
        
        # Column headers for this tab
        st.markdown(f"**Brand {tab_idx + 1} Column Headers:**")
        col_left_h, col_right_h = st.columns(2)
        
        with col_left_h:
            left_header = st.text_input(
                "Left Column Header",
                value=saved_left_header,
                key=f"jtbd_tab{tab_idx}_left_header_{segment['id']}"
            )
        
        with col_right_h:
            right_header = st.text_input(
                "Right Column Header",
                value=saved_right_header,
                key=f"jtbd_tab{tab_idx}_right_header_{segment['id']}"
            )
        
        # Number of JTBD sections for this tab
        num_jtbd_sections = st.number_input(
            f"Number of JTBD Sections in Brand {tab_idx + 1} (1-8)",
            min_value=1,
            max_value=8,
            value=len(saved_jtbd_sections) if saved_jtbd_sections else 3,
            key=f"jtbd_tab{tab_idx}_num_sections_{segment['id']}"
        )
        
        # JTBD section inputs for this tab
        jtbd_sections_data = []
        for i in range(num_jtbd_sections):
            st.markdown(f"**Tab {tab_idx + 1} - Section {i+1}:**")
            
            # Get saved section data if available
            saved_jtbd_section = saved_jtbd_sections[i] if i < len(saved_jtbd_sections) else {}
            saved_label = saved_jtbd_section.get("label", "")
            saved_left = saved_jtbd_section.get("left", "")
            saved_right = saved_jtbd_section.get("right", "")
            
            col_label, col_left, col_right = st.columns([1, 2, 2])
            
            with col_label:
                section_label = st.text_input(
                    f"Section Label",
                    value=saved_label,
                    key=f"jtbd_tab{tab_idx}_sec{i}_label_{segment['id']}",
                    placeholder="e.g., LDA-40YO, UP-HR-MP"
                )
            
            with col_left:
                left_content = st.text_area(
                    f"Left Content",
                    value=saved_left,
                    placeholder="What's Working?\n• Point 1\n• Point 2\n\nWhat's Holding Us Back?\n• Issue 1\n• Issue 2",
                    height=200,
                    key=f"jtbd_tab{tab_idx}_sec{i}_left_{segment['id']}"
                )
            
            with col_right:
                right_content = st.text_area(
                    f"Right Content (JTBDs)",
                    value=saved_right,
                    placeholder="1. First JTBD\n• Detail 1\n• Detail 2\n\n2. Second JTBD\n• Detail 1\n• Detail 2",
                    height=200,
                    key=f"jtbd_tab{tab_idx}_sec{i}_right_{segment['id']}"
                )
            
            jtbd_sections_data.append({
                "label": section_label,
                "left": left_content,
                "right": right_content
            })
        
        all_tabs_data.append({
            "tab_name": tab_name,
            "slide_title": slide_title,
            "description": tab_description,
            "left_header": left_header,
            "right_header": right_header,
            "sections": jtbd_sections_data
        })
        
        # Individual save button for this tab
        if st.button(f"💾 Save Tab {tab_idx + 1} ({tab_name or f'JTBD {tab_idx + 1}'})", key=f"save_jtbd_tab{tab_idx}_{segment['id']}"):
            # Validate that we have some content
            if not any(s.get("left") or s.get("right") for s in jtbd_sections_data):
                st.warning("⚠️ Please add content to at least one section before saving.")
            else:
                # Load existing config to preserve other tabs
                existing_config = jtbd_config if jtbd_config else {}
                existing_tabs = existing_config.get("tabs", [])
                
                # Build the tab data
                current_tab_data = {
                    "tab_name": tab_name,
                    "slide_title": slide_title,
                    "description": tab_description,
                    "left_header": left_header,
                    "right_header": right_header,
                    "sections": jtbd_sections_data
                }
                
                # Update or add this specific tab
                if tab_idx < len(existing_tabs):
                    existing_tabs[tab_idx] = current_tab_data
                else:
                    # Extend the list if needed
                    while len(existing_tabs) < tab_idx:
                        existing_tabs.append({
                            "tab_name": f"JTBD {len(existing_tabs) + 1}",
                            "slide_title": "",
                            "description": "",
                            "left_header": "What's Working & Holding Us Back?",
                            "right_header": "JTBDs:",
                            "sections": []
                        })
                    existing_tabs.append(current_tab_data)
                
                # Delete existing
                delete_tables_for_section(segment["id"], "Battlegrounds", "JTBD View")
                
                # Save updated configuration
                config_json = json.dumps({
                    "tabs": existing_tabs
                })
                
                save_table(
                    name="JTBD View",
                    section="Battlegrounds",
                    dataset_id=dataset_id,
                    segment_id=segment["id"],
                    columns=["Config"],
                    filter_json=config_json,
                    created_by=current_user["username"]
                )
                
                st.success(f"✅ Tab {tab_idx + 1} saved to dashboard!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        
        # Delete button next to save
        if saved_jtbd and tab_idx < len(saved_jtbd_tabs):
            if st.button(f"🗑️ Delete Brand {tab_idx + 1} JTBD", key=f"delete_jtbd_tab{tab_idx}_{segment['id']}", type="secondary"):
                # Load existing config
                existing_config = jtbd_config if jtbd_config else {}
                existing_tabs = existing_config.get("tabs", [])
                
                # Remove this tab
                if tab_idx < len(existing_tabs):
                    existing_tabs.pop(tab_idx)
                    
                    # Delete and re-save without this tab
                    delete_tables_for_section(segment["id"], "Battlegrounds", "JTBD View")
                    
                    if existing_tabs:  # Only save if there are remaining tabs
                        config_json = json.dumps({
                            "tabs": existing_tabs
                        })
                        save_table(
                            name="JTBD View",
                            section="Battlegrounds",
                            dataset_id=dataset_id,
                            segment_id=segment["id"],
                            columns=["Config"],
                            filter_json=config_json,
                            created_by=current_user["username"]
                        )
                    
                    st.success(f"Brand {tab_idx + 1} JTBD deleted!")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
    
    # Save All Brands button (after all individual tabs)
    st.markdown("---")
    st.markdown("### 💾 Save All Brands Configuration")
    st.caption("This will save ALL brands based on the current 'Number of Brands' setting and remove any old brands.")
    
    if st.button(f"💾 Save All {num_jtbd_tabs} Brand(s) to Dashboard", key=f"save_all_jtbd_{segment['id']}", type="primary"):
        # Validate that we have some content in at least one tab
        has_content = False
        for tab_data in all_tabs_data:
            if any(s.get("left") or s.get("right") for s in tab_data.get("sections", [])):
                has_content = True
                break
        
        if not has_content:
            st.warning("⚠️ Please add content to at least one section in at least one brand before saving.")
        else:
            # Delete existing JTBD configuration
            delete_tables_for_section(segment["id"], "Battlegrounds", "JTBD View")
            
            # Save the complete configuration with only the current number of brands
            config_json = json.dumps({
                "tabs": all_tabs_data
            })
            
            save_table(
                name="JTBD View",
                section="Battlegrounds",
                dataset_id=dataset_id,
                segment_id=segment["id"],
                columns=["Config"],
                filter_json=config_json,
                created_by=current_user["username"]
            )
            
            st.success(f"✅ All {num_jtbd_tabs} brand(s) saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    
    # Preview
    if any(tab["sections"] for tab in all_tabs_data if any(s["left"] or s["right"] for s in tab["sections"])):
        st.markdown("---")
        st.markdown("**Preview:**")
        
        # Display JTBD tabs preview
        if num_jtbd_tabs > 1:
            # Create tabs for preview
            tab_names = [tab["tab_name"] or f"Tab {i+1}" for i, tab in enumerate(all_tabs_data)]
            preview_tabs = st.tabs(tab_names)
            
            for tab_idx, preview_tab in enumerate(preview_tabs):
                with preview_tab:
                    tab_data = all_tabs_data[tab_idx]
                    
                    # Show slide title if exists
                    if tab_data.get("slide_title"):
                        st.markdown(f"### {tab_data['slide_title']}")
                    
                    # Show tab description if exists
                    if tab_data.get("description"):
                        from app_ui.dashboard import format_comment
                        formatted_desc = format_comment(tab_data["description"])
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
                                {formatted_desc}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Get headers for this tab
                    tab_left_header = tab_data.get("left_header", "")
                    tab_right_header = tab_data.get("right_header", "")
                    
                    for section in tab_data["sections"]:
                        if section["left"] or section["right"]:
                            # Rectangular label on the left (vertical text - inverted)
                            cols = st.columns([0.5, 4.75, 4.75])
                            
                            with cols[0]:
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
                                        min-height: 250px;
                                        min-width: 50px;
                                    '>
                                        {section["label"]}
                                    </div>
                                """, unsafe_allow_html=True)
                            
                            with cols[1]:
                                # Left section with header
                                if tab_left_header:
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
                                            {tab_left_header}
                                        </div>
                                    """, unsafe_allow_html=True)
                                
                                if section["left"]:
                                    from app_ui.dashboard import format_comment
                                    formatted_left = format_comment(section["left"])
                                    border_radius = "0 0 8px 8px" if tab_left_header else "8px"
                                    st.markdown(f"""
                                        <div style='
                                            background: #FFFFFF;
                                            border: 1px solid #CCCCCC;
                                            padding: 1.2rem;
                                            border-radius: {border_radius};
                                            min-height: 250px;
                                            max-height: 400px;
                                            overflow-y: auto;
                                            font-size: 0.9rem;
                                            line-height: 1.7;
                                            color: #1A1A1A;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            {formatted_left}
                                        </div>
                                    """, unsafe_allow_html=True)
                            
                            with cols[2]:
                                # Right section with header
                                if tab_right_header:
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
                                            {tab_right_header}
                                        </div>
                                    """, unsafe_allow_html=True)
                                
                                if section["right"]:
                                    from app_ui.dashboard import format_comment
                                    formatted_right = format_comment(section["right"])
                                    border_radius = "0 0 8px 8px" if tab_right_header else "8px"
                                    st.markdown(f"""
                                        <div style='
                                            background: #FFFFFF;
                                            border: 1px solid #CCCCCC;
                                            padding: 1.2rem;
                                            border-radius: {border_radius};
                                            min-height: 250px;
                                            max-height: 400px;
                                            overflow-y: auto;
                                            font-size: 0.9rem;
                                            line-height: 1.7;
                                            color: #1A1A1A;
                                            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                        '>
                                            {formatted_right}
                                        </div>
                                    """, unsafe_allow_html=True)
                            
                            # Add spacing between sections
                            st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
        else:
            # Single tab - display without tabs
            tab_data = all_tabs_data[0]
            
            # Show slide title if exists
            if tab_data.get("slide_title"):
                st.markdown(f"### {tab_data['slide_title']}")
            
            # Show tab description if exists
            if tab_data.get("description"):
                from app_ui.dashboard import format_comment
                formatted_desc = format_comment(tab_data["description"])
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
                        {formatted_desc}
                    </div>
                """, unsafe_allow_html=True)
            
            # Get headers for this tab
            tab_left_header = tab_data.get("left_header", "")
            tab_right_header = tab_data.get("right_header", "")
            
            for section in tab_data["sections"]:
                if section["left"] or section["right"]:
                    # Rectangular label on the left (vertical text - inverted)
                    cols = st.columns([0.5, 4.75, 4.75])
                    
                    with cols[0]:
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
                                min-height: 120px;
                                min-width: 50px;
                            '>
                                {section["label"]}
                            </div>
                        """, unsafe_allow_html=True)
                    
                    with cols[1]:
                        # Left section with header
                        if tab_left_header:
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
                                    {tab_left_header}
                                </div>
                            """, unsafe_allow_html=True)
                        
                        if section["left"]:
                            from app_ui.dashboard import format_comment
                            formatted_left = format_comment(section["left"])
                            border_radius = "0 0 8px 8px" if tab_left_header else "8px"
                            st.markdown(f"""
                                <div style='
                                    background: #FFFFFF;
                                    border: 1px solid #CCCCCC;
                                    padding: 1.2rem;
                                    border-radius: {border_radius};
                                    min-height: 250px;
                                    max-height: 400px;
                                    overflow-y: auto;
                                    font-size: 0.9rem;
                                    line-height: 1.7;
                                    color: #1A1A1A;
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                '>
                                    {formatted_left}
                                </div>
                            """, unsafe_allow_html=True)
                    
                    with cols[2]:
                        # Right section with header
                        if tab_right_header:
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
                                    {tab_right_header}
                                </div>
                            """, unsafe_allow_html=True)
                        
                        if section["right"]:
                            from app_ui.dashboard import format_comment
                            formatted_right = format_comment(section["right"])
                            border_radius = "0 0 8px 8px" if tab_right_header else "8px"
                            st.markdown(f"""
                                <div style='
                                    background: #FFFFFF;
                                    border: 1px solid #CCCCCC;
                                    padding: 1.2rem;
                                    border-radius: {border_radius};
                                    min-height: 200px;
                                    font-size: 0.9rem;
                                    line-height: 1.7;
                                    color: #1A1A1A;
                                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                                '>
                                    {formatted_right}
                                </div>
                            """, unsafe_allow_html=True)
                    
                    # Add spacing between sections
                    st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)
    
    # PLACEHOLDER SLIDES SECTION - After JTBD
    st.markdown("---")
    st.markdown("#### Placeholder Slides")
    st.caption("Add 3 placeholder slides after JTBD section")
    
    # Load existing placeholder slides
    saved_placeholders = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "JTBD Placeholders"), None)
    
    if saved_placeholders and saved_placeholders["filter_json"]:
        saved_placeholder_config = json.loads(saved_placeholders["filter_json"])
        saved_placeholder_data = saved_placeholder_config.get("placeholders", [])
    else:
        saved_placeholder_data = []
    
    with st.expander("Upload Placeholder Slides (optional)", expanded=False):
        placeholder_slides = []
        
        for i in range(3):
            st.markdown(f"**Placeholder Slide {i+1}:**")
            
            # Get saved data if available
            saved_placeholder = saved_placeholder_data[i] if i < len(saved_placeholder_data) else {}
            saved_title = saved_placeholder.get("title", "")
            saved_comment = saved_placeholder.get("comment", "")
            saved_media_id = saved_placeholder.get("media_id")
            
            col1, col2 = st.columns([1, 1])
            
            with col1:
                placeholder_file = st.file_uploader(
                    f"Upload Slide {i+1}",
                    type=["png", "jpg", "jpeg", "pptx", "pdf"],
                    key=f"jtbd_placeholder_{i}_{segment['id']}"
                )
            
            with col2:
                placeholder_title = st.text_input(
                    f"Slide {i+1} Title",
                    value=saved_title,
                    key=f"jtbd_placeholder_title_{i}_{segment['id']}"
                )
                
                placeholder_comment = st.text_area(
                    f"Slide {i+1} Comment",
                    value=saved_comment,
                    height=80,
                    key=f"jtbd_placeholder_comment_{i}_{segment['id']}"
                )
            
            # Use existing media_id if no new file uploaded
            media_id = saved_media_id if not placeholder_file else None
            
            if placeholder_file:
                media_id = save_media_file(placeholder_file, current_user["username"])
            
            placeholder_slides.append({
                "media_id": media_id,
                "title": placeholder_title,
                "comment": placeholder_comment
            })
            
            st.markdown("---")
        
        # Save button for placeholders
        if st.button("💾 Save Placeholder Slides", key=f"save_jtbd_placeholders_{segment['id']}"):
            # Delete existing
            delete_tables_for_section(segment["id"], "Battlegrounds", "JTBD Placeholders")
            
            # Save new configuration
            config_json = json.dumps({
                "placeholders": placeholder_slides
            })
            
            save_table(
                name="JTBD Placeholders",
                section="Battlegrounds",
                dataset_id=dataset_id,
                segment_id=segment["id"],
                columns=["Config"],
                filter_json=config_json,
                created_by=current_user["username"]
            )
            
            st.success("✅ Placeholder slides saved to dashboard!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        
        # Preview placeholders
        if any(p["media_id"] or p["title"] or p["comment"] for p in placeholder_slides):
            st.markdown("**Preview:**")
            for i, placeholder in enumerate(placeholder_slides):
                if placeholder["media_id"] or placeholder["title"] or placeholder["comment"]:
                    st.markdown(f"**Slide {i+1}:**")
                    if placeholder["title"]:
                        st.markdown(f"*{placeholder['title']}*")
                    if placeholder["media_id"]:
                        media_path = get_media_path(placeholder["media_id"])
                        if media_path and media_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                            st.image(media_path, use_container_width=True)
                        else:
                            st.info(f"📄 File uploaded: {media_path}")
                    if placeholder["comment"]:
                        st.caption(placeholder["comment"])
                    st.markdown("---")



def render_brand_truths_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Brand Truths: Title, description, and brand sections with images"""

    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    
    # SECTION 1: Brand Profile Comparison Table (CSV Upload) - NEW SECTION AT TOP
    st.markdown("### Brand-Wise Profile Data Table")
    st.caption("Upload a CSV with multiple brand columns for comparison")
    
    # Load existing brand profile table
    saved_brand_profile = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Profile Comparison"), None)
    
    # Title for the table
    if saved_brand_profile and saved_brand_profile["filter_json"]:
        saved_profile_config = json.loads(saved_brand_profile["filter_json"])
        saved_profile_title = saved_profile_config.get("title", "Brand-Wise Profile Data")
    else:
        saved_profile_title = "Brand-Wise Profile Data"
    
    profile_table_title = st.text_input(
        "Table Title",
        value=saved_profile_title,
        placeholder="e.g., Brand-Wise Profile Data",
        key=f"brand_profile_title_{segment['id']}"
    )
    
    if saved_brand_profile and saved_brand_profile["filter_json"]:
        st.info("✅ Brand Profile Comparison table already uploaded. Upload a new CSV to replace it.")
        with st.expander("View Current Data", expanded=False):
            try:
                saved_data = json.loads(saved_brand_profile["filter_json"])
                df_saved = pd.DataFrame(saved_data.get("data", {}))
                # Replace None/NaN values with empty strings for display
                df_saved = df_saved.fillna("")
                st.dataframe(df_saved, use_container_width=True, hide_index=True)
            except:
                st.error("Error loading saved data")
    
    # CSV file uploader
    uploaded_brand_csv = st.file_uploader(
        "Upload CSV File",
        type=["csv"],
        key=f"brand_profile_csv_{segment['id']}",
        help="CSV should have: First column = Metric names, Other columns = Brand names (Premium Whisky, Blenders Pride, etc.)"
    )
    
    if uploaded_brand_csv:
        try:
            # Read CSV
            df_brand_csv = pd.read_csv(uploaded_brand_csv)
            
            # Replace None/NaN values with empty strings for display
            df_brand_csv = df_brand_csv.fillna("")
            
            if len(df_brand_csv.columns) < 2:
                st.error("CSV must have at least 2 columns: Metric column and at least one brand column")
            else:
                st.success(f"✅ CSV loaded successfully! {len(df_brand_csv)} rows, {len(df_brand_csv.columns)} columns found.")
                
                # Base column is always the second column (first brand column)
                base_column = df_brand_csv.columns[1]
                
                # Calculate index for ALL brand columns (except first metric column and base column)
                brand_columns = df_brand_csv.columns[2:].tolist()  # All columns after base column
                
                # Add index columns for each brand column
                for brand_col in brand_columns:
                    def calculate_brand_index(row, base_col, compare_col):
                        """Calculate index comparing two brand columns"""
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
                    
                    df_brand_csv[f"_index_{brand_col}"] = df_brand_csv.apply(
                        lambda row, bc=brand_col: calculate_brand_index(row, base_column, bc), 
                        axis=1
                    )
                
                # Preview with conditional formatting
                st.markdown("**Preview with Conditional Formatting:**")
                st.caption(f"Formatting applied to all brand columns (comparing to '{base_column}')")
                
                def color_all_brand_columns(row):
                    """Apply background color to all brand columns based on their index"""
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
                            brand_col_idx = df_brand_csv.columns.get_loc(brand_col)
                            styles[brand_col_idx] = color
                        except:
                            pass
                    
                    return styles
                
                styled_brand_preview = df_brand_csv.style.apply(color_all_brand_columns, axis=1)
                
                # Hide all index columns
                column_config = {f"_index_{col}": None for col in brand_columns}
                
                st.dataframe(
                    styled_brand_preview,
                    use_container_width=True,
                    hide_index=True,
                    height=400,
                    column_config=column_config
                )
                
                st.markdown("""
                    **Color Legend:**
                    - 🟢 Dark Green: Index > 110 (Strong over-indexing)
                    - 🟢 Light Green: Index 105-110 (Slight over-indexing)
                    - 🟠 Orange: Index < 75 (Under-indexing)
                    - ⚪ White: Index 75-105 (Neutral)
                """)
                
                # Save button for brand profile table
                if st.button("Save Brand Profile Comparison Table", key=f"save_brand_profile_{segment['id']}"):
                    if not profile_table_title:
                        st.error("Please provide a title for the table.")
                    else:
                        # Delete existing
                        delete_tables_for_section(segment["id"], "Brand Truths", "Brand Profile Comparison")
                        
                        # Save data without _index columns
                        cols_to_drop = [col for col in df_brand_csv.columns if col.startswith("_index_")]
                        df_to_save = df_brand_csv.drop(columns=cols_to_drop)
                        profile_dict = {
                            "title": profile_table_title,
                            "base_column": base_column,
                            "data": df_to_save.to_dict('list')
                        }
                        
                        save_table(
                            name="Brand Profile Comparison",
                            dataset_id=dataset_id,
                            columns=["Config"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="Brand Truths",
                            filter_json=json.dumps(profile_dict),
                            comment=""
                        )
                        st.success("Brand Profile Comparison table saved to dashboard!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                
                # Delete button next to save
                if saved_brand_profile:
                    if st.button("🗑️ Delete Brand Profile Comparison Table", key=f"delete_brand_profile_{segment['id']}", type="secondary"):
                        delete_tables_for_section(segment["id"], "Brand Truths", "Brand Profile Comparison")
                        st.success("Brand Profile Comparison table deleted!")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
        
        except Exception as e:
            st.error(f"Error reading CSV: {str(e)}")
            st.info("Please ensure your CSV has proper format with metric names in first column and brand columns after")
    
    st.markdown("---")
    
    # SECTION 2: Brand Truths Configuration (Original Section)
    st.markdown("### Brand Truths Summary")
    st.caption("Compare profile insights for multiple brands")
    
    saved_brand_truths = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
    
    # Parse saved config
    brand_truths_config = json.loads(saved_brand_truths["filter_json"]) if saved_brand_truths and saved_brand_truths["filter_json"] else {}
    saved_brand_title = brand_truths_config.get("title", "Brand Truth Summary")
    saved_brand_description = brand_truths_config.get("description", "")
    saved_brand_sections = brand_truths_config.get("brands", [])
    
    # Title and main description - pre-populated with saved values
    brand_title = st.text_input(
        "Slide Title",
        value=saved_brand_title,
        placeholder="e.g., Double Whammy for BP – Threat on NE & Laterals",
        key=f"brand_title_{segment['id']}",
        help="This title will appear on the dashboard"
    )
    
    brand_description = st.text_area(
        "Overall Comment",
        value=saved_brand_description,
        placeholder="e.g., BP watch-outs across age groups; threat from RF & Sig on Laterals...",
        height=100,
        key=f"brand_desc_{segment['id']}"
    )
    
    st.markdown("---")
    
    # Number of brand sections
    num_brands = st.number_input(
        "Number of brands (1-8)",
        min_value=1,
        max_value=8,
        value=3,
        key=f"brand_num_sections_{segment['id']}"
    )
    
    # Brand section inputs - pre-populated with saved values
    brands_data = []
    for i in range(num_brands):
        st.markdown(f"**Brand Section {i+1}:**")
        
        # Get saved brand data if available
        saved_brand = saved_brand_sections[i] if i < len(saved_brand_sections) else {}
        saved_brand_name = saved_brand.get("name", "")
        saved_brand_content = saved_brand.get("content", "")
        
        col_name, col_content = st.columns([1, 3])
        
        with col_name:
            brand_name = st.text_input(
                f"Brand Name",
                value=saved_brand_name,
                placeholder="e.g., Signature",
                key=f"brand_sec{i}_name_{segment['id']}"
            )
        
        with col_content:
            brand_content = st.text_area(
                f"Brand insights",
                value=saved_brand_content,
                placeholder="Enter brand insights, trends, threats, opportunities...",
                height=150,
                key=f"brand_sec{i}_content_{segment['id']}"
            )
        
        brands_data.append({
            "number": i + 1,
            "name": brand_name,
            "content": brand_content
        })
    
    # Preview
    if brand_title or brand_description or any(b["content"] for b in brands_data):
        st.markdown("---")
        st.markdown("**Preview:**")
        
        if brand_title:
            st.markdown(f"### {brand_title}")
        
        if brand_description:
            st.markdown(f"""
                <div style='
                    background: linear-gradient(to right, #FFF9E6 0%, #FFF3D6 100%);
                    border: 1px solid #E8D7A0;
                    padding: 1rem 1.5rem;
                    margin: 1rem 0;
                    border-radius: 8px;
                    text-align: center;
                    font-size: 1rem;
                    line-height: 1.6;
                    color: #2C2C2C;
                '>
                    {format_comment_preview(brand_description)}
                </div>
            """, unsafe_allow_html=True)
        
        # Display brand sections with intelligent layout
        total_brands = len(brands_data)
        
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
            row_brands = brands_data[brand_idx:brand_idx + row_size]
            cols = st.columns(row_size)
            brand_idx += row_size
            
            for idx, (col, brand) in enumerate(zip(cols, row_brands)):
                with col:
                    if brand["name"] or brand["content"]:
                        # Brand name as header
                        if brand["name"]:
                            st.markdown(f"### {brand['name']}")
                        
                        # Brand content
                        if brand["content"]:
                            st.markdown(f"""
                                <div style='
                                    background: #F5F5F5;
                                    border: 1px solid #CCCCCC;
                                    padding: 1rem;
                                    margin: 0.5rem 0;
                                    border-radius: 8px;
                                    height: 300px;
                                    overflow-y: auto;
                                    font-size: 0.9rem;
                                    line-height: 1.6;
                                    color: #1A1A1A;
                                '>
                                    {format_comment_preview(brand["content"])}
                                </div>
                            """, unsafe_allow_html=True)
            
            # Add spacing between rows
            st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
    
    # Save button
    if st.button("Save Brands Summary to Dashboard", key=f"save_brand_truths_{segment['id']}"):
        if not brand_title:
            st.error("Please provide a title for the view.")
        else:
            # Delete existing
            delete_tables_for_section(segment["id"], "Brand Truths", "Brand Truths View")
            
            # Get existing S&V data to preserve it
            saved_sv_data = brand_truths_config.get("strengths_vulnerabilities", {})
            
            # Save configuration
            config_data = json.dumps({
                "title": brand_title,
                "description": brand_description,
                "strengths_vulnerabilities": saved_sv_data,  # Preserve existing S&V data
                "brands": [{
                    "number": b["number"],
                    "name": b["name"],
                    "content": b["content"]
                } for b in brands_data]
            })
            
            save_table(
                name="Brand Truths View",
                dataset_id=dataset_id,
                columns=["Config"],
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="Brand Truths",
                filter_json=config_data,
                comment=""
            )
            st.success("Brand Truths saved to dashboard!")
    
    st.markdown("---")
    
    # Brand Fit Scores by Needs Section (BEFORE S&V)
    st.markdown("### Brand Fit Scores by Needs")
    st.caption("Multiple slides will be displayed as tabs")
    
    # Get existing carousel images
    from app_core.media import get_media_for_segment
    existing_media = get_media_for_segment(segment["id"])
    brand_carousel_media = [m for m in existing_media if m.get("section") == "Brand Truths" and m.get("name") == "Brand Carousel"]
    brand_carousel_media = sorted(brand_carousel_media, key=lambda x: x.get("id", 0))
    
    # Show existing carousel images with edit/delete options
    if brand_carousel_media:
        st.markdown("#### Existing Carousel Slides")
        for idx, media in enumerate(brand_carousel_media):
            st.markdown(f"**Slide {idx+1}:**")
            file_path = media.get("file_path")
            if file_path and os.path.exists(file_path):
                # Parse existing data
                combined_comment = media.get("comment", "")
                existing_page_title = ""
                existing_comment = ""
                
                if combined_comment and "##PAGE_TITLE##" in combined_comment:
                    parts = combined_comment.split("##PAGE_TITLE##")
                    if len(parts) > 1:
                        remaining = parts[1]
                        if "##COMMENT##" in remaining:
                            page_parts = remaining.split("##COMMENT##")
                            existing_page_title = page_parts[0]
                            existing_comment = page_parts[1] if len(page_parts) > 1 else ""
                        else:
                            existing_page_title = remaining
                else:
                    existing_comment = combined_comment
                
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path, caption=f"Slide {idx+1}", use_container_width=True)
                with col_info:
                    tab_title = st.text_input("Tab Title", value=media.get("title", ""), key=f"carousel_tab_edit_{media['id']}")
                    page_title = st.text_input("Slide Title", value=existing_page_title, key=f"carousel_page_edit_{media['id']}")
                    comment = st.text_area("Comment", value=existing_comment, key=f"carousel_comment_edit_{media['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_carousel_{media['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            # Combine page_title and comment with markers
                            combined_new = f"##PAGE_TITLE##{page_title}##COMMENT##" + comment
                            update_media_metadata(media["id"], tab_title, combined_new)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_carousel_{media['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(media["id"])
                            st.success("Deleted!")
                            st.rerun()
            
            if idx < len(brand_carousel_media) - 1:
                st.markdown("---")
        
        st.markdown("---")
    
    # Upload new carousel images section
    st.markdown("#### Upload New Carousel Slides")
    st.caption("Upload multiple slides at once (will be added to existing slides)")
    
    # Use session state to track upload counter for clearing file uploader
    if f"brand_carousel_upload_counter_{segment['id']}" not in st.session_state:
        st.session_state[f"brand_carousel_upload_counter_{segment['id']}"] = 0
    
    uploaded_carousel_images = st.file_uploader(
        "Upload Slides (multiple allowed)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"brand_carousel_images_{segment['id']}_{st.session_state[f'brand_carousel_upload_counter_{segment['id']}']}"
    )
    
    # Title and comment inputs for each uploaded image
    carousel_configs = []
    if uploaded_carousel_images:
        st.markdown("---")
        st.markdown("**Configure each new carousel image:**")
        
        for idx, img in enumerate(uploaded_carousel_images):
            st.markdown(f"**New Carousel Image {idx+1}:**")
            
            # Layout: Image on left, title + comment on right
            col_img, col_inputs = st.columns([1, 1])
            
            with col_img:
                st.image(img, use_container_width=True)
            
            with col_inputs:
                tab_title = st.text_input(
                    "Tab Title (short name for tab)",
                    value=f"Page {len(brand_carousel_media) + idx+1}",
                    key=f"brand_carousel_tab_title_{segment['id']}_{idx}",
                    placeholder=f"e.g., Page {len(brand_carousel_media) + idx+1}"
                )
                
                page_title = st.text_input(
                    "Slide Title",
                    value="",
                    key=f"brand_carousel_page_title_{segment['id']}_{idx}",
                    placeholder="e.g., Brand Performance Overview..."
                )
                
                comment = st.text_area(
                    "Comment (optional)",
                    value="",
                    key=f"brand_carousel_comment_{segment['id']}_{idx}",
                    placeholder="Add insights, observations, or context...",
                    height=150
                )
            
            carousel_configs.append({"tab_title": tab_title, "page_title": page_title, "comment": comment})
            
            if idx < len(uploaded_carousel_images) - 1:
                st.markdown("---")
    
    # Save button for new carousel images
    if uploaded_carousel_images:
        if st.button("Save New Slides to Dashboard", key=f"save_brand_carousel_{segment['id']}"):
            if not carousel_configs or len(carousel_configs) != len(uploaded_carousel_images):
                st.error("Please configure all carousel images before saving.")
            else:
                from app_core.media import save_media_upload
                
                try:
                    # Save all uploaded images with tab titles, page titles, and comments
                    saved_count = 0
                    for idx, uploaded_img in enumerate(uploaded_carousel_images):
                        config = carousel_configs[idx]
                        
                        # Store page_title in comment field with special marker, and actual comment after
                        combined_comment = f"##PAGE_TITLE##{config['page_title']}##COMMENT##" + config["comment"]
                        
                        save_media_upload(
                            uploaded_file=uploaded_img,
                            segment_id=segment["id"],
                            section="Brand Truths",
                            created_by=current_user["username"],
                            comment=combined_comment,
                            label="Brand Carousel",
                            title=config["tab_title"]
                        )
                        saved_count += 1
                    
                    # Increment counter to clear file uploader on next render
                    st.session_state[f"brand_carousel_upload_counter_{segment['id']}"] += 1
                    
                    st.success(f"{saved_count} new carousel image(s) saved to dashboard!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving carousel images: {str(e)}")
                    import traceback
                    st.error(traceback.format_exc())
    
    st.markdown("---")
    
    # Standalone Images Section (BEFORE S&V)
    st.markdown("### Additional Analysis Slides")
    st.caption("Upload slides and add title and comment")
    
    # Get existing standalone images for Brand Truths
    brand_standalone_images = [m for m in existing_media if m.get("section") == "Brand Truths" and m.get("name") == "Standalone Images"]
    
    # Create a dictionary mapping slot numbers to images
    # We'll use the comment field to store slot info: "SLOT:1##actual_comment"
    slot_map = {}
    for img in brand_standalone_images:
        comment = img.get("comment", "")
        if comment.startswith("SLOT:"):
            try:
                slot_num = int(comment.split("##")[0].replace("SLOT:", ""))
                slot_map[slot_num] = img
            except:
                pass
    
    # Image 1
    st.markdown("**Consumer Palate Slide 1**")
    existing_s1 = slot_map.get(1, None)
    
    if existing_s1:
        file_path_s1 = existing_s1.get("file_path")
        if file_path_s1 and os.path.exists(file_path_s1):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_s1.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_s1, caption="Current Slide", use_container_width=True)
            with col_info:
                title_s1 = st.text_input("Title", value=existing_s1.get("title", ""), key=f"brand_s1_title_edit_{segment['id']}")
                comment_s1 = st.text_area("Comment", value=actual_comment, key=f"brand_s1_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_brand_s1_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        # Preserve slot number in comment
                        updated_comment = f"SLOT:1##" + comment_s1
                        update_media_metadata(existing_s1["id"], title_s1, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_brand_s1_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_s1["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_s1 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg"], key=f"brand_standalone_1_{segment['id']}")
        title_s1 = st.text_input("Slide Title", key=f"brand_s_title_1_{segment['id']}")
        comment_s1 = st.text_area("Slide Comment", key=f"brand_s_comment_1_{segment['id']}", height=150)
        
        if st.button("Save Slide 1", key=f"save_brand_s1_{segment['id']}"):
            if not uploaded_s1:
                st.error("Please upload Image 1.")
            else:
                from app_core.media import save_media_upload
                # Store slot number in comment
                slot_comment = f"SLOT:1##" + comment_s1
                save_media_upload(
                    uploaded_file=uploaded_s1,
                    segment_id=segment["id"],
                    section="Brand Truths",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_s1,
                    label="Standalone Images"
                )
                st.success("Image 1 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 2
    st.markdown("**Consumer Palate slide 2**")
    existing_s2 = slot_map.get(2, None)
    
    if existing_s2:
        file_path_s2 = existing_s2.get("file_path")
        if file_path_s2 and os.path.exists(file_path_s2):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_s2.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_s2, caption="Current Slide", use_container_width=True)
            with col_info:
                title_s2 = st.text_input("Title", value=existing_s2.get("title", ""), key=f"brand_s2_title_edit_{segment['id']}")
                comment_s2 = st.text_area("Comment", value=actual_comment, key=f"brand_s2_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_brand_s2_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:2##" + comment_s2
                        update_media_metadata(existing_s2["id"], title_s2, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_brand_s2_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_s2["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_s2 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg"], key=f"brand_standalone_2_{segment['id']}")
        title_s2 = st.text_input("Slide Title", key=f"brand_s_title_2_{segment['id']}")
        comment_s2 = st.text_area("Slide Comment", key=f"brand_s_comment_2_{segment['id']}", height=150)
        
        if st.button("Save Slide 2", key=f"save_brand_s2_{segment['id']}"):
            if not uploaded_s2:
                st.error("Please upload Image 2.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:2##" + comment_s2
                save_media_upload(
                    uploaded_file=uploaded_s2,
                    segment_id=segment["id"],
                    section="Brand Truths",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_s2,
                    label="Standalone Images"
                )
                st.success("Image 2 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 3
    st.markdown("**Brand Associations Slide**")
    existing_s3 = slot_map.get(3, None)
    
    if existing_s3:
        file_path_s3 = existing_s3.get("file_path")
        if file_path_s3 and os.path.exists(file_path_s3):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_s3.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_s3, caption="Current Slide", use_container_width=True)
            with col_info:
                title_s3 = st.text_input("Title", value=existing_s3.get("title", ""), key=f"brand_s3_title_edit_{segment['id']}")
                comment_s3 = st.text_area("Comment", value=actual_comment, key=f"brand_s3_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_brand_s3_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:3##" + comment_s3
                        update_media_metadata(existing_s3["id"], title_s3, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_brand_s3_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_s3["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_s3 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg"], key=f"brand_standalone_3_{segment['id']}")
        title_s3 = st.text_input("Slide Title", key=f"brand_s_title_3_{segment['id']}")
        comment_s3 = st.text_area("Slide Comment", key=f"brand_s_comment_3_{segment['id']}", height=150)
        
        if st.button("Save Slide 3", key=f"save_brand_s3_{segment['id']}"):
            if not uploaded_s3:
                st.error("Please upload Image 3.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:3##" + comment_s3
                save_media_upload(
                    uploaded_file=uploaded_s3,
                    segment_id=segment["id"],
                    section="Brand Truths",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_s3,
                    label="Standalone Images"
                )
                st.success("Image 3 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 4
    st.markdown("**Repertoire vs Core Slide**")
    existing_s4 = slot_map.get(4, None)
    
    if existing_s4:
        file_path_s4 = existing_s4.get("file_path")
        if file_path_s4 and os.path.exists(file_path_s4):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_s4.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_s4, caption="Current Slide", use_container_width=True)
            with col_info:
                title_s4 = st.text_input("Title", value=existing_s4.get("title", ""), key=f"brand_s4_title_edit_{segment['id']}")
                comment_s4 = st.text_area("Comment", value=actual_comment, key=f"brand_s4_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_brand_s4_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:4##" + comment_s4
                        update_media_metadata(existing_s4["id"], title_s4, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_brand_s4_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_s4["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_s4 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg"], key=f"brand_standalone_4_{segment['id']}")
        title_s4 = st.text_input("Slide Title", key=f"brand_s_title_4_{segment['id']}")
        comment_s4 = st.text_area("Slide Comment", key=f"brand_s_comment_4_{segment['id']}", height=150)
        
        if st.button("Save Slide 4", key=f"save_brand_s4_{segment['id']}"):
            if not uploaded_s4:
                st.error("Please upload Image 4.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:4##" + comment_s4
                save_media_upload(
                    uploaded_file=uploaded_s4,
                    segment_id=segment["id"],
                    section="Brand Truths",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_s4,
                    label="Standalone Images"
                )
                st.success("Image 4 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Image 5
    st.markdown("**MOC Slide**")
    existing_s5 = slot_map.get(5, None)
    
    if existing_s5:
        file_path_s5 = existing_s5.get("file_path")
        if file_path_s5 and os.path.exists(file_path_s5):
            # Extract actual comment (remove SLOT: prefix)
            raw_comment = existing_s5.get("comment", "")
            actual_comment = raw_comment.split("##", 1)[1] if "##" in raw_comment else raw_comment
            
            col_img, col_info = st.columns([1, 1])
            with col_img:
                st.image(file_path_s5, caption="Current Slide", use_container_width=True)
            with col_info:
                title_s5 = st.text_input("Title", value=existing_s5.get("title", ""), key=f"brand_s5_title_edit_{segment['id']}")
                comment_s5 = st.text_area("Comment", value=actual_comment, key=f"brand_s5_comment_edit_{segment['id']}", height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("💾 Update", key=f"update_brand_s5_{segment['id']}", type="primary"):
                        from app_core.media import update_media_metadata
                        updated_comment = f"SLOT:5##" + comment_s5
                        update_media_metadata(existing_s5["id"], title_s5, updated_comment)
                        st.success("Updated!")
                        st.rerun()
                with col_btn2:
                    if st.button("🗑️ Delete", key=f"delete_brand_s5_{segment['id']}", type="secondary"):
                        from app_core.media import delete_media
                        delete_media(existing_s5["id"])
                        st.success("Deleted!")
                        st.rerun()
    else:
        uploaded_s5 = st.file_uploader("Upload Slide", type=["png", "jpg", "jpeg"], key=f"brand_standalone_5_{segment['id']}")
        title_s5 = st.text_input("Slide Title", key=f"brand_s_title_5_{segment['id']}")
        comment_s5 = st.text_area("Slide Comment", key=f"brand_s_comment_5_{segment['id']}", height=150)
        
        if st.button("Save Slide 5", key=f"save_brand_s5_{segment['id']}"):
            if not uploaded_s5:
                st.error("Please upload Image 5.")
            else:
                from app_core.media import save_media_upload
                slot_comment = f"SLOT:5##" + comment_s5
                save_media_upload(
                    uploaded_file=uploaded_s5,
                    segment_id=segment["id"],
                    section="Brand Truths",
                    created_by=current_user["username"],
                    comment=slot_comment,
                    title=title_s5,
                    label="Standalone Images"
                )
                st.success("Image 5 saved to dashboard!")
                st.rerun()
    
    st.markdown("---")
    
    # Placeholder Slides section title
    st.markdown("### Placeholder Slides")
    
    # Placeholder Images (in expander)
    with st.expander("📸 Upload Placeholder Slides (optional)", expanded=False):
        # Get existing placeholder images
        brand_placeholder_images = [m for m in existing_media if m.get("section") == "Brand Truths" and m.get("name") == "Placeholder Images"]
        brand_placeholder_images = sorted(brand_placeholder_images, key=lambda x: x.get("id", 0))
        
        # Placeholder Image 1
        st.markdown("**Placeholder Image 1:**")
        existing_p1 = brand_placeholder_images[0] if len(brand_placeholder_images) > 0 else None
        
        if existing_p1:
            file_path_p1 = existing_p1.get("file_path")
            if file_path_p1 and os.path.exists(file_path_p1):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p1, caption="Current Placeholder 1", use_container_width=True)
                with col_info:
                    title_p1 = st.text_input("Title", value=existing_p1.get("title", ""), key=f"brand_p1_title_edit_{segment['id']}")
                    comment_p1 = st.text_area("Comment", value=existing_p1.get("comment", ""), key=f"brand_p1_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_brand_p1_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p1["id"], title_p1, comment_p1)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_brand_p1_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p1["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p1 = st.file_uploader("Upload Placeholder Image 1", type=["png", "jpg", "jpeg"], key=f"brand_placeholder_1_{segment['id']}")
            title_p1 = st.text_input("Title for Placeholder 1", key=f"brand_p_title_1_{segment['id']}")
            comment_p1 = st.text_area("Comment for Placeholder 1", key=f"brand_p_comment_1_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 1", key=f"save_brand_p1_{segment['id']}"):
                if not uploaded_p1:
                    st.error("Please upload Placeholder Image 1.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p1,
                        segment_id=segment["id"],
                        section="Brand Truths",
                        created_by=current_user["username"],
                        comment=comment_p1,
                        title=title_p1,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 1 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 2
        st.markdown("**Placeholder Image 2:**")
        existing_p2 = brand_placeholder_images[1] if len(brand_placeholder_images) > 1 else None
        
        if existing_p2:
            file_path_p2 = existing_p2.get("file_path")
            if file_path_p2 and os.path.exists(file_path_p2):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p2, caption="Current Placeholder 2", use_container_width=True)
                with col_info:
                    title_p2 = st.text_input("Title", value=existing_p2.get("title", ""), key=f"brand_p2_title_edit_{segment['id']}")
                    comment_p2 = st.text_area("Comment", value=existing_p2.get("comment", ""), key=f"brand_p2_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_brand_p2_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p2["id"], title_p2, comment_p2)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_brand_p2_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p2["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p2 = st.file_uploader("Upload Placeholder Image 2", type=["png", "jpg", "jpeg"], key=f"brand_placeholder_2_{segment['id']}")
            title_p2 = st.text_input("Title for Placeholder 2", key=f"brand_p_title_2_{segment['id']}")
            comment_p2 = st.text_area("Comment for Placeholder 2", key=f"brand_p_comment_2_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 2", key=f"save_brand_p2_{segment['id']}"):
                if not uploaded_p2:
                    st.error("Please upload Placeholder Image 2.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p2,
                        segment_id=segment["id"],
                        section="Brand Truths",
                        created_by=current_user["username"],
                        comment=comment_p2,
                        title=title_p2,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 2 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 3
        st.markdown("**Placeholder Image 3:**")
        existing_p3 = brand_placeholder_images[2] if len(brand_placeholder_images) > 2 else None
        
        if existing_p3:
            file_path_p3 = existing_p3.get("file_path")
            if file_path_p3 and os.path.exists(file_path_p3):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p3, caption="Current Placeholder 3", use_container_width=True)
                with col_info:
                    title_p3 = st.text_input("Title", value=existing_p3.get("title", ""), key=f"brand_p3_title_edit_{segment['id']}")
                    comment_p3 = st.text_area("Comment", value=existing_p3.get("comment", ""), key=f"brand_p3_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_brand_p3_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p3["id"], title_p3, comment_p3)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_brand_p3_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p3["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p3 = st.file_uploader("Upload Placeholder Image 3", type=["png", "jpg", "jpeg"], key=f"brand_placeholder_3_{segment['id']}")
            title_p3 = st.text_input("Title for Placeholder 3", key=f"brand_p_title_3_{segment['id']}")
            comment_p3 = st.text_area("Comment for Placeholder 3", key=f"brand_p_comment_3_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 3", key=f"save_brand_p3_{segment['id']}"):
                if not uploaded_p3:
                    st.error("Please upload Placeholder Image 3.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p3,
                        segment_id=segment["id"],
                        section="Brand Truths",
                        created_by=current_user["username"],
                        comment=comment_p3,
                        title=title_p3,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 3 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 4
        st.markdown("**Placeholder Image 4:**")
        existing_p4 = brand_placeholder_images[3] if len(brand_placeholder_images) > 3 else None
        
        if existing_p4:
            file_path_p4 = existing_p4.get("file_path")
            if file_path_p4 and os.path.exists(file_path_p4):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p4, caption="Current Placeholder 4", use_container_width=True)
                with col_info:
                    title_p4 = st.text_input("Title", value=existing_p4.get("title", ""), key=f"brand_p4_title_edit_{segment['id']}")
                    comment_p4 = st.text_area("Comment", value=existing_p4.get("comment", ""), key=f"brand_p4_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_brand_p4_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p4["id"], title_p4, comment_p4)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_brand_p4_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p4["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p4 = st.file_uploader("Upload Placeholder Image 4", type=["png", "jpg", "jpeg"], key=f"brand_placeholder_4_{segment['id']}")
            title_p4 = st.text_input("Title for Placeholder 4", key=f"brand_p_title_4_{segment['id']}")
            comment_p4 = st.text_area("Comment for Placeholder 4", key=f"brand_p_comment_4_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 4", key=f"save_brand_p4_{segment['id']}"):
                if not uploaded_p4:
                    st.error("Please upload Placeholder Image 4.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p4,
                        segment_id=segment["id"],
                        section="Brand Truths",
                        created_by=current_user["username"],
                        comment=comment_p4,
                        title=title_p4,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 4 saved!")
                    st.rerun()
        
        st.markdown("---")
        
        # Placeholder Image 5
        st.markdown("**Placeholder Image 5:**")
        existing_p5 = brand_placeholder_images[4] if len(brand_placeholder_images) > 4 else None
        
        if existing_p5:
            file_path_p5 = existing_p5.get("file_path")
            if file_path_p5 and os.path.exists(file_path_p5):
                col_img, col_info = st.columns([1, 1])
                with col_img:
                    st.image(file_path_p5, caption="Current Placeholder 5", use_container_width=True)
                with col_info:
                    title_p5 = st.text_input("Title", value=existing_p5.get("title", ""), key=f"brand_p5_title_edit_{segment['id']}")
                    comment_p5 = st.text_area("Comment", value=existing_p5.get("comment", ""), key=f"brand_p5_comment_edit_{segment['id']}", height=100)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Update", key=f"update_brand_p5_{segment['id']}", type="primary"):
                            from app_core.media import update_media_metadata
                            update_media_metadata(existing_p5["id"], title_p5, comment_p5)
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete", key=f"delete_brand_p5_{segment['id']}", type="secondary"):
                            from app_core.media import delete_media
                            delete_media(existing_p5["id"])
                            st.success("Deleted!")
                            st.rerun()
        else:
            uploaded_p5 = st.file_uploader("Upload Placeholder Image 5", type=["png", "jpg", "jpeg"], key=f"brand_placeholder_5_{segment['id']}")
            title_p5 = st.text_input("Title for Placeholder 5", key=f"brand_p_title_5_{segment['id']}")
            comment_p5 = st.text_area("Comment for Placeholder 5", key=f"brand_p_comment_5_{segment['id']}", height=150)
            
            if st.button("Save Placeholder 5", key=f"save_brand_p5_{segment['id']}"):
                if not uploaded_p5:
                    st.error("Please upload Placeholder Image 5.")
                else:
                    from app_core.media import save_media_upload
                    save_media_upload(
                        uploaded_file=uploaded_p5,
                        segment_id=segment["id"],
                        section="Brand Truths",
                        created_by=current_user["username"],
                        comment=comment_p5,
                        title=title_p5,
                        label="Placeholder Images"
                    )
                    st.success("Placeholder 5 saved!")
                    st.rerun()
    
    # S&V section - appears after carousel and standalone images
    st.markdown("---")
    st.markdown("### Strengths & Vulnerabilities")
    st.caption("Add content for the brand strengths and vulnerabilities")
    
    # Get saved S&V data
    saved_sv_data = brand_truths_config.get("strengths_vulnerabilities", {})
    
    # Main title for S&V section
    sv_main_title = st.text_input(
        "Slide Title",
        value=saved_sv_data.get("main_title", "PRI Strengths & Vulnerabilities"),
        placeholder="e.g., PRI Strengths & Vulnerabilities",
        key=f"brand_sv_main_title_{segment['id']}"
    )
    
    # Two columns for Strengths and Vulnerabilities
    col_strength, col_vuln = st.columns(2)
    
    with col_strength:
        st.markdown("**Brand Strengths:**")
        strength_title = st.text_input(
            "Strengths Box Title",
            value=saved_sv_data.get("strength_title", "Brand Strengths"),
            placeholder="e.g., Brand Strengths",
            key=f"brand_strength_title_{segment['id']}"
        )
        strength_content = st.text_area(
            "Strengths Content",
            value=saved_sv_data.get("strength_content", ""),
            placeholder="Add bullet points for strengths...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_strength_content_{segment['id']}"
        )
    
    with col_vuln:
        st.markdown("**Brand Vulnerabilities:**")
        vuln_title = st.text_input(
            "Vulnerabilities Box Title",
            value=saved_sv_data.get("vuln_title", "Brand Vulnerabilities"),
            placeholder="e.g., Brand Vulnerabilities",
            key=f"brand_vuln_title_{segment['id']}"
        )
        vuln_content = st.text_area(
            "Vulnerabilities Content",
            value=saved_sv_data.get("vuln_content", ""),
            placeholder="Add bullet points for vulnerabilities...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_vuln_content_{segment['id']}"
        )
    
    # Preview S&V section
    if sv_main_title or strength_content or vuln_content:
        st.markdown("---")
        st.markdown("**Preview Strengths & Vulnerabilities:**")
        
        if sv_main_title:
            st.markdown(f"### {sv_main_title}")
        
        col_prev_str, col_prev_vul = st.columns(2)
        
        with col_prev_str:
            if strength_title or strength_content:
                formatted_strength = format_comment_preview(strength_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #E8F5E9 0%, #F1F8F4 100%);
                        border: 2px dashed #4CAF50;
                        border-radius: 15px;
                        padding: 1.5rem;
                        height: 300px;
                        overflow-y: auto;
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
                        '>{formatted_strength}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        with col_prev_vul:
            if vuln_title or vuln_content:
                formatted_vuln = format_comment_preview(vuln_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #FCE4EC 0%, #F8E8EE 100%);
                        border: 2px dashed #E91E63;
                        border-radius: 15px;
                        padding: 1.5rem;
                        height: 300px;
                        overflow-y: auto;
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
                        '>{formatted_vuln}</div>
                    </div>
                """, unsafe_allow_html=True)
    
    # Separate save button for S&V
    if st.button("Save Strengths & Vulnerabilities", key=f"save_brand_sv_{segment['id']}"):
        # Get existing brand truths data to preserve it
        existing_tables = get_tables_for_segment(segment["id"])
        saved_brand_truths_current = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
        
        if saved_brand_truths_current and saved_brand_truths_current["filter_json"]:
            existing_config = json.loads(saved_brand_truths_current["filter_json"])
        else:
            existing_config = {
                "title": "Brand Truth Summary",
                "description": "",
                "brands": []
            }
        
        # Delete existing
        delete_tables_for_section(segment["id"], "Brand Truths", "Brand Truths View")
        
        # Update S&V data while preserving other fields
        existing_config["strengths_vulnerabilities"] = {
            "main_title": sv_main_title,
            "strength_title": strength_title,
            "strength_content": strength_content,
            "vuln_title": vuln_title,
            "vuln_content": vuln_content
        }
        
        # Save updated configuration
        save_table(
            name="Brand Truths View",
            dataset_id=dataset_id,
            columns=["Config"],
            created_by=current_user["username"],
            segment_id=segment["id"],
            section="Brand Truths",
            filter_json=json.dumps(existing_config),
            comment=""
        )
        st.success("Strengths & Vulnerabilities saved to dashboard!")
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()
    
    # Delete button next to save
    if saved_brand_truths and brand_truths_config.get("strengths_vulnerabilities"):
        if st.button("🗑️ Delete Strengths & Vulnerabilities", key=f"delete_brand_sv_{segment['id']}", type="secondary"):
            # Get existing data
            existing_tables = get_tables_for_segment(segment["id"])
            saved_brand_truths_current = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
            
            if saved_brand_truths_current and saved_brand_truths_current["filter_json"]:
                existing_config = json.loads(saved_brand_truths_current["filter_json"])
                # Remove S&V data
                existing_config.pop("strengths_vulnerabilities", None)
                
                # Delete and re-save without S&V
                delete_tables_for_section(segment["id"], "Brand Truths", "Brand Truths View")
                save_table(
                    name="Brand Truths View",
                    dataset_id=dataset_id,
                    columns=["Config"],
                    created_by=current_user["username"],
                    segment_id=segment["id"],
                    section="Brand Truths",
                    filter_json=json.dumps(existing_config),
                    comment=""
                )
                st.success("Strengths & Vulnerabilities deleted!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
    
    # SWOT Analysis section - appears after S&V
    st.markdown("---")
    st.markdown("### SWOT Analysis")
    st.caption("Add a comprehensive SWOT analysis with 4 quadrants")
    
    # Get saved SWOT data
    saved_swot_data = brand_truths_config.get("swot_analysis", {})
    
    # Main title for SWOT
    swot_main_title = st.text_input(
        "Slide Title",
        value=saved_swot_data.get("main_title", "PRI Portfolio SWOT"),
        placeholder="e.g., PRI Portfolio SWOT",
        key=f"brand_swot_main_title_{segment['id']}"
    )
    
    # Create 2x2 grid for SWOT
    col_s, col_w = st.columns(2)
    
    with col_s:
        st.markdown("**Strengths (S):**")
        swot_s_content = st.text_area(
            "Strengths Content",
            value=saved_swot_data.get("strengths", ""),
            placeholder="Add bullet points for strengths...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_swot_s_{segment['id']}"
        )
    
    with col_w:
        st.markdown("**Weaknesses (W):**")
        swot_w_content = st.text_area(
            "Weaknesses Content",
            value=saved_swot_data.get("weaknesses", ""),
            placeholder="Add bullet points for weaknesses...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_swot_w_{segment['id']}"
        )
    
    col_o, col_t = st.columns(2)
    
    with col_o:
        st.markdown("**Opportunities (O):**")
        swot_o_content = st.text_area(
            "Opportunities Content",
            value=saved_swot_data.get("opportunities", ""),
            placeholder="Add bullet points for opportunities...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_swot_o_{segment['id']}"
        )
    
    with col_t:
        st.markdown("**Threats (T):**")
        swot_t_content = st.text_area(
            "Threats Content",
            value=saved_swot_data.get("threats", ""),
            placeholder="Add bullet points for threats...\n- Point 1\n- Point 2",
            height=200,
            key=f"brand_swot_t_{segment['id']}"
        )
        
    # Preview SWOT
    if swot_main_title or swot_s_content or swot_w_content or swot_o_content or swot_t_content:
        st.markdown("---")
        st.markdown("**Preview SWOT Analysis:**")
        
        if swot_main_title:
            st.markdown(f"### {swot_main_title}")
        
        # Top row: S and W
        col_prev_s, col_prev_w = st.columns(2)
        
        with col_prev_s:
            if swot_s_content:
                formatted_s = format_comment_preview(swot_s_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #E3F2FD 0%, #BBDEFB 100%);
                        border: 2px solid #2196F3;
                        border-radius: 12px;
                        padding: 1.5rem;
                        height: 350px;
                        display: flex;
                        flex-direction: column;
                    '>
                        <div style='
                            text-align: center;
                            font-size: 1.3rem;
                            font-weight: 700;
                            color: #1565C0;
                            margin-bottom: 1rem;
                            flex-shrink: 0;
                        '>STRENGTHS</div>
                        <div style='
                            font-size: 0.9rem;
                            line-height: 1.7;
                            color: #0D47A1;
                            overflow-y: auto;
                            flex-grow: 1;
                            padding-right: 0.5rem;
                        '>{formatted_s}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        with col_prev_w:
            if swot_w_content:
                formatted_w = format_comment_preview(swot_w_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #FFF3E0 0%, #FFE0B2 100%);
                        border: 2px solid #FF9800;
                        border-radius: 12px;
                        padding: 1.5rem;
                        height: 350px;
                        display: flex;
                        flex-direction: column;
                    '>
                        <div style='
                            text-align: center;
                            font-size: 1.3rem;
                            font-weight: 700;
                            color: #E65100;
                            margin-bottom: 1rem;
                            flex-shrink: 0;
                        '>WEAKNESS</div>
                        <div style='
                            font-size: 0.9rem;
                            line-height: 1.7;
                            color: #BF360C;
                            overflow-y: auto;
                            flex-grow: 1;
                            padding-right: 0.5rem;
                        '>{formatted_w}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        
        # Bottom row: O and T
        col_prev_o, col_prev_t = st.columns(2)
        
        with col_prev_o:
            if swot_o_content:
                formatted_o = format_comment_preview(swot_o_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
                        border: 2px solid #4CAF50;
                        border-radius: 12px;
                        padding: 1.5rem;
                        height: 350px;
                        display: flex;
                        flex-direction: column;
                    '>
                        <div style='
                            text-align: center;
                            font-size: 1.3rem;
                            font-weight: 700;
                            color: #2E7D32;
                            margin-bottom: 1rem;
                            flex-shrink: 0;
                        '>OPPORTUNITIES</div>
                        <div style='
                            font-size: 0.9rem;
                            line-height: 1.7;
                            color: #1B5E20;
                            overflow-y: auto;
                            flex-grow: 1;
                            padding-right: 0.5rem;
                        '>{formatted_o}</div>
                    </div>
                """, unsafe_allow_html=True)
        
        with col_prev_t:
            if swot_t_content:
                formatted_t = format_comment_preview(swot_t_content)
                st.markdown(f"""
                    <div style='
                        background: linear-gradient(135deg, #FFEBEE 0%, #FFCDD2 100%);
                        border: 2px solid #F44336;
                        border-radius: 12px;
                        padding: 1.5rem;
                        height: 350px;
                        display: flex;
                        flex-direction: column;
                    '>
                        <div style='
                            text-align: center;
                            font-size: 1.3rem;
                            font-weight: 700;
                            color: #C62828;
                            margin-bottom: 1rem;
                            flex-shrink: 0;
                        '>THREATS</div>
                        <div style='
                            font-size: 0.9rem;
                            line-height: 1.7;
                            color: #B71C1C;
                            overflow-y: auto;
                            flex-grow: 1;
                            padding-right: 0.5rem;
                        '>{formatted_t}</div>
                    </div>
                """, unsafe_allow_html=True)
    
    # Separate save button for SWOT
    if st.button("Save SWOT Analysis", key=f"save_brand_swot_{segment['id']}"):
        # Get existing brand truths data to preserve it
        existing_tables = get_tables_for_segment(segment["id"])
        saved_brand_truths_current = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
        
        if saved_brand_truths_current and saved_brand_truths_current["filter_json"]:
            existing_config = json.loads(saved_brand_truths_current["filter_json"])
        else:
            existing_config = {
                "title": "Brand Truth Summary",
                "description": "",
                "brands": []
            }
        
        # Delete existing
        delete_tables_for_section(segment["id"], "Brand Truths", "Brand Truths View")
        
        # Update SWOT data while preserving other fields
        existing_config["swot_analysis"] = {
            "main_title": swot_main_title,
            "strengths": swot_s_content,
            "weaknesses": swot_w_content,
            "opportunities": swot_o_content,
            "threats": swot_t_content
        }
        
        # Save updated configuration
        save_table(
            name="Brand Truths View",
            dataset_id=dataset_id,
            columns=["Config"],
            created_by=current_user["username"],
            segment_id=segment["id"],
            section="Brand Truths",
            filter_json=json.dumps(existing_config),
            comment=""
        )
        st.success("SWOT Analysis saved to dashboard!")
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()
    
    # Delete button next to save
    if saved_brand_truths and brand_truths_config.get("swot_analysis"):
        if st.button("🗑️ Delete SWOT Analysis", key=f"delete_brand_swot_{segment['id']}", type="secondary"):
            # Get existing data
            existing_tables = get_tables_for_segment(segment["id"])
            saved_brand_truths_current = next((t for t in existing_tables if t["section"] == "Brand Truths" and t["name"] == "Brand Truths View"), None)
            
            if saved_brand_truths_current and saved_brand_truths_current["filter_json"]:
                existing_config = json.loads(saved_brand_truths_current["filter_json"])
                # Remove SWOT data
                existing_config.pop("swot_analysis", None)
                
                # Delete and re-save without SWOT
                delete_tables_for_section(segment["id"], "Brand Truths", "Brand Truths View")
                save_table(
                    name="Brand Truths View",
                    dataset_id=dataset_id,
                    columns=["Config"],
                    created_by=current_user["username"],
                    segment_id=segment["id"],
                    section="Brand Truths",
                    filter_json=json.dumps(existing_config),
                    comment=""
                )
                st.success("SWOT Analysis deleted!")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()


def get_india_geojson_url():
    """Return path to local India states GeoJSON file"""
    return "static/india_states.geojson"


def normalize_state_name(state_name: str) -> str:
    """Normalize state names to match GeoJSON format"""
    # Common mappings between data and GeoJSON
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


def render_india_map_overview(all_states: List[str], tabs_config: List[Dict]) -> None:
    """Render India map showing state assignments across tabs with GeoJSON visualization"""
    import plotly.graph_objects as go
    import requests
    
    # Map states to their tab assignments
    state_to_tab = {}
    
    for idx, tab in enumerate(tabs_config):
        tab_name = tab.get("name", f"Tab {idx+1}")
        states = tab.get("states", [])
        
        for state in states:
            # Normalize state name for GeoJSON matching
            normalized_state = normalize_state_name(state)
            state_to_tab[normalized_state] = {"tab_index": idx, "tab_name": tab_name, "original_name": state}
    
    # Create color mapping
    tab_colors = {
        0: "#4CAF50",  # Green - Advantaged
        1: "#FFC107",  # Yellow - Watch out
        2: "#F44336",  # Red - Challenged
        -1: "#E0E0E0",  # Gray - Unassigned
    }
    
    try:
        # Load GeoJSON data from local file
        geojson_path = get_india_geojson_url()
        with open(geojson_path, 'r', encoding='utf-8') as f:
            india_geojson = json.load(f)
        
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
            marker_opacity=0.7,
            marker_line_width=1,
            marker_line_color='white',
            text=hover_text,
            hovertemplate='%{text}<extra></extra>',
            showscale=False
        ))
        
        fig.update_layout(
            mapbox_style="carto-positron",
            mapbox_zoom=3.5,
            mapbox_center={"lat": 22.5, "lon": 79},
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=500
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.warning(f"Could not load India map visualization: {str(e)}")
        st.caption("Showing state list instead:")
    
    # Display as a grid with colored badges (fallback or additional info)
    st.markdown("**State Assignment by Tab:**")
    
    # Group states by tab
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
    
    unassigned_states = [s for s in all_states if s not in tab_0_states + tab_1_states + tab_2_states]
    
    # Create 3 columns for the 3 tabs
    col1, col2, col3 = st.columns(3)
    
    with col1:
        tab_name = tabs_config[0].get("name", "Tab 1") if len(tabs_config) > 0 else "Tab 1"
        st.markdown(f"**{tab_name}** ({len(tab_0_states)} states)")
        if tab_0_states:
            for state in sorted(tab_0_states):
                st.markdown(f"<span style='background-color: {tab_colors[0]}; color: white; padding: 0.2rem 0.5rem; border-radius: 0.3rem; margin: 0.2rem; display: inline-block;'>{state}</span>", unsafe_allow_html=True)
            # Show brands for this tab
            brands = tabs_config[0].get("brands", []) if len(tabs_config) > 0 else []
            if brands:
                st.caption(f"🏷️ Brands: {', '.join(brands[:3])}{'...' if len(brands) > 3 else ''}")
        else:
            st.info("No states assigned")
    
    with col2:
        tab_name = tabs_config[1].get("name", "Tab 2") if len(tabs_config) > 1 else "Tab 2"
        st.markdown(f"**{tab_name}** ({len(tab_1_states)} states)")
        if tab_1_states:
            for state in sorted(tab_1_states):
                st.markdown(f"<span style='background-color: {tab_colors[1]}; color: white; padding: 0.2rem 0.5rem; border-radius: 0.3rem; margin: 0.2rem; display: inline-block;'>{state}</span>", unsafe_allow_html=True)
            # Show brands for this tab
            brands = tabs_config[1].get("brands", []) if len(tabs_config) > 1 else []
            if brands:
                st.caption(f"🏷️ Brands: {', '.join(brands[:3])}{'...' if len(brands) > 3 else ''}")
        else:
            st.info("No states assigned")
    
    with col3:
        tab_name = tabs_config[2].get("name", "Tab 3") if len(tabs_config) > 2 else "Tab 3"
        st.markdown(f"**{tab_name}** ({len(tab_2_states)} states)")
        if tab_2_states:
            for state in sorted(tab_2_states):
                st.markdown(f"<span style='background-color: {tab_colors[2]}; color: white; padding: 0.2rem 0.5rem; border-radius: 0.3rem; margin: 0.2rem; display: inline-block;'>{state}</span>", unsafe_allow_html=True)
            # Show brands for this tab
            brands = tabs_config[2].get("brands", []) if len(tabs_config) > 2 else []
            if brands:
                st.caption(f"🏷️ Brands: {', '.join(brands[:3])}{'...' if len(brands) > 3 else ''}")
        else:
            st.info("No states assigned")
    
    # Show unassigned states
    if unassigned_states:
        st.markdown("**Unassigned States:**")
        unassigned_html = " ".join([
            f"<span style='background-color: #9E9E9E; color: white; padding: 0.2rem 0.5rem; border-radius: 0.3rem; margin: 0.2rem; display: inline-block;'>{state}</span>"
            for state in sorted(unassigned_states)
        ])
        st.markdown(unassigned_html, unsafe_allow_html=True)

def render_battlegrounds_calc_preview(df_segment: pd.DataFrame, segment: Dict, selected_states: List[str], selected_brands: List[str]) -> None:
    """Preview state performance calculations for Battlegrounds
    
    Note: df_segment is already filtered by segment, which is correct.
    All calculations use ALL brands within the segment (not just selected brands for denominators).
    """
    
    # Filter data for A24 and A25
    df_calc = df_segment[df_segment["PRI Year"].isin(["A24", "A25"])].copy()
    
    if df_calc.empty:
        st.warning("No data available for A24 and A25")
        return
    
    # Ensure Revised NS is numeric
    df_calc = clean_numeric_column(df_calc, "Revised NS")
    
    # Calculate All India segment metrics (using ALL brands in the segment)
    # This is correct - df_calc is already segment-filtered
    all_india_a24 = df_calc[df_calc["PRI Year"] == "A24"]["Revised NS"].sum()
    all_india_a25 = df_calc[df_calc["PRI Year"] == "A25"]["Revised NS"].sum()
    all_india_growth = ((all_india_a25 - all_india_a24) / all_india_a24 * 100) if all_india_a24 > 0 else 0
    
    st.markdown(f"**All India Segment Growth (A25):** {all_india_growth:+.1f}%")
    st.markdown("---")
    
    # Define colors for each state position (matching dashboard mode)
    state_colors = [
        {"bg": "#E8F5E9", "border": "#81C784", "text": "#2E7D32"},  # State 1: Light green
        {"bg": "#E3F2FD", "border": "#90CAF9", "text": "#1565C0"},  # State 2: Light blue
        {"bg": "#FFEBEE", "border": "#EF9A9A", "text": "#C62828"}   # State 3: Light red/pink
    ]
    
    # Process each selected state
    for state_idx, state in enumerate(selected_states[:3]):  # Show max 3 states in preview
        st.markdown(f"### {state}")
        
        # Filter data for this state
        df_state = df_calc[df_calc["State"] == state].copy()
        
        if df_state.empty:
            st.warning(f"No data for {state}")
            continue
        
        # SEGMENT-LEVEL CALCULATIONS (ALL BRANDS)
        state_segment_a24 = df_state[df_state["PRI Year"] == "A24"]["Revised NS"].sum()
        state_segment_a25 = df_state[df_state["PRI Year"] == "A25"]["Revised NS"].sum()
        
        # Segment MS (State share of All India)
        segment_ms = (state_segment_a25 / all_india_a25 * 100) if all_india_a25 > 0 else 0
        
        # Segment A25 Growth
        segment_growth = ((state_segment_a25 - state_segment_a24) / state_segment_a24 * 100) if state_segment_a24 > 0 else 0
        
        # State BTM Status vs AI
        btm_status = segment_growth - all_india_growth
        
        # Get color for this state based on position
        state_color = state_colors[state_idx % len(state_colors)]
        btm_color = state_color["text"]
        btm_bg_color = state_color["bg"]
        border_color = state_color["border"]
        
        # Display state header
        st.markdown(f"""
            <div style='background-color: {btm_bg_color}; padding: 1rem; border-radius: 0.5rem; margin-bottom: 1rem; border-left: 4px solid {border_color};'>
                <div style='display: flex; justify-content: space-between; align-items: center;'>
                    <div>
                        <h4 style='margin: 0;'>{state}</h4>
                        <p style='margin: 0.5rem 0 0 0; color: {btm_color}; font-weight: bold; font-size: 1.1rem;'>
                            State BTM Status vs AI: {btm_status:+.1f}%
                        </p>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Create table data
        table_data = []
        
        # Segment row
        table_data.append({
            "": "Segment",
            "MS (A25)": f"{segment_ms:.1f}%",
            "A25 Growth": f"{segment_growth:+.1f}%"
        })
        
        # BRAND-LEVEL CALCULATIONS (SELECTED BRANDS ONLY)
        for brand in selected_brands:
            df_brand = df_state[df_state["Brand"] == brand].copy()
            
            if df_brand.empty:
                continue
            
            brand_a24 = df_brand[df_brand["PRI Year"] == "A24"]["Revised NS"].sum()
            brand_a25 = df_brand[df_brand["PRI Year"] == "A25"]["Revised NS"].sum()
            
            # Brand MS (brand share of state segment - denominator uses ALL brands)
            brand_ms = (brand_a25 / state_segment_a25 * 100) if state_segment_a25 > 0 else 0
            
            # Brand A25 Growth
            brand_growth = ((brand_a25 - brand_a24) / brand_a24 * 100) if brand_a24 > 0 else 0
            
            table_data.append({
                "": brand,
                "MS (A25)": f"{brand_ms:.1f}%",
                "A25 Growth": f"{brand_growth:+.1f}%"
            })
        
        # Display table
        if table_data:
            df_display = pd.DataFrame(table_data)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        
        st.markdown("---")
    
    if len(selected_states) > 3:
        st.info(f"Showing preview for first 3 states. Total {len(selected_states)} states will be displayed on dashboard.")


def render_battlegrounds_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Battlegrounds: 3 tabs with states, brands, and images"""

    
    if df_filtered.empty:
        st.warning("No data available for this segment.")
        return
    
    # Check required columns
    if "State" not in df_filtered.columns or "Brand Family" not in df_filtered.columns or "Brand" not in df_filtered.columns:
        st.error("Missing required columns: State, Brand Family, or Brand")
        return
    
    # Load existing saved configuration
    existing_tables = get_tables_for_segment(segment["id"])
    saved_battlegrounds = next((t for t in existing_tables if t["section"] == "Battlegrounds" and t["name"] == "Battlegrounds Config"), None)
    
    # Parse saved config
    bg_config = json.loads(saved_battlegrounds["filter_json"]) if saved_battlegrounds and saved_battlegrounds["filter_json"] else {}
    saved_tabs = bg_config.get("tabs", [
        {"name": "Battleground Cluster 1", "states": [], "families": [], "brands": []},
        {"name": "Battleground Cluster 2", "states": [], "families": [], "brands": []},
        {"name": "Battleground Cluster 3", "states": [], "families": [], "brands": []}
    ])
    
    # Get available states and brands
    all_states = sorted(df_filtered["State"].dropna().unique().tolist())
    brand_families = sorted(df_filtered["Brand Family"].dropna().unique().tolist())
    
    # Configure 3 tabs
    st.markdown("### Battlegrounds Deep Dive")
    st.caption("Cluster states into three groups based on the brand's position and market realities")
    
    tabs_config = []
    # Track which states have been selected in previous tabs
    used_states = []
    
    for i in range(3):
        st.markdown(f"---")
        st.markdown(f"### Cluster {i+1} Configuration")
        
        # Get saved tab data
        saved_tab = saved_tabs[i] if i < len(saved_tabs) else {"name": ["Battleground Cluster 1", "Battleground Cluster 2", "Battleground Cluster 3"][i], "states": [], "families": [], "brands": []}
        
        # Show existing images if any
        from app_core.media import get_media_for_segment
        existing_media = get_media_for_segment(segment["id"])
        tab_media = [m for m in existing_media if m.get("section") == "Battlegrounds" and m.get("name") == f"Tab {i+1} Images"]
        
        # Get existing images
        existing_img1 = next((m for m in tab_media if "Image 1" in m.get("comment", "")), None)
        existing_img2 = next((m for m in tab_media if "Image 2" in m.get("comment", "")), None)
        
        # Default colors for each tab
        default_colors = ["#4CAF50", "#FFC107", "#F44336"]  # Green, Yellow, Red
        
        # Tab name and color in two columns
        col_name, col_color = st.columns([3, 1])
        
        with col_name:
            tab_name = st.text_input(
                f"Cluster {i+1} Name",
                value=saved_tab.get("name", ["Battleground Cluster 1", "Battleground Cluster 2", "Battleground Cluster 3"][i]),
                key=f"bg_tab{i}_name_{segment['id']}",
                help="This will be the tab title on the dashboard"
            )
        
        with col_color:
            tab_color = st.color_picker(
                "Select Color",
                value=saved_tab.get("color", default_colors[i]),
                key=f"bg_tab{i}_color_{segment['id']}",
                help="Color for map and state assignments"
            )
        
        # Fixed section headers (not editable)
        state_perf_header = "State Performance"
        strategic_insights_header = "Strategic Insights"
        
        st.markdown("---")
        
        # State selection - exclude states already selected in previous tabs
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Assign States:**")
            # Available states = all states minus those selected in previous tabs
            available_states_for_tab = [s for s in all_states if s not in used_states or s in saved_tab.get("states", [])]
            
            selected_states = st.multiselect(
                f"Select states for {tab_name}",
                options=available_states_for_tab,
                default=saved_tab.get("states", []),
                key=f"bg_tab{i}_states_{segment['id']}",
                help="States can only be assigned to one tab"
            )
            
            # Add selected states to used_states for next tabs
            used_states.extend(selected_states)
        
        with col2:
            st.markdown("**Select Brands:**")
            # Brand family selection
            selected_families = st.multiselect(
                "Select Brand Families",
                options=brand_families,
                default=saved_tab.get("families", []),
                key=f"bg_tab{i}_families_{segment['id']}"
            )
            
            # Brand selection based on families
            if selected_families:
                brands_in_families = sorted(
                    df_filtered[df_filtered["Brand Family"].isin(selected_families)]["Brand"].dropna().unique().tolist()
                )
                default_brands = [b for b in saved_tab.get("brands", []) if b in brands_in_families]
                selected_brands = st.multiselect(
                    "Select Brands",
                    options=brands_in_families,
                    default=default_brands if default_brands else brands_in_families,
                    key=f"bg_tab{i}_brands_{segment['id']}"
                )
            else:
                selected_brands = []
                st.info("Select Brand Families first")
        
        # IMAGE 1 (TOP) - MOVED HERE AFTER BRAND SELECTION, BEFORE STATE PERFORMANCE ANALYSIS
        st.markdown("---")
        st.markdown("**Sources of Growth Slide**")
        st.caption("Upload Slide")
        
        col_img1, col_inputs1 = st.columns([1, 1])
        
        with col_img1:
            # Show existing or new upload
            if existing_img1 and not st.session_state.get(f"replace_img1_tab{i}_{segment['id']}", False):
                file_path = existing_img1.get("file_path")
                if file_path and os.path.exists(file_path):
                    if str(file_path).lower().endswith((".ppt", ".pptx")):
                        st.caption(f"📄 Current: {os.path.basename(file_path)}")
                    else:
                        st.image(file_path, caption="Current Image 1", use_container_width=True)
            
            uploaded_image_1 = st.file_uploader(
                f"Upload new image (replaces existing)",
                type=["png", "jpg", "jpeg", "pptx"],
                key=f"bg_tab{i}_img1_{segment['id']}",
                label_visibility="collapsed"
            )
            if uploaded_image_1:
                if uploaded_image_1.name.endswith(('.png', '.jpg', '.jpeg')):
                    st.image(uploaded_image_1, caption="New Image 1", use_container_width=True)
                else:
                    st.info(f"📄 {uploaded_image_1.name}")
        
        with col_inputs1:
            img1_title = st.text_input(
                "Slide Title",
                value=existing_img1.get("title", "") if existing_img1 else "",
                key=f"bg_tab{i}_img1_title_{segment['id']}",
                placeholder="Enter title for top image"
            )
            
            img1_comment = st.text_area(
                "Slide Comment",
                value=existing_img1.get("comment", "").replace(f"Tab {i+1} - Image 1", "").strip() if existing_img1 else "",
                key=f"bg_tab{i}_img1_comment_{segment['id']}",
                placeholder="Add insights, observations, or context...",
                height=150
            )
        
        # State Performance Calculation Section
        st.markdown("---")
        st.caption("BTM data is autopopulated; fill comments for SOG, 5Cs, and Imagery")
        
        # Comment for calculation section
        saved_calc_comment = saved_tab.get("calc_comment", "")
        calc_comment = st.text_area(
            "Cluster 1 Overall Comment",
            value=saved_calc_comment,
            key=f"bg_tab{i}_calc_comment_{segment['id']}",
            placeholder="Add insights about state performance, BTM status, brand contributions...",
            height=100
        )
        
        
        # Custom column heading names
        st.markdown("**Customize Column Headings:**")
        col_h1, col_h2, col_h3 = st.columns(3)
        
        with col_h1:
            col1_heading = st.text_input(
                "Column 1 Heading",
                value=saved_tab.get("col1_heading", "SOG"),
                key=f"bg_tab{i}_col1_heading_{segment['id']}",
                placeholder="e.g., SOG"
            )
        
        with col_h2:
            col2_heading = st.text_input(
                "Column 2 Heading",
                value=saved_tab.get("col2_heading", "5Cs"),
                key=f"bg_tab{i}_col2_heading_{segment['id']}",
                placeholder="e.g., 5Cs"
            )
        
        with col_h3:
            col3_heading = st.text_input(
                "Column 3 Heading",
                value=saved_tab.get("col3_heading", "Imagery"),
                key=f"bg_tab{i}_col3_heading_{segment['id']}",
                placeholder="e.g., Imagery"
            )
        
        st.markdown("---")
        
        # Get saved state-specific columns
        saved_state_columns = saved_tab.get("state_columns", {})
        
        state_columns_data = {}
        
        if selected_states:
            for state in selected_states:
                st.markdown(f"**{state}:**")
                
                # Get saved data for this state
                saved_state_data = saved_state_columns.get(state, {
                    "SOG": "",
                    "5Cs": "",
                    "Imagery": ""
                })
                
                col_sog, col_5cs, col_imagery = st.columns(3)
                
                with col_sog:
                    sog_content = st.text_area(
                        col1_heading,
                        value=saved_state_data.get("SOG", ""),
                        key=f"bg_tab{i}_state_{state}_sog_{segment['id']}",
                        placeholder=f"{col1_heading} insights for {state}...",
                        height=120
                    )
                
                with col_5cs:
                    fivecs_content = st.text_area(
                        col2_heading,
                        value=saved_state_data.get("5Cs", ""),
                        key=f"bg_tab{i}_state_{state}_5cs_{segment['id']}",
                        placeholder=f"{col2_heading} insights for {state}...",
                        height=120
                    )
                
                with col_imagery:
                    imagery_content = st.text_area(
                        col3_heading,
                        value=saved_state_data.get("Imagery", ""),
                        key=f"bg_tab{i}_state_{state}_imagery_{segment['id']}",
                        placeholder=f"{col3_heading} insights for {state}...",
                        height=120
                    )
                
                state_columns_data[state] = {
                    "SOG": sog_content,
                    "5Cs": fivecs_content,
                    "Imagery": imagery_content
                }
                
                st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        else:
            st.info(f"Select states to configure their {col1_heading}, {col2_heading}, and {col3_heading} content")
        
        # Show preview if states and brands are selected
        if selected_states and selected_brands:
            with st.expander("📊 Preview State Performance Calculations", expanded=False):
                render_battlegrounds_calc_preview(df_filtered, segment, selected_states, selected_brands)
        elif selected_states or selected_brands:
            st.info("Select both states and brands to see calculation preview")
        
        st.markdown("---")
        
        # IMAGE 2 (BOTTOM)
        st.markdown("**Outlet Activation Slide**")
        st.caption("Upload Slide")
        
        col_img2, col_inputs2 = st.columns([1, 1])
        
        with col_img2:
            # Show existing or new upload
            if existing_img2 and not st.session_state.get(f"replace_img2_tab{i}_{segment['id']}", False):
                file_path = existing_img2.get("file_path")
                if file_path and os.path.exists(file_path):
                    if str(file_path).lower().endswith((".ppt", ".pptx")):
                        st.caption(f"📄 Current: {os.path.basename(file_path)}")
                    else:
                        st.image(file_path, caption="Current Image 2", use_container_width=True)
            
            uploaded_image_2 = st.file_uploader(
                f"Upload new image (replaces existing)",
                type=["png", "jpg", "jpeg", "pptx"],
                key=f"bg_tab{i}_img2_{segment['id']}",
                label_visibility="collapsed"
            )
            if uploaded_image_2:
                if uploaded_image_2.name.endswith(('.png', '.jpg', '.jpeg')):
                    st.image(uploaded_image_2, caption="New Image 2", use_container_width=True)
                else:
                    st.info(f"📄 {uploaded_image_2.name}")
        
        with col_inputs2:
            img2_title = st.text_input(
                "Slide Title",
                value=existing_img2.get("title", "") if existing_img2 else "",
                key=f"bg_tab{i}_img2_title_{segment['id']}",
                placeholder="Enter title for bottom image"
            )
            
            img2_comment = st.text_area(
                "Slide Comment",
                value=existing_img2.get("comment", "").replace(f"Tab {i+1} - Image 2", "").strip() if existing_img2 else "",
                key=f"bg_tab{i}_img2_comment_{segment['id']}",
                placeholder="Add insights, observations, or context...",
                height=150
            )
        
        st.markdown("---")
        
        # Placeholder Slides section title
        st.markdown("### Placeholder Slides")
        
        # Placeholder slides (in expander)
        with st.expander("📸 Upload Placeholder Slides (Optional)", expanded=False):
            st.caption("Upload up to 2 placeholder slides for this tab")
            
            # Get existing placeholder slides for this tab
            placeholder_slides = [m for m in existing_media if m.get("section") == "Battlegrounds" and m.get("name") == f"Tab {i+1} Placeholders"]
            placeholder_slides = sorted(placeholder_slides, key=lambda x: x.get("id", 0))
            
            # Placeholder 1
            st.markdown("**Placeholder Slide 1:**")
            existing_p1 = placeholder_slides[0] if len(placeholder_slides) > 0 else None
            
            if existing_p1:
                file_path_p1 = existing_p1.get("file_path")
                if file_path_p1 and os.path.exists(file_path_p1):
                    col_img, col_info = st.columns([1, 1])
                    with col_img:
                        if str(file_path_p1).lower().endswith((".ppt", ".pptx")):
                            st.caption(f"📄 Current: {os.path.basename(file_path_p1)}")
                        else:
                            st.image(file_path_p1, caption="Current Placeholder 1", use_container_width=True)
                    with col_info:
                        p1_title = st.text_input("Title", value=existing_p1.get("title", ""), key=f"bg_tab{i}_p1_title_edit_{segment['id']}")
                        p1_comment = st.text_area("Comment", value=existing_p1.get("comment", "").replace(f"Tab {i+1} - Placeholder 1", "").strip(), key=f"bg_tab{i}_p1_comment_edit_{segment['id']}", height=100)
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("💾 Update", key=f"update_bg_p1_tab{i}_{segment['id']}", type="primary"):
                                from app_core.media import update_media_metadata
                                update_media_metadata(existing_p1["id"], p1_title, f"Tab {i+1} - Placeholder 1 {p1_comment}")
                                st.success("Updated!")
                                st.rerun()
                        with col_btn2:
                            if st.button("🗑️ Delete", key=f"delete_bg_p1_tab{i}_{segment['id']}", type="secondary"):
                                from app_core.media import delete_media
                                delete_media(existing_p1["id"])
                                st.success("Deleted!")
                                st.rerun()
            else:
                uploaded_p1 = st.file_uploader("Upload Placeholder 1", type=["png", "jpg", "jpeg", "pptx"], key=f"bg_tab{i}_p1_{segment['id']}")
                p1_title = st.text_input("Title for Placeholder 1", key=f"bg_tab{i}_p1_title_{segment['id']}", placeholder="Enter title")
                p1_comment = st.text_area("Comment for Placeholder 1 (optional)", key=f"bg_tab{i}_p1_comment_{segment['id']}", placeholder="Add insights...", height=120)
                
                if st.button(f"Save Placeholder 1", key=f"save_bg_p1_tab{i}_{segment['id']}"):
                    if not uploaded_p1:
                        st.error("Please upload Placeholder 1.")
                    else:
                        save_media_upload(
                            uploaded_file=uploaded_p1,
                            segment_id=segment["id"],
                            section="Battlegrounds",
                            created_by=current_user["username"],
                            comment=f"Tab {i+1} - Placeholder 1 {p1_comment}",
                            label=f"Tab {i+1} Placeholders",
                            title=p1_title
                        )
                        st.success("Placeholder 1 saved!")
                        st.rerun()
            
            st.markdown("---")
            
            # Placeholder 2
            st.markdown("**Placeholder Slide 2:**")
            existing_p2 = placeholder_slides[1] if len(placeholder_slides) > 1 else None
            
            if existing_p2:
                file_path_p2 = existing_p2.get("file_path")
                if file_path_p2 and os.path.exists(file_path_p2):
                    col_img, col_info = st.columns([1, 1])
                    with col_img:
                        if str(file_path_p2).lower().endswith((".ppt", ".pptx")):
                            st.caption(f"📄 Current: {os.path.basename(file_path_p2)}")
                        else:
                            st.image(file_path_p2, caption="Current Placeholder 2", use_container_width=True)
                    with col_info:
                        p2_title = st.text_input("Title", value=existing_p2.get("title", ""), key=f"bg_tab{i}_p2_title_edit_{segment['id']}")
                        p2_comment = st.text_area("Comment", value=existing_p2.get("comment", "").replace(f"Tab {i+1} - Placeholder 2", "").strip(), key=f"bg_tab{i}_p2_comment_edit_{segment['id']}", height=100)
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("💾 Update", key=f"update_bg_p2_tab{i}_{segment['id']}", type="primary"):
                                from app_core.media import update_media_metadata
                                update_media_metadata(existing_p2["id"], p2_title, f"Tab {i+1} - Placeholder 2 {p2_comment}")
                                st.success("Updated!")
                                st.rerun()
                        with col_btn2:
                            if st.button("🗑️ Delete", key=f"delete_bg_p2_tab{i}_{segment['id']}", type="secondary"):
                                from app_core.media import delete_media
                                delete_media(existing_p2["id"])
                                st.success("Deleted!")
                                st.rerun()
            else:
                uploaded_p2 = st.file_uploader("Upload Placeholder 2", type=["png", "jpg", "jpeg", "pptx"], key=f"bg_tab{i}_p2_{segment['id']}")
                p2_title = st.text_input("Title for Placeholder 2", key=f"bg_tab{i}_p2_title_{segment['id']}", placeholder="Enter title")
                p2_comment = st.text_area("Comment for Placeholder 2 (optional)", key=f"bg_tab{i}_p2_comment_{segment['id']}", placeholder="Add insights...", height=120)
                
                if st.button(f"Save Placeholder 2", key=f"save_bg_p2_tab{i}_{segment['id']}"):
                    if not uploaded_p2:
                        st.error("Please upload Placeholder 2.")
                    else:
                        save_media_upload(
                            uploaded_file=uploaded_p2,
                            segment_id=segment["id"],
                            section="Battlegrounds",
                            created_by=current_user["username"],
                            comment=f"Tab {i+1} - Placeholder 2 {p2_comment}",
                            label=f"Tab {i+1} Placeholders",
                            title=p2_title
                        )
                        st.success("Placeholder 2 saved!")
                        st.rerun()
        
        st.markdown("---")
        
        # Save button for this tab
        if st.button(f"Save {tab_name} to Dashboard", key=f"save_bg_tab{i}_{segment['id']}"):
            if not selected_states and not selected_families:
                st.error("Please assign at least some states or select brands for this tab.")
            else:
                # Load existing config to update just this tab
                existing_config = bg_config.get("tabs", [
                    {"name": "Battleground Cluster 1", "states": [], "families": [], "brands": []},
                    {"name": "Battleground Cluster 2", "states": [], "families": [], "brands": []},
                    {"name": "Battleground Cluster 3", "states": [], "families": [], "brands": []}
                ])
                
                # Update this tab's config
                existing_config[i] = {
                    "name": tab_name,
                    "color": tab_color,
                    "states": selected_states,
                    "families": selected_families,
                    "brands": selected_brands,
                    "calc_comment": calc_comment,
                    "state_columns": state_columns_data,  # Store state-specific columns
                    "col1_heading": col1_heading,  # Store custom column headings
                    "col2_heading": col2_heading,
                    "col3_heading": col3_heading,
                    "state_perf_header": state_perf_header,  # Store section headers
                    "strategic_insights_header": strategic_insights_header
                }
                
                # Delete and save updated config
                delete_tables_for_section(segment["id"], "Battlegrounds", "Battlegrounds Config")
                
                config_data = json.dumps({"tabs": existing_config})
                
                save_table(
                    name="Battlegrounds Config",
                    dataset_id=dataset_id,
                    columns=["Config"],
                    created_by=current_user["username"],
                    segment_id=segment["id"],
                    section="Battlegrounds",
                    filter_json=config_data,
                    comment=""
                )
                
                # Delete existing images for this tab
                delete_media_for_section(segment["id"], "Battlegrounds", f"Tab {i+1} Images")
                
                # Save image 1 with title and comment (if uploaded)
                if uploaded_image_1:
                    save_media_upload(
                        uploaded_file=uploaded_image_1,
                        segment_id=segment["id"],
                        section="Battlegrounds",
                        created_by=current_user["username"],
                        comment=f"Tab {i+1} - Image 1 {img1_comment}",
                        label=f"Tab {i+1} Images",
                        title=img1_title
                    )
                elif existing_img1:
                    # Re-save existing image with updated title/comment
                    import shutil
                    from pathlib import Path
                    existing_path = existing_img1.get("file_path")
                    if existing_path and os.path.exists(existing_path):
                        # Create a temporary file object to re-upload
                        class TempFile:
                            def __init__(self, path):
                                self.name = os.path.basename(path)
                                self.path = path
                            def getbuffer(self):
                                with open(self.path, 'rb') as f:
                                    return f.read()
                        
                        temp_file = TempFile(existing_path)
                        save_media_upload(
                            uploaded_file=temp_file,
                            segment_id=segment["id"],
                            section="Battlegrounds",
                            created_by=current_user["username"],
                            comment=f"Tab {i+1} - Image 1 {img1_comment}",
                            label=f"Tab {i+1} Images",
                            title=img1_title
                        )
                
                # Save image 2 with title and comment (if uploaded)
                if uploaded_image_2:
                    save_media_upload(
                        uploaded_file=uploaded_image_2,
                        segment_id=segment["id"],
                        section="Battlegrounds",
                        created_by=current_user["username"],
                        comment=f"Tab {i+1} - Image 2 {img2_comment}",
                        label=f"Tab {i+1} Images",
                        title=img2_title
                    )
                elif existing_img2:
                    # Re-save existing image with updated title/comment
                    import shutil
                    from pathlib import Path
                    existing_path = existing_img2.get("file_path")
                    if existing_path and os.path.exists(existing_path):
                        # Create a temporary file object to re-upload
                        class TempFile:
                            def __init__(self, path):
                                self.name = os.path.basename(path)
                                self.path = path
                            def getbuffer(self):
                                with open(self.path, 'rb') as f:
                                    return f.read()
                        
                        temp_file = TempFile(existing_path)
                        save_media_upload(
                            uploaded_file=temp_file,
                            segment_id=segment["id"],
                            section="Battlegrounds",
                            created_by=current_user["username"],
                            comment=f"Tab {i+1} - Image 2 {img2_comment}",
                            label=f"Tab {i+1} Images",
                            title=img2_title
                        )
                
                # Count saved images
                total_images = (1 if uploaded_image_1 else 0) + (1 if uploaded_image_2 else 0)
                st.success(f"{tab_name} saved to dashboard with {total_images} image(s)!")
        
        # Store tab configuration for state exclusivity tracking
        tabs_config.append({
            "name": tab_name,
            "states": selected_states,
            "families": selected_families,
            "brands": selected_brands
        })
    
    # JTBD Section at the end
    st.markdown("---")
    st.markdown("---")
    render_battlegrounds_jtbd_config(segment, df_filtered, dataset_id, current_user)


