import pandas as pd
import plotly.express as px
import streamlit as st


def plot_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_cols: list[str], chart_key: str | None = None) -> None:
    """Render a chart preview or dashboard chart using Plotly."""
    if x_col not in df.columns:
        st.warning(f"Column {x_col} not in dataset.")
        return
    missing_y = [col for col in y_cols if col not in df.columns]
    if missing_y:
        st.warning(f"Columns {', '.join(missing_y)} not in dataset.")
        return

    id_vars = [x_col]
    if "brand" in df.columns and "brand" not in id_vars:
        id_vars.append("brand")
    plot_df = df[id_vars + y_cols].copy()

    # Only coerce to datetime when the column is not numeric and not already datetime-like
    if (
        not pd.api.types.is_datetime64_any_dtype(plot_df[x_col])
        and not pd.api.types.is_numeric_dtype(plot_df[x_col])
    ):
        try:
            plot_df[x_col] = pd.to_datetime(plot_df[x_col])
        except Exception:  # noqa: BLE001
            pass

    melted = plot_df.melt(id_vars=id_vars, var_name="metric", value_name="value")
    if "brand" in melted.columns:
        melted["series"] = melted["brand"].astype(str) + " · " + melted["metric"]
    else:
        melted["series"] = melted["metric"]

    if chart_type == "bar":
        fig = px.bar(
            melted,
            x=x_col,
            y="value",
            color="series",
            barmode="group",
            hover_data={x_col: True, "series": True, "value": ":.2f"},
            height=320,
        )
    else:
        fig = px.line(
            melted,
            x=x_col,
            y="value",
            color="series",
            markers=True,
            hover_data={x_col: True, "series": True, "value": ":.2f"},
            height=320,
        )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
    st.plotly_chart(fig, use_container_width=True, key=chart_key)
