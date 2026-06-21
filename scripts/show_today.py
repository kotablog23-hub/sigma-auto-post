#!/usr/bin/env python3
"""今日のポスト全件表示（投稿済み + cron-job.org予測 + scheduled_today.py予定）"""
import json, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
BASE = Path("~/sigma").expanduser()

# 最新state取得
subprocess.run(["git", "-C", str(BASE), "pull", "--quiet"],
               capture_output=True)

now = datetime.now(JST)
today_str = now.strftime("%Y-%m-%d")
weekday = now.strftime("%a")  # Mon/Tue/Wed/Thu/Fri/Sat/Sun

posts = []

# 1) 投稿済み（smart_post_state.json）
state_file = BASE / "x_posts/.smart_post_state.json"
if state_file.exists():
    data = json.loads(state_file.read_text())
    for h in data.get("history", []):
        try:
            dt = datetime.fromisoformat(h["posted_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            dt = dt.astimezone(JST)
        except Exception:
            continue
        if dt.strftime("%Y-%m-%d") == today_str:
            text = h["key"].split("|", 1)[1] if "|" in h["key"] else h["key"]
            posts.append({
                "time": dt.strftime("%H:%M"),
                "source": "GitHub Actions",
                "text": text,
                "status": "投稿済み",
            })
posted_times = {p["time"] for p in posts}

# 2) cron-job.orgの残り予定（未投稿分）
sched_file = BASE / "scripts/cronjob_schedule.json"
if sched_file.exists():
    sched = json.loads(sched_file.read_text())
    for t in sched["schedule"].get(weekday, []):
        if t not in posted_times:
            h, m = map(int, t.split(":"))
            target = datetime(now.year, now.month, now.day, h, m, tzinfo=JST)
            if target > now:
                posts.append({
                    "time": t,
                    "source": "cron-job.org予測",
                    "text": "(auto_post.pyが時刻・カテゴリに応じて選択)",
                    "status": "予定",
                })

posts.sort(key=lambda x: x["time"])

print(f"\n=== 今日のポスト ({today_str} {weekday}) ===\n")
if not posts:
    print("今日の投稿なし")
else:
    for i, p in enumerate(posts, 1):
        label = f"[{p['status']}]" if p["status"] == "投稿済み" else f"[{p['status']}]"
        print(f"[{i}] {p['time']} {p['source']} {label}")
        print(p["text"])
        print()
