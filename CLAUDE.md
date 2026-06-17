# 事業概要
- X（旧Twitter）アカウント @puregrinding23 でシグマ系・自己啓発コンテンツを自動投稿
- ターゲット：20代男性
- メインツール：GitHub Actions + auto_post.py + posts_categorized.xlsx
- リポジトリ：~/sigma（GitHub: kotablog23-hub/sigma-auto-post、private）

# 投稿システム仕様
- 週35投稿スケジュール（日:7, 月:6, 火〜木:5, 金:5, 土:2）
- カテゴリ分類：morning / lunch / night / sunday / friday / summer / spring / exam / normal
- normalカテゴリのリプには固定URL：https://x.com/puregrinding23/status/2058145954361123021
- 状態管理：.smart_post_state.json
- 投稿開始位置：2026-03-08以降

# 部署構成
- マーケ部門
- コンテンツ制作・編集部
- ツール管理・開発部門（バックエンド含む）
- 経理部門（準備中）

# 禁止事項（必ず守ること）
- タスクが完了していないのに完了と宣言しない
- 手動作業を提案しない。自動化で解決する
- ユーザーが説明していないことを勝手に補完して結論を出さない
- 同じミスを二度しない（下記ミス記録を参照）

# ミス記録
- tweets.jsアーカイブの「…」問題：アーカイブ側のバグ。X APIで正しい全文を取得して上書きで解決済み（216件修正）
- GitHub ActionsへのPAT：repoスコープだけでなくworkflowスコープも必須
- .envファイルは.gitignoreに追加済み。コミットしない
- GitHub Actionsが動いている間にローカルで変更する場合、必ずgit pullしてからpush

# 作業ルール
- データの問題はClaudeが自分でファイルを調べる（ユーザーに説明させない）
- 不明点はユーザーに聞く前にファイルやAPIで確認する
- pushする前は必ずgit pull
