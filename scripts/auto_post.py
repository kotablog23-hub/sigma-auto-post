#!/usr/bin/env python3
"""
スマートカテゴリ選択版 X 自動投稿スクリプト

posts_categorized.xlsx を読み込み、実行時の時間・曜日・月に応じて
カテゴリを選び、未投稿の投稿をランダムに選んで投稿する。

使い方:
  python3 auto_post.py            # 1件投稿
  python3 auto_post.py --dry-run  # 確認のみ（実際には投稿しない）
  python3 auto_post.py --status   # 残件数をカテゴリ別に表示

必要な環境変数 (~/sigma/.env):
  X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET

cron 設定例:
  0  7 * * 1-5  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 12 * * 1-5  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 12 * * 0    cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 17 * * 0    cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 17 * * 1    cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 20 * * 2    cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 20 * * 4    cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
"""

import base64, hashlib, hmac, json, os, random, re, sys, time, uuid, zipfile
import urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ── パス（スクリプト位置基準で解決 → ローカル・GitHub Actions 共通） ──
_BASE        = Path(__file__).resolve().parent.parent
XLSX_PATH    = _BASE / "x_posts/posts_categorized.xlsx"
TWEETS_JS    = _BASE / "x_posts/tweets.js"
STATE_PATH   = _BASE / "x_posts/.smart_post_state.json"
ENV_PATH     = _BASE / ".env"

# ── X API エンドポイント ────────────────────────────────────────
TWEETS_URL       = "https://api.twitter.com/2/tweets"
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

# ── Threads API エンドポイント ──────────────────────────────────
THREADS_API = "https://graph.threads.net/v1.0"

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# ── noteリンク自動分類 ──────────────────────────────────────────
REPLY_TEXTS = {
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

def classify_note(text: str) -> str:
    scores = {k: sum(1 for w in ws if w in text) for k, ws in NOTE_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "motemigaki"


# ── .env 読み込み ───────────────────────────────────────────────
def load_env():
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


# ── xlsx 読み込み ───────────────────────────────────────────────
def load_posts() -> list[dict]:
    with zipfile.ZipFile(XLSX_PATH) as zf:
        sst_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        strings = [si.find(f"{{{NS}}}t").text or ""
                   for si in sst_root.findall(f"{{{NS}}}si")]
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
            "likes":         int(r[2] or 0),
            "rts":           int(r[3] or 0),
            "time_category": r[4] if len(r) > 4 else "normal",
            "key":           f"{r[0]}|{r[1][:40]}",
        })
    return posts


# ── tweets.js から画像URL辞書を構築 ────────────────────────────
def load_media_map() -> dict:
    if not TWEETS_JS.exists():
        return {}
    raw = TWEETS_JS.read_text(encoding="utf-8")
    raw = re.sub(r"^window\.YTD\.tweets\.part\d+\s*=\s*", "", raw.strip())
    data = json.loads(raw)
    media_map = {}
    for item in data:
        t = item["tweet"]
        try:
            dt = datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S +0000 %Y")
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        media = (t.get("extended_entities", {}).get("media") or
                 t.get("entities", {}).get("media", []))
        urls = [m["media_url_https"] for m in media if m.get("type") == "photo"]
        if urls:
            media_map[date_str] = urls
    return media_map


# ── カテゴリ選択ロジック ────────────────────────────────────────
def pick_category(now: datetime, available: dict) -> str | None:
    h  = now.hour
    wd = now.weekday()   # 0=月, 4=金, 6=日
    m  = now.month

    # 季節カテゴリ（normal fallback 時に 25% で混入）
    seasonal = None
    if 6 <= m <= 8:   seasonal = "summer"
    elif 3 <= m <= 4: seasonal = "spring"
    elif 1 <= m <= 3: seasonal = "exam"

    # 時間・曜日による優先カテゴリ
    if wd == 4 and h >= 19:   primary = "friday"
    elif wd == 6:              primary = "sunday"
    elif 7 <= h < 9:           primary = "morning"
    elif 12 <= h < 13:         primary = "lunch"
    elif 19 <= h < 22:         primary = "night"
    else:                      primary = "normal"

    # 優先カテゴリに未投稿があればそれを使う
    if primary != "normal" and available.get(primary):
        return primary

    # normal fallback に季節を混入（25%）
    if seasonal and available.get(seasonal) and random.random() < 0.25:
        return seasonal

    if available.get("normal"):
        return "normal"

    # 残り全カテゴリから探す
    for cat in ["morning","night","lunch","sunday","friday","summer","spring","exam"]:
        if available.get(cat):
            return cat

    return None


# ── OAuth 1.0a ─────────────────────────────────────────────────
def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="-._~")

def _oauth_header(method: str, url: str, creds: dict) -> str:
    p = {
        "oauth_consumer_key":     creds["api_key"],
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            creds["access_token"],
        "oauth_version":          "1.0",
    }
    param_str = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(p.items()))
    base = f"{_pct(method.upper())}&{_pct(url)}&{_pct(param_str)}"
    key  = f"{_pct(creds['api_secret'])}&{_pct(creds['access_token_secret'])}"
    sig  = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    p["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{k}="{_pct(v)}"' for k, v in sorted(p.items()))


def _upload_media(img_url: str, creds: dict) -> str:
    with urllib.request.urlopen(img_url) as resp:
        img_data = resp.read()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        MEDIA_UPLOAD_URL, data=body, method="POST",
        headers={"Authorization": _oauth_header("POST", MEDIA_UPLOAD_URL, creds),
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["media_id_string"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Media upload HTTP {e.code}: {e.read().decode()}") from e


def _post_tweet(body: dict, creds: dict, reply_to_id: str = None,
                media_ids: list = None) -> str:
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    if media_ids:
        body["media"] = {"media_ids": media_ids}
    req = urllib.request.Request(
        TWEETS_URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": _oauth_header("POST", TWEETS_URL, creds),
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["data"]["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e


# ── Threads API ────────────────────────────────────────────────
def _threads_get_user_id(token: str) -> str:
    url = f"{THREADS_API}/me?fields=id&access_token={urllib.parse.quote(token, safe='')}"
    try:
        with urllib.request.urlopen(url) as resp:
            return json.loads(resp.read())["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Threads /me HTTP {e.code}: {e.read().decode()}") from e


def _post_threads(text: str, token: str, user_id: str, reply_to_id: str = None) -> str:
    params = {"media_type": "TEXT", "text": text, "access_token": token}
    if reply_to_id:
        params["reply_to_id"] = reply_to_id
    create_url = f"{THREADS_API}/{user_id}/threads"
    req = urllib.request.Request(
        create_url,
        data=urllib.parse.urlencode(params).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            container_id = json.loads(resp.read())["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Threads create HTTP {e.code}: {e.read().decode()}") from e

    time.sleep(5)
    pub_params = {"creation_id": container_id, "access_token": token}
    pub_req = urllib.request.Request(
        f"{THREADS_API}/{user_id}/threads_publish",
        data=urllib.parse.urlencode(pub_params).encode(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(pub_req) as resp:
            return json.loads(resp.read())["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Threads publish HTTP {e.code}: {e.read().decode()}") from e


# ── 状態管理 ───────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"posted_keys": [], "history": []}

def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")


# ── メイン ─────────────────────────────────────────────────────
def main():
    load_env()
    now     = datetime.now()
    log_pfx = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}]"
    dry_run = "--dry-run" in sys.argv
    status  = "--status"  in sys.argv

    # 環境変数
    creds = {
        "api_key":             os.environ.get("X_API_KEY", ""),
        "api_secret":          os.environ.get("X_API_SECRET", ""),
        "access_token":        os.environ.get("X_ACCESS_TOKEN", ""),
        "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET", ""),
    }
    if not dry_run and not status:
        missing = [k for k, v in creds.items() if not v]
        if missing:
            sys.exit(f"❌ 環境変数未設定: {', '.join(missing)}")

    posts     = load_posts()
    state     = load_state()
    posted_ks = set(state["posted_keys"])
    media_map = load_media_map()

    # 対象期間フィルター
    posts = [p for p in posts
             if "2026-03-08" <= p["date"][:10] <= "2026-06-17"]

    # カテゴリ別に未投稿を分類
    available: dict[str, list] = defaultdict(list)
    for p in posts:
        if p["key"] not in posted_ks:
            available[p["time_category"]].append(p)

    total_remaining = sum(len(v) for v in available.values())

    # --status モード
    if status:
        print(f"総未投稿: {total_remaining}件 / {len(posts)}件")
        for cat in ["morning","lunch","night","sunday","friday","summer","spring","exam","normal"]:
            print(f"  {cat:<10}: {len(available.get(cat, []))}件")
        return

    if total_remaining == 0:
        print(f"{log_pfx} ✅ 全投稿完了")
        return

    # カテゴリ選択
    cat = pick_category(now, available)
    if cat is None:
        print(f"{log_pfx} ❌ 投稿可能な投稿が見つかりません")
        return

    # カテゴリ内で日付順に選択
    post = sorted(available[cat], key=lambda p: p["date"])[0]

    note_cat   = classify_note(post["text"])
    reply_text = REPLY_TEXTS[note_cat]
    img_urls   = media_map.get(post["date"], [])

    print(f"{log_pfx} カテゴリ: {cat} | note: {note_cat}")
    print(f"{log_pfx} 元日時: {post['date']}")
    print(f"{log_pfx} 本文: {post['text'][:80]}{'...' if len(post['text'])>80 else ''}")
    print(f"{log_pfx} 画像: {len(img_urls)}枚 | 残り: {total_remaining-1}件")

    if dry_run:
        print(f"{log_pfx} [DRY RUN] スキップ")
        return

    # 画像アップロード
    media_ids = []
    for img_url in img_urls[:4]:
        mid = _upload_media(img_url, creds)
        media_ids.append(mid)
        print(f"{log_pfx} 画像アップ: {img_url.split('/')[-1]} → {mid}")

    # 本文投稿
    tweet_id = _post_tweet({"text": post["text"]}, creds,
                            media_ids=media_ids or None)
    print(f"{log_pfx} ✅ 投稿: https://x.com/i/web/status/{tweet_id}")

    # リプライ (X)
    time.sleep(3)
    reply_id = _post_tweet({"text": reply_text}, creds, reply_to_id=tweet_id)
    print(f"{log_pfx} ✅ リプライ: https://x.com/i/web/status/{reply_id}")

    # Threads 投稿（失敗してもX投稿は保存する）
    th_post_id = th_reply_id = None
    threads_token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if threads_token:
        try:
            threads_uid = _threads_get_user_id(threads_token)
            th_post_id = _post_threads(post["text"], threads_token, threads_uid)
            print(f"{log_pfx} ✅ Threads投稿: {th_post_id}")
            time.sleep(3)
            th_reply_id = _post_threads(reply_text, threads_token, threads_uid,
                                        reply_to_id=th_post_id)
            print(f"{log_pfx} ✅ Threadsリプライ: {th_reply_id}")
        except Exception as e:
            print(f"{log_pfx} ⚠️ Threads投稿失敗（X投稿は成功）: {e}")

    # 状態保存
    history_entry = {
        "key":       post["key"],
        "category":  cat,
        "tweet_id":  tweet_id,
        "reply_id":  reply_id,
        "posted_at": now.isoformat(),
    }
    if th_post_id:
        history_entry["threads_post_id"]  = th_post_id
    if th_reply_id:
        history_entry["threads_reply_id"] = th_reply_id
    state["posted_keys"].append(post["key"])
    state["history"].append(history_entry)
    save_state(state)


if __name__ == "__main__":
    main()
