import streamlit as st

from app_core.charts import count_charts_for_segment
from app_core.segments import SEGMENT_ORDER
from app_core.tables import count_tables_for_segment
from app_core.uploads import count_uploads_for_segment, get_uploads


def render_segment_landing(segments) -> None:
    st.subheader("Segments")
    st.caption("Choose a segment to enter its Data Studio and Dashboard.")
    if not segments:
        st.info("No segments configured.")
        return

    name_to_rank = {name: idx + 1 for idx, name in enumerate(SEGMENT_ORDER)}
    total = len(SEGMENT_ORDER)

    first_row = segments[:3]
    second_row = segments[3:]

    cols = st.columns(3)
    for col, segment in zip(cols, first_row):
        with col:
            rank = name_to_rank.get(segment["name"], len(SEGMENT_ORDER) + 1)
            render_segment_card(segment, rank, total)

    if second_row:
        cols2 = st.columns(3)
        for idx, segment in enumerate(second_row):
            with cols2[idx]:
                rank = name_to_rank.get(segment["name"], len(SEGMENT_ORDER) + 1)
                render_segment_card(segment, rank, total)


def render_segment_card(segment, rank: int, total: int) -> None:
    uploads = count_uploads_for_segment(segment["id"])
    if uploads == 0:
        uploads = len(get_uploads())
    charts = count_charts_for_segment(segment["id"])
    tables = count_tables_for_segment(segment["id"])
    total_blocks = charts + tables
    st.markdown(
        f"""
        <div class="info-card" style="border-top: 5px solid {segment.get('color', '#f5b400')}; min-height: 160px;">
            <div style="display:flex; align-items:center; gap:0.4rem; margin-bottom:0.2rem;">
                <div class="pill">Segment</div>
                <div class="pill" style="background:rgba(0,0,0,0.04); border-color:rgba(0,0,0,0.08); color: var(--text);">Tier {rank}/{total}</div>
            </div>
            <h3 style="margin: 0.1rem 0;">{segment['name']}</h3>
            <p style="color: var(--muted); margin:0;">{segment.get('description','')}</p>
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
