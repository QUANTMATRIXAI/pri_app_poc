import datetime
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st


DB_PATH = Path("data/app.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('editor', 'viewer')),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                data_json TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()


def ensure_chart_comment_column() -> None:
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(charts)") .fetchall()]
        if "comment" not in cols:
            conn.execute("ALTER TABLE charts ADD COLUMN comment TEXT DEFAULT ''")
            conn.commit()


def migrate_charts_table() -> None:
    with get_connection() as conn:
        # check schema
        schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='charts'"
        ).fetchone()
        if not schema_row:
            conn.execute(
                """
                CREATE TABLE charts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    chart_type TEXT NOT NULL,
                    x_col TEXT NOT NULL,
                    y_cols TEXT NOT NULL,
                    dataset_id INTEGER NOT NULL,
                    created_by TEXT NOT NULL,
                    comment TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
            return

        schema_sql = schema_row["sql"] or ""
        needs_migration = "CHECK(chart_type" in schema_sql
        has_comment = "comment" in schema_sql
        if not needs_migration and has_comment:
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS charts_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                chart_type TEXT NOT NULL,
                x_col TEXT NOT NULL,
                y_cols TEXT NOT NULL,
                dataset_id INTEGER NOT NULL,
                created_by TEXT NOT NULL,
                comment TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO charts_new (id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at)
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by,
                   COALESCE(comment, '') AS comment, created_at
            FROM charts
            """
        )
        conn.execute("DROP TABLE charts")
        conn.execute("ALTER TABLE charts_new RENAME TO charts")
        conn.commit()


def inject_styles() -> None:
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


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt_value = salt or os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_value.encode("utf-8"), 390000
    ).hex()
    return salt_value, hashed


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, hashed = hash_password(password, salt)
    return hashed == expected_hash


def create_default_users() -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if existing:
            return

        now = datetime.datetime.utcnow().isoformat()
        defaults = [
            ("admin", "admin123", "editor"),
            ("viewer", "viewer123", "viewer"),
        ]
        for username, password, role in defaults:
            salt, hashed = hash_password(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, hashed, salt, role, now),
            )
        conn.commit()


def load_config() -> Dict:
    with get_connection() as conn:
        row = conn.execute("SELECT payload FROM config WHERE id = 1").fetchone()
        if row:
            return json.loads(row["payload"])
        default_config = {
            "ssl_endpoint": "https://example.com",
            "check_frequency_minutes": 15,
            "notify_email": "ops@example.com",
        }
        conn.execute(
            "INSERT OR REPLACE INTO config (id, payload) VALUES (1, ?)",
            (json.dumps(default_config),),
        )
        conn.commit()
        return default_config


def save_config(payload: Dict) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (id, payload) VALUES (1, ?)",
            (json.dumps(payload),),
        )
        conn.commit()


def add_user(username: str, password: str, role: str) -> Tuple[bool, str]:
    try:
        salt, hashed = hash_password(password)
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    username,
                    hashed,
                    salt,
                    role,
                    datetime.datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return True, "User created"
    except sqlite3.IntegrityError:
        return False, "Username already exists"


def verify_credentials(username: str, password: str) -> Optional[Dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, password_hash, salt, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    if verify_password(password, row["salt"], row["password_hash"]):
        return {"username": row["username"], "role": row["role"]}
    return None


def save_upload(filename: str, df: pd.DataFrame, uploaded_by: str) -> None:
    data_json = df.to_json(orient="records")
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO uploads (filename, data_json, uploaded_by, uploaded_at) VALUES (?, ?, ?, ?)",
            (
                filename,
                data_json,
                uploaded_by,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    return cursor.lastrowid


def get_upload_history(limit: int = 10):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, uploaded_by, uploaded_at FROM uploads ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return rows


def get_uploads():
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, filename, uploaded_by, uploaded_at FROM uploads ORDER BY uploaded_at DESC"
        ).fetchall()


def load_dataset(upload_id: int) -> Optional[pd.DataFrame]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data_json FROM uploads WHERE id = ?",
            (upload_id,),
        ).fetchone()
    if not row:
        return None
    try:
        return pd.read_json(row["data_json"])
    except ValueError:
        return None


def load_latest_dataset() -> Tuple[Optional[int], Optional[pd.DataFrame]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, data_json FROM uploads ORDER BY uploaded_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None, None
    try:
        return row["id"], pd.read_json(row["data_json"])
    except ValueError:
        return None, None


def save_chart(
    name: str,
    chart_type: str,
    x_col: str,
    y_cols: list[str],
    dataset_id: int,
    created_by: str,
    comment: str = "",
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO charts (name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                chart_type,
                x_col,
                json.dumps(y_cols),
                dataset_id,
                created_by,
                comment,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def get_saved_charts():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, name, chart_type, x_col, y_cols, dataset_id, created_by, comment, created_at
            FROM charts
            ORDER BY created_at DESC
            """
        ).fetchall()


def count_uploads() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM uploads").fetchone()
        return row["c"]


def count_charts() -> int:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM charts").fetchone()
        return row["c"]


def get_dataset_label(dataset_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT filename FROM uploads WHERE id = ?",
            (dataset_id,),
        ).fetchone()
    return row["filename"] if row else f"Dataset #{dataset_id}"


def delete_chart(chart_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM charts WHERE id = ?", (chart_id,))
        conn.commit()


def plot_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_cols: list[str]) -> None:
    if chart_type == "correlation":
        numeric_df = df[y_cols].select_dtypes(include="number") if y_cols else df.select_dtypes(include="number")
        if numeric_df.shape[1] < 2:
            st.warning("Select at least two numeric columns for correlation.")
            return
        corr = numeric_df.corr().stack().reset_index()
        corr.columns = ["var1", "var2", "corr"]
        heatmap = (
            alt.Chart(corr)
            .mark_rect()
            .encode(
                x="var1",
                y="var2",
                color=alt.Color("corr", scale=alt.Scale(domain=(-1, 1), scheme="yellowgreenblue")),
                tooltip=["var1", "var2", alt.Tooltip("corr", format=".2f")],
            )
            .properties(height=280)
        )
        st.altair_chart(heatmap, use_container_width=True)
        return

    if x_col not in df.columns:
        st.warning(f"Column {x_col} not in dataset.")
        return
    missing_y = [col for col in y_cols if col not in df.columns]
    if missing_y:
        st.warning(f"Columns {', '.join(missing_y)} not in dataset.")
        return

    plot_df = df[[x_col] + y_cols].copy()
    if pd.api.types.is_datetime64_any_dtype(plot_df[x_col]) is False:
        try:
            plot_df[x_col] = pd.to_datetime(plot_df[x_col])
        except Exception:  # noqa: BLE001
            pass
    melted = plot_df.melt(id_vars=x_col, var_name="series", value_name="value")
    base = (
        alt.Chart(melted)
        .encode(
            x=alt.X(x_col, title=x_col),
            y=alt.Y("value", title=None),
            color=alt.Color("series", legend=alt.Legend(title="")),
            tooltip=[x_col, "series", "value"],
        )
        .properties(height=280)
    )
    if chart_type == "area":
        chart = base.mark_area(opacity=0.6)
    elif chart_type == "bar":
        chart = base.mark_bar()
    else:
        chart = base.mark_line(point=True)
    st.altair_chart(chart, use_container_width=True)


def draw_dashboard(charts, is_editor: bool = False) -> None:
    st.subheader("Dashboard")
    search = st.text_input("Search charts", placeholder="Search by chart name, dataset, or note...")
    uploads_total = count_uploads()
    charts_total = count_charts()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Datasets</div>
                <div class="metric-value">{uploads_total}</div>
                <div class="stCaption">Uploaded by editors</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f"""
            <div class="info-card">
                <div class="pill">Published charts</div>
                <div class="metric-value">{charts_total}</div>
                <div class="stCaption">Visible on dashboard</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("")
    if not charts:
        st.info("No charts published yet. Editors can build charts from uploaded data.")
        sample = pd.DataFrame(
            {
                "timestamp": pd.date_range(datetime.datetime.today(), periods=10, freq="H"),
                "latency_ms": [120, 110, 150, 130, 125, 118, 160, 140, 135, 128],
                "success_rate": [0.99, 0.98, 0.985, 0.99, 0.995, 0.97, 0.965, 0.99, 0.993, 0.997],
            }
        )
        st.line_chart(sample.set_index("timestamp"))
        return

    filtered = []
    search_lower = (search or "").strip().lower()
    for chart in charts:
        dataset_label = get_dataset_label(chart["dataset_id"])
        comment = chart["comment"] if "comment" in chart.keys() else ""
        haystack = " ".join([chart["name"], dataset_label, comment or ""]).lower()
        if search_lower and search_lower not in haystack:
            continue
        filtered.append((chart, dataset_label, comment))

    if not filtered:
        st.info("No charts match your search.")
        return

    for i in range(0, len(filtered), 2):
        cols = st.columns(2)
        for offset, pack in enumerate(filtered[i : i + 2]):
            chart, dataset_label, comment = pack
            with cols[offset]:
                df = load_dataset(chart["dataset_id"])
                if df is None or df.empty:
                    st.warning(f"Dataset missing for chart '{chart['name']}'.")
                    continue
                y_cols = json.loads(chart["y_cols"])
                st.markdown('<div class="chart-card">', unsafe_allow_html=True)
                st.markdown(f"<h4 class='chart-title'>{chart['name']}</h4>", unsafe_allow_html=True)
                st.markdown(
                    f"<div class='meta-line'><span class='pill'>Dataset</span> {dataset_label}</div>",
                    unsafe_allow_html=True,
                )
                if comment:
                    st.markdown(
                        f"<div class='comment-box'>{comment}</div>",
                        unsafe_allow_html=True,
                    )
                plot_chart(df, chart["chart_type"], chart["x_col"], y_cols)
                if is_editor:
                    if st.button("Delete chart", key=f"del_{chart['id']}"):
                        delete_chart(chart["id"])
                        st.success("Chart removed")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        st.markdown("<div style='height:0.6rem;'></div>", unsafe_allow_html=True)


def render_data_upload(current_user: Dict) -> None:
    st.subheader("Data Studio")
    st.caption("Editors only. Publish charts with a note; dashboard shows the chart name, dataset, and note.")
    st.markdown(
        """
        <ul style="color: var(--muted); margin-top:0.1rem; margin-bottom:0.4rem;">
            <li>Select dataset, chart type, and columns.</li>
            <li>Preview the chart, add a note, then save.</li>
            <li>Saved charts appear on the dashboard for viewers.</li>
        </ul>
        """,
        unsafe_allow_html=True,
    )

    chart_tab, upload_tab = st.tabs(["Publish chart", "Upload data"])

    with chart_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Build a chart and add a note")
        render_chart_builder(current_user)
        st.markdown('</div>', unsafe_allow_html=True)

    with upload_tab:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("#### Upload CSV / Excel")
        uploaded = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"])
        if uploaded:
            try:
                if uploaded.name.endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_excel(uploaded)
                upload_id = save_upload(uploaded.name, df, current_user["username"])
                st.success(f"Saved {uploaded.name} (rows: {len(df)}) as dataset #{upload_id}")
                st.dataframe(df.head(), use_container_width=True)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to process file: {exc}")
        st.markdown('<div style="margin-top:0.5rem;" class="stCaption">Recent uploads</div>', unsafe_allow_html=True)
        history = get_upload_history()
        if not history:
            st.write("No uploads yet.")
        else:
            st.table(history)
        st.markdown('</div>', unsafe_allow_html=True)


def render_chart_builder(current_user: Dict) -> None:
    uploads = get_uploads()
    if not uploads:
        st.info("Upload data first to build charts.")
        return

    st.session_state.setdefault("chart_preview", None)

    upload_options = {f"#{row['id']} • {row['filename']}": row["id"] for row in uploads}
    default_upload_label = list(upload_options.keys())[0]

    with st.form("chart_builder"):
        st.markdown("**Step 1 · Dataset & chart type**")
        top_left, top_right = st.columns(2)
        with top_left:
            chart_name = st.text_input("Chart name", value="SSL Health Overview")
            selected_label = st.selectbox("Dataset", options=list(upload_options.keys()), index=0)
        with top_right:
            chart_type = st.selectbox("Chart type", options=["line", "area", "bar", "correlation"])

        dataset_id = upload_options[selected_label]
        df = load_dataset(dataset_id)
        if df is None or df.empty:
            st.warning("Selected dataset is empty.")
            st.form_submit_button("Preview chart", disabled=True)
            return
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        default_y = [numeric_cols[0]] if numeric_cols else []

        st.markdown("**Step 2 · Columns**")
        col_x, col_y = st.columns([1, 1.3])
        with col_x:
            if chart_type == "correlation":
                x_col = df.columns.tolist()[0]
                st.text_input("X axis column", value=x_col, disabled=True, help="Not used for correlation heatmap.")
            else:
                x_col = st.selectbox("X axis column", options=df.columns.tolist(), index=0)
        with col_y:
            if chart_type == "correlation":
                y_cols = st.multiselect(
                    "Columns for correlation heatmap (numeric)",
                    options=df.columns.tolist(),
                    default=numeric_cols[:4],
                )
            else:
                y_cols = st.multiselect("Y axis columns", options=df.columns.tolist(), default=default_y)

        preview = st.form_submit_button("Preview chart", use_container_width=True)

    if preview:
        if not y_cols:
            st.error("Select at least one Y column.")
            st.session_state["chart_preview"] = None
        else:
            st.session_state["chart_preview"] = {
                "chart_name": chart_name.strip() or "Chart",
                "chart_type": chart_type,
                "x_col": x_col,
                "y_cols": y_cols,
                "dataset_id": dataset_id,
            }
            # comment captured via widget; no manual reset here to avoid widget key conflicts

    preview_data = st.session_state.get("chart_preview")
    if preview_data:
        df_preview = load_dataset(preview_data["dataset_id"])
        if df_preview is None or df_preview.empty:
            st.warning("Dataset unavailable for preview.")
            return
        prev_col, note_col = st.columns([1.6, 1])
        with prev_col:
            st.markdown("#### Preview")
            plot_chart(df_preview, preview_data["chart_type"], preview_data["x_col"], preview_data["y_cols"])
        with note_col:
            st.markdown("#### Add note and publish")
            comment = st.text_area(
                "Dashboard note (optional)",
                key="chart_preview_comment",
                placeholder="Add context for viewers...",
            )
            if st.button("Save chart to dashboard", use_container_width=True):
                save_chart(
                    preview_data["chart_name"],
                    preview_data["chart_type"],
                    preview_data["x_col"],
                    preview_data["y_cols"],
                    preview_data["dataset_id"],
                    current_user["username"],
                    comment.strip(),
                )
                st.success(f"Saved chart to dashboard using dataset #{preview_data['dataset_id']}")
                st.session_state["chart_preview"] = None
                st.session_state.pop("chart_preview_comment", None)
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()


def render_config(config: Dict) -> Dict:
    st.subheader("Configuration")
    with st.form("config_form"):
        endpoint = st.text_input("SSL endpoint", value=config.get("ssl_endpoint", ""))
        freq = st.number_input(
            "Check frequency (minutes)",
            min_value=1,
            value=int(config.get("check_frequency_minutes", 15)),
        )
        email = st.text_input("Notify email", value=config.get("notify_email", ""))
        submitted = st.form_submit_button("Save configuration")
    if submitted:
        new_config = {
            "ssl_endpoint": endpoint.strip(),
            "check_frequency_minutes": freq,
            "notify_email": email.strip(),
        }
        save_config(new_config)
        st.success("Configuration saved")
        return new_config
    return config


def render_user_management() -> None:
    st.subheader("User Management")
    with get_connection() as conn:
        users = conn.execute(
            "SELECT username, role, created_at FROM users ORDER BY created_at DESC"
        ).fetchall()
    st.table(users)

    st.markdown("**Add user**")
    with st.form("add_user"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        role = st.selectbox("Role", options=["editor", "viewer"])
        submitted = st.form_submit_button("Create user")
    if submitted:
        if not username or not password:
            st.error("Username and password are required.")
        else:
            ok, msg = add_user(username.strip(), password, role)
            if ok:
                st.success(f"{msg}: {username} ({role})")
            else:
                st.error(msg)


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
        st.markdown('</div>', unsafe_allow_html=True)
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


def main():
    st.set_page_config(
        page_title="Trial Dashboard",
        page_icon="📊",
        layout="wide",
    )
    inject_styles()

    init_db()
    migrate_charts_table()
    ensure_chart_comment_column()
    create_default_users()

    if "user" not in st.session_state:
        st.session_state["user"] = None

    current_user = st.session_state["user"]

    if current_user:
        st.markdown(
            "<style>[data-testid='stSidebar'] { display: block; }</style>",
            unsafe_allow_html=True,
        )
        st.sidebar.success(f"Logged in as {current_user['username']} ({current_user['role']})")
        if not current_user["role"] == "editor":
            if st.sidebar.button("Refresh dashboard"):
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()
        if st.sidebar.button("Log out"):
            st.session_state["user"] = None
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
    else:
        login_panel()
        return

    st.markdown(
        """
        <div class="info-card" style="margin-bottom: 1rem;">
            <div class="pill">Secure Workspace</div>
            <h1 style="margin-bottom:0.2rem;">Trial Dashboard</h1>
            <p style="color: var(--muted); margin-bottom:0;">Editors manage data and publish charts; viewers see the live dashboard only.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    current_user = st.session_state["user"]
    is_editor = current_user["role"] == "editor"
    menu = ["Dashboard"]
    if is_editor:
        menu += ["Data Studio"]
    selection = st.sidebar.radio("Navigate", options=menu, index=0)

    saved_charts = get_saved_charts()
    if selection == "Dashboard":
        draw_dashboard(saved_charts, is_editor=is_editor)
    elif selection == "Data Studio" and is_editor:
        render_data_upload(current_user)
    else:
        st.warning("You do not have access to this section.")


if __name__ == "__main__":
    main()
