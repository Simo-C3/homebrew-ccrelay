from __future__ import annotations

import json
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


def test_root_version_options() -> None:
    for option in ("--version", "-V"):
        result = runner.invoke(app, [option])

        assert result.exit_code == 0
        assert result.stdout.strip() == f"ccrelay {__version__}"


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


def test_doctor_json_and_strict_exit_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "ccrelay.cli.collect_checks",
        lambda: [
            Check("LiteLLM", True, "installed"),
            Check("Copilot OAuth cache", False, "missing"),
        ],
    )

    normal = runner.invoke(app, ["doctor", "--json"])
    strict = runner.invoke(app, ["doctor", "--json", "--strict"])

    assert normal.exit_code == 0
    assert json.loads(normal.stdout)["ok"] is False
    assert json.loads(normal.stdout)["exit_code"] == 0
    assert strict.exit_code == 1
    assert json.loads(strict.stdout)["ok"] is False
    assert json.loads(strict.stdout)["exit_code"] == 1


def test_doctor_online_uses_requested_timeout(monkeypatch) -> None:
    observed: list[float] = []
    monkeypatch.setattr("ccrelay.cli.collect_checks", lambda: [])
    monkeypatch.setattr(
        "ccrelay.cli.collect_online_checks",
        lambda *, timeout: observed.append(timeout) or [Check("online", True, "ok")],
    )

    result = runner.invoke(app, ["doctor", "--online", "--timeout", "1.5", "--json"])

    assert result.exit_code == 0
    assert observed == [1.5]


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
    monkeypatch.setattr("ccrelay.cli.wait_for_proxy", lambda _settings, **_kwargs: None)

    result = runner.invoke(app, ["service", "start"])

    assert result.exit_code == 0
    assert actions == ["start"]


def test_proxy_run_accepts_logging_and_startup_options(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    loads: list[dict[str, object]] = []
    observed: list[tuple[RuntimeSettings, dict[str, object]]] = []
    monkeypatch.setattr(
        "ccrelay.cli.load_service_settings",
        lambda **kwargs: loads.append(kwargs) or runtime,
    )
    monkeypatch.setattr(
        "ccrelay.cli.get_codex_app_status",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr(
        "ccrelay.cli.run_proxy_until_stopped",
        lambda settings, **kwargs: observed.append((settings, kwargs)),
    )
    log_path = tmp_path / "custom.log"

    result = runner.invoke(
        app,
        [
            "proxy",
            "run",
            "--port",
            "4242",
            "--verbose",
            "--startup-timeout",
            "12",
            "--log-level",
            "debug",
            "--log-file",
            str(log_path),
        ],
    )

    assert result.exit_code == 0
    assert loads == [{"port": 4242}]
    assert observed[0][0].log_path == log_path
    assert observed[0][1] == {
        "show_logs": True,
        "startup_timeout": 12.0,
        "log_level": "debug",
    }


def test_bare_proxy_remains_a_foreground_alias(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda **_kwargs: runtime)
    monkeypatch.setattr(
        "ccrelay.cli.run_proxy_until_stopped",
        lambda _settings, **kwargs: calls.append(kwargs),
    )

    result = runner.invoke(app, ["proxy", "--startup-timeout", "15"])

    assert result.exit_code == 0
    assert calls[0]["startup_timeout"] == 15.0


def test_proxy_setenv_json(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda: runtime)
    monkeypatch.setattr("ccrelay.cli.proxy_is_healthy", lambda _settings: True)

    result = runner.invoke(app, ["proxy", "setenv", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["base_url"] == "http://127.0.0.1:4141/v1"
    assert payload["environment"]["CCRELAY_PROXY_KEY"] == "sk-ccrelay-test"


def test_service_timeout_and_no_wait(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    waits: list[float] = []
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda **_kwargs: runtime)
    monkeypatch.setattr(
        "ccrelay.cli.get_codex_app_status",
        lambda: SimpleNamespace(enabled=False),
    )
    monkeypatch.setattr("ccrelay.cli.run_brew_service", lambda _action: "")
    monkeypatch.setattr(
        "ccrelay.cli.wait_for_proxy",
        lambda _settings, *, timeout: waits.append(timeout),
    )

    waited = runner.invoke(app, ["service", "start", "--timeout", "12"])
    not_waited = runner.invoke(app, ["service", "restart", "--no-wait"])

    assert waited.exit_code == 0
    assert not_waited.exit_code == 0
    assert waits == [12.0]


def test_service_status_json_and_quiet(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda: runtime)
    monkeypatch.setattr("ccrelay.cli.proxy_is_healthy", lambda _settings: True)

    status = runner.invoke(app, ["service", "status", "--json"])
    quiet = runner.invoke(app, ["service", "status", "--quiet"])

    assert status.exit_code == 0
    assert json.loads(status.stdout)["running"] is True
    assert quiet.exit_code == 0
    assert quiet.stdout == ""


def test_service_logs_runs_tail(monkeypatch, tmp_path) -> None:
    runtime = RuntimeSettings(
        port=4141,
        proxy_key="sk-ccrelay-test",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )
    runtime.log_path.write_text("one\ntwo\n")
    commands: list[list[str]] = []
    monkeypatch.setattr("ccrelay.cli.load_service_settings", lambda: runtime)
    monkeypatch.setattr(
        "ccrelay.cli.subprocess.run",
        lambda command, **_kwargs: (
            commands.append(command) or subprocess.CompletedProcess(command, 0)
        ),
    )

    result = runner.invoke(app, ["service", "logs", "--lines", "2", "--follow"])

    assert result.exit_code == 0
    assert commands == [["tail", "-n", "2", "-f", str(runtime.log_path)]]


def test_codex_app_enable_dry_run_does_not_create_files(monkeypatch, tmp_path) -> None:
    codex_home = tmp_path / "codex"
    state_dir = tmp_path / "state"
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CCRELAY_STATE_DIR", str(state_dir))
    monkeypatch.setenv("CCRELAY_CACHE_DIR", str(cache_dir))

    result = runner.invoke(app, ["codex-app", "enable", "--dry-run"])

    assert result.exit_code == 0
    assert "No files were changed." in result.stdout
    assert not codex_home.exists()
    assert not state_dir.exists()
    assert not cache_dir.exists()
