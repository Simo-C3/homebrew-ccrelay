# リリース戦略

`ccrelay` は `main` から GitHub Release と Homebrew Bottle を公開する。
小さく安全にリリースし、問題があればタグを動かさず修正版を追加する。

## 基本方針

- `main` は常にリリース可能な状態を保つ。
- バージョンは [Semantic Versioning](https://semver.org/lang/ja/) に従う。
  - PATCH: 後方互換なバグ修正
  - MINOR: 後方互換な機能追加。`0.x` の破壊的変更も MINOR とする
  - MAJOR: `1.0.0` 以降の破壊的変更
- 通常の変更は短命なブランチで行い、テスト済みの変更だけを `main` に入れる。
- リリースタグ `vX.Y.Z` と公開済み成果物は変更しない。
- GitHub の自動生成リリースノートを変更履歴とし、コミット件名は変更内容が分かるように書く。

## リリースの流れ

```text
変更を main に統合
  -> リリース準備 PR（version・Formula・source SHA）
  -> vX.Y.Z タグ
  -> GitHub Release / source archive
  -> Homebrew Bottle
  -> インストール確認
```

### 1. リリースを準備する

1. リリースする変更と次のバージョンを決める。
2. `pyproject.toml` と `src/ccrelay/__init__.py` のバージョンを更新し、`uv lock` で
   `uv.lock` を同期する。
3. `Formula/ccrelay.rb` の URL を新しいタグへ更新し、古い `bottle` ブロックを削除する。
4. **クリーンな checkout** で sdist を生成し、その SHA-256 を Formula に設定する。
5. 次のゲートをすべて通し、リリース準備 PR を `main` にマージする。

```bash
uv sync --frozen
uv run ruff check .
uv run mypy
uv run pytest --cov=ccrelay
uv build --sdist
shasum -a 256 dist/ccrelay-X.Y.Z.tar.gz
brew audit --formula Formula/ccrelay.rb
```

作業ツリーの未コミット変更を sdist に混ぜない。SHA は一時的な clone または clean な
worktree で計算し、同じ成果物をローカルでも展開して内容を確認する。

### 2. 公開する

`main` のリリース準備コミットに注釈付きタグを作成して push する。

```bash
git tag -a vX.Y.Z -m "ccrelay X.Y.Z"
git push origin main vX.Y.Z
```

GitHub Actions の **Publish Homebrew bottle** を `tag=vX.Y.Z` で実行する。workflow は次を行う。

1. タグから source archive を作り、Formula の SHA と一致することを検証する。
2. GitHub Release を作成し、source archive を添付する。
3. Apple Silicon macOS 向け Bottle をビルドしてテストする。
4. Bottle を Release に添付し、Formula の `bottle` ブロックを `main` に反映する。

### 3. 公開後に確認する

workflow の成功だけで完了とせず、利用者と同じ経路で確認する。

```bash
brew update
brew upgrade ccrelay
ccrelay version
ccrelay doctor
brew test Simo-C3/ccrelay/ccrelay
```

GitHub Release に source archive と Bottle があり、Formula が新しいバージョンと Bottle を
参照していることも確認する。

## 失敗時の対応

- Bottle のビルドやアップロードだけが失敗した場合は、同じタグで workflow を再実行する。
- タグの内容や source archive に問題がある場合は、タグを付け替えず PATCH バージョンで修正する。
- 利用者への影響が大きい場合は、問題をリリースノートに追記し、修正版を優先して公開する。
- 原因と再発防止策は PR または Issue に残す。
