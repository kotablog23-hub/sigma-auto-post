import json, re, csv
from datetime import datetime, timezone

# --- Parse tweets.js ---
with open("/home/kota/sigma/x_posts/tweets.js", encoding="utf-8") as f:
    raw = f.read()
raw = re.sub(r"^window\.YTD\.tweets\.part\d+\s*=\s*", "", raw.strip())
data = json.loads(raw)

# --- Filter: same rules as posts_clean.xlsx + date range ---
DATE_FROM = datetime(2026, 1, 29, tzinfo=timezone.utc)
DATE_TO   = datetime(2026, 4, 17, 23, 59, 59, tzinfo=timezone.utc)

LINKS = {
    "motemigaki": "https://note.com/puregrinding1/n/n4eabc4c9b556",
    "shijaku":    "https://note.com/puregrinding1/n/n75b3881b4678",
    "zoryo":      "https://note.com/puregrinding1/n/na60936ff3ad1",
}

KW = {
    "motemigaki": [
        "モテ", "恋愛", "外見", "見た目", "コミュ", "コミュニケーション", "男磨き",
        "清潔感", "服装", "ファッション", "髪", "女性", "女子", "チー牛", "非モテ",
        "デート", "彼女", "自己開示", "会話", "話し方", "印象", "魅力", "好感度",
        "自閉症", "陰キャ", "リア充", "合コン", "ナンパ", "恋人",
    ],
    "shijaku": [
        "スマホ", "ドーパミン", "集中", "スクリーンタイム", "デジタル", "SNS",
        "YouTube", "ショート", "依存", "中毒", "通知", "ポルノ", "スクロール",
        "刺激", "快楽", "誘惑", "スマホ断ち", "スマホ中毒", "デトックス",
        "ショートコンテンツ", "退屈", "暇", "無気力", "やる気", "集中力",
        "脳", "報酬", "習慣", "意志力",
    ],
    "zoryo": [
        "筋トレ", "トレーニング", "ジム", "食事", "プロテイン", "カロリー",
        "増量", "体型", "筋肉", "体重", "バルク", "タンパク質", "ヒョロガリ",
        "鍛え", "筋量", "食べ", "肉", "炭水化物", "脂質", "栄養",
        "ベンチプレス", "スクワット", "デッドリフト", "重量", "rep", "セット",
    ],
}

def classify(text):
    scores = {cat: 0 for cat in KW}
    for cat, words in KW.items():
        for w in words:
            if w in text:
                scores[cat] += 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "motemigaki"  # fallback: 最も汎用的な自己改善商品
    return best

def expand_urls(text, entities):
    for u in entities.get("urls", []):
        tco = u.get("url", "")
        expanded = u.get("expanded_url", "")
        if tco and expanded:
            text = text.replace(tco, expanded)
    # 残ったt.coリンク（メディア添付など）は削除
    text = re.sub(r'https://t\.co/\S+', '', text).strip()
    return text

def extract_media_urls(tweet):
    # extended_entities が複数画像に対応（entities.media は1枚目のみ）
    media_list = tweet.get("extended_entities", {}).get("media", [])
    if not media_list:
        media_list = tweet.get("entities", {}).get("media", [])
    # photoのみ（video/animated_gifは除外）
    return [m["media_url_https"] for m in media_list if m.get("type") == "photo"]

rows = []
for item in data:
    t = item["tweet"]
    if t.get("retweeted", False):
        continue
    text = t.get("full_text", "")
    if text.startswith("RT @") or text.startswith("@"):
        continue
    try:
        dt = datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S +0000 %Y").replace(tzinfo=timezone.utc)
    except Exception:
        continue
    if not (DATE_FROM <= dt <= DATE_TO):
        continue
    text = expand_urls(text, t.get("entities", {}))
    media_urls = extract_media_urls(t)
    cat = classify(text)
    rows.append({
        "date":       dt.strftime("%Y-%m-%d %H:%M:%S"),
        "text":       text,
        "reply":      LINKS[cat],
        "media_urls": "|".join(media_urls),
    })

rows.sort(key=lambda r: r["date"])
print(f"対象件数: {len(rows)} 件")

# --- カテゴリ内訳 ---
from collections import Counter
cats = Counter()
for r in rows:
    for k, v in LINKS.items():
        if r["reply"] == v:
            cats[k] += 1
print(f"  男磨き大全: {cats['motemigaki']} 件")
print(f"  静寂論:     {cats['shijaku']} 件")
print(f"  増量ガイド: {cats['zoryo']} 件")

# --- Buffer CSV ---
out = "/home/kota/sigma/x_posts/buffer_import.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=["date", "text", "reply", "media_urls"])
    writer.writeheader()
    writer.writerows(rows)

print(f"保存完了: {out}")
