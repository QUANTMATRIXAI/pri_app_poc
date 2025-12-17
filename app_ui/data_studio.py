import json
from typing import Dict, List

import pandas as pd
import streamlit as st

from app_core.charts import delete_charts_for_section, get_charts_for_segment, save_chart
from app_core.constants import SECTIONS
from app_core.filters import apply_filters
from app_core.media import delete_media_for_section, save_media_upload
from app_core.tables import delete_tables_for_section, get_tables_for_segment, save_table
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


def render_data_upload(current_user: Dict, segment: Dict) -> None:
    st.subheader(f"Data Studio · {segment['name']}")
    st.caption(
        "Publish charts or tables to the dashboard for this segment. All uploads, previews, and saves stay within this segment."
    )

    blocks_tab, upload_tab = st.tabs(["Dashboard blocks", "Upload data"])

    with blocks_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Configure dashboard blocks")
        render_block_publisher(current_user, segment)
        st.markdown("</div>", unsafe_allow_html=True)

    with upload_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Upload CSV / Excel to this segment")
        col_a, col_b = st.columns([2, 1])
        with col_a:
            uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"], key=f"upload_{segment['id']}")
        with col_b:
            if st.button("Load sample dataset", key=f"sample_{segment['id']}"):
                sample_df = get_sample_dataset()
                upload_id = save_upload_for_segment(
                    "sample_dataset.csv", sample_df, current_user["username"], segment["id"]
                )
                st.success(f"Loaded sample dataset #{upload_id} for {segment['name']}")
                st.dataframe(sample_df.head(), use_container_width=True)
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

        st.markdown("#### Manage datasets")
        uploads_list = get_uploads(segment_id=segment["id"])
        if not uploads_list:
            st.write("No datasets in this segment.")
        else:
            for row in uploads_list:
                charts_c, tables_c = get_dataset_usage(row["id"])
                cols = st.columns([2, 1, 1, 1])
                with cols[0]:
                    st.markdown(f"**{row['filename']}**")
                    st.caption(f"Uploaded: {row['uploaded_at']}")
                with cols[1]:
                    st.caption(f"Charts: {charts_c}")
                with cols[2]:
                    st.caption(f"Tables: {tables_c}")
                with cols[3]:
                    disabled = charts_c > 0 or tables_c > 0
                    label = "In use" if disabled else "Delete"
                    if st.button(label, key=f"del_upload_{row['id']}", disabled=disabled):
                        ok, msg = delete_upload(row["id"])
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # Status expander
    charts = get_charts_for_segment(segment["id"])
    tables = get_tables_for_segment(segment["id"])
    with st.expander("Current dashboard status"):
        st.markdown(
            f"- Charts: **{len(charts)}**  \n- Tables: **{len(tables)}**",
            unsafe_allow_html=False,
        )
        if charts:
            st.markdown("**Charts**")
            for c in charts:
                st.markdown(f"- {c['name']} · {c['section']}")
        if tables:
            st.markdown("**Tables**")
            for t in tables:
                st.markdown(f"- {t['name']} · {t['section']}")


def render_block_publisher(current_user: Dict, segment: Dict) -> None:
    uploads = get_uploads(segment_id=segment["id"])
    if not uploads:
        st.info("Upload data first to configure dashboard blocks.")
        if st.button("Load sample dataset", key=f"blocks_load_sample_{segment['id']}"):
            sample_df = get_sample_dataset()
            upload_id = save_upload_for_segment("sample_dataset.csv", sample_df, current_user["username"], segment["id"])
            st.success(f"Loaded sample dataset #{upload_id} for {segment['name']}")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        return

    upload_options = {f"#{row['id']} - {row['filename']}": row["id"] for row in uploads}
    selected_label = st.selectbox(
        "Dataset for previews",
        options=list(upload_options.keys()),
        index=0,
        key=f"blocks_dataset_{segment['id']}",
    )
    dataset_id = upload_options[selected_label]
    df = load_dataset(dataset_id)
    if df is None or df.empty:
        st.warning("Selected dataset is empty.")
        return

    blocks = [
        {
            "name": "NS Landscape - Yearly Sales",
            "section": "NS Landscape",
            "type": "chart",
            "chart_type": "line",
            "view_mode": "yearly",
            "x_col": "year",
            "y_cols": ["sales"],
        },
        {
            "name": "Segment Truths - Yearly Volume",
            "section": "Segment Truths",
            "type": "chart",
            "chart_type": "bar",
            "view_mode": "yearly",
            "x_col": "year",
            "y_cols": ["volume"],
        },
        # Brand Truths and Segment Trends now use images instead of charts
        {"name": "Brand Trends - Monthly Table", "section": "Brand Trends", "type": "table", "view_mode": "monthly", "columns": ["year", "month", "brand", "sales", "volume", "price"]},
        {"name": "Battlegrounds - Yearly Price Table", "section": "Battlegrounds", "type": "table", "view_mode": "yearly", "columns": ["year", "brand", "price"]},
        {"name": "Brand Truths - Image", "section": "Brand Truths", "type": "media"},
        {"name": "Segment Trends - Image", "section": "Segment Trends", "type": "media"},
    ]

    st.markdown("**Preview & publish**")
    for block in blocks:
        key_suffix = f"{segment['id']}_{block['section'].replace(' ', '_')}_{block['name'].replace(' ', '_')}"
        # per-section filters
        brands = []
        years = []
        if block["type"] != "media":
            filter_col1, filter_col2 = st.columns([2, 2])
            with filter_col1:
                if "brand" in df.columns:
                    brands = st.multiselect(
                        "Brands",
                        options=sorted(df["brand"].dropna().unique().tolist()),
                        default=sorted(df["brand"].dropna().unique().tolist()),
                        key=f"{key_suffix}_brands",
                    )
            with filter_col2:
                if "year" in df.columns:
                    years = sorted(pd.to_numeric(df["year"], errors="coerce").dropna().astype(int).unique().tolist())
                    years = st.multiselect(
                        "Years",
                        options=years,
                        default=years,
                        key=f"{key_suffix}_years",
                    )

        filter_spec = {
            "brands": brands,
            "years": years,
            "view_mode": "monthly" if block.get("view_mode") == "monthly" else "yearly",
        }
        df_filtered = apply_filters(df.copy(), filter_spec) if block["type"] != "media" else df

        col_preview, col_actions = st.columns([3, 1])
        with col_preview:
            st.markdown(f"##### {block['name']} ({block['section']})")
            if block["type"] == "chart":
                if block["x_col"] not in df_filtered.columns:
                    st.warning(f"Column {block['x_col']} not in dataset.")
                else:
                    plot_chart(
                        df_filtered,
                        block["chart_type"],
                        block["x_col"],
                        block["y_cols"],
                        chart_key=f"block_preview_{key_suffix}",
                    )
            elif block["type"] == "table":
                cols_in_df = [c for c in block["columns"] if c in df_filtered.columns]
                if cols_in_df:
                    st.dataframe(df_filtered[cols_in_df].head(50), use_container_width=True)
                else:
                    st.warning("Columns not found in dataset.")
            else:
                st.info("Upload an image in the action column to publish to this section.")
        with col_actions:
            comment_key = f"block_comment_{key_suffix}"
            comment_val = st.text_area(
                "Comment (use **bold**, prefix with ## for a larger line)",
                key=comment_key,
                height=80,
                help="Wrap text with **double asterisks** to bold; start a line with ## for a larger heading.",
            )
            # extra comments list
            extra_key = f"block_extra_comments_{key_suffix}"
            if extra_key not in st.session_state:
                st.session_state[extra_key] = []
            note_key = f"add_note_{key_suffix}"
            new_comment = st.text_input("Add another note", key=note_key)
            if st.button("Add note", key=f"add_btn_{key_suffix}"):
                if new_comment.strip():
                    st.session_state[extra_key].append(new_comment.strip())
                    st.session_state[note_key] = ""
            if st.session_state[extra_key]:
                st.markdown("Extra notes:")
                to_remove = None
                for idx, note in enumerate(st.session_state[extra_key]):
                    cols_rm = st.columns([3, 1])
                    with cols_rm[0]:
                        st.write(f"- {note}")
                    with cols_rm[1]:
                        if st.button("Remove", key=f"rm_note_{key_suffix}_{idx}"):
                            to_remove = idx
                if to_remove is not None:
                    st.session_state[extra_key].pop(to_remove)
            if block["type"] == "media":
                uploaded = st.file_uploader(
                    "Images / PPT",
                    type=["png", "jpg", "jpeg", "ppt", "pptx"],
                    accept_multiple_files=True,
                    key=f"media_upload_{key_suffix}",
                )
                if st.button("Save to dashboard", key=f"save_block_{key_suffix}"):
                    if uploaded:
                        delete_media_for_section(segment["id"], block["section"])
                        for file in uploaded:
                            save_media_upload(
                                file,
                                segment["id"],
                                block["section"],
                                current_user["username"],
                                comment_val.strip() + format_extra_comments(st.session_state.get(extra_key, [])),
                            )
                        st.success(f"Saved {len(uploaded)} image(s) to {block['section']}")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                    else:
                        st.error("Upload an image to save.")
            else:
                if st.button("Save to dashboard", key=f"save_block_{key_suffix}"):
                    if block["type"] == "chart":
                        delete_charts_for_section(segment["id"], block["section"], block["name"])
                        save_chart(
                            block["name"],
                            block["chart_type"],
                            block["x_col"],
                            block["y_cols"],
                            dataset_id,
                            current_user["username"],
                            segment["id"],
                            block["section"],
                            json.dumps(filter_spec),
                            comment_val.strip() + format_extra_comments(st.session_state.get(extra_key, [])),
                        )
                    else:
                        delete_tables_for_section(segment["id"], block["section"], block["name"])
                        save_table(
                            block["name"],
                            dataset_id,
                            block["columns"],
                            current_user["username"],
                            segment["id"],
                            block["section"],
                            json.dumps(filter_spec),
                            comment_val.strip() + format_extra_comments(st.session_state.get(extra_key, [])),
                        )
                    st.success(f"Saved to {block['section']}")
                    if hasattr(st, "rerun"):
                        st.rerun()
                    else:
                        st.experimental_rerun()
def format_extra_comments(extras: list[str] | None) -> str:
    if not extras:
        return ""
    bullet = "<br>" + "<br>".join([f"• {c}" for c in extras])
    return bullet
