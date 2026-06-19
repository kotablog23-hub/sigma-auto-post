#!/usr/bin/env python3
"""
当日の投稿スケジュール確認スクリプト

今日の投稿スケジュール（GitHub Actionsの時刻）に基づいて、
各スロットで投稿される予定の投稿文を全文表示する。

使い方:
  python3 check_today.py
"""

import json, random, re, sys, zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BASE      = Path(__file__).resolve().parent.parent
XLSX_PATH  = _BASE / "x_posts/posts_categorized.xlsx"
STATE_PATH = _BASE / "x_posts/.smart_post_state.json"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

JST = timezone(timedelta(hours=9))

# GitHub Actions のスケジュール（JST時刻）
# 曜日: 0=月, 1=火, 2=水, 3=木, 4=金, 5=土, 6=日
SCHEDULE = {
    6: [12, 13, 14, 15, 16, 17, 19],       # 日
    0: [12, 13, 15, 17, 19, 21],            # 月
    1: [12, 15, 19, 21, 22],                # 火
    2: [12, 15, 19, 21, 22],                # 水
    3: [12, 15, 19, 21, 22],                # 木
    4: [12, 13, 15, 19, 21],                # 金
    5: [12, 19],                            # 土
}

NOTE_TITLES = {
    "motemigaki": "「爆速でモテる男磨きのやり方」非モテが恋愛の土台を築き上げる男磨きby元自閉症チー牛が解説\nhttps://note.com/puregrinding1/n/n4eabc4c9b556",
    "shijaku":    "【スマホ中毒者向け】\"デジタル・ドーパミン廃人\"だった私がスクリーンタイム10時間→1時間で人生を奪還した思考法\nhttps://note.com/puregrinding1/n/n75b3881b4678",
    "zoryo":      "【ヒョロガリ向け】最短で「モテボディ」を獲得するための食事プログラム｜by元体重39kgのヒョロガリが解説。\nhttps://note.com/puregrinding1/n/na60936ff3ad1",
}
NOTE_KW = {
    "motemigaki": ["モテ","恋愛","外見","見た目","コミュ","男磨き","清潔感","服装","ファッション",
                   "髪","女性","女子","チー牛","非モテ","デート","彼女","自己開示","会話","話し方",
                   "印象","魅力","好感度","自閉症","陰キャ","童貞","匂い","臭い","清潔","春"],
    "shijaku":    ["スマホ","ドーパミン","集中","スクリーンタイム","デジタル","SNS","YouTube",
                   "ショート","依存","中毒","通知","ポルノ","スクロール","刺激","快楽","誘惑",
                   "スマホ断ち","脳","報酬","習慣","意志力","テストステロン"],
    "zoryo":      ["筋トレ","トレーニング","ジム","食事","プロテイン","カロリー","増量","体型",
                   "筋肉","体重","バルク","タンパク質","ヒョロガリ","鍛え","筋量","食べ","肉",
                   "炭水化物","Big３","ベンチ","スクワット","デッドリフト","夏"],
}

def classify_note(text):
    scores = {k: sum(1 for w in ws if w in text) for k, ws in NOTE_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "motemigaki"


def load_posts():
    with zipfile.ZipFile(XLSX_PATH) as zf:
        sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        strings = []
        for si in sst_root.findall(f"{{{NS}}}si"):
            t = si.find(f"{{{NS}}}t")
            if t is not None:
                strings.append(t.text or "")
            else:
                strings.append("".join(p.text or "" for p in si.findall(f".//{{{NS}}}t")))
        sheet_root = ET.fromstring(zf.read("xl/worksheets/sheet1.xml"))

    posts = []
    for row in sheet_root.findall(f".//{{{NS}}}row"):
        cells = row.findall(f"{{{NS}}}c")
        if not cells:
            continue
        def val(c):
            v = c.find(f"{{{NS}}}v")
            if v is None: return ""
            return strings[int(v.text)] if c.get("t") == "s" else (v.text or "")
        r = [val(c) for c in cells]
        if len(r) < 5 or r[1] == "投稿文":
            continue
        posts.append({
            "date":          r[0],
            "text":          r[1],
            "time_category": r[4] if len(r) > 4 else "normal",
            "key":           f"{r[0]}|{r[1][:40]}",
        })
    return posts


def pick_category(hour, weekday, month, available):
    seasonal = None
    if 6 <= month <= 8:   seasonal = "summer"
    elif 3 <= month <= 4: seasonal = "spring"
    elif 1 <= month <= 3: seasonal = "exam"

    if weekday == 4 and hour >= 19:   primary = "friday"
    elif weekday == 6:                primary = "sunday"
    elif 7 <= hour < 9:               primary = "morning"
    elif 12 <= hour < 13:             primary = "lunch"
    elif 19 <= hour < 22:             primary = "night"
    else:                             primary = "normal"

    if primary != "normal" and available.get(primary):
        return primary
    if seasonal and available.get(seasonal) and random.random() < 0.25:
        return seasonal
    if available.get("normal"):
        return "normal"
    for cat in ["morning","night","lunch","sunday","friday","summer","spring","exam"]:
        if available.get(cat):
            return cat
    return None


def main():
    now_jst = datetime.now(JST)
    today_wd = now_jst.weekday()
    today_month = now_jst.month
    slots = SCHEDULE.get(today_wd, [])

    day_names = ["月", "火", "水", "木", "金", "土", "日"]
    print(f"{'='*60}")
    print(f"  {now_jst.strftime('%Y-%m-%d')} ({day_names[today_wd]}曜日) の投稿予定")
    print(f"  スロット数: {len(slots)}件  {[f'{h}:00' for h in slots]}")
    print(f"{'='*60}\n")

    posts = load_posts()
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() \
            else {"posted_keys": [], "history": []}
    posted_ks = set(state["posted_keys"])

    # 対象期間フィルター（上限は実行当日）
    today_str = now_jst.strftime("%Y-%m-%d")
    posts = [p for p in posts if "2026-03-08" <= p["date"][:10] <= today_str]

    # 各スロットをシミュレート（投稿済みセットを更新しながら順番に）
    sim_posted = set(posted_ks)

    for slot_hour in slots:
        available = defaultdict(list)
        for p in posts:
            if p["key"] not in sim_posted:
                available[p["time_category"]].append(p)

        cat = pick_category(slot_hour, today_wd, today_month, available)

        print(f"┌─ {slot_hour:02d}:00 JST {'─'*45}")
        if cat is None:
            print(f"│  ⚠️  投稿可能な投稿なし")
            print(f"└{'─'*50}\n")
            continue

        post = sorted(available[cat], key=lambda p: p["date"])[0]
        note_cat = classify_note(post["text"])

        print(f"│  カテゴリ: {cat}  |  noteリンク: {note_cat}")
        print(f"│  元日時: {post['date']}")
        print(f"│")
        for line in post["text"].splitlines():
            print(f"│  {line}")
        print(f"│")
        note_names = {"motemigaki": "男磨き大全", "shijaku": "静寂論", "zoryo": "増量ガイド"}
        print(f"│  ▷ noteリンク ({note_names[note_cat]}):")
        for line in NOTE_TITLES[note_cat].splitlines():
            print(f"│    {line}")
        print(f"└{'─'*50}\n")

        sim_posted.add(post["key"])

    total_remaining = sum(1 for p in posts if p["key"] not in posted_ks)
    print(f"現在の未投稿残り: {total_remaining}件")


if __name__ == "__main__":
    main()
