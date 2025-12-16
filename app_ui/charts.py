import altair as alt
import pandas as pd
import streamlit as st


def plot_chart(df: pd.DataFrame, chart_type: str, x_col: str, y_cols: list[str]) -> None:
    """Render a chart preview or dashboard chart."""
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
            ).properties(height=280)
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
