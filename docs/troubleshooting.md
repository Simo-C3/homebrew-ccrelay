# トラブルシューティング

まず状態と診断結果を確認します。

```bash
ccrelay --version
ccrelay service status
ccrelay doctor
ccrelay service logs --lines 200
```

## 認証情報が見つからない

`doctor` で `Copilot OAuth cache` が警告になる場合は、認証をやり直します。

```bash
ccrelay auth
ccrelay doctor
```

## サービスが起動しない

起動待ち時間を延ばして再起動し、ログを確認します。

```bash
ccrelay service restart --timeout 120
ccrelay service logs --lines 200
```

既定ポート `4141` が他のプロセスに使われている場合は、別のポートへ変更します。

```bash
ccrelay service restart --port 4142
```

Codex App 連携中にポートを変えた場合は、Codex App も再起動してください。

## Codex App に切り替えが反映されない

サービスと設定の状態を確認します。

```bash
ccrelay service status
ccrelay codex-app status
```

サービスが停止していれば `ccrelay service start` を実行します。設定が有効なら Codex App を
完全に終了してから再起動してください。

設定を元に戻す場合は、変更内容を確認してから無効化します。

```bash
ccrelay codex-app disable --dry-run
ccrelay codex-app disable
```

ccrelay を更新した直後であれば、管理設定を再適用してから Codex App を再起動します。

```bash
ccrelay codex-app enable
```

これにより、旧版の `experimental_bearer_token` を使う未変更の設定も新しい
`X-CCRelay-Key` 形式へ移行されます。

## 組み込み imagegen が表示されない、または認証エラーになる

`imagegen` は GitHub Copilot ではなく、Codex でログイン中の ChatGPT 画像バックエンドを
使います。`OPENAI_API_KEY` は不要です。次を確認してください。

- Codex が ChatGPT アカウントでログイン済みである
- ChatGPT Free プランではない（Codex 側で Free プランの画像生成は無効になります）
- Codex で画像入力に対応するモデルを選択している
- `ccrelay codex-app enable` の実行後に Codex を完全に再起動した
- 手動設定では `requires_openai_auth = true` と `X-CCRelay-Key` を設定した

`ChatGPT authentication is required for imagegen` と表示される場合は、ローカルキーまたは
Codex の ChatGPT 認証が画像リクエストに付いていません。管理設定を再適用して Codex へ
再ログインし、Codex を再起動してください。

## 詳細ログを確認したい

前景起動ではログレベルと出力先を指定できます。

```bash
ccrelay service stop
ccrelay proxy run --log-level debug --verbose --log-file ./ccrelay.log
```

終了後、通常運用へ戻すには `ccrelay service start` を実行します。ログは一般的な認証情報を
マスクしますが、共有前に内容を確認してください。

## GitHub への接続を確認したい

```bash
ccrelay doctor --online --timeout 10
```

この確認は GitHub のデバイス認証エンドポイントへ接続するだけで、認証やモデル呼び出しは
行いません。

## 解決しない場合

Issue には次の情報を添えてください。プロキシキー、OAuth 情報、Codex 設定ファイルの全文は
含めないでください。

- `ccrelay --version` の結果
- macOS と CPU アーキテクチャのバージョン
- 実行したコマンドとエラーメッセージ
- 秘密情報を除いた関連ログ
