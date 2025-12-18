import json
from typing import Dict, List

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app_core.charts import delete_charts_for_section, get_charts_for_segment, save_chart
from app_core.constants import SECTIONS
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
    save_upload_for_segment,
)

from .charts import plot_chart


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
    df = load_dataset(latest["id"])
    if df is None or df.empty:
        st.warning("Selected dataset is empty.")
        return
    
    df = normalize_dataset_year(df)

    # Filter data by segment
    seg_map = {
        "value": "admix value",
        "deluxe": "admix deluxe",
        "premium": "admix premium",
        "spib": "s& pib",
        "sp bio": "sp+ib",
        "spbio": "sp+ib",
    }
    seg_name = seg_map.get(segment["name"].strip().lower(), segment["name"].strip().lower())
    df_filtered = df[df.get("Revised Seg", "").astype(str).str.strip().str.lower() == seg_name]

    # Show data info
    note = f"Using latest {'global' if using_global else 'segment'} upload: **{latest['filename']}**"
    st.info(f"{note} | Total rows: {len(df)} | Segment rows: {len(df_filtered)}")

    # Data preview
    st.markdown("### Segment Data Preview")
    if df_filtered.empty:
        st.warning(f"No rows found for segment '{segment['name']}' in the uploaded data.")
    else:
        st.dataframe(df_filtered.head(200), use_container_width=True)

    # Section tabs for configuration
    st.markdown("---")
    st.markdown("### Configure Dashboard Sections")
    tabs = st.tabs(["NS Landscape", "Segment Truths", "Brand Truths", "Segment Trends", "Brand Trends", "Battlegrounds"])
    
    with tabs[0]:
        render_ns_landscape_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[1]:
        render_segment_truths_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[2]:
        st.info("Configuration for Brand Truths will be available soon.")
    
    with tabs[3]:
        render_segment_trends_config(segment, df_filtered, latest["id"], current_user)
    
    with tabs[4]:
        st.info("Configuration for Brand Trends will be available soon.")
    
    with tabs[5]:
        st.info("Configuration for Battlegrounds will be available soon.")


def render_ns_landscape_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure NS Landscape: Manufacturing Pivot Table + Brand Multi-Bar Chart"""
    st.markdown("#### NS Landscape Configuration")
    
    if df_filtered.empty:
        st.warning("No data available for this segment.")
        return
    
    # Check required columns
    required_cols = ["PRI Year", "Mfg Com", "NS M INR", "Brand Family", "Brand"]
    missing_cols = [col for col in required_cols if col not in df_filtered.columns]
    if missing_cols:
        st.error(f"Missing required columns: {', '.join(missing_cols)}")
        return
    
    st.markdown("---")
    
    # 1. Manufacturing Pivot Table Configuration
    st.markdown("### 1. Manufacturing Pivot Table")
    st.caption("Pivot table showing NS M INR by Manufacturing Company and PRI Year with YoY Growth and CAGR")
    
    # Year filter
    available_years = ["A23", "A24", "A25"]
    years_in_data = [y for y in available_years if y in df_filtered["PRI Year"].unique()]
    
    selected_years_pivot = st.multiselect(
        "Select PRI Years",
        options=years_in_data,
        default=years_in_data,
        key=f"ns_pivot_years_{segment['id']}"
    )
    
    # Preview pivot
    if selected_years_pivot:
        preview_pivot = create_manufacturing_pivot(df_filtered, selected_years_pivot)
        if preview_pivot is not None:
            st.markdown("**Preview:**")
            st.dataframe(preview_pivot, use_container_width=True, hide_index=True)
    
    # Comment box AFTER preview
    pivot_comment = st.text_area(
        "Add comment for pivot table (optional)",
        key=f"ns_pivot_comment_{segment['id']}",
        placeholder="Add insights or notes about the manufacturing view..."
    )
    
    if st.button("Save Manufacturing Pivot to Dashboard", key=f"save_ns_pivot_{segment['id']}"):
        if not selected_years_pivot:
            st.error("Please select at least one year.")
        else:
            # Delete existing pivot for this section
            delete_tables_for_section(segment["id"], "NS Landscape", "Manufacturing Pivot")
            
            # Save configuration
            filter_config = json.dumps({"years": selected_years_pivot})
            save_table(
                name="Manufacturing Pivot",
                dataset_id=dataset_id,
                columns=["Mfg Com", "PRI Year", "NS M INR"],  # Will be pivoted
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=pivot_comment
            )
            st.success("Manufacturing Pivot saved to dashboard!")
    
    st.markdown("---")
    
    # 2. Brand Multi-Bar Chart Configuration
    st.markdown("### 2. Brand Performance Chart")
    st.caption("Multi-bar chart showing NS M INR by Brand across PRI Years")
    
    # Filters in 2 columns
    brand_families = sorted(df_filtered["Brand Family"].dropna().unique().tolist())
    
    col1, col2 = st.columns(2)
    
    with col1:
        selected_families = st.multiselect(
            "Select Brand Families",
            options=brand_families,
            default=brand_families[:2] if len(brand_families) > 2 else brand_families,
            key=f"ns_chart_families_{segment['id']}"
        )
    
    with col2:
        if selected_families:
            brands_in_families = sorted(
                df_filtered[df_filtered["Brand Family"].isin(selected_families)]["Brand"].dropna().unique().tolist()
            )
            # Auto-select all brands in selected families by default
            selected_brands = st.multiselect(
                "Select Brands to display",
                options=brands_in_families,
                default=brands_in_families,  # All brands auto-selected
                key=f"ns_chart_brands_{segment['id']}"
            )
        else:
            selected_brands = []
            st.info("Select Brand Family first")
    
    # Preview chart
    if selected_brands:
        df_chart = df_filtered[df_filtered["Brand"].isin(selected_brands)]
        df_chart = df_chart[df_chart["PRI Year"].isin(years_in_data)]
        
        if not df_chart.empty:
            st.markdown("**Preview:**")
            # Create data for chart
            chart_data = df_chart.groupby(["Brand", "Brand Family", "PRI Year"])["NS M INR"].sum().reset_index()
            
            # Sort brands: 
            # 1. Calculate 3-year sum for each brand
            brand_totals = chart_data.groupby(["Brand", "Brand Family"])["NS M INR"].sum().reset_index()
            brand_totals.columns = ["Brand", "Brand Family", "Total"]
            
            # 2. Calculate family totals (sum of selected brands in each family)
            family_totals = brand_totals.groupby("Brand Family")["Total"].sum().reset_index()
            family_totals.columns = ["Brand Family", "Family Total"]
            family_totals = family_totals.sort_values("Family Total", ascending=False)
            
            # 3. Merge and sort: families by total, then brands within family by total
            brand_totals = brand_totals.merge(family_totals, on="Brand Family")
            brand_totals = brand_totals.sort_values(["Family Total", "Total"], ascending=[False, False])
            
            # Create ordered brand list
            brand_order = brand_totals["Brand"].tolist()
            
            # Use Plotly Express with professional color scheme
            import plotly.express as px
            
            # Green color scheme - light to dark
            color_map = {
                "A23": "#90EE90",  # Light Green
                "A24": "#4CAF50",  # Medium Green
                "A25": "#1B5E20"   # Dark Green
            }
            
            fig = px.bar(
                chart_data,
                x="Brand",
                y="NS M INR",
                color="PRI Year",
                barmode="group",
                text="NS M INR",
                height=450,
                color_discrete_map=color_map,
                category_orders={"PRI Year": ["A23", "A24", "A25"], "Brand": brand_order}
            )
            
            # Format text on bars
            fig.update_traces(texttemplate='%{text:.2s}', textposition='outside')
            fig.update_layout(
                xaxis_title="Brand",
                yaxis_title="NS M INR",
                legend_title="PRI Year"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Comment box AFTER chart preview
    chart_comment = st.text_area(
        "Add comment for chart (optional)",
        key=f"ns_chart_comment_{segment['id']}",
        placeholder="Add insights about brand performance..."
    )
    
    if st.button("Save Brand Chart to Dashboard", key=f"save_ns_chart_{segment['id']}"):
        if not selected_families or not selected_brands:
            st.error("Please select Brand Families and at least one Brand.")
        else:
            # Delete existing chart for this section
            delete_charts_for_section(segment["id"], "NS Landscape", "Brand Performance")
            
            # Save configuration
            filter_config = json.dumps({
                "brand_families": selected_families,
                "brands": selected_brands,
                "years": years_in_data
            })
            save_chart(
                name="Brand Performance",
                chart_type="bar",
                x_col="Brand",
                y_cols=["NS M INR"],
                dataset_id=dataset_id,
                created_by=current_user["username"],
                segment_id=segment["id"],
                section="NS Landscape",
                filter_json=filter_config,
                comment=chart_comment
            )
            st.success("Brand Performance Chart saved to dashboard!")
    
    st.markdown("---")
    
    # 3. Zonal Pivot Table Configuration
    st.markdown("### 3. Zonal Pivot Table (Brand Family x Zone)")
    st.caption("Pivot table showing NS M INR for A25 by Brand Family, Brand, and Zone")
    
    # Use same brand families and brands from chart
    if selected_families and selected_brands:
        # Check if Zone column exists
        if "Zone" not in df_filtered.columns:
            st.warning("Zone column not found in dataset. This table requires a 'Zone' column.")
        else:
            # Filter data for A24 and A25 (needed for growth calculations)
            df_zonal = df_filtered[df_filtered["PRI Year"].isin(["A24", "A25"])].copy()
            df_zonal = df_zonal[df_zonal["Brand Family"].isin(selected_families)]
            df_zonal = df_zonal[df_zonal["Brand"].isin(selected_brands)]
            
            if not df_zonal.empty:
                # Preview zonal table
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
                            
                            # Filter rows for this zone
                            zone_df = preview_zonal[["Brand", "Type", f"{zone}_MS", f"{zone}_Gr", f"{zone}_BTM"]].copy()
                            
                            # Apply styling to highlight brand families
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
                
                # Comment box AFTER zonal preview
                zonal_comment = st.text_area(
                    "Add comment for zonal table (optional)",
                    key=f"ns_zonal_comment_{segment['id']}",
                    placeholder="Add insights about zonal performance..."
                )
                
                if st.button("Save Zonal Table to Dashboard", key=f"save_ns_zonal_{segment['id']}"):
                    # Delete existing zonal table
                    delete_tables_for_section(segment["id"], "NS Landscape", "Zonal Pivot")
                    
                    # Save configuration
                    filter_config = json.dumps({
                        "brand_families": selected_families,
                        "brands": selected_brands,
                        "year": "A25"
                    })
                    save_table(
                        name="Zonal Pivot",
                        dataset_id=dataset_id,
                        columns=["Brand Family", "Brand", "Zone", "NS M INR"],
                        created_by=current_user["username"],
                        segment_id=segment["id"],
                        section="NS Landscape",
                        filter_json=filter_config,
                        comment=zonal_comment
                    )
                    st.success("Zonal Pivot Table saved to dashboard!")
            else:
                st.info("No data available for A25 with selected brands.")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 4. NORTH Zone State Drill-Down
    st.markdown("### 4. NORTH Zone - State Drill-Down")
    st.caption("State-level performance within NORTH zone with brand deep-dive")
    
    if selected_families and selected_brands:
        # Check if State column exists
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset. This feature requires a 'State' column.")
        else:
            # Filter data for NORTH zone only
            df_north = df_filtered[df_filtered["Zone"] == "North Zone"].copy()
            
            if df_north.empty:
                st.info("No data available for NORTH zone.")
            else:
                # Get all states in NORTH zone
                states_in_north = sorted(df_north["State"].dropna().unique().tolist())
                
                # First show state summary for ALL states in North Zone
                st.markdown("**State Summary - All States in North Zone:**")
                preview_all_states = create_north_state_drilldown(df_filtered, selected_families, selected_brands, states_in_north)
                
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
                
                # Comment for state summary table - RIGHT AFTER the table
                north_comment_top = st.text_area(
                    "Comment for State Summary Table (optional)",
                    key=f"ns_north_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                # Then let user select states for deep-dive - use sorted states as default
                selected_states = st.multiselect(
                    "Select States for Brand Deep-Dive",
                    options=sorted_states if preview_all_states else states_in_north,
                    default=sorted_states[:4] if (preview_all_states and len(sorted_states) > 4) else (sorted_states if preview_all_states else states_in_north[:4]),
                    key=f"ns_north_states_{segment['id']}"
                )
                
                if selected_states:
                    # Preview deep-dive
                    st.markdown("**Preview - State Deep-Dive:**")
                    preview_north = create_north_state_drilldown(df_filtered, selected_families, selected_brands, selected_states)
                    
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
                
                # Comment for brand deep-dive AFTER preview
                st.markdown("---")
                north_comment_bottom = st.text_area(
                    "Comment for Brand Deep-Dive (optional)",
                    key=f"ns_north_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save NORTH Zone Drill-Down to Dashboard", key=f"save_ns_north_{segment['id']}"):
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
                        
                        # Save configuration
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "states": selected_states,
                            "zone": "North Zone"
                        })
                        save_table(
                            name="NORTH State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "NS M INR"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("NORTH Zone Drill-Down saved to dashboard!")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 5. WEST+CSD Zone State Drill-Down
    st.markdown("### 5. WEST+CSD Zone - State Drill-Down")
    st.caption("State-level performance within WEST+CSD zone with brand deep-dive")
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_west = df_filtered[df_filtered["Zone"] == "West+CSD Zone"].copy()
            
            if df_west.empty:
                st.info("No data available for WEST+CSD zone.")
            else:
                states_in_west = sorted(df_west["State"].dropna().unique().tolist())
                
                st.markdown("**State Summary - All States in West+CSD Zone:**")
                preview_all_west = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, states_in_west, "West+CSD Zone")
                
                if preview_all_west:
                    summary_styled = style_state_summary(preview_all_west['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_west = preview_all_west['state_summary'][preview_all_west['state_summary']['State'] != 'WEST+CSD']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table
                west_comment_top = st.text_area(
                    "Comment for State Summary Table (optional)",
                    key=f"ns_west_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                selected_states_west = st.multiselect(
                    "Select States for Brand Deep-Dive",
                    options=sorted_states_west if preview_all_west else states_in_west,
                    default=sorted_states_west[:4] if (preview_all_west and len(sorted_states_west) > 4) else (sorted_states_west if preview_all_west else states_in_west[:4]),
                    key=f"ns_west_states_{segment['id']}"
                )
                
                if selected_states_west:
                    st.markdown("**Preview - State Deep-Dive:**")
                    preview_west = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, selected_states_west, "West+CSD Zone")
                    
                    if preview_west and preview_west['state_details']:
                        render_state_drilldown_preview(preview_west, selected_states_west)
                
                # Comment for brand deep-dive AFTER preview
                st.markdown("---")
                west_comment_bottom = st.text_area(
                    "Comment for Brand Deep-Dive (optional)",
                    key=f"ns_west_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save WEST+CSD Zone Drill-Down to Dashboard", key=f"save_ns_west_{segment['id']}"):
                    if not selected_states_west:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "WEST+CSD State Drill-Down")
                        
                        comments_json = json.dumps({"top": west_comment_top, "bottom": west_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "states": selected_states_west,
                            "zone": "West+CSD Zone"
                        })
                        save_table(
                            name="WEST+CSD State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "NS M INR"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("WEST+CSD Zone Drill-Down saved to dashboard!")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 6. EAST Zone State Drill-Down
    st.markdown("### 6. EAST Zone - State Drill-Down")
    st.caption("State-level performance within EAST zone with brand deep-dive")
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_east = df_filtered[df_filtered["Zone"] == "East Zone"].copy()
            
            if df_east.empty:
                st.info("No data available for EAST zone.")
            else:
                states_in_east = sorted(df_east["State"].dropna().unique().tolist())
                
                st.markdown("**State Summary - All States in East Zone:**")
                preview_all_east = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, states_in_east, "East Zone")
                
                if preview_all_east:
                    summary_styled = style_state_summary(preview_all_east['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_east = preview_all_east['state_summary'][preview_all_east['state_summary']['State'] != 'EAST']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table
                east_comment_top = st.text_area(
                    "Comment for State Summary Table (optional)",
                    key=f"ns_east_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                selected_states_east = st.multiselect(
                    "Select States for Brand Deep-Dive",
                    options=sorted_states_east if preview_all_east else states_in_east,
                    default=sorted_states_east[:4] if (preview_all_east and len(sorted_states_east) > 4) else (sorted_states_east if preview_all_east else states_in_east[:4]),
                    key=f"ns_east_states_{segment['id']}"
                )
                
                if selected_states_east:
                    st.markdown("**Preview - State Deep-Dive:**")
                    preview_east = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, selected_states_east, "East Zone")
                    
                    if preview_east and preview_east['state_details']:
                        render_state_drilldown_preview(preview_east, selected_states_east)
                
                # Comment for brand deep-dive AFTER preview
                st.markdown("---")
                east_comment_bottom = st.text_area(
                    "Comment for Brand Deep-Dive (optional)",
                    key=f"ns_east_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save EAST Zone Drill-Down to Dashboard", key=f"save_ns_east_{segment['id']}"):
                    if not selected_states_east:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "EAST State Drill-Down")
                        
                        comments_json = json.dumps({"top": east_comment_top, "bottom": east_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "states": selected_states_east,
                            "zone": "East Zone"
                        })
                        save_table(
                            name="EAST State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "NS M INR"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("EAST Zone Drill-Down saved to dashboard!")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")
    
    st.markdown("---")
    
    # 7. SOUTH Zone State Drill-Down
    st.markdown("### 7. SOUTH Zone - State Drill-Down")
    st.caption("State-level performance within SOUTH zone with brand deep-dive")
    
    if selected_families and selected_brands:
        if "State" not in df_filtered.columns:
            st.warning("State column not found in dataset.")
        else:
            df_south = df_filtered[df_filtered["Zone"] == "South Zone"].copy()
            
            if df_south.empty:
                st.info("No data available for SOUTH zone.")
            else:
                states_in_south = sorted(df_south["State"].dropna().unique().tolist())
                
                st.markdown("**State Summary - All States in South Zone:**")
                preview_all_south = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, states_in_south, "South Zone")
                
                if preview_all_south:
                    summary_styled = style_state_summary(preview_all_south['state_summary'])
                    st.dataframe(summary_styled, use_container_width=True, hide_index=True)
                    
                    # Get sorted states from summary (excluding zone row)
                    sorted_states_south = preview_all_south['state_summary'][preview_all_south['state_summary']['State'] != 'SOUTH']['State'].tolist()
                
                # Comment for state summary table - RIGHT AFTER the table
                south_comment_top = st.text_area(
                    "Comment for State Summary Table (optional)",
                    key=f"ns_south_comment_top_{segment['id']}",
                    placeholder="Add insights about state-level performance...",
                    height=100
                )
                
                st.markdown("---")
                
                selected_states_south = st.multiselect(
                    "Select States for Brand Deep-Dive",
                    options=sorted_states_south if preview_all_south else states_in_south,
                    default=sorted_states_south[:4] if (preview_all_south and len(sorted_states_south) > 4) else (sorted_states_south if preview_all_south else states_in_south[:4]),
                    key=f"ns_south_states_{segment['id']}"
                )
                
                if selected_states_south:
                    st.markdown("**Preview - State Deep-Dive:**")
                    preview_south = create_zone_state_drilldown(df_filtered, selected_families, selected_brands, selected_states_south, "South Zone")
                    
                    if preview_south and preview_south['state_details']:
                        render_state_drilldown_preview(preview_south, selected_states_south)
                
                # Comment for brand deep-dive AFTER preview
                st.markdown("---")
                south_comment_bottom = st.text_area(
                    "Comment for Brand Deep-Dive (optional)",
                    key=f"ns_south_comment_bottom_{segment['id']}",
                    placeholder="Add insights about brand performance by state...",
                    height=100
                )
                
                if st.button("Save SOUTH Zone Drill-Down to Dashboard", key=f"save_ns_south_{segment['id']}"):
                    if not selected_states_south:
                        st.error("Please select at least one state for deep-dive.")
                    else:
                        delete_tables_for_section(segment["id"], "NS Landscape", "SOUTH State Drill-Down")
                        
                        comments_json = json.dumps({"top": south_comment_top, "bottom": south_comment_bottom})
                        filter_config = json.dumps({
                            "brand_families": selected_families,
                            "brands": selected_brands,
                            "states": selected_states_south,
                            "zone": "South Zone"
                        })
                        save_table(
                            name="SOUTH State Drill-Down",
                            dataset_id=dataset_id,
                            columns=["State", "Brand Family", "Brand", "NS M INR"],
                            created_by=current_user["username"],
                            segment_id=segment["id"],
                            section="NS Landscape",
                            filter_json=filter_config,
                            comment=comments_json
                        )
                        st.success("SOUTH Zone Drill-Down saved to dashboard!")
    else:
        st.info("Configure Brand Families and Brands in section 2 first.")


def render_segment_truths_config(segment: Dict, df_filtered: pd.DataFrame, dataset_id: int, current_user: Dict) -> None:
    """Configure Segment Truths: Title, Image, Comment, and Profile Data"""
    st.markdown("#### Segment Truths Configuration")
    
    # Title input
    segment_title = st.text_input(
        "Segment Title",
        value="",
        placeholder="e.g., Younger (LDA-35yo); Singles & Nuclear Families...",
        key=f"seg_truth_title_{segment['id']}"
    )
    
    # Big comment box
    st.markdown("**Segment Insights:**")
    segment_comment = st.text_area(
        "Add detailed insights about the segment",
        placeholder="• 60% Young (LDA-35) consumers; 88% Graduates\n• 57% Urban & 26% Semi-urban\n• Segment over-indexing on SEC A...",
        height=200,
        key=f"seg_truth_comment_{segment['id']}"
    )
    
    # Preview section
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
        st.markdown("**P3M Segment Profile Data:**")
        # Expander with profile data
        with st.expander("View Profile Data", expanded=True):
            # Hardcoded data table
            profile_data = {
                "Metric": [
                "P3M Seg Profile",
                "LDA-24",
                "25-30",
                "LDA-35",
                "36-45",
                "46+",
                "",
                "NCCS A",
                "",
                "Single",
                "Married w/ Kids",
                "Married w/o Kids",
                "Single Parent",
                "",
                "Business Owners",
                "Salaried",
                "",
                "High",
                "Medium",
                "Low",
                "",
                "NE: Directs Entrant",
                "NE: From Beer",
                "NE: From Whites",
                "NE: NETT",
                "Non-Entrant",
                "",
                "Core %",
                "Repertoire %"
                ],
                "TBA": [
                "",
                "8%",
                "43%",
                "56%",
                "32%",
                "17%",
                "",
                "68",
                "",
                "28%",
                "41%",
                "9%",
                "21%",
                "",
                "40%",
                "56%",
                "",
                "63%",
                "28%",
                "9%",
                "",
                "9%",
                "8%",
                "10%",
                "27%",
                "73%",
                "",
                "",
                ""
                ],
                "Premium Whisky": [
                "",
                "10%",
                "45%",
                "60%",
                "31%",
                "14%",
                "",
                "72",
                "",
                "32%",
                "34%",
                "7%",
                "26%",
                "",
                "41%",
                "56%",
                "",
                "68%",
                "25%",
                "6%",
                "",
                "10%",
                "9%",
                "13%",
                "32%",
                "68%",
                "",
                "42%",
                "58%"
                ]
            }
            
            df_profile = pd.DataFrame(profile_data)
            st.dataframe(df_profile, use_container_width=True, hide_index=True, height=450)
    
    # Save button for title, comment, and profile data
    if st.button("Save Segment Insights to Dashboard", key=f"save_seg_insights_{segment['id']}"):
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
    
    # Image uploads section - SEPARATE
    st.markdown("---")
    st.markdown("### Supporting Visuals")
    st.markdown("**Upload Images (Optional):**")
    st.caption("Upload up to 3 images that will be displayed one below the other")
    
    uploaded_image_1 = st.file_uploader(
        "Image 1",
        type=["png", "jpg", "jpeg"],
        key=f"seg_truth_img1_{segment['id']}"
    )
    
    uploaded_image_2 = st.file_uploader(
        "Image 2",
        type=["png", "jpg", "jpeg"],
        key=f"seg_truth_img2_{segment['id']}"
    )
    
    uploaded_image_3 = st.file_uploader(
        "Image 3",
        type=["png", "jpg", "jpeg"],
        key=f"seg_truth_img3_{segment['id']}"
    )
    
    # Preview uploaded images
    if uploaded_image_1 or uploaded_image_2 or uploaded_image_3:
        st.markdown("**Image Preview:**")
        if uploaded_image_1:
            st.image(uploaded_image_1, caption="Image 1", use_container_width=True)
        if uploaded_image_2:
            st.image(uploaded_image_2, caption="Image 2", use_container_width=True)
        if uploaded_image_3:
            st.image(uploaded_image_3, caption="Image 3", use_container_width=True)
    
    # Separate save button for images only
    if st.button("Save Images to Dashboard", key=f"save_seg_images_{segment['id']}"):
        if not (uploaded_image_1 or uploaded_image_2 or uploaded_image_3):
            st.error("Please upload at least one image.")
        else:
            from app_core.media import save_media_upload
            
            # Delete existing images for this section
            delete_media_for_section(segment["id"], "Segment Truths", "Segment Truth Images")
            
            if uploaded_image_1:
                save_media_upload(
                    uploaded_file=uploaded_image_1,
                    segment_id=segment["id"],
                    section="Segment Truths",
                    created_by=current_user["username"],
                    comment="Image 1",
                    label="Segment Truth Images"
                )
            
            if uploaded_image_2:
                save_media_upload(
                    uploaded_file=uploaded_image_2,
                    segment_id=segment["id"],
                    section="Segment Truths",
                    created_by=current_user["username"],
                    comment="Image 2",
                    label="Segment Truth Images"
                )
            
            if uploaded_image_3:
                save_media_upload(
                    uploaded_file=uploaded_image_3,
                    segment_id=segment["id"],
                    section="Segment Truths",
                    created_by=current_user["username"],
                    comment="Image 3",
                    label="Segment Truth Images"
                )
            
            st.success("Images saved to dashboard!")


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
                
                display_df = state_df.drop(columns=['Type'])
                styled_df = display_df.style.apply(highlight_families, axis=1).applymap(color_negatives)
                st.dataframe(styled_df, use_container_width=True, hide_index=True, height=350)


def create_zone_state_drilldown(df: pd.DataFrame, selected_families: List[str], selected_brands: List[str], selected_states: List[str], zone_name: str) -> Dict | None:
    """Generic function to create state drill-down for any zone"""
    
    if df.empty:
        return None
    
    # Filter for specified zone and selected brands/families
    df_zone = df[df["Zone"] == zone_name].copy()
    df_zone = df_zone[df_zone["Brand Family"].isin(selected_families)]
    df_zone = df_zone[df_zone["Brand"].isin(selected_brands)]
    
    if df_zone.empty:
        return None
    
    # Separate A24 and A25 data
    df_a25 = df_zone[df_zone["PRI Year"] == "A25"].copy()
    df_a24 = df_zone[df_zone["PRI Year"] == "A24"].copy()
    
    # Calculate All India totals (for the segment with selected brands)
    df_all = df[df["Brand Family"].isin(selected_families) & df["Brand"].isin(selected_brands)].copy()
    ai_a25_total = df_all[df_all["PRI Year"] == "A25"]["NS M INR"].sum()
    ai_a24_total = df_all[df_all["PRI Year"] == "A24"]["NS M INR"].sum()
    ai_growth = ((ai_a25_total / ai_a24_total) - 1) * 100 if ai_a24_total > 0 else 0
    
    # ===== STATE SUMMARY TABLE =====
    state_a25 = df_a25.groupby("State")["NS M INR"].sum().to_dict()
    state_a24 = df_a24.groupby("State")["NS M INR"].sum().to_dict()
    
    # Calculate zone totals
    zone_a25 = sum(state_a25.values())
    zone_a24 = sum(state_a24.values())
    zone_sal = (zone_a25 / ai_a25_total * 100) if ai_a25_total > 0 else 0
    zone_growth = ((zone_a25 / zone_a24) - 1) * 100 if zone_a24 > 0 else 0
    zone_btm = zone_growth - ai_growth
    
    # Get zone display name
    zone_display = zone_name.replace(" Zone", "").replace("+", "+").upper()
    
    summary_rows = []
    
    # First row: Zone summary
    summary_rows.append({
        "State": zone_display,
        "A25 Sal % Contribution to AI": f"{zone_sal:.0f}%",
        "A25 Gr": f"{zone_growth:+.1f}%",
        "BTM": f"{zone_btm:+.1f}%"
    })
    
    # Then individual states - collect with numeric salience for sorting
    state_rows_with_sal = []
    for state in selected_states:
        a25_ns = state_a25.get(state, 0)
        a24_ns = state_a24.get(state, 0)
        
        sal_contribution = (a25_ns / ai_a25_total * 100) if ai_a25_total > 0 else 0
        state_growth = ((a25_ns / a24_ns) - 1) * 100 if a24_ns > 0 else 0
        btm = state_growth - ai_growth
        
        state_rows_with_sal.append({
            "State": state,
            "A25 Sal % Contribution to AI": f"{sal_contribution:.0f}%",
            "A25 Gr": f"{state_growth:+.1f}%",
            "BTM": f"{btm:+.1f}%",
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
    brand_state_a25 = df_a25.groupby(["State", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    brand_state_a24 = df_a24.groupby(["State", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    
    state_details = {}
    
    for state in selected_states:
        segment_state_a25 = state_a25.get(state, 0)
        segment_state_a24 = state_a24.get(state, 0)
        segment_state_growth = ((segment_state_a25 / segment_state_a24) - 1) * 100 if segment_state_a24 > 0 else 0
        
        detail_rows = []
        
        for family in selected_families:
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
            ]["NS M INR"].sum()
            family_a24 = brand_state_a24[
                (brand_state_a24["State"] == state) & (brand_state_a24["Brand Family"] == family)
            ]["NS M INR"].sum()
            
            if family_a25 == 0 and family_a24 == 0:
                detail_rows.append({
                    "Brand": f"{family} FAM",
                    "MS": "-",
                    "A25 Gr": "-",
                    "BTM": "-",
                    "Type": "family"
                })
            else:
                family_ms = (family_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                family_growth = ((family_a25 / family_a24) - 1) * 100 if family_a24 > 0 else 0
                family_btm = family_growth - segment_state_growth
                
                detail_rows.append({
                    "Brand": f"{family} FAM",
                    "MS": f"{family_ms:.0f}%",
                    "A25 Gr": f"{family_growth:+.1f}%",
                    "BTM": f"{family_btm:+.0f}%",
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
                
                brand_a25 = brand_data_a25["NS M INR"].sum() if not brand_data_a25.empty else 0
                brand_a24 = brand_data_a24["NS M INR"].sum() if not brand_data_a24.empty else 0
                
                if brand_a25 == 0 and brand_a24 == 0:
                    detail_rows.append({
                        "Brand": brand,
                        "MS": "-",
                        "A25 Gr": "-",
                        "BTM": "-",
                        "Type": "brand"
                    })
                else:
                    brand_ms = (brand_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 and brand_a25 > 0 else 0
                    brand_growth = ((brand_a25 / brand_a24) - 1) * 100 if brand_a24 > 0 else 0
                    brand_btm = brand_growth - segment_state_growth
                    
                    detail_rows.append({
                        "Brand": brand,
                        "MS": f"{brand_ms:.0f}%",
                        "A25 Gr": f"{brand_growth:+.1f}%",
                        "BTM": f"{brand_btm:+.0f}%",
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
    
    # Need both A24 and A25 data for growth calculation
    df_all = df.copy()
    
    # Filter to selected brands and families
    df_a25 = df_all[(df_all["PRI Year"] == "A25") & 
                    (df_all["Brand Family"].isin(selected_families)) & 
                    (df_all["Brand"].isin(selected_brands))].copy()
    
    df_a24 = df_all[(df_all["PRI Year"] == "A24") & 
                    (df_all["Brand Family"].isin(selected_families)) & 
                    (df_all["Brand"].isin(selected_brands))].copy()
    
    # Get all zones
    zones = sorted(df_a25["Zone"].unique().tolist())
    
    # THREE LEVELS OF AGGREGATION FOR A25:
    
    # Level 1: Zone × Brand Family × Brand (most granular)
    brand_zone_a25 = df_a25.groupby(["Zone", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    brand_zone_a24 = df_a24.groupby(["Zone", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    
    # Level 2: Zone × Brand Family (family totals per zone)
    family_zone_a25 = df_a25.groupby(["Zone", "Brand Family"])["NS M INR"].sum().reset_index()
    family_zone_a24 = df_a24.groupby(["Zone", "Brand Family"])["NS M INR"].sum().reset_index()
    
    # Level 3: Zone only (segment totals per zone)
    segment_zone_a25 = df_a25.groupby("Zone")["NS M INR"].sum().to_dict()
    segment_zone_a24 = df_a24.groupby("Zone")["NS M INR"].sum().to_dict()
    
    # Calculate segment growth for each zone
    segment_growth = {}
    for zone in zones:
        a25_total = segment_zone_a25.get(zone, 0)
        a24_total = segment_zone_a24.get(zone, 0)
        segment_growth[zone] = ((a25_total / a24_total) - 1) * 100 if a24_total > 0 else 0
    
    # Build unified table
    rows = []
    
    for family in selected_families:
        # Get brands in this family from the data
        family_brands_in_data = brand_zone_a25[brand_zone_a25["Brand Family"] == family]["Brand"].unique().tolist()
        family_brands = [b for b in selected_brands if b in family_brands_in_data]
        
        if not family_brands:
            continue
        
        # Add Brand Family header row
        family_row = {"Brand": f"{family} FAM", "Type": "family"}
        
        # Calculate family total across all zones for salience
        family_total_all_zones = family_zone_a25[family_zone_a25["Brand Family"] == family]["NS M INR"].sum()
        
        for zone in zones:
            # Get family totals for this zone
            family_zone_data_a25 = family_zone_a25[(family_zone_a25["Zone"] == zone) & (family_zone_a25["Brand Family"] == family)]
            family_sum_a25 = family_zone_data_a25["NS M INR"].sum() if not family_zone_data_a25.empty else 0
            
            family_zone_data_a24 = family_zone_a24[(family_zone_a24["Zone"] == zone) & (family_zone_a24["Brand Family"] == family)]
            family_sum_a24 = family_zone_data_a24["NS M INR"].sum() if not family_zone_data_a24.empty else 0
            
            # MS = Family share in this zone (vs segment total in zone)
            segment_total_zone = segment_zone_a25.get(zone, 0)
            family_ms = (family_sum_a25 / segment_total_zone * 100) if segment_total_zone > 0 else 0
            
            # Salience = This zone's share of family's total across all zones
            family_salience = (family_sum_a25 / family_total_all_zones * 100) if family_total_all_zones > 0 else 0
            
            # Growth = Family growth in this zone
            family_growth = ((family_sum_a25 / family_sum_a24) - 1) * 100 if family_sum_a24 > 0 else 0
            
            # BTM = Family growth - Segment growth in this zone
            family_btm = family_growth - segment_growth[zone]
            
            family_row[f"{zone}_MS"] = f"{family_ms:.0f}% | {family_salience:.0f}%"
            family_row[f"{zone}_Gr"] = f"{family_growth:.1f}%"
            family_row[f"{zone}_BTM"] = f"{family_btm:+.0f}%"
        
        rows.append(family_row)
        
        # Add individual brand rows
        for brand in family_brands:
            brand_row = {"Brand": brand, "Type": "brand"}
            
            # Calculate brand total across all zones for salience
            brand_total_all_zones = brand_zone_a25[(brand_zone_a25["Brand Family"] == family) & 
                                                     (brand_zone_a25["Brand"] == brand)]["NS M INR"].sum()
            
            for zone in zones:
                # Get brand data for this zone
                brand_zone_data_a25 = brand_zone_a25[(brand_zone_a25["Zone"] == zone) & 
                                                       (brand_zone_a25["Brand Family"] == family) & 
                                                       (brand_zone_a25["Brand"] == brand)]
                a25_val = brand_zone_data_a25["NS M INR"].sum() if not brand_zone_data_a25.empty else 0
                
                brand_zone_data_a24 = brand_zone_a24[(brand_zone_a24["Zone"] == zone) & 
                                                       (brand_zone_a24["Brand Family"] == family) & 
                                                       (brand_zone_a24["Brand"] == brand)]
                a24_val = brand_zone_data_a24["NS M INR"].sum() if not brand_zone_data_a24.empty else 0
                
                # MS = Brand share in this zone (vs segment total in zone)
                segment_total_zone = segment_zone_a25.get(zone, 0)
                ms = (a25_val / segment_total_zone * 100) if segment_total_zone > 0 else 0
                
                # Salience = This zone's share of brand's total across all zones
                salience = (a25_val / brand_total_all_zones * 100) if brand_total_all_zones > 0 else 0
                
                # Growth = Brand growth in this zone
                growth = ((a25_val / a24_val) - 1) * 100 if a24_val > 0 else 0
                
                # BTM = Brand growth - Segment growth in this zone
                btm = growth - segment_growth[zone]
                
                brand_row[f"{zone}_MS"] = f"{ms:.0f}% | {salience:.0f}%"
                brand_row[f"{zone}_Gr"] = f"{growth:.1f}%"
                brand_row[f"{zone}_BTM"] = f"{btm:+.0f}%"
            
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
    """Create manufacturing pivot table with YoY growth and CAGR (no base year shown)"""
    
    # Filter to selected years
    df_years = df[df["PRI Year"].isin(selected_years)].copy()
    
    if df_years.empty:
        return None
    
    # Create pivot
    pivot = pd.pivot_table(
        df_years,
        index="Mfg Com",
        columns="PRI Year",
        values="NS M INR",
        aggfunc="sum",
        fill_value=0
    )
    
    # Reindex to ensure year order
    pivot = pivot.reindex(columns=selected_years, fill_value=0)
    
    # Add Segment Total row
    segment_total = pivot.sum(axis=0).to_frame().T
    segment_total.index = ["Segment Total"]
    pivot = pd.concat([pivot, segment_total], axis=0)
    
    # Keep only growth columns (no base year)
    columns_to_keep = ["Mfg Com"]
    
    # Calculate YoY Growth %
    for i in range(1, len(selected_years)):
        prev_year = selected_years[i-1]
        curr_year = selected_years[i]
        if prev_year in pivot.columns and curr_year in pivot.columns:
            col_name = f"{curr_year} Growth %"
            pivot[col_name] = ((pivot[curr_year] - pivot[prev_year]) / pivot[prev_year] * 100).replace([np.inf, -np.inf], 0).fillna(0).round(1)
            columns_to_keep.append(col_name)
    
    # Calculate 2-Year CAGR (A23 to A25)
    if "A23" in selected_years and "A25" in selected_years:
        start = pivot["A23"]
        end = pivot["A25"]
        pivot["2 Yr CAGR %"] = np.where(
            start > 0,
            ((end / start) ** 0.5 - 1) * 100,
            0
        ).round(1)
        columns_to_keep.append("2 Yr CAGR %")
    
    # Reset index to make Mfg Com a column
    pivot = pivot.reset_index()
    pivot = pivot.rename(columns={"index": "Mfg Com"})
    
    # Sort: Segment Total first, then others
    custom_order = ["Segment Total", "PRI", "Diageo", "Others"]
    pivot["sort_key"] = pivot["Mfg Com"].apply(lambda x: custom_order.index(x) if x in custom_order else 999)
    pivot = pivot.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)
    
    # Select only required columns (Mfg Com + growth columns + CAGR)
    final_columns = [col for col in columns_to_keep if col in pivot.columns]
    pivot_display = pivot[final_columns]
    
    return pivot_display


def create_north_state_drilldown(df: pd.DataFrame, selected_families: List[str], selected_brands: List[str], selected_states: List[str]) -> Dict | None:
    """Create NORTH zone state drill-down with state summary and brand deep-dive
    
    Formulas:
    - A25 Sal % Contribution to AI = State A25 NS / All India A25 NS × 100
    - A25 Gr (Segment) = (State A25 Seg NS - State A24 Seg NS) / State A24 Seg NS × 100
    - BTM (State vs AI) = State Growth - All India Growth
    - MS (in state) = Brand A25 NS in State / Segment A25 NS in State × 100
    - A25 Gr (Brand in state) = (Brand A25 NS - Brand A24 NS) / Brand A24 NS × 100
    - BTM (Brand vs Segment in state) = Brand Growth in State - Segment Growth in State
    """
    
    if df.empty:
        return None
    
    # Filter for NORTH zone and selected brands/families
    df_north = df[df["Zone"] == "North Zone"].copy()
    df_north = df_north[df_north["Brand Family"].isin(selected_families)]
    df_north = df_north[df_north["Brand"].isin(selected_brands)]
    
    if df_north.empty:
        return None
    
    # Separate A24 and A25 data
    df_a25 = df_north[df_north["PRI Year"] == "A25"].copy()
    df_a24 = df_north[df_north["PRI Year"] == "A24"].copy()
    
    # Calculate All India totals (for the segment with selected brands)
    df_all = df[df["Brand Family"].isin(selected_families) & df["Brand"].isin(selected_brands)].copy()
    ai_a25_total = df_all[df_all["PRI Year"] == "A25"]["NS M INR"].sum()
    ai_a24_total = df_all[df_all["PRI Year"] == "A24"]["NS M INR"].sum()
    ai_growth = ((ai_a25_total / ai_a24_total) - 1) * 100 if ai_a24_total > 0 else 0
    
    # ===== STATE SUMMARY TABLE =====
    # Aggregate by state for segment totals
    state_a25 = df_a25.groupby("State")["NS M INR"].sum().to_dict()
    state_a24 = df_a24.groupby("State")["NS M INR"].sum().to_dict()
    
    # Calculate NORTH zone totals (sum of all states in North Zone)
    north_zone_a25 = sum(state_a25.values())
    north_zone_a24 = sum(state_a24.values())
    north_zone_sal = (north_zone_a25 / ai_a25_total * 100) if ai_a25_total > 0 else 0
    north_zone_growth = ((north_zone_a25 / north_zone_a24) - 1) * 100 if north_zone_a24 > 0 else 0
    north_zone_btm = north_zone_growth - ai_growth
    
    summary_rows = []
    
    # First row: NORTH zone summary
    summary_rows.append({
        "State": "NORTH",
        "A25 Sal % Contribution to AI": f"{north_zone_sal:.0f}%",
        "A25 Gr": f"{north_zone_growth:+.1f}%",
        "BTM": f"{north_zone_btm:+.1f}%"
    })
    
    # Then individual states
    for state in selected_states:
        a25_ns = state_a25.get(state, 0)
        a24_ns = state_a24.get(state, 0)
        
        # A25 Sal % Contribution to AI
        sal_contribution = (a25_ns / ai_a25_total * 100) if ai_a25_total > 0 else 0
        
        # A25 Growth (Segment in state)
        state_growth = ((a25_ns / a24_ns) - 1) * 100 if a24_ns > 0 else 0
        
        # BTM (State vs AI)
        btm = state_growth - ai_growth
        
        summary_rows.append({
            "State": state,
            "A25 Sal % Contribution to AI": f"{sal_contribution:.0f}%",
            "A25 Gr": f"{state_growth:+.1f}%",
            "BTM": f"{btm:+.1f}%"
        })
    
    state_summary = pd.DataFrame(summary_rows)
    
    # ===== STATE DEEP-DIVE TABLES =====
    # Brand-level data by state
    brand_state_a25 = df_a25.groupby(["State", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    brand_state_a24 = df_a24.groupby(["State", "Brand Family", "Brand"])["NS M INR"].sum().reset_index()
    
    state_details = {}
    
    for state in selected_states:
        # Get segment total for this state (for MS calculation)
        segment_state_a25 = state_a25.get(state, 0)
        segment_state_a24 = state_a24.get(state, 0)
        segment_state_growth = ((segment_state_a25 / segment_state_a24) - 1) * 100 if segment_state_a24 > 0 else 0
        
        detail_rows = []
        
        for family in selected_families:
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
            ]["NS M INR"].sum()
            family_a24 = brand_state_a24[
                (brand_state_a24["State"] == state) & (brand_state_a24["Brand Family"] == family)
            ]["NS M INR"].sum()
            
            # If family has no sales in this state, show "-"
            if family_a25 == 0 and family_a24 == 0:
                detail_rows.append({
                    "Brand": f"{family} FAM",
                    "MS": "-",
                    "A25 Gr": "-",
                    "BTM": "-",
                    "Type": "family"
                })
            else:
                family_ms = (family_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 else 0
                family_growth = ((family_a25 / family_a24) - 1) * 100 if family_a24 > 0 else 0
                family_btm = family_growth - segment_state_growth
                
                detail_rows.append({
                    "Brand": f"{family} FAM",
                    "MS": f"{family_ms:.0f}%",
                    "A25 Gr": f"{family_growth:+.1f}%",
                    "BTM": f"{family_btm:+.0f}%",
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
                
                # Always show brand, even if 0
                brand_a25 = brand_data_a25["NS M INR"].sum() if not brand_data_a25.empty else 0
                brand_a24 = brand_data_a24["NS M INR"].sum() if not brand_data_a24.empty else 0
                
                # If brand has no sales in this state (both A25 and A24 are 0), show "-"
                if brand_a25 == 0 and brand_a24 == 0:
                    detail_rows.append({
                        "Brand": brand,
                        "MS": "-",
                        "A25 Gr": "-",
                        "BTM": "-",
                        "Type": "brand"
                    })
                else:
                    brand_ms = (brand_a25 / segment_state_a25 * 100) if segment_state_a25 > 0 and brand_a25 > 0 else 0
                    brand_growth = ((brand_a25 / brand_a24) - 1) * 100 if brand_a24 > 0 else 0
                    brand_btm = brand_growth - segment_state_growth
                    
                    detail_rows.append({
                        "Brand": brand,
                        "MS": f"{brand_ms:.0f}%",
                        "A25 Gr": f"{brand_growth:+.1f}%",
                        "BTM": f"{brand_btm:+.0f}%",
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
    """Configure Segment Trends: Carousel Images"""
    st.markdown("#### Segment Trends Configuration")
    st.caption("Upload images that will be displayed as tabs/pages")
    
    # Image uploads
    st.markdown("**Upload Images:**")
    st.caption("Upload multiple images - each will become a tab on the dashboard")
    
    uploaded_images = st.file_uploader(
        "Upload Images (multiple allowed)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key=f"seg_trends_images_{segment['id']}"
    )
    
    # Page names input for each uploaded image
    page_names = []
    if uploaded_images:
        st.markdown("**Name each page/tab:**")
        for idx, img in enumerate(uploaded_images):
            page_name = st.text_input(
                f"Page {idx+1} name",
                value=f"Page {idx+1}",
                key=f"seg_trends_page_name_{segment['id']}_{idx}",
                placeholder=f"Enter name for page {idx+1}"
            )
            page_names.append(page_name)
        
        # Preview uploaded images with custom names
        st.markdown(f"**Preview ({len(uploaded_images)} images uploaded):**")
        
        if len(uploaded_images) > 1:
            preview_tabs = st.tabs(page_names)
            for idx, (tab, img) in enumerate(zip(preview_tabs, uploaded_images)):
                with tab:
                    col1, col2, col3 = st.columns([0.5, 2, 0.5])
                    with col2:
                        st.image(img, use_container_width=True)
        else:
            col1, col2, col3 = st.columns([0.5, 2, 0.5])
            with col2:
                st.image(uploaded_images[0], use_container_width=True)
    
    # Save button
    if st.button("Save Segment Trends Images to Dashboard", key=f"save_seg_trends_{segment['id']}"):
        if not uploaded_images:
            st.error("Please upload at least one image.")
        else:
            from app_core.media import save_media_upload
            
            # Delete existing images for this section
            delete_media_for_section(segment["id"], "Segment Trends", "Segment Trends Carousel")
            
            # Save all uploaded images with custom page names
            for idx, uploaded_img in enumerate(uploaded_images):
                page_name = page_names[idx] if idx < len(page_names) else f"Page {idx+1}"
                save_media_upload(
                    uploaded_file=uploaded_img,
                    segment_id=segment["id"],
                    section="Segment Trends",
                    created_by=current_user["username"],
                    comment=page_name,  # Store page name in comment field
                    label="Segment Trends Carousel"
                )
            
            st.success(f"{len(uploaded_images)} image(s) saved to dashboard!")

    
    st.markdown("---")
    st.markdown("### Custom Trends View Builder")
    st.caption("Create a custom view with title, description, and numbered sections")
    
    # Title and main description
    trends_title = st.text_input(
        "View Title",
        value="",
        placeholder="e.g., Premium Whisky Trends in L1Y",
        key=f"trends_title_{segment['id']}"
    )
    
    trends_description = st.text_area(
        "Main Description",
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
        
        # Option to customize section number/label
        col_num, col_left, col_right = st.columns([1, 2, 2])
        
        with col_num:
            section_label = st.text_input(
                f"Label",
                value=str(i + 1),
                key=f"trends_sec{i}_label_{segment['id']}",
                help="Default is number, but you can use any text"
            )
        
        with col_left:
            left_content = st.text_area(
                f"Left content",
                placeholder="Enter content for left side...",
                height=100,
                key=f"trends_sec{i}_left_{segment['id']}"
            )
        
        with col_right:
            right_content = st.text_area(
                f"Right content",
                placeholder="Enter content for right side...",
                height=100,
                key=f"trends_sec{i}_right_{segment['id']}"
            )
        
        sections_data.append({
            "number": section_label,
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
            # Escape HTML and preserve line breaks
            import html
            escaped_desc = html.escape(trends_description).replace('\n', '<br>')
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
                        {escaped_desc}
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
                        import html
                        escaped_left = html.escape(section["left"]).replace('\n', '<br>')
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
                                    {escaped_left}
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                
                with cols[2]:
                    if section["right"]:
                        import html
                        escaped_right = html.escape(section["right"]).replace('\n', '<br>')
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
                                    {escaped_right}
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
