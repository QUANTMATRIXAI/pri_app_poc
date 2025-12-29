import streamlit as st
from app_core.auth import verify_credentials

def login_panel() -> None:
    # 1. Page Configuration & Global Styles
    st.markdown(
        """
        <style>
            /* Hides the default Streamlit sidebar and header */
            [data-testid="stSidebar"], [data-testid="stHeader"] {
                display: none;
            }
            
            /* GLOBAL BACKGROUND: Soft professional gradient */
            .stApp {
                background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                background-attachment: fixed;
            }

            /* VERTICAL CENTER ALIGNMENT */
            /* This forces the main container to center its content vertically */
            .main .block-container {
                padding-top: 2rem !important;
                padding-bottom: 2rem !important;
                max-width: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 90vh; /* Takes up most of the viewport height */
            }

            /* LOGIN CARD CONTAINER */
            /* This is the white box holding the form */
            div[data-testid="stVerticalBlock"] > div:has(div.login-header) {
                # background-color: white;
                # padding: 1rem 1rem;
                # border-radius: 2px;
                # box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                # width: 100%;
                max-width: 750px; /* Wider card */
                margin: auto;
                /* Replace the old border line with this: */
                border: 20px solid #f5b400;
            }

            /* TEXT INPUT STYLING */
            .stTextInput > div > div > input {
                border-radius: 10px !important;
                border: 1px solid #e0e0e0 !important;
                padding: 12px 18px !important;
                background-color: #f9f9f9 !important;
                color: #333 !important;
                transition: all 0.3s ease;
                font-size: 1rem !important;
            }
            
            /* Focus state for inputs (Yellow glow) */
            .stTextInput > div > div > input:focus {
                border-color: #f5b400 !important;
                background-color: #fff !important;
                box-shadow: 0 0 0 2px rgba(245, 180, 0, 0.2) !important;
            }
            
            /* Input Labels */
            .stTextInput label {
                font-size: 14px !important;
                color: #555 !important;
                font-weight: 500 !important;
            }

            /* SUBMIT BUTTON STYLING */
            .stButton > button {
                width: 100%;
                background-color: #f5b400 !important; /* Your Brand Yellow */
                color: #000 !important;
                border: none !important;
                border-radius: 10px !important;
                padding: 0.85rem 1rem !important;
                font-weight: 700 !important;
                font-size: 1rem !important;
                letter-spacing: 0.5px;
                transition: all 0.3s ease;
                margin-top: 10px;
            }
            
            .stButton > button:hover {
                background-color: #e0a800 !important;
                box-shadow: 0 5px 15px rgba(245, 180, 0, 0.3);
                transform: translateY(-1px);
            }
            
            .stButton > button:active {
                transform: translateY(1px);
            }

            /* Custom Typography Classes */
            .login-header {
                text-align: center;
                margin-bottom: 1.5rem;
            }
            .login-title {
                font-size: 2rem;
                font-weight: 700;
                color: #1a1a1a;
                margin-top: 10px;
                margin-bottom: 5px;
            }
            .login-subtitle {
                font-size: 0.95rem;
                color: #666;
            }
            
            /* Logo Alignment */
            .logo-container {
                display: flex;
                justify-content: center;
                margin-bottom: 1.5rem;
            }
            .stImage {
                display: flex;
                justify-content: center;
            }
            .stImage > img {
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # 2. Layout Structure
    # We use a centered column with specific max-width logic
    col_left, col_main, col_right = st.columns([1, 4, 1])

    with col_main:
        # We inject a div with class 'login-header' to anchor our CSS selector above
        st.markdown('<div class="login-header">', unsafe_allow_html=True)
        
        # Logo Handling
        try:
            # Display logo with proper size
            st.image("logo/1.jpg", width=200)
        except:
            st.warning("Logo not found")

        st.markdown('<div class="login-title">Trinity Dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-subtitle">Please sign in to continue</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True) # End Header

        # 3. The Form
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="admin@quantmatrix.ai")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            
            # Spacing
            st.markdown("###") 
            
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