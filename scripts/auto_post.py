#!/usr/bin/env python3
"""
X 自動投稿スクリプト — buffer_import.csv を順番に1件ずつ投稿し、
投稿直後に自動リプライで note リンクを付ける。

使い方:
  python3 auto_post.py          # 次の1件を投稿
  python3 auto_post.py --dry-run  # 実際には投稿せず確認のみ

必要な環境変数:
  X_API_KEY
  X_API_SECRET
  X_ACCESS_TOKEN
  X_ACCESS_TOKEN_SECRET

cron 設定例（エンゲージメント上位スロットに合わせた例）:
  0 12 * * 0  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 17 * * 0  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 17 * * 1  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 20 * * 2  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
  0 20 * * 4  cd /home/kota && python3 sigma/scripts/auto_post.py >> sigma/scripts/post.log 2>&1
"""

import csv, hmac, hashlib, json, os, sys, time, uuid
import urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime

# ── パス設定 ──────────────────────────────────────────────
CSV_PATH   = Path("~/sigma/x_posts/buffer_import.csv").expanduser()
STATE_PATH = Path("~/sigma/x_posts/.post_state.json").expanduser()
LOG_PREFIX = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

# ── X API エンドポイント ───────────────────────────────────
TWEETS_URL       = "https://api.twitter.com/2/tweets"
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"

# ── OAuth 1.0a 署名（標準ライブラリのみ） ─────────────────
import base64 as _b64

def _pct(s: str) -> str:
    # RFC 3986 unreserved chars: A-Z a-z 0-9 - . _ ~
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
    # signature base string
    param_str = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(p.items()))
    base = f"{_pct(method.upper())}&{_pct(url)}&{_pct(param_str)}"
    # signing key
    key = f"{_pct(creds['api_secret'])}&{_pct(creds['access_token_secret'])}"
    sig = _b64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    p["oauth_signature"] = sig
    # Authorization header (keys unencoded, values percent-encoded)
    parts = ", ".join(f'{k}="{_pct(v)}"' for k, v in sorted(p.items()))
    return f"OAuth {parts}"


def _upload_media(img_url: str, creds: dict) -> str:
    """画像URLからダウンロードしてX Mediaにアップロード、media_id_stringを返す"""
    with urllib.request.urlopen(img_url) as resp:
        img_data = resp.read()
        content_type = resp.headers.get("Content-Type", "image/jpeg")
    # multipart/form-data で送信（bodyはOAuth署名に含めない）
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
    header = _oauth_header("POST", MEDIA_UPLOAD_URL, creds)
    req = urllib.request.Request(
        MEDIA_UPLOAD_URL,
        data=body,
        headers={
            "Authorization": header,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["media_id_string"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Media upload HTTP {e.code}: {e.read().decode()}") from e


def _post(body: dict, creds: dict, reply_to_id: str = None, media_ids: list = None) -> dict:
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    if media_ids:
        body["media"] = {"media_ids": media_ids}
    payload = json.dumps(body).encode()
    header = _oauth_header("POST", TWEETS_URL, creds)
    req = urllib.request.Request(
        TWEETS_URL,
        data=payload,
        headers={
            "Authorization": header,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {err}") from e


# ── 状態管理 ───────────────────────────────────────────────
def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"next_index": 0, "posted": []}

def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── メイン ─────────────────────────────────────────────────
def main():
    dry_run = "--dry-run" in sys.argv

    # 環境変数チェック
    creds = {
        "api_key":             os.environ.get("X_API_KEY", ""),
        "api_secret":          os.environ.get("X_API_SECRET", ""),
        "access_token":        os.environ.get("X_ACCESS_TOKEN", ""),
        "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET", ""),
    }
    missing = [k for k, v in creds.items() if not v]
    if missing and not dry_run:
        sys.exit(f"❌ 環境変数が未設定: {', '.join(missing)}")

    # CSV 読み込み
    if not CSV_PATH.exists():
        sys.exit(f"❌ CSV が見つかりません: {CSV_PATH}")
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    state = load_state()
    idx = state["next_index"]

    if idx >= len(rows):
        print(f"{LOG_PREFIX} ✅ 全投稿完了（{len(rows)}件）")
        return

    row = rows[idx]
    text       = row["text"].strip()
    reply_url  = row["reply"].strip()
    orig_date  = row["date"].strip()
    media_urls = [u for u in row.get("media_urls", "").split("|") if u.strip()]

    print(f"{LOG_PREFIX} [{idx+1}/{len(rows)}] 元日時: {orig_date}")
    print(f"{LOG_PREFIX} 本文: {text[:80]}{'...' if len(text)>80 else ''}")
    print(f"{LOG_PREFIX} 画像: {len(media_urls)}枚")
    print(f"{LOG_PREFIX} リプライURL: {reply_url}")

    if dry_run:
        for u in media_urls:
            print(f"{LOG_PREFIX} [DRY RUN] 画像: {u}")
        print(f"{LOG_PREFIX} [DRY RUN] 投稿はスキップされました")
        print(f"{LOG_PREFIX} [DRY RUN] 次回のインデックス: {idx+1}")
        return

    # 画像アップロード（最大4枚）
    media_ids = []
    for img_url in media_urls[:4]:
        media_id = _upload_media(img_url, creds)
        media_ids.append(media_id)
        print(f"{LOG_PREFIX} 画像アップ完了: {img_url.split('/')[-1]} → {media_id}")

    # 本文投稿
    result = _post({"text": text}, creds, media_ids=media_ids or None)
    tweet_id = result["data"]["id"]
    print(f"{LOG_PREFIX} ✅ 投稿完了: https://x.com/i/web/status/{tweet_id}")

    # URLをタイトル付きリプライ文に変換
    REPLY_TEXTS = {
        "https://note.com/puregrinding1/n/n4eabc4c9b556":
            "「爆速でモテる男磨きのやり方」非モテが恋愛の土台を築き上げる男磨きby元自閉症チー牛が解説\nhttps://note.com/puregrinding1/n/n4eabc4c9b556",
        "https://note.com/puregrinding1/n/n75b3881b4678":
            "【スマホ中毒者向け】\"デジタル・ドーパミン廃人\"だった私がスクリーンタイム10時間→1時間で人生を奪還した思考法\nhttps://note.com/puregrinding1/n/n75b3881b4678",
        "https://note.com/puregrinding1/n/na60936ff3ad1":
            "【ヒョロガリ向け】最短で「モテボディ」を獲得するための食事プログラム｜by元体重39kgのヒョロガリが解説。\nhttps://note.com/puregrinding1/n/na60936ff3ad1",
    }
    reply_text = REPLY_TEXTS.get(reply_url, reply_url)

    # リプライ投稿（少し待ってから）
    time.sleep(3)
    r_result = _post({"text": reply_text}, creds, reply_to_id=tweet_id)
    reply_id = r_result["data"]["id"]
    print(f"{LOG_PREFIX} ✅ リプライ完了: https://x.com/i/web/status/{reply_id}")

    # 状態保存
    state["next_index"] = idx + 1
    state.setdefault("posted", []).append({
        "index":    idx,
        "tweet_id": tweet_id,
        "reply_id": reply_id,
        "posted_at": datetime.now().isoformat(),
        "orig_date": orig_date,
    })
    save_state(state)
    print(f"{LOG_PREFIX} 残り: {len(rows) - idx - 1}件")


if __name__ == "__main__":
    main()
