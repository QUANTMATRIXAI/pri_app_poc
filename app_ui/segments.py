import streamlit as st

from app_core.charts import count_charts_for_segment
from app_core.tables import count_tables_for_segment
from app_core.uploads import count_uploads_for_segment


def render_segment_landing(segments) -> None:
    st.subheader("Segments")
    st.caption("Choose a segment to enter its Data Studio and Dashboard.")
    if not segments:
        st.info("No segments configured.")
        return

    for i in range(0, len(segments), 3):
        cols = st.columns(3)
        for offset, segment in enumerate(segments[i : i + 3]):
            with cols[offset]:
                render_segment_card(segment)


def render_segment_card(segment) -> None:
    uploads = count_uploads_for_segment(segment["id"])
    charts = count_charts_for_segment(segment["id"])
    tables = count_tables_for_segment(segment["id"])
    total_blocks = charts + tables
    st.markdown(
        f"""
        <div class="info-card" style="border-top: 5px solid {segment.get('color', '#f5b400')}; min-height: 180px;">
            <div class="pill">Segment</div>
            <h3 style="margin: 0.2rem 0;">{segment['name']}</h3>
            <p style="color: var(--muted); margin:0;">{segment.get('description','')}</p>
            <div style="margin-top:0.6rem; display:flex; gap:0.7rem;">
                <div style="font-size:0.9rem;"><strong>{uploads}</strong> datasets</div>
                <div style="font-size:0.9rem;"><strong>{total_blocks}</strong> blocks</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(f"Open {segment['name']}", key=f"open_seg_{segment['id']}"):
        st.session_state["selected_segment_id"] = segment["id"]
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()
