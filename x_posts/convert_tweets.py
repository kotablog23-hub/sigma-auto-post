import json, re, zipfile, io
from datetime import datetime, timezone

# --- Parse tweets.js ---
with open("/home/kota/sigma/x_posts/tweets.js", encoding="utf-8") as f:
    raw = f.read()
raw = re.sub(r"^window\.YTD\.tweets\.part\d+\s*=\s*", "", raw.strip())
data = json.loads(raw)

# --- Filter ---
rows = []
for item in data:
    t = item["tweet"]
    retweeted = t.get("retweeted", False)
    text = t.get("full_text", "")
    if retweeted:
        continue
    if text.startswith("RT @"):
        continue
    if text.startswith("@"):
        continue
    created_at = t.get("created_at", "")
    try:
        dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S +0000 %Y")
        date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        date_str = created_at
    likes = int(t.get("favorite_count", 0))
    rts = int(t.get("retweet_count", 0))
    rows.append((date_str, text, likes, rts))

# Sort by date ascending
rows.sort(key=lambda r: r[0])

print(f"抽出件数: {len(rows)} 件")

# --- Build xlsx from scratch ---
headers = ["日付", "投稿文", "いいね数", "RT数"]
all_strings = list(headers)
for row in rows:
    all_strings.append(str(row[0]))
    all_strings.append(str(row[1]))
# Deduplicate while preserving order
seen = {}
for s in all_strings:
    if s not in seen:
        seen[s] = len(seen)
sst = list(seen.keys())
idx = seen  # string -> index

def esc(s):
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))

# sharedStrings.xml
sst_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
sst_xml += f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(sst)}" uniqueCount="{len(sst)}">'
for s in sst:
    sst_xml += f'<si><t xml:space="preserve">{esc(s)}</t></si>'
sst_xml += '</sst>'

# styles.xml (minimal)
styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts><font><sz val="11"/><name val="Calibri"/></font>
  <font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/>
  </cellXfs>
</styleSheet>'''

# worksheet
def col_letter(n):  # 0-indexed
    return chr(ord('A') + n)

def make_cell(col, row_num, value, is_str=False, style=0):
    ref = f"{col_letter(col)}{row_num}"
    if is_str:
        return f'<c r="{ref}" t="s" s="{style}"><v>{value}</v></c>'
    else:
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'

sheet_rows = []
# Header row
header_cells = ""
for ci, h in enumerate(headers):
    header_cells += make_cell(ci, 1, idx[h], is_str=True, style=1)
sheet_rows.append(f'<row r="1">{header_cells}</row>')

# Data rows
for ri, (date_str, text, likes, rts) in enumerate(rows):
    rn = ri + 2
    cells = ""
    cells += make_cell(0, rn, idx[date_str], is_str=True, style=0)
    cells += make_cell(1, rn, idx[text], is_str=True, style=0)
    cells += make_cell(2, rn, likes, is_str=False, style=0)
    cells += make_cell(3, rn, rts, is_str=False, style=0)
    sheet_rows.append(f'<row r="{rn}">{cells}</row>')

total_rows = len(rows) + 1
sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(sheet_rows)}</sheetData>
</worksheet>'''

# workbook.xml
wb_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="posts" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''

rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''

wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

out_path = "/home/kota/sigma/x_posts/posts_clean.xlsx"
with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("[Content_Types].xml", content_types)
    zf.writestr("_rels/.rels", rels)
    zf.writestr("xl/workbook.xml", wb_xml)
    zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
    zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    zf.writestr("xl/sharedStrings.xml", sst_xml)
    zf.writestr("xl/styles.xml", styles_xml)

print(f"保存完了: {out_path}")
