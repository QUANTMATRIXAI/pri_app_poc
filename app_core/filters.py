import pandas as pd


def apply_filters(df: pd.DataFrame, filters: dict | None) -> pd.DataFrame:
    if not filters:
        return df
    filtered = df.copy()
    brands = filters.get("brands")
    year_range = filters.get("year_range")
    if brands and "brand" in filtered.columns:
        filtered = filtered[filtered["brand"].isin(brands)]
    if year_range and "year" in filtered.columns:
        start, end = year_range
        if pd.api.types.is_datetime64_any_dtype(filtered["year"]):
            filtered["year"] = filtered["year"].dt.year
        filtered = filtered[(filtered["year"] >= start) & (filtered["year"] <= end)]
    return filtered

