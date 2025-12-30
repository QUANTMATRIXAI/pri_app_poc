import streamlit as st
from app_core.auth import verify_credentials

def login_panel() -> None:
    st.markdown(
        """
        <style>
            /* Hide Streamlit chrome */
            [data-testid="stSidebar"],
            [data-testid="stHeader"],
            [data-testid="stToolbar"],
            footer,
            [data-testid="stDecoration"]{
                display:none !important;
            }

            /* Background */
            div[data-testid="stAppViewContainer"]{
                min-height:100vh !important;
                background:
                    radial-gradient(1100px circle at 12% 12%, rgba(245,180,0,0.14), transparent 42%),
                    radial-gradient(900px circle at 88% 10%, rgba(0,0,0,0.06), transparent 55%),
                    linear-gradient(180deg, #fcfcfd 0%, #f4f6fb 100%) !important;
            }

            /* --- TRUE CENTER (important) --- */
            div[data-testid="stAppViewContainer"] > section.main{
                padding: 0 !important;            /* remove top padding */
                margin: 0 !important;
                min-height: 100vh !important;
            }
            div[data-testid="stAppViewContainer"] > section.main > div{
                min-height: 100vh !important;     /* make wrapper full height */
                display: flex !important;
                align-items: center !important;   /* vertical center */
                justify-content: center !important; /* horizontal center */
            }

            /* Card */
            div[data-testid="stMainBlockContainer"],
            section.main .block-container{
                max-width: 440px !important;
                width: 100% !important;
                margin: 0 !important;             /* important for centering */
                padding: 22px 22px 18px 22px !important;

                background: rgba(255,255,255,0.92) !important;
                border: 1px solid rgba(17,24,39,0.10) !important;
                border-radius: 18px !important;
                box-shadow: 0 16px 40px rgba(0,0,0,0.08) !important;
                backdrop-filter: blur(10px) !important;
            }

            /* Remove form extra box */
            div[data-testid="stForm"], form[data-testid="stForm"]{
                border:none !important;
                background:transparent !important;
                padding:0 !important;
                box-shadow:none !important;
            }
            div[data-testid="stForm"] > div{ padding:0 !important; }

            /* Inputs + button (keep your styling as-is if you want) */
        </style>
        """,
        unsafe_allow_html=True,
    )

    # header
    c1, c2 = st.columns([1, 8], vertical_alignment="center")
    with c1:
        try:
            st.image("logo/1.jpg", width=52)
        except:
            pass
    with c2:
        st.markdown("<div style='font-size:20px;font-weight:750;'>Trinity Dashboard</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12.5px;color:#6b7280;'>Sign in to continue</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", placeholder="admin@quantmatrix.ai")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submitted = st.form_submit_button("Sign In")

        if submitted:
            if not username.strip() or not password:
                st.error("Please enter both username and password")
            else:
                user = verify_credentials(username.strip(), password)
                if user:
                    st.session_state["user"] = user
                    st.rerun()
                else:
                    st.error("Invalid credentials")
