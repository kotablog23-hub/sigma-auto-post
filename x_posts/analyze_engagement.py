import zipfile, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from collections import defaultdict

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

xlsx = "/home/kota/sigma/x_posts/posts_clean.xlsx"
with zipfile.ZipFile(xlsx) as zf:
    sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = [si.find(f"{{{NS}}}t").text or "" for si in sst_root.findall(f"{{{NS}}}si")]

    sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))

rows = []
for row in sheet_root.findall(f".//{{{NS}}}row"):
    cells = row.findall(f"{{{NS}}}c")
    if not cells:
        continue
    def val(c):
        v = c.find(f"{{{NS}}}v")
        if v is None:
            return None
        return strings[int(v.text)] if c.get("t") == "s" else v.text
    row_vals = [val(c) for c in cells]
    if len(row_vals) < 4 or row_vals[0] == "日付":  # skip header
        continue
    date_str, text, likes, rts = row_vals[0], row_vals[1], row_vals[2], row_vals[3]
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        # JST = UTC+9
        dt_jst = dt.astimezone(tz=None).__class__(dt.year, dt.month, dt.day,
                  dt.hour + 9 if dt.hour + 9 < 24 else dt.hour + 9 - 24,
                  dt.minute, dt.second)
        # 簡易JST変換
        from datetime import timedelta
        dt_jst = dt + timedelta(hours=9)
    except Exception as e:
        continue
    eng = int(likes or 0) + int(rts or 0)
    rows.append((dt_jst, eng))

print(f"読み込み件数: {len(rows)} 件")

DAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]

def time_slot(hour):
    if 5 <= hour < 8:   return "早朝(5-8時)"
    if 8 <= hour < 12:  return "午前(8-12時)"
    if 12 <= hour < 15: return "昼(12-15時)"
    if 15 <= hour < 19: return "夕方(15-19時)"
    if 19 <= hour < 23: return "夜(19-23時)"
    return "深夜(23-5時)"

bucket = defaultdict(list)
for dt, eng in rows:
    day = DAYS_JP[dt.weekday()]
    slot = time_slot(dt.hour)
    bucket[(day, slot)].append(eng)

results = []
for (day, slot), engs in bucket.items():
    avg = sum(engs) / len(engs)
    results.append((day, slot, avg, len(engs)))

results.sort(key=lambda x: -x[2])

print("\n曜日×時間帯別 平均エンゲージメント（いいね+RT）上位10")
print(f"{'順位':<4} {'曜日':<3} {'時間帯':<14} {'平均ENG':>8} {'投稿数':>6}")
print("-" * 45)
for i, (day, slot, avg, cnt) in enumerate(results[:10], 1):
    print(f"{i:<4} {day:<3} {slot:<14} {avg:>8.2f} {cnt:>6}件")

print("\n全パターン（参考）:")
print(f"{'順位':<4} {'曜日':<3} {'時間帯':<14} {'平均ENG':>8} {'投稿数':>6}")
print("-" * 45)
for i, (day, slot, avg, cnt) in enumerate(results, 1):
    print(f"{i:<4} {day:<3} {slot:<14} {avg:>8.2f} {cnt:>6}件")
