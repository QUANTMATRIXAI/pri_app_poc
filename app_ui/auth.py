import streamlit as st

from app_core.auth import verify_credentials


def login_panel() -> None:
    st.markdown(
        "<style>[data-testid='stSidebar'] { display: none; }</style>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="login-hero">
        <h2>Welcome to Trial Dashboard</h2>
        <p style="color: var(--muted);">Sign in to access the dashboard and data studio.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1.1, 1])
    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown("#### Sign in")
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username")
            password = st.text_input("Password", type="password", placeholder="Password")
            submitted = st.form_submit_button("Sign in")
        st.markdown("</div>", unsafe_allow_html=True)
    if submitted:
        user = verify_credentials(username.strip(), password)
        if user:
            st.session_state["user"] = user
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        else:
            st.error("Invalid credentials")

