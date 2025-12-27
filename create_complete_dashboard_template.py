import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# Create a new workbook
wb = Workbook()
wb.remove(wb.active)  # Remove default sheet

# Helper function to add styled header
def add_section_header(ws, row, text):
    ws.cell(row=row, column=1, value=text)
    cell = ws.cell(row=row, column=1)
    cell.font = Font(bold=True, size=12, color="FFFFFF")
    cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    ws.merge_cells(f'A{row}:D{row}')
    return row + 1

# 1. NS LANDSCAPE SHEET
ws_ns = wb.create_sheet("NS Landscape")
row = 1
ws_ns.cell(row, 1, "NS LANDSCAPE CONFIGURATION")
ws_ns.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_ns.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_ns.merge_cells(f'A{row}:D{row}')
row += 2

ws_ns.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

# 1. Manufacturing Pivot Table
row = add_section_header(ws_ns, row, "1. MANUFACTURING PIVOT TABLE")
ws_ns.append(["Manufacturing Pivot", "Table Title", "NS Overview", "Title for the manufacturing pivot table"])
ws_ns.append(["", "Comment", "", "Insights or notes about the manufacturing view"])

row = ws_ns.max_row + 2

# 2. Brand Performance Chart
row = add_section_header(ws_ns, row, "2. BRAND PERFORMANCE CHART")
ws_ns.append(["Brand Performance", "Selected Brand Families", "", "Comma-separated brand families (e.g., Family1, Family2)"])
ws_ns.append(["", "Selected Brands", "", "Comma-separated brand names"])
ws_ns.append(["", "Excluded States", "", "Comma-separated states to exclude from all sections"])
ws_ns.append(["", "Comment", "", "Insights about brand performance"])

row = ws_ns.max_row + 2

# 2.5. Brand Family Performance Chart
row = add_section_header(ws_ns, row, "2.5. BRAND FAMILY PERFORMANCE CHART")
ws_ns.append(["Brand Family Performance", "Selected Brand Families", "", "Comma-separated brand families (from Section 2)"])
ws_ns.append(["", "Selected Brands", "", "Comma-separated brands to include (from Section 2)"])
ws_ns.append(["", "Comment", "", "Insights about brand family performance"])

row = ws_ns.max_row + 2

# 3. Zonal Pivot Table
row = add_section_header(ws_ns, row, "3. ZONAL PIVOT TABLE (Brand Family x Zone)")
ws_ns.append(["Zonal Pivot", "Table Title", "NS Zonal View", "Title for the zonal pivot table"])
ws_ns.append(["", "Comment", "", "Insights about zonal performance"])

row = ws_ns.max_row + 2

# 4. NORTH Zone State Drill-Down
row = add_section_header(ws_ns, row, "4. NORTH ZONE - STATE DRILL-DOWN")
ws_ns.append(["NORTH Zone", "Table Title", "Battleground in North", "Title for NORTH zone section"])
ws_ns.append(["", "Selected States for Deep-Dive", "", "Comma-separated states (e.g., Uttar Pradesh, Punjab)"])
ws_ns.append(["", "Comment for State Summary", "", "Insights about state-level performance"])
ws_ns.append(["", "Comment for Brand Deep-Dive", "", "Insights about brand performance by state"])

row = ws_ns.max_row + 2

# 5. WEST+CSD Zone State Drill-Down
row = add_section_header(ws_ns, row, "5. WEST+CSD ZONE - STATE DRILL-DOWN")
ws_ns.append(["WEST+CSD Zone", "Table Title", "Battleground in West+CSD", "Title for WEST+CSD zone section"])
ws_ns.append(["", "Selected States for Deep-Dive", "", "Comma-separated states"])
ws_ns.append(["", "Comment for State Summary", "", "Insights about state-level performance"])
ws_ns.append(["", "Comment for Brand Deep-Dive", "", "Insights about brand performance by state"])

row = ws_ns.max_row + 2

# 6. EAST Zone State Drill-Down
row = add_section_header(ws_ns, row, "6. EAST ZONE - STATE DRILL-DOWN")
ws_ns.append(["EAST Zone", "Table Title", "Battleground in East", "Title for EAST zone section"])
ws_ns.append(["", "Selected States for Deep-Dive", "", "Comma-separated states"])
ws_ns.append(["", "Comment for State Summary", "", "Insights about state-level performance"])
ws_ns.append(["", "Comment for Brand Deep-Dive", "", "Insights about brand performance by state"])

row = ws_ns.max_row + 2

# 7. SOUTH Zone State Drill-Down
row = add_section_header(ws_ns, row, "7. SOUTH ZONE - STATE DRILL-DOWN")
ws_ns.append(["SOUTH Zone", "Table Title", "Battleground in South", "Title for SOUTH zone section"])
ws_ns.append(["", "Selected States for Deep-Dive", "", "Comma-separated states"])
ws_ns.append(["", "Comment for State Summary", "", "Insights about state-level performance"])
ws_ns.append(["", "Comment for Brand Deep-Dive", "", "Insights about brand performance by state"])

row = ws_ns.max_row + 2

# 5. Placeholder Images
row = add_section_header(ws_ns, row, "5. PLACEHOLDER IMAGES (5 Images)")
for i in range(1, 6):
    ws_ns.append(["Placeholder Images", f"Placeholder {i} - Title", "", f"Title for placeholder image {i}"])
    ws_ns.append(["", f"Placeholder {i} - Comment", "", f"Comment/description for placeholder image {i}"])
    ws_ns.append(["", f"Placeholder {i} - Image File", "", f"Image file name to upload for placeholder {i}"])

row = ws_ns.max_row + 2

# 6. Custom Trends View Builder
row = add_section_header(ws_ns, row, "6. CUSTOM TRENDS VIEW BUILDER")
ws_ns.append(["Custom Trends", "Number of Views (1-6)", "", "How many separate views to create"])
for v in range(1, 7):
    ws_ns.append(["", f"View {v} - Tab Title", "", f"Tab name shown in dashboard for View {v}"])
    ws_ns.append(["", f"View {v} - Content Title", "", f"Main title displayed in View {v}"])
    ws_ns.append(["", f"View {v} - Description", "", f"Description text for View {v}"])
    ws_ns.append(["", f"View {v} - Number of Sections (1-8)", "", f"How many sections in View {v}"])
    for s in range(1, 9):
        ws_ns.append(["", f"View {v} - Section {s} - Left Content", "", f"Left side content for section {s}"])
        ws_ns.append(["", f"View {v} - Section {s} - Right Content", "", f"Right side content for section {s}"])

# 2. SEGMENT TRUTHS SHEET
ws_seg = wb.create_sheet("Segment Truths")
row = 1
ws_seg.cell(row, 1, "SEGMENT TRUTHS CONFIGURATION")
ws_seg.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_seg.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_seg.merge_cells(f'A{row}:D{row}')
row += 2

ws_seg.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

row = add_section_header(ws_seg, row, "OPENING IMAGE")
ws_seg.append(["Opening Image", "Image Title", "", "Title for the opening image"])
ws_seg.append(["", "Image Comment", "", "Comment for the opening image"])
ws_seg.append(["", "Image File", "", "Image file name to upload"])

row = ws_seg.max_row + 2
row = add_section_header(ws_seg, row, "SEGMENT INSIGHTS")
ws_seg.append(["Segment Insights", "Segment Title", "Segment Profile Summary", "Main title for segment truths"])
ws_seg.append(["", "Segment Comment/Insights", "", "Detailed insights about the segment (use bullet points)"])

row = ws_seg.max_row + 2
row = add_section_header(ws_seg, row, "P3M SEGMENT PROFILE TABLE")
ws_seg.append(["P3M Profile", "CSV File", "", "CSV file name with 3 columns: Metric, TBA, Premium Whisky"])
for i in range(1, 21):
    ws_seg.append(["", f"Row {i} - Metric", "", f"Metric name for row {i}"])
    ws_seg.append(["", f"Row {i} - TBA Value", "", f"TBA value for row {i}"])
    ws_seg.append(["", f"Row {i} - Premium Whisky Value", "", f"Premium Whisky value for row {i}"])

row = ws_seg.max_row + 2
row = add_section_header(ws_seg, row, "CAROUSEL IMAGES - SET 1 (Multiple Images)")
for i in range(1, 6):
    ws_seg.append(["Carousel 1", f"Image {i} - Title", "", f"Title for carousel 1 image {i}"])
    ws_seg.append(["", f"Image {i} - Comment", "", f"Comment for carousel 1 image {i}"])
    ws_seg.append(["", f"Image {i} - Image File", "", f"Image file name for carousel 1 image {i}"])

row = ws_seg.max_row + 2
row = add_section_header(ws_seg, row, "CAROUSEL IMAGES - SET 2 (Multiple Images)")
for i in range(1, 6):
    ws_seg.append(["Carousel 2", f"Image {i} - Title", "", f"Title for carousel 2 image {i}"])
    ws_seg.append(["", f"Image {i} - Comment", "", f"Comment for carousel 2 image {i}"])
    ws_seg.append(["", f"Image {i} - Image File", "", f"Image file name for carousel 2 image {i}"])

# 3. BRAND TRUTHS SHEET
ws_brand = wb.create_sheet("Brand Truths")
row = 1
ws_brand.cell(row, 1, "BRAND TRUTHS CONFIGURATION")
ws_brand.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_brand.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_brand.merge_cells(f'A{row}:D{row}')
row += 2

ws_brand.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

row = add_section_header(ws_brand, row, "1. BRAND PROFILE COMPARISON TABLE")
ws_brand.append(["Brand Profile Table", "Table Title", "", "Title for the comparison table"])
ws_brand.append(["", "CSV File", "", "CSV file name with brand comparison data"])
ws_brand.append(["", "Base Column", "", "Base brand column for index calculation"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "2. BRAND TRUTHS SECTIONS")
ws_brand.append(["Main", "View Title", "Brand Truths Summary - Competitor View", "Main title for Brand Truths section"])
ws_brand.append(["", "Main Description", "", "Main description text"])
ws_brand.append(["", "Number of Brand Sections (1-8)", "", "How many brand sections to create"])

for i in range(1, 9):
    ws_brand.append(["", f"Brand {i} - Number", "", f"Brand number for sorting (e.g., {i})"])
    ws_brand.append(["", f"Brand {i} - Name", "", f"Name of brand {i}"])
    ws_brand.append(["", f"Brand {i} - Content", "", f"Content/description for brand {i}"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "3. CAROUSEL IMAGES (Multiple Images)")
for i in range(1, 6):
    ws_brand.append(["Carousel Images", f"Image {i} - Tab Title", "", f"Short tab name for carousel image {i}"])
    ws_brand.append(["", f"Image {i} - Page Title", "", f"Full page title for carousel image {i}"])
    ws_brand.append(["", f"Image {i} - Comment", "", f"Comment for carousel image {i}"])
    ws_brand.append(["", f"Image {i} - Image File", "", f"Image file name for carousel image {i}"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "4. STANDALONE IMAGES (4 Images)")
for i in range(1, 5):
    ws_brand.append(["Standalone Images", f"Image {i} - Title", "", f"Title for standalone image {i}"])
    ws_brand.append(["", f"Image {i} - Comment", "", f"Comment for standalone image {i}"])
    ws_brand.append(["", f"Image {i} - Image File", "", f"Image file name for standalone image {i}"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "5. PLACEHOLDER IMAGES (5 Images)")
for i in range(1, 6):
    ws_brand.append(["Placeholder Images", f"Placeholder {i} - Title", "", f"Title for placeholder {i}"])
    ws_brand.append(["", f"Placeholder {i} - Comment", "", f"Comment for placeholder {i}"])
    ws_brand.append(["", f"Placeholder {i} - Image File", "", f"Image file for placeholder {i}"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "6. STRENGTHS & VULNERABILITIES")
ws_brand.append(["S&V", "Main Title", "PRI Strengths & Vulnerabilities:", "Main title for S&V section"])
ws_brand.append(["", "Strengths Box Title", "Brand Strengths", "Title for strengths box"])
ws_brand.append(["", "Strengths Content", "", "Content for strengths (use bullet points)"])
ws_brand.append(["", "Vulnerabilities Box Title", "Brand Vulnerabilities", "Title for vulnerabilities box"])
ws_brand.append(["", "Vulnerabilities Content", "", "Content for vulnerabilities (use bullet points)"])

row = ws_brand.max_row + 2
row = add_section_header(ws_brand, row, "7. SWOT ANALYSIS")
ws_brand.append(["SWOT", "Main Title", "PRI Portfolio SWOT", "Main title for SWOT section"])
ws_brand.append(["", "Strengths Content", "", "SWOT strengths content (use bullet points)"])
ws_brand.append(["", "Weaknesses Content", "", "SWOT weaknesses content (use bullet points)"])
ws_brand.append(["", "Opportunities Content", "", "SWOT opportunities content (use bullet points)"])
ws_brand.append(["", "Threats Content", "", "SWOT threats content (use bullet points)"])

# 4. SEGMENT TRENDS SHEET
ws_seg_trends = wb.create_sheet("Segment Trends")
row = 1
ws_seg_trends.cell(row, 1, "SEGMENT TRENDS CONFIGURATION")
ws_seg_trends.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_seg_trends.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_seg_trends.merge_cells(f'A{row}:D{row}')
row += 2

ws_seg_trends.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

row = add_section_header(ws_seg_trends, row, "ADDITIONAL IMAGES (5 Images)")
for i in range(1, 6):
    ws_seg_trends.append(["Additional Images", f"Image {i} - Title", "", f"Title for additional image {i}"])
    ws_seg_trends.append(["", f"Image {i} - Comment", "", f"Comment for additional image {i}"])
    ws_seg_trends.append(["", f"Image {i} - Image File", "", f"Image file name for additional image {i}"])

row = ws_seg_trends.max_row + 2
row = add_section_header(ws_seg_trends, row, "PLACEHOLDER IMAGES (5 Images)")
for i in range(1, 6):
    ws_seg_trends.append(["Placeholder Images", f"Placeholder {i} - Title", "", f"Title for placeholder {i}"])
    ws_seg_trends.append(["", f"Placeholder {i} - Comment", "", f"Comment for placeholder {i}"])
    ws_seg_trends.append(["", f"Placeholder {i} - Image File", "", f"Image file for placeholder {i}"])

row = ws_seg_trends.max_row + 2
row = add_section_header(ws_seg_trends, row, "CUSTOM TRENDS VIEW BUILDER")
ws_seg_trends.append(["Custom Trends", "Number of Views (1-6)", "", "How many custom views"])
for v in range(1, 7):
    ws_seg_trends.append(["", f"View {v} - Tab Title", "", f"Tab name for View {v}"])
    ws_seg_trends.append(["", f"View {v} - Content Title", "", f"Content title for View {v}"])
    ws_seg_trends.append(["", f"View {v} - Description", "", f"Description for View {v}"])
    ws_seg_trends.append(["", f"View {v} - Number of Sections (1-8)", "", f"Number of sections in View {v}"])
    for s in range(1, 9):
        ws_seg_trends.append(["", f"View {v} - Section {s} - Left", "", f"Left content for section {s}"])
        ws_seg_trends.append(["", f"View {v} - Section {s} - Right", "", f"Right content for section {s}"])

# 5. BRAND TRENDS SHEET
ws_brand_trends = wb.create_sheet("Brand Trends")
row = 1
ws_brand_trends.cell(row, 1, "BRAND TRENDS CONFIGURATION")
ws_brand_trends.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_brand_trends.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_brand_trends.merge_cells(f'A{row}:D{row}')
row += 2

ws_brand_trends.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

row = add_section_header(ws_brand_trends, row, "STANDALONE IMAGES (5 Images)")
for i in range(1, 6):
    ws_brand_trends.append(["Standalone Images", f"Image {i} - Title", "", f"Title for standalone image {i}"])
    ws_brand_trends.append(["", f"Image {i} - Comment", "", f"Comment for standalone image {i}"])
    ws_brand_trends.append(["", f"Image {i} - Image File", "", f"Image file for standalone image {i}"])

row = ws_brand_trends.max_row + 2
row = add_section_header(ws_brand_trends, row, "PLACEHOLDER IMAGES (5 Images)")
for i in range(1, 6):
    ws_brand_trends.append(["Placeholder Images", f"Placeholder {i} - Title", "", f"Title for placeholder {i}"])
    ws_brand_trends.append(["", f"Placeholder {i} - Comment", "", f"Comment for placeholder {i}"])
    ws_brand_trends.append(["", f"Placeholder {i} - Image File", "", f"Image file for placeholder {i}"])

row = ws_brand_trends.max_row + 2
row = add_section_header(ws_brand_trends, row, "CUSTOM TRENDS VIEW BUILDER")
ws_brand_trends.append(["Custom Trends", "Number of Views (1-6)", "", "How many custom views"])
for v in range(1, 7):
    ws_brand_trends.append(["", f"View {v} - Tab Title", "", f"Tab name for View {v}"])
    ws_brand_trends.append(["", f"View {v} - Content Title", "", f"Content title for View {v}"])
    ws_brand_trends.append(["", f"View {v} - Description", "", f"Description for View {v}"])
    ws_brand_trends.append(["", f"View {v} - Number of Sections (1-8)", "", f"Number of sections"])
    for s in range(1, 9):
        ws_brand_trends.append(["", f"View {v} - Section {s} - Left", "", f"Left content"])
        ws_brand_trends.append(["", f"View {v} - Section {s} - Right", "", f"Right content"])

# 6. BATTLEGROUNDS SHEET
ws_bg = wb.create_sheet("Battlegrounds")
row = 1
ws_bg.cell(row, 1, "BATTLEGROUNDS CONFIGURATION")
ws_bg.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_bg.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_bg.merge_cells(f'A{row}:D{row}')
row += 2

ws_bg.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

for tab_num in range(1, 4):
    tab_names = ["DOMINATE", "DRIVE", "DISRUPT"]
    tab_colors = ["#4CAF50", "#FFC107", "#F44336"]
    
    row = add_section_header(ws_bg, ws_bg.max_row + 1, f"TAB {tab_num} - {tab_names[tab_num-1]}")
    
    # Image 1 (Top)
    ws_bg.append([f"Tab {tab_num}", "Image 1 (Top) - Title", "", "Title for top image"])
    ws_bg.append(["", "Image 1 (Top) - Comment", "", "Comment for top image"])
    ws_bg.append(["", "Image 1 (Top) - Image File", "", "Image file name for top image"])
    
    # Tab Configuration
    ws_bg.append(["", "Tab Name", tab_names[tab_num-1], "Name of the tab (editable)"])
    ws_bg.append(["", "Tab Color", tab_colors[tab_num-1], "Color code for the tab"])
    ws_bg.append(["", "Left Section Header", "State Performance", "Header for left section"])
    ws_bg.append(["", "Right Section Header", "Strategic Insights", "Header for right section"])
    ws_bg.append(["", "Column 1 Heading", "SOG", "First insights column name"])
    ws_bg.append(["", "Column 2 Heading", "5Cs", "Second insights column name"])
    ws_bg.append(["", "Column 3 Heading", "Imagery", "Third insights column name"])
    
    # States and Brands
    ws_bg.append(["", "Assigned States", "", "Comma-separated state names (e.g., Uttar Pradesh, Bihar)"])
    ws_bg.append(["", "Selected Brand Families", "", "Comma-separated brand families"])
    ws_bg.append(["", "Selected Brands", "", "Comma-separated brand names"])
    ws_bg.append(["", "Calculation Comment", "", "Comment for state performance section"])
    
    # State-specific insights (for up to 10 states)
    for state_num in range(1, 11):
        ws_bg.append(["", f"State {state_num} - Name", "", f"Name of state {state_num}"])
        ws_bg.append(["", f"State {state_num} - SOG Content", "", f"SOG insights for state {state_num}"])
        ws_bg.append(["", f"State {state_num} - 5Cs Content", "", f"5Cs insights for state {state_num}"])
        ws_bg.append(["", f"State {state_num} - Imagery Content", "", f"Imagery insights for state {state_num}"])
    
    # Image 2 (Bottom)
    ws_bg.append(["", "Image 2 (Bottom) - Title", "", "Title for bottom image"])
    ws_bg.append(["", "Image 2 (Bottom) - Comment", "", "Comment for bottom image"])
    ws_bg.append(["", "Image 2 (Bottom) - Image File", "", "Image file name for bottom image"])

# 7. JTBD SHEET
ws_jtbd = wb.create_sheet("JTBD")
row = 1
ws_jtbd.cell(row, 1, "JOBS TO BE DONE (JTBD) CONFIGURATION")
ws_jtbd.cell(row, 1).font = Font(bold=True, size=14, color="FFFFFF")
ws_jtbd.cell(row, 1).fill = PatternFill(start_color="203864", end_color="203864", fill_type="solid")
ws_jtbd.merge_cells(f'A{row}:D{row}')
row += 2

ws_jtbd.append(["Section", "Field", "Value", "Instructions/Notes"])
row += 1

row = add_section_header(ws_jtbd, row, "MAIN CONFIGURATION")
ws_jtbd.append(["Main", "Title", "", "Main title for JTBD section"])
ws_jtbd.append(["", "Number of Tabs (1-6)", "", "How many JTBD tabs to create"])

for tab_num in range(1, 7):
    row = ws_jtbd.max_row + 2
    row = add_section_header(ws_jtbd, row, f"TAB {tab_num}")
    ws_jtbd.append([f"Tab {tab_num}", "Tab Name", "", f"Name for tab {tab_num}"])
    ws_jtbd.append(["", "Description", "", f"Description for tab {tab_num}"])
    ws_jtbd.append(["", "Left Header", "What's Working & Holding Us Back?", "Left column header"])
    ws_jtbd.append(["", "Right Header", "JTBDs", "Right column header"])
    ws_jtbd.append(["", "Number of Sections (1-8)", "", f"How many sections in tab {tab_num}"])
    
    for sec_num in range(1, 9):
        ws_jtbd.append(["", f"Section {sec_num} - Label", "", f"Label for section {sec_num}"])
        ws_jtbd.append(["", f"Section {sec_num} - Left Content", "", f"Left content for section {sec_num}"])
        ws_jtbd.append(["", f"Section {sec_num} - Right Content", "", f"Right content for section {sec_num}"])

# Style all sheets
for ws in [ws_ns, ws_seg, ws_brand, ws_seg_trends, ws_brand_trends, ws_bg, ws_jtbd]:
    # Header row styling
    for cell in ws[3]:
        cell.font = Font(bold=True, size=11)
        cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
    # Set column widths
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 40
    ws.column_dimensions['C'].width = 50
    ws.column_dimensions['D'].width = 60
    
    # Freeze panes
    ws.freeze_panes = 'A4'

# Save the workbook
wb.save("Dashboard_Configuration_Template_COMPLETE.xlsx")
print("✅ Complete Excel template created: Dashboard_Configuration_Template_COMPLETE.xlsx")
print(f"   - NS Landscape: {ws_ns.max_row} rows")
print(f"   - Segment Truths: {ws_seg.max_row} rows")
print(f"   - Brand Truths: {ws_brand.max_row} rows")
print(f"   - Segment Trends: {ws_seg_trends.max_row} rows")
print(f"   - Brand Trends: {ws_brand_trends.max_row} rows")
print(f"   - Battlegrounds: {ws_bg.max_row} rows")
print(f"   - JTBD: {ws_jtbd.max_row} rows")
