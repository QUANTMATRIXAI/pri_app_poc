import pandas as pd


def apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    """Apply shared dashboard filters (brands, years, view mode) and return a filtered/aggregated frame."""
    if not filters:
        return df
    filtered = df.copy()
    brands = filters.get("brands") or []
    years = filters.get("years") or filters.get("year_range") or []
    view_mode = filters.get("view_mode") or "monthly"

    if brands and "brand" in filtered.columns:
        filtered = filtered[filtered["brand"].isin(brands)]

    if years and "year" in filtered.columns:
        years_int = []
        for y in years:
            try:
                years_int.append(int(y))
            except Exception:  # noqa: BLE001
                continue
        if years_int:
            filtered = filtered[filtered["year"].astype(int).isin(years_int)]

    if "month" in filtered.columns:
        filtered["month"] = pd.to_numeric(filtered["month"], errors="coerce").astype("Int64")

    if view_mode == "yearly":
        if "year" in filtered.columns:
            group_cols = ["year"]
            if "brand" in filtered.columns:
                group_cols.append("brand")
            num_cols = filtered.select_dtypes(include="number").columns.tolist()
            agg_dict = {col: "sum" for col in num_cols if col not in group_cols}
            filtered = filtered.groupby(group_cols, dropna=True).agg(agg_dict).reset_index()
    else:
        # monthly view: add a period column for plotting convenience
        if "year" in filtered.columns and "month" in filtered.columns:
            filtered["period"] = pd.to_datetime(
                filtered["year"].astype(int).astype(str)
                + "-"
                + filtered["month"].astype(int).astype(str).str.zfill(2)
                + "-01",
                errors="coerce",
            )
    return filtered
