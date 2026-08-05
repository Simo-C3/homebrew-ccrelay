from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

from typer.testing import CliRunner

from ccrelay import __version__
from ccrelay.cli import app
from ccrelay.diagnostics import Check
from ccrelay.settings import RuntimeSettings

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"ccrelay {__version__}" in result.stdout


def test_doctor_fails_when_litellm_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "ccrelay.cli.collect_checks",
        lambda: [
            Check("LiteLLM", False, "missing"),
        ],
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "[WARN] LiteLLM: missing" in result.stdout


def test_cli_import_does_not_eagerly_import_litellm() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ccrelay.cli; assert 'litellm' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_service_start_does_not_restart_running_service(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    actions: list[str] = []
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda **_kwargs: runtime)
    monkeypatch.setattr(
        "ccrelay.cli.get_codex_app_status",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr(
        "ccrelay.cli.run_brew_service",
        lambda action: actions.append(action) or "ok",
    )
    monkeypatch.setattr("ccrelay.cli.wait_for_proxy", lambda _settings: None)

    result = runner.invoke(app, ["service", "start"])

    assert result.exit_code == 0
    assert actions == ["start"]
