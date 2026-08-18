# はじめに

`ccrelay` は、Codex の通常のモデルリクエストをローカルの LiteLLM 経由で GitHub Copilot
Chat API に転送します。組み込みの `imagegen` が使う画像リクエストだけは、Codex でログイン
している ChatGPT の画像バックエンドへ転送します。ゲートウェイは `127.0.0.1` のみで
待ち受けます。

## 前提条件

- macOS
- Homebrew
- GitHub Copilot を利用できる GitHub アカウント
- Codex CLI または Codex App
- Codex での ChatGPT ログイン（組み込み `imagegen` には ChatGPT Free 以外のプランが必要）

画像生成に `OPENAI_API_KEY` は不要です。ChatGPT の認証情報は画像経路だけで使われ、LiteLLM や
GitHub Copilot には転送されません。

利用前に GitHub・所属組織の規約を確認してください。このプロジェクトは実験的な実装であり、
互換性、課金経路、アカウントへの影響を保証しません。

## 1. インストール

```bash
brew install Simo-C3/ccrelay/ccrelay
ccrelay --version
ccrelay doctor
```

`doctor` はローカル環境だけを検査し、モデルへのリクエストは送りません。

## 2. GitHub Copilot の認証

```bash
ccrelay auth
```

表示されるデバイスフローに従って認証します。認証情報は OS 標準のユーザー状態
ディレクトリ内に、ユーザーだけがアクセスできる権限で保存されます。

## 3. プロキシの起動

ログイン時に自動起動するサービスとして開始します。

```bash
ccrelay service start
ccrelay service status
```

既定の接続先は `http://127.0.0.1:4141` です。自動起動が不要な場合は
`ccrelay service run`、前景で確認したい場合は `ccrelay proxy run` を使います。

## 4. Codex App との連携

書き換え内容を確認してから有効にできます。

```bash
ccrelay codex-app enable --dry-run
ccrelay codex-app enable
ccrelay codex-app status
```

有効化後に Codex App を再起動してください。設定先は `$CODEX_HOME/config.toml`、
`CODEX_HOME` が未設定なら `~/.codex/config.toml` です。既存のモデル設定や無関係な設定は
保持されます。旧版の `experimental_bearer_token` 形式を利用している場合も、もう一度
`ccrelay codex-app enable` を実行すると新しい形式へ移行されます。

元のプロバイダーに戻す場合も、先に変更内容を確認できます。

```bash
ccrelay codex-app disable --dry-run
ccrelay codex-app disable
```

手動で Codex CLI のプロバイダーを設定する場合は、稼働中のプロキシから接続情報を取得します。

```bash
eval "$(ccrelay proxy setenv)"
```

Codex CLI 用の手動設定例は次のとおりです。

```toml
model_provider = "ccrelay"

[model_providers.ccrelay]
name = "ccrelay GitHub Copilot"
base_url = "http://127.0.0.1:4141/v1"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
env_http_headers = { X-CCRelay-Key = "CCRELAY_PROXY_KEY" }
```

出力されるローカルキーは秘密情報として扱ってください。`requires_openai_auth` を有効にすることで
Codex の ChatGPT ログインが維持され、組み込み `imagegen` が画像経路を利用できます。

## 5. 経路の確認

稼働しているだけでは、意図した課金経路を通ったことは確認できません。通常利用の前に、小さな
プロンプトを1回実行し、次を確認してください。

1. 通常のテキストリクエストで GitHub Copilot の利用量が想定どおり増えた。
2. OpenAI API の利用量が増えていない。
3. 読み取り、ファイル編集、シェル実行が正常に動く。
4. `imagegen` を使う場合は、画像生成が ChatGPT アカウント側で扱われ、GitHub Copilot や
   OpenAI API キー経由になっていない。

不明点がある場合は利用を止め、規約、組織ポリシー、課金状況を確認してください。

## 日常的な操作

```bash
ccrelay service status
ccrelay service logs --lines 200
ccrelay service restart
ccrelay service stop
```

詳しい引数は [コマンドリファレンス](command-reference.md)、問題がある場合は
[トラブルシューティング](troubleshooting.md) を参照してください。
