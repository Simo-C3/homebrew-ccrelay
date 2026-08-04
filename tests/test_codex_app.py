from __future__ import annotations

import json
import stat

import pytest
from tomlkit import parse

from ccrelay.codex_app import disable_codex_app, enable_codex_app, get_codex_app_status
from ccrelay.settings import RuntimeSettings


def settings(tmp_path) -> RuntimeSettings:
    return RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-secret",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )


def test_enable_and_disable_restore_codex_config(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    config_path = codex_home / "config.toml"
    codex_home.mkdir()
    original = '# keep this comment\nmodel = "original"\nmodel_provider = "openai"\n'
    config_path.write_text(original)
    config_path.chmod(0o644)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))

    enabled = enable_codex_app(settings(tmp_path))

    document = parse(config_path.read_text())
    provider = document["model_providers"]["ccrelay"]
    assert enabled.enabled
    assert document["model"] == "original"
    assert document["model_provider"] == "ccrelay"
    assert provider["base_url"] == "http://127.0.0.1:4141/v1"
    assert provider["experimental_bearer_token"] == "sk-ccrelay-secret"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert "# keep this comment" in config_path.read_text()

    disabled = disable_codex_app()

    assert not disabled.enabled
    assert config_path.read_text() == original
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o644


def test_disable_preserves_unrelated_changes(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    config_path = codex_home / "config.toml"
    document = parse(config_path.read_text())
    document["sandbox_mode"] = "workspace-write"
    config_path.write_text(document.as_string())

    disable_codex_app()

    restored = parse(config_path.read_text())
    assert restored["sandbox_mode"] == "workspace-write"
    assert "model" not in restored
    assert "model_provider" not in restored
    assert "model_providers" not in restored


def test_disable_preserves_model_selected_after_enable(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model = "before"\nmodel_provider = "openai"\n')
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    document = parse(config_path.read_text())
    document["model"] = "selected-after-enable"
    config_path.write_text(document.as_string())

    disable_codex_app()

    restored = parse(config_path.read_text())
    assert restored["model"] == "selected-after-enable"
    assert restored["model_provider"] == "openai"


def test_disable_preserves_changed_model_provider(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    config_path = codex_home / "config.toml"
    document = parse(config_path.read_text())
    document["model_provider"] = "other"
    config_path.write_text(document.as_string())

    disabled = disable_codex_app()
    restored = parse(config_path.read_text())

    assert not disabled.enabled
    assert disabled.preserved_changes == ("model_provider",)
    assert restored["model_provider"] == "other"
    assert "model_providers" not in restored


def test_disable_preserves_changed_provider_table(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model_provider = "openai"\n')
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    document = parse(config_path.read_text())
    provider = document["model_providers"]["ccrelay"]
    provider["base_url"] = "http://127.0.0.1:9999/v1"
    provider.add("custom_setting", True)
    config_path.write_text(document.as_string())

    disabled = disable_codex_app()
    restored = parse(config_path.read_text())

    assert not disabled.enabled
    assert disabled.preserved_changes == ("model_providers.ccrelay",)
    assert restored["model_provider"] == "openai"
    assert restored["model_providers"]["ccrelay"]["base_url"].endswith(":9999/v1")
    assert restored["model_providers"]["ccrelay"]["custom_setting"] is True
    assert "experimental_bearer_token" not in restored["model_providers"]["ccrelay"]
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o644


def test_disable_keeps_private_mode_for_changed_token(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model_provider = "openai"\n')
    config_path.chmod(0o644)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    document = parse(config_path.read_text())
    document["model_providers"]["ccrelay"]["experimental_bearer_token"] = "user-token"
    config_path.write_text(document.as_string())

    disabled = disable_codex_app()
    restored = parse(config_path.read_text())

    assert restored["model_providers"]["ccrelay"]["experimental_bearer_token"] == "user-token"
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600
    assert disabled.preserved_changes == (
        "model_providers.ccrelay",
        "file permissions (restricted to protect the preserved token)",
    )


def test_enable_refuses_to_overwrite_changed_provider_table(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    config_path = codex_home / "config.toml"
    document = parse(config_path.read_text())
    document["model_providers"]["ccrelay"]["base_url"] = "http://custom.invalid/v1"
    config_path.write_text(document.as_string())

    with pytest.raises(RuntimeError, match="model_providers.ccrelay"):
        enable_codex_app(settings(tmp_path))

    unchanged = parse(config_path.read_text())
    assert unchanged["model_providers"]["ccrelay"]["base_url"] == "http://custom.invalid/v1"


def test_enable_updates_an_unchanged_managed_provider(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    updated_settings = RuntimeSettings(
        port=4242,
        proxy_key="sk-ccrelay-updated",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )

    enable_codex_app(updated_settings)

    document = parse((codex_home / "config.toml").read_text())
    provider = document["model_providers"]["ccrelay"]
    assert provider["base_url"] == "http://127.0.0.1:4242/v1"
    assert provider["experimental_bearer_token"] == "sk-ccrelay-updated"


def test_disable_preserves_changed_file_permissions(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text('model_provider = "openai"\n')
    config_path.chmod(0o644)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    config_path.chmod(0o640)

    disabled = disable_codex_app()

    assert disabled.preserved_changes == ("file permissions",)
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o640


def test_disable_preserves_deleted_config_file(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    enable_codex_app(settings(tmp_path))
    config_path = codex_home / "config.toml"
    config_path.unlink()

    disabled = disable_codex_app()

    assert disabled.preserved_changes == ("config file removal",)
    assert not config_path.exists()


def test_enable_refuses_existing_ccrelay_provider(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text("[model_providers.ccrelay]\nname = 'custom'\n")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))

    with pytest.raises(RuntimeError, match="not managed by ccrelay"):
        enable_codex_app(settings(tmp_path))

    assert not get_codex_app_status().enabled


def test_enable_migrates_legacy_backup(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        'model = "gpt-forced"\n'
        'model_provider = "ccrelay"\n'
        "[model_providers.ccrelay]\n"
        'name = "ccrelay GitHub Copilot"\n'
        'base_url = "http://127.0.0.1:4141/v1"\n'
        'experimental_bearer_token = "sk-ccrelay-secret"\n'
        'wire_api = "responses"\n'
    )
    state_dir = tmp_path / "state"
    backup_path = state_dir / "service" / "codex-app-backup.json"
    backup_path.parent.mkdir(parents=True)
    backup_path.write_text(
        json.dumps(
            {
                "version": 1,
                "config_path": str(config_path),
                "config_existed": True,
                "config_mode": 0o600,
                "trailing_newlines": 1,
                "model": {"present": True, "value": "gpt-selected-in-codex"},
                "model_provider": {"present": True, "value": "openai"},
            }
        )
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(state_dir))

    enable_codex_app(settings(tmp_path))

    document = parse(config_path.read_text())
    backup = json.loads(backup_path.read_text())
    assert document["model"] == "gpt-selected-in-codex"
    assert backup["version"] == 3
    assert "model" not in backup
    assert backup["applied"]["model_provider"] == "ccrelay"
    assert "sk-ccrelay-secret" not in backup_path.read_text()
