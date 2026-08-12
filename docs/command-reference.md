# コマンドリファレンス

すべての階層で `--help` を利用できます。例: `ccrelay service start --help`。

## 基本コマンド

| コマンド | 説明 | 主なオプション |
| --- | --- | --- |
| `ccrelay --version` | バージョンを表示して終了 | `-V` |
| `ccrelay --help` | トップレベルのヘルプを表示 | なし |
| `ccrelay --install-completion` | 現在のシェルへ補完をインストール | なし |
| `ccrelay --show-completion` | シェル補完スクリプトを表示 | なし |
| `ccrelay version` | バージョンを表示 | なし |
| `ccrelay auth` | GitHub Copilot の OAuth デバイス認証 | なし |
| `ccrelay doctor` | モデルを呼ばずに環境を診断 | `--json`, `--strict`, `--online`, `--timeout SECONDS` |

`doctor --online` は GitHub への接続だけを追加確認します。認証やモデル呼び出しは行いません。
`--strict` を付けると、警告が1件でもあれば終了ステータスが非ゼロになります。オンライン確認の
既定タイムアウトは5秒です。

## プロキシ

### `ccrelay proxy run`

前景でプロキシを起動します。従来の `ccrelay proxy` も同じ動作です。

| オプション | 説明 | 既定値 |
| --- | --- | --- |
| `--port PORT` | 待受ポート（1–65535） | 保存済みの値、初回は `4141` |
| `--verbose`, `-v` | 秘密情報をマスクしたログを標準エラーへ表示 | 無効 |
| `--startup-timeout SECONDS` | LiteLLM の起動待ち時間 | `90` |
| `--log-level LEVEL` | `error`, `warning`, `info`, `debug` | `error` |
| `--log-file PATH` | マスク済みログの出力先 | サービス用ログ |

### `ccrelay proxy setenv`

稼働中のプロキシへの接続情報を出力します。

| オプション | 説明 | 既定値 |
| --- | --- | --- |
| `--shell SHELL` | `auto`, `bash`, `zsh`, `fish` の形式で出力 | `auto` |
| `--json` | JSON 形式で出力 | 無効 |

出力にはローカルのプロキシキーが含まれます。ログや共有ファイルへ保存しないでください。

## Homebrew サービス

| コマンド | 説明 |
| --- | --- |
| `ccrelay service run` | ログイン時の自動起動を登録せず、バックグラウンドで起動 |
| `ccrelay service start` | バックグラウンドで起動し、ログイン時の自動起動を登録 |
| `ccrelay service restart` | サービスを再起動して設定変更を反映 |
| `ccrelay service stop` | サービスを停止 |
| `ccrelay service status` | 接続先とヘルスチェック結果を表示 |
| `ccrelay service logs` | マスク済みログを表示 |

`run`、`start`、`restart` では次のオプションを利用できます。

| オプション | 説明 | 既定値 |
| --- | --- | --- |
| `--port PORT` | 待受ポート（1–65535） | 保存済みの値、初回は `4141` |
| `--wait` / `--no-wait` | 正常起動を待つか選択 | `--wait` |
| `--timeout SECONDS` | 正常起動の待ち時間 | `90` |

ポート変更は `service restart --port PORT` で反映します。Codex App 連携中はプロバイダー
URL も更新されるため、実行後に Codex App を再起動してください。

`status` のオプション:

- `--json`: 状態、URL、ポート、ログパスを JSON で出力
- `--quiet`, `-q`: 何も出力せず、終了ステータスだけを返す

`logs` のオプション:

- `--lines N`, `-n N`: 既存ログの表示行数（既定値: `100`）
- `--follow`, `-f`: 新しいログを継続表示

## Codex App

| コマンド | 説明 | オプション |
| --- | --- | --- |
| `ccrelay codex-app enable` | Codex のプロバイダーを `ccrelay` に切り替え | `--dry-run` |
| `ccrelay codex-app disable` | 切り替え前のプロバイダーへ戻す | `--dry-run` |
| `ccrelay codex-app status` | 現在の選択、モデル、設定ファイルを表示 | `--json` |

`--dry-run` はファイルを書き換えず、対象と変更内容だけを表示します。`disable` は ccrelay が
変更した値だけを戻し、有効化後に加えられた利用者の変更を可能な範囲で保持します。

## 終了ステータス

- `0`: 成功。`service status` ではプロキシが応答中
- `1`: コマンド失敗。`service status` では停止中または応答なし

自動化では `service status --quiet` または各コマンドの `--json` を利用してください。

## 環境変数

通常利用では設定不要です。テストや独自配置でのみ使用してください。

| 変数 | 用途 |
| --- | --- |
| `CODEX_HOME` | Codex 設定ディレクトリを変更 |
| `CCRELAY_STATE_DIR` | 認証情報とサービス設定の保存先を変更 |
| `CCRELAY_CACHE_DIR` | ログなどのキャッシュ保存先を変更 |
| `CCRELAY_LITELLM_BIN` | LiteLLM 実行ファイルを指定 |
| `CCRELAY_BREW_BIN` | Homebrew 実行ファイルを指定 |

`CCRELAY_PROXY_KEY` は `proxy setenv` が出力するローカル認証キーです。公開しないでください。
