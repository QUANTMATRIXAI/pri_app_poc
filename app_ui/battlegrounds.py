from typing import Dict

import streamlit as st

from app_core.battlegrounds import get_battleground_notes, save_battleground_note


def render_battleground_notes_editor(segment: Dict, current_user: Dict) -> None:
    """Editor UI to configure Battlegrounds JTBD tabs."""
    notes = get_battleground_notes(segment["id"])
    notes_by_index = {n["tab_index"]: n for n in notes}
    tabs = st.tabs(["Cluster 1", "Cluster 2", "Cluster 3"])
    for idx, tab in enumerate(tabs, start=1):
        saved = notes_by_index.get(idx, {})
        with tab:
            st.markdown(f"#### Cluster {idx}")
            title_key = f"bg_title_{segment['id']}_{idx}"
            working_key = f"bg_work_{segment['id']}_{idx}"
            jtbd_key = f"bg_jtbd_{segment['id']}_{idx}"
            title_val = st.text_input(
                "Tab name",
                value=saved.get("title", f"Cluster {idx}"),
                key=title_key,
                placeholder="e.g., Cluster 1: Premiums",
            )
            col_a, col_b = st.columns(2)
            with col_a:
                working_val = st.text_area(
                    "What's Working & Holding Us Back?",
                    value=saved.get("working_text", ""),
                    height=200,
                    key=working_key,
                )
            with col_b:
                jtbd_val = st.text_area(
                    "JTBDs",
                    value=saved.get("jtbd_text", ""),
                    height=200,
                    key=jtbd_key,
                )
            if st.button("Save tab", key=f"bg_save_{segment['id']}_{idx}"):
                save_battleground_note(
                    segment_id=segment["id"],
                    tab_index=idx,
                    title=title_val.strip() or f"Cluster {idx}",
                    working_text=working_val.strip(),
                    jtbd_text=jtbd_val.strip(),
                    username=current_user["username"],
                )
                st.success(f"Saved Cluster {idx}")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
