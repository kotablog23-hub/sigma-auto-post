#!/usr/bin/env python3
"""今日のポスト全件表示（投稿済み確定 + 未来スロットはauto_post.pyと同じロジックで本文予測）"""
import json, subprocess
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import random

JST = timezone(timedelta(hours=9))
BASE = Path("~/sigma").expanduser()
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# 最新stateをGitHubから取得
subprocess.run(["git", "-C", str(BASE), "pull", "--quiet"], capture_output=True)

now = datetime.now(JST)
today_str = now.strftime("%Y-%m-%d")
weekday = now.strftime("%a")

# ── xlsx読み込み ──────────────────────────────────────────────────
def load_posts():
    import openpyxl
    wb = openpyxl.load_workbook(BASE / "x_posts/posts_categorized.xlsx")
    ws = wb.active
    posts = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[0] or not row[1]: continue
        date = str(row[0])
        text = str(row[1])
        cat  = str(row[4]) if len(row) > 4 and row[4] else "normal"
        posts.append({"date": date, "text": text, "cat": cat,
                      "key": f"{row[0]}|{text[:40]}"})
    return posts

# ── auto_post.pyと同じカテゴリ選択ロジック ──────────────────────
def pick_category(hour, wd_num, available):
    if wd_num == 4 and hour >= 19:   primary = "friday"
    elif wd_num == 6:                 primary = "sunday"
    elif 7 <= hour < 9:              primary = "morning"
    elif 12 <= hour < 13:            primary = "lunch"
    elif 19 <= hour < 22:            primary = "night"
    else:                             primary = "normal"
    if primary != "normal" and available.get(primary):
        return primary
    if available.get("normal"):
        return "normal"
    for cat in ["morning","night","lunch","sunday","friday","summer","spring","exam"]:
        if available.get(cat): return cat
    return None

# ── 投稿済みキーを読み込み ────────────────────────────────────────
state_file = BASE / "x_posts/.smart_post_state.json"
state = json.loads(state_file.read_text()) if state_file.exists() else {"posted_keys": [], "history": []}
posted_keys = set(state["posted_keys"])

# ── 全文テキスト辞書（キー→全文）────────────────────────────────
def build_fulltext_map(posts):
    m = {}
    for p in posts:
        m[p["key"]] = p["text"]
    return m

# ── 投稿済みエントリ（今日分）────────────────────────────────────
confirmed = []
for h in state.get("history", []):
    try:
        dt = datetime.fromisoformat(h["posted_at"])
        if dt.tzinfo is None: dt = dt.replace(tzinfo=JST)
        dt = dt.astimezone(JST)
    except: continue
    if dt.strftime("%Y-%m-%d") == today_str and not h.get("note"):
        confirmed.append({"time": dt.strftime("%H:%M"), "key": h["key"], "status": "投稿済み"})
# 投稿済み時刻をスケジュールスロットに±5分でマッチさせる
def match_slot(posted_time, slots):
    ph, pm = map(int, posted_time.split(":"))
    for s in slots:
        sh, sm = map(int, s.split(":"))
        if abs((ph * 60 + pm) - (sh * 60 + sm)) <= 5:
            return s
    return posted_time

sched_file_tmp = BASE / "scripts/cronjob_schedule.json"
all_slots = []
if sched_file_tmp.exists():
    _sched = json.loads(sched_file_tmp.read_text())
    all_slots = _sched["schedule"].get(weekday, [])

for p in confirmed:
    p["slot"] = match_slot(p["time"], all_slots)

posted_times = {p["slot"] for p in confirmed}

# xlsxから全文マップ構築
all_posts = load_posts()
fulltext_map = build_fulltext_map(all_posts)

# 投稿済みの本文を全文に置換
for p in confirmed:
    p["text"] = fulltext_map.get(p["key"], p["key"].split("|", 1)[1] if "|" in p["key"] else p["key"])

# ── 未来スロットをシミュレーション ──────────────────────────────
sched_file = BASE / "scripts/cronjob_schedule.json"
future_slots = []
if sched_file.exists():
    sched = json.loads(sched_file.read_text())
    for t in sched["schedule"].get(weekday, []):
        if t in posted_times: continue
        future_slots.append(t)

# シミュレーション用：eligible未投稿を用意（60日以内・2026-03-08以降）
cutoff = (now - timedelta(days=60)).strftime("%Y-%m-%d")
eligible = [p for p in all_posts
            if "2026-03-08" <= p["date"][:10] <= cutoff and p["key"] not in posted_keys]

available_map = defaultdict(list)
for p in eligible:
    available_map[p["cat"]].append(p)

wd_num = now.weekday()  # 0=Mon, 6=Sun

simulated = []
sim_used = set()
for t in future_slots:
    h2, m2 = map(int, t.split(":"))
    # その時刻でのカテゴリ判定
    sim_available = {cat: [x for x in ps if x["key"] not in sim_used]
                     for cat, ps in available_map.items()}
    cat = pick_category(h2, wd_num, sim_available)
    if cat is None:
        simulated.append({"time": t, "text": "(投稿可能なポストなし)", "status": "予定"})
        continue
    candidates = sorted([x for x in sim_available[cat] if x["key"] not in sim_used],
                        key=lambda x: x["date"])
    if not candidates:
        simulated.append({"time": t, "text": "(投稿可能なポストなし)", "status": "予定"})
        continue
    chosen = candidates[0]
    sim_used.add(chosen["key"])
    simulated.append({"time": t, "text": chosen["text"], "status": "予定"})

# ── 表示 ──────────────────────────────────────────────────────────
all_entries = sorted(simulated, key=lambda x: x["time"])
print(f"\n=== 今日のポスト ({today_str} {weekday}) ===\n")
for i, p in enumerate(all_entries, 1):
    print(f"[{i}] {p['time']} [予定]")
    print(p["text"])
    print()
