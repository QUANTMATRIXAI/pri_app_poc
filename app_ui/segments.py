import streamlit as st

from app_core.charts import count_charts_for_segment
from app_core.tables import count_tables_for_segment
from app_core.uploads import count_uploads_for_segment, get_uploads


def render_segment_landing(segments) -> None:
    st.subheader("Segments")
    st.caption("Choose a segment to enter its Data Studio and Dashboard.")
    if not segments:
        st.info("No segments configured.")
        return

    # Display segments in rows of 4
    rows = [segments[i:i+4] for i in range(0, len(segments), 4)]
    
    for row in rows:
        cols = st.columns(4)
        for col, segment in zip(cols, row):
            with col:
                render_segment_card(segment)


def render_segment_card(segment) -> None:
    uploads = count_uploads_for_segment(segment["id"])
    if uploads == 0:
        uploads = len(get_uploads())
    charts = count_charts_for_segment(segment["id"])
    tables = count_tables_for_segment(segment["id"])
    total_blocks = charts + tables
    
    st.markdown(
        f"""
        <div class="info-card" style="border-top: 5px solid {segment.get('color', '#f5b400')}; min-height: 120px;">
            <h3 style="margin: 0.5rem 0; font-size: 1.2rem; color: #1d2733;">{segment['name']}</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(f"Open {segment['name']}", key=f"open_seg_{segment['id']}", use_container_width=True):
        st.session_state["selected_segment_id"] = segment["id"]
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()
