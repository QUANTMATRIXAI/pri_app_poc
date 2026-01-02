import streamlit as st
from app_core.auth import verify_credentials
import os
import base64

def login_panel() -> None:
    # Minimal CSS - just hide sidebar and style button
    st.markdown(
        """
        <style>
            [data-testid="stSidebar"] { display: none !important; }
            
            /* Professional gradient background with subtle pattern */
            .stApp {
                background: 
                    radial-gradient(circle at 20% 80%, rgba(245, 180, 0, 0.08) 0%, transparent 50%),
                    radial-gradient(circle at 80% 20%, rgba(29, 39, 51, 0.05) 0%, transparent 50%),
                    radial-gradient(circle at 40% 40%, rgba(245, 180, 0, 0.04) 0%, transparent 30%),
                    linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #f1f5f9 100%) !important;
            }
            
            /* Subtle animated gradient overlay */
            .stApp::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: 
                    url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23f5b400' fill-opacity='0.03'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
                pointer-events: none;
                z-index: 0;
            }
            
            .stButton button {
                width: 100%;
                background: white !important;
                color: #f5b400 !important;
                border: 2px solid #f5b400 !important;
                font-weight: 600 !important;
                box-shadow: 0 4px 14px rgba(245, 180, 0, 0.15) !important;
                transition: all 0.3s ease !important;
            }
            .stButton button:hover {
                background: #f5b400 !important;
                color: white !important;
                box-shadow: 0 6px 20px rgba(245, 180, 0, 0.3) !important;
                transform: translateY(-1px) !important;
            }
            
            /* Style the form container */
            [data-testid="stForm"] {
                background: rgba(255, 255, 255, 0.9) !important;
                backdrop-filter: blur(10px) !important;
                border-radius: 16px !important;
                padding: 2rem !important;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08) !important;
                border: 1px solid rgba(255, 255, 255, 0.8) !important;
            }
            
            /* Style inputs */
            .stTextInput input {
                border-radius: 10px !important;
                border: 1px solid #e2e8f0 !important;
                background: #f8fafc !important;
                transition: all 0.2s ease !important;
            }
            .stTextInput input:focus {
                border-color: #f5b400 !important;
                box-shadow: 0 0 0 3px rgba(245, 180, 0, 0.1) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Create centered layout
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Add some top spacing
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        # Title on left, Logo on right - using HTML for proper alignment
        logo_path = "static/Pernod_Ricard_logo_2019.svg.png"
        logo_html = ""
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                logo_data = base64.b64encode(f.read()).decode()
            logo_html = f'<img src="data:image/png;base64,{logo_data}" style="width: 120px;" />'
        
        st.markdown(
            f"""
            <div style='display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem;'>
                <h1 style='margin: 0; color: #1d2733; font-size: 1.6rem; font-weight: 700;'>
                    Strategic Alignment Dashboard
                </h1>
                {logo_html}
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Login form
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="admin@quantmatrix.ai")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("Sign In", use_container_width=True)

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
        
        # Footer with QM logo and text on same line
        st.markdown("<br><br>", unsafe_allow_html=True)
        
        qm_logo_path = "logo/1.jpg"
        if os.path.exists(qm_logo_path):
            with open(qm_logo_path, "rb") as f:
                qm_logo_data = base64.b64encode(f.read()).decode()
            
            st.markdown(
                f"""
                <div style='display: flex; align-items: center; justify-content: center; gap: 0.5rem;'>
                    <img src="data:image/jpeg;base64,{qm_logo_data}" style="width: 45px; height: 45px; border-radius: 4px;" />
                    <span style='color: #6b7280; font-size: 0.9rem;'>
                        Powered by <strong style='color: #1d2733;'>Quant Matrix AI</strong>
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                """
                <p style='text-align: center; color: #6b7280; font-size: 0.9rem;'>
                    Powered by <strong style='color: #1d2733;'>Quant Matrix AI</strong>
                </p>
                """,
                unsafe_allow_html=True
            )
