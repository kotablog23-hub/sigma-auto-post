#!/usr/bin/env python3
"""
今日の指定時間にX投稿するスクリプト
~/sigma/.env から認証情報を読み込み、指定時刻まで待機して順番に投稿する。
"""
import base64, hashlib, hmac, json, os, time, uuid
import urllib.parse, urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ── .env 読み込み ──────────────────────────────────────────
def load_env(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

load_env(Path("~/sigma/.env").expanduser())

# ── 投稿リスト（時刻はローカル時間 HH:MM） ────────────────
POSTS = [
    {
        "time": "18:07",
        "text": (
            "「ジムに行く金がない」とか言ってる奴マジ？\n\n"
            "俺が貧乏大学生の時は\n\n"
            "・図書館で冷暖房節約\n"
            "・自販機を使うなど論外。水筒持参。\n"
            "・トイレでションベンしても流さない。\n\n"
            "死ぬほどケチってた。\n\n"
            "本気で身体を変えたいと思ってるなら無駄遣いは最小限にした方がいい。"
        ),
    },
    {
        "time": "18:43",
        "text": (
            "臭い人がやっている悪癖\n\n"
            "・飲酒\n・口呼吸\n・運動不足\n・肥満を放置\n"
            "・香水で誤魔化す\n・朝シャンしない\n・腸内環境の破壊\n\n"
            "食事を整え、運動で汗をかき、一日の終わりと始まりに綺麗に流す。\n"
            "これだけで匂い対策はできる。"
        ),
    },
    {
        "time": "19:21",
        "text": (
            "生涯童貞な男の特徴\n\n"
            "・無害\n・奥手\n・メガネ\n・無表情\n"
            "・いい人\n・ヒョロガリ\n・自己主張しない\n\n"
            "極論\n"
            "イケメンでも奥手 → 童貞\n"
            "ブサイクでも行動 → 非童貞\n\n"
            "外見的魅力と行動はセットじゃないと無意味。"
        ),
    },
    {
        "time": "20:17",
        "text": (
            "筋トレ動画で「簡単」「夏までに」「科学的な」のワードが出たら、一回引きで見た方がいい。\n\n"
            "メディアを精査して正しく鍛える。\n"
            "これが一番難しい。"
        ),
    },
    {
        "time": "21:38",
        "text": (
            "テストステロンを上げる習慣\n\n"
            "・肉食\n・Big３\n・睡眠7時間以上\n"
            "・勝負ごとに勝つ\n・自分との約束を守る\n"
            "・ジム週3以上\n・美女と話す\n\n"
            "勝癖がついている男は全員テストステロンが高い。"
        ),
    },
]

# ── noteリンク自動分類 ─────────────────────────────────────
LINKS = {
    "motemigaki": "https://note.com/puregrinding1/n/n4eabc4c9b556",
    "shijaku":    "https://note.com/puregrinding1/n/n75b3881b4678",
    "zoryo":      "https://note.com/puregrinding1/n/na60936ff3ad1",
}
REPLY_TEXTS = {
    "motemigaki": "「爆速でモテる男磨きのやり方」非モテが恋愛の土台を築き上げる男磨きby元自閉症チー牛が解説\nhttps://note.com/puregrinding1/n/n4eabc4c9b556",
    "shijaku":    "【スマホ中毒者向け】\"デジタル・ドーパミン廃人\"だった私がスクリーンタイム10時間→1時間で人生を奪還した思考法\nhttps://note.com/puregrinding1/n/n75b3881b4678",
    "zoryo":      "【ヒョロガリ向け】最短で「モテボディ」を獲得するための食事プログラム｜by元体重39kgのヒョロガリが解説。\nhttps://note.com/puregrinding1/n/na60936ff3ad1",
}
KW = {
    "motemigaki": ["モテ","恋愛","外見","見た目","コミュ","男磨き","清潔感","服装","ファッション",
                   "髪","女性","女子","チー牛","非モテ","デート","彼女","自己開示","会話","話し方",
                   "印象","魅力","好感度","自閉症","陰キャ","童貞","匂い","臭い","清潔"],
    "shijaku":    ["スマホ","ドーパミン","集中","スクリーンタイム","デジタル","SNS","YouTube",
                   "ショート","依存","中毒","通知","ポルノ","スクロール","刺激","快楽","誘惑",
                   "スマホ断ち","脳","報酬","習慣","意志力","テストステロン"],
    "zoryo":      ["筋トレ","トレーニング","ジム","食事","プロテイン","カロリー","増量","体型",
                   "筋肉","体重","バルク","タンパク質","ヒョロガリ","鍛え","筋量","食べ","肉",
                   "炭水化物","Big３","ベンチ","スクワット","デッドリフト"],
}

def classify(text):
    scores = {cat: sum(1 for w in words if w in text) for cat, words in KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "motemigaki"

# ── OAuth 1.0a ─────────────────────────────────────────────
TWEETS_URL = "https://api.twitter.com/2/tweets"

def _pct(s):
    return urllib.parse.quote(str(s), safe="-._~")

def _oauth_header(method, url, creds):
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
    sig  = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    p["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{k}="{_pct(v)}"' for k, v in sorted(p.items()))

def post_tweet(text, creds, reply_to_id=None):
    body = {"text": text}
    if reply_to_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_id}
    payload = json.dumps(body).encode()
    req = urllib.request.Request(
        TWEETS_URL,
        data=payload,
        headers={
            "Authorization": _oauth_header("POST", TWEETS_URL, creds),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["data"]["id"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e

# ── メイン ─────────────────────────────────────────────────
def main():
    creds = {
        "api_key":             os.environ["X_API_KEY"],
        "api_secret":          os.environ["X_API_SECRET"],
        "access_token":        os.environ["X_ACCESS_TOKEN"],
        "access_token_secret": os.environ["X_ACCESS_TOKEN_SECRET"],
    }

    log = Path("~/sigma/scripts/scheduled_today.log").expanduser()

    def lg(msg):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    lg(f"スクリプト開始 — {len(POSTS)}件を予約")

    today = datetime.now().date()
    for i, post in enumerate(POSTS, 1):
        h, m = map(int, post["time"].split(":"))
        target = datetime(today.year, today.month, today.day, h, m, 0)
        now = datetime.now()
        wait = (target - now).total_seconds()

        if wait < -60:
            lg(f"[{i}/5] {post['time']} はすでに過ぎているためスキップ")
            continue

        if wait > 0:
            lg(f"[{i}/5] {post['time']} まで {int(wait//60)}分{int(wait%60)}秒 待機...")
            time.sleep(wait)

        text = post["text"]
        cat  = classify(text)
        reply_text = REPLY_TEXTS[cat]

        lg(f"[{i}/5] 投稿開始: {post['time']} — カテゴリ={cat}")
        try:
            tweet_id = post_tweet(text, creds)
            lg(f"[{i}/5] ✅ 投稿完了: https://x.com/i/web/status/{tweet_id}")
            time.sleep(3)
            reply_id = post_tweet(reply_text, creds, reply_to_id=tweet_id)
            lg(f"[{i}/5] ✅ リプライ完了: https://x.com/i/web/status/{reply_id}")
        except Exception as e:
            lg(f"[{i}/5] ❌ エラー: {e}")

    lg("全投稿完了")

if __name__ == "__main__":
    main()
