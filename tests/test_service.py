from __future__ import annotations

import json
import stat
import subprocess

import pytest

from ccrelay.service import load_service_settings, run_brew_service


def test_service_settings_are_persistent_and_private(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CCRELAY_CACHE_DIR", str(tmp_path / "cache"))

    initial = load_service_settings(port=4321)
    updated = load_service_settings()

    assert updated.port == 4321
    assert updated.proxy_key == initial.proxy_key
    settings_path = tmp_path / "state" / "service" / "settings.json"
    assert json.loads(settings_path.read_text())["version"] == 2
    assert "model" not in json.loads(settings_path.read_text())
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600


def test_invalid_saved_service_settings_fail(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CCRELAY_CACHE_DIR", str(tmp_path / "cache"))
    service_dir = tmp_path / "state" / "service"
    service_dir.mkdir(parents=True)
    (service_dir / "settings.json").write_text('{"version": 1, "port": 0}')

    with pytest.raises(RuntimeError, match="Invalid 'port'"):
        load_service_settings()


def test_legacy_service_settings_drop_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CCRELAY_CACHE_DIR", str(tmp_path / "cache"))
    service_dir = tmp_path / "state" / "service"
    service_dir.mkdir(parents=True)
    settings_path = service_dir / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "version": 1,
                "model": "gpt-old",
                "port": 4321,
                "proxy_key": "sk-ccrelay-existing",
            }
        )
    )

    settings = load_service_settings()

    assert settings.port == 4321
    assert settings.proxy_key == "sk-ccrelay-existing"
    assert json.loads(settings_path.read_text()) == {
        "version": 2,
        "port": 4321,
        "proxy_key": "sk-ccrelay-existing",
    }


def test_brew_service_command(monkeypatch) -> None:
    monkeypatch.setenv("CCRELAY_BREW_BIN", "/opt/homebrew/bin/brew")
    monkeypatch.setenv("CCRELAY_BREW_FORMULA", "Simo-C3/ccrelay/ccrelay")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="started\n", stderr="")

    monkeypatch.setattr("ccrelay.service.subprocess.run", fake_run)

    assert run_brew_service("start") == "started"
    assert calls == [
        ["/opt/homebrew/bin/brew", "services", "start", "Simo-C3/ccrelay/ccrelay"]
    ]


def test_brew_service_failure_is_reported(monkeypatch) -> None:
    monkeypatch.setenv("CCRELAY_BREW_BIN", "/opt/homebrew/bin/brew")

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="service failed\n")

    monkeypatch.setattr("ccrelay.service.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="service failed"):
        run_brew_service("start")
