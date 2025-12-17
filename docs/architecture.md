# Trinity Dashboard – Architecture Overview

This document explains how the refactored Streamlit app is structured, how segments/sections work, where data lives, and what session state is used. It is meant to help new contributors extend the app independently.

## High-level flow
- **Entry**: `app.py` bootstraps Streamlit, sets page title (“Trinity - Data Science Democratised”), and handles auth/user role. After login you land on the **Segments** page.
- **Segments page**: Cards for five segments (Value, Deluxe, Premium, SPIB, SP BIO) ordered by value→premium. Each card shows dataset/block counts and opens that segment.
- **Inside a segment**: Two main areas shown via a left nav (radio buttons):
  - **Data Studio** (editor-only): configure/publish fixed dashboard blocks per section; upload/manage datasets.
  - **Dashboard** (editor+viewer): read-only view of published content (edit/delete buttons only appear for editors).
- **Sections**: Tabs across the dashboard: `NS Landscape`, `Segment Truths`, `Brand Truths`, `Segment Trends`, `Brand Trends`, `Battlegrounds`. Content is scoped per segment+section.

## Fixed dashboard blocks (what gets published)
Located in `app_ui/data_studio.py` (`blocks` list).
- **NS Landscape**
  - Line chart: Yearly Sales (`year` vs `sales`, filtered by brand/year).
  - Media slots: NS Image 1/2/3 (image or PPT).
- **Segment Truths**
  - Bar chart: Yearly Volume (`year` vs `volume`, filtered by brand/year).
- **Brand Truths**
  - Image upload (replaces chart).
- **Segment Trends**
  - Image upload (replaces chart).
- **Brand Trends**
  - Monthly table (columns: year, month, brand, sales, volume, price).
- **Battlegrounds**
  - Yearly table (columns: year, brand, price).

Editors choose filters (brands/years) and add comments/extra notes per block, then **Save to dashboard**. Save overwrites prior content for that segment+section+block name.

## Data model & storage
- **Datasets**: Uploaded CSV/XLSX stored as files in `data/` and indexed in DB (`uploads` table). Sample dataset can be loaded per segment.
- **Charts**: Saved in DB (`charts` table) with JSON filter spec and y-columns list. Dataset ID references uploaded data.
- **Tables**: Saved in DB (`tables` table) with columns and filter spec. Preview built at render time from the dataset.
- **Media**: Uploaded files stored under `data/media/`; metadata in DB (`media` table) with `segment_id`, `section`, `name`, `comment`, `file_path`.
- **Computed counts**: Helpers in `app_core` count datasets and blocks per segment for the landing cards and dashboard header.

## Rendering behavior (dashboard)
Implemented in `app_ui/dashboard.py`.
- Tabs per section (`SECTIONS` constant). Items fetched per section and grouped by type.
- **NS Landscape special handling**: media (Images 1–3) render as tabs *under the NS chart*; if no chart, a fallback renders the tabs once.
- **Charts**: Plotly chart plus comment (supports `**bold**` and `## heading`), dataset pill, and “View data” expander. Editor-only delete button.
- **Tables**: Styled dataframe with conditional formatting (highlight min/max). Editor-only: editable grid (local), download edited CSV, save back to dataset, delete button.
- **Media**: Image/PPT display with per-item comments, per-entry delete (editor-only). PPTs are downloadable (no inline preview). Keys are namespaced to avoid Streamlit collisions.

## Session state usage (Data Studio)
All keys are namespaced with segment id + section + block name to avoid collisions across segments/blocks.
- Dataset selector: `blocks_dataset_{segment_id}`.
- Filters per block: `{key_suffix}_brands`, `{key_suffix}_years`, where `key_suffix = "{segment_id}_{section}_{block_name}"`.
- Comments: `block_comment_{key_suffix}`.
- Extra notes (add/remove): `block_extra_comments_{key_suffix}` list; add via `add_note_{key_suffix}` input and `add_btn_{key_suffix}` button; remove buttons `rm_note_{key_suffix}_{idx}`.
- Media uploads: `media_upload_{key_suffix}` (accepts multiple files).
- Save buttons: `save_block_{key_suffix}` (charts/tables/media).
- Chart preview keys: `block_preview_{key_suffix}` passed to Plotly.

Dashboard uses search input `dash_search_{segment_id}` and unique per-element keys for deletions/downloads/editors.

## File-by-file map
- `app.py`: entrypoint, layout shell, segment routing, role handling.
- `app_core/`:
  - `constants.py`: SECTIONS list.
  - `uploads.py`: dataset CRUD, sample data, dataset counts, overwrite_dataset for editor edits.
  - `charts.py`, `tables.py`: persistence for charts/tables.
  - `media.py`: media save/delete/list.
  - `filters.py`: apply brand/year/view filters to dataframes.
- `app_ui/data_studio.py`: editor publishing UI and dataset upload/manage UI.
- `app_ui/dashboard.py`: viewer/editor dashboard render, media/tab handling.
- `app_ui/charts.py`: Plotly chart rendering helper.

## Permissions
- **Editor**: Can upload datasets, publish/overwrite blocks, delete blocks/media, edit tables locally and overwrite datasets, download edited CSV.
- **Viewer**: Read-only dashboard; no buttons to mutate data.

## Key conventions
- Block identity: `(segment_id, section, block name)` ensures isolation per segment and prevents cross-contamination.
- Filter spec stored as JSON (`brands`, `years`, `view_mode`) on chart/table rows.
- Comments allow light formatting (`**bold**`, `## heading`, line breaks, bullet prefix `ƒ?›` for extra notes).

## Known behaviors
- Media delete removes all media records for that segment+section+name; keys are randomized per render to avoid Streamlit duplicate key errors.
- Editable tables are limited to 500 rows in the UI; saving overwrites the underlying dataset for that table’s dataset id.

## Extending safely
- Add new fixed blocks by appending to `blocks` in `data_studio.py` and ensuring corresponding render logic exists in `dashboard.py`.
- Keep session_state keys unique by including segment id + section + block name.
- When adding widgets, avoid reusing keys across sections; prefer deterministic prefixes.
- Use `apply_filters` for any new chart/table to keep brand/year scoping consistent.

## Practical examples

### Adding a new chart block
1) **Define block in Data Studio** (`app_ui/data_studio.py`, `blocks` list):
```python
{
    "name": "Battlegrounds - Discount Trend",
    "section": "Battlegrounds",
    "type": "chart",
    "chart_type": "line",
    "view_mode": "monthly",
    "x_col": "month",
    "y_cols": ["discount_pct"],
}
```
2) **Filters & comments**: No extra code needed—existing UI will render brand/year filters and comment/notes.
3) **Save**: Hitting “Save to dashboard” calls `save_chart(...)`, storing filter spec + y_cols.
4) **Render**: In `dashboard.py`, charts auto-render via `render_chart_block` because type=`chart` is already supported.

### Adding a new table block
1) Add to `blocks` with `type: "table"` and `columns` list.
2) On dashboard, it will use `build_table_preview` + `highlight_extremes`; editors get the editable grid and can overwrite the dataset.

### Adding a new media slot
1) Add a block with `type: "media"` and `name`.
2) Data Studio will show an upload widget; saving overwrites media for that segment/section/name.
3) Dashboard will show it via `render_media_block` (images/PPT downloads) with per-item comments and delete (editor-only).

### Filter spec shape
Stored as JSON per chart/table:
```json
{
  "brands": ["Alpha", "Beta"],
  "years": [2023, 2024],
  "view_mode": "yearly"  // or "monthly"
}
```
`apply_filters` uses these to slice the dataframe before plotting/display.

### Comment formatting
- Bold: `**Important**`
- Heading: `## Key takeaway`
- Extra notes (added via “Add note”): stored with prefix `ƒ?›` and rendered as indented bullets.

### Keys you might copy
- Dataset selector: `blocks_dataset_{segment_id}`
- Filters: `{segment_id}_{section}_{block}_brands` / `_years`
- Preview chart key: `block_preview_{segment_id}_{section}_{block}`
- Save button: `save_block_{segment_id}_{section}_{block}`
