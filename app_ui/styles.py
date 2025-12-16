import streamlit as st


def inject_styles() -> None:
    """Inject the shared style sheet into the Streamlit page."""
    st.markdown(
        """
        <style>
            :root {
                --bg: #f4f6fb;
                --panel: #ffffff;
                --card: #ffffff;
                --accent: #f5b400;
                --text: #1d2733;
                --muted: #5b6472;
            }
            body, .stApp {
                background: var(--bg);
                color: var(--text);
            }
            .block-container {
                padding-top: 1.2rem;
                padding-bottom: 1.2rem;
                max-width: 95vw;
            }
            h1, h2, h3, h4, h5, h6, .stCaption, label, p, span {
                color: var(--text) !important;
            }
            .info-card {
                background: var(--card);
                border: 1px solid rgba(0,0,0,0.04);
                padding: 0.9rem 1.05rem;
                border-radius: 12px;
                box-shadow: 0 10px 22px rgba(0,0,0,0.05);
            }
            .panel {
                background: var(--panel);
                border: 1px solid rgba(0,0,0,0.05);
                padding: 1rem 1.05rem;
                border-radius: 12px;
            }
            .pill {
                display: inline-block;
                padding: 0.25rem 0.55rem;
                border-radius: 999px;
                background: rgba(245,180,0,0.16);
                color: var(--accent);
                border: 1px solid rgba(245,180,0,0.28);
                font-size: 0.8rem;
            }
            .chart-card {
                background: var(--card);
                border-radius: 14px;
                border: 1px solid rgba(0,0,0,0.05);
                padding: 0.9rem 1rem;
                box-shadow: 0 10px 26px rgba(0,0,0,0.06);
            }
            .metric-value {
                font-size: 1.8rem;
                font-weight: 700;
                color: var(--accent);
            }
            .stTabs [role="tablist"] {
                border-bottom: 1px solid rgba(0,0,0,0.06);
                gap: 0.4rem;
            }
            .stTabs [role="tab"] {
                padding: 0.35rem 0.8rem;
            }
            .stButton>button {
                background: var(--accent) !important;
                color: #1d2733 !important;
                border-radius: 8px !important;
                border: none !important;
                font-weight: 700 !important;
            }
            .stAlert {
                border-radius: 10px;
            }
            .comment-box {
                background: #fff8df;
                border-left: 3px solid var(--accent);
                padding: 0.5rem 0.8rem;
                border-radius: 8px;
                color: var(--text);
                margin-bottom: 0.6rem;
                font-size: 0.92rem;
            }
            .meta-line {
                font-size: 0.9rem;
                color: var(--muted);
                margin-bottom: 0.35rem;
            }
            .chart-title {
                margin-bottom: 0.1rem;
            }
            .login-card {
                background: #ffffff;
                border: 1px solid rgba(0,0,0,0.05);
                border-radius: 14px;
                padding: 1.2rem 1.3rem;
                box-shadow: 0 12px 28px rgba(0,0,0,0.08);
            }
            .login-hero {
                text-align: center;
                margin-bottom: 1rem;
                color: var(--text);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

