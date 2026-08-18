from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ccrelay import __version__
from ccrelay.codex_app import (
    CodexAppPreview,
    disable_codex_app,
    enable_codex_app,
    get_codex_app_status,
    preview_disable_codex_app,
    preview_enable_codex_app,
)
from ccrelay.diagnostics import collect_checks, collect_online_checks
from ccrelay.runtime import (
    CopilotAuthenticationError,
    authenticate_copilot,
    run_proxy_until_stopped,
)
from ccrelay.service import (
    load_service_settings,
    proxy_is_healthy,
    run_brew_service,
    wait_for_proxy,
)
from ccrelay.settings import RuntimeSettings


class LogLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class ShellMode(StrEnum):
    AUTO = "auto"
    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"


app = typer.Typer(
    name="ccrelay",
    help="Route Codex model requests to GitHub Copilot while preserving built-in imagegen.",
    no_args_is_help=True,
)
proxy_app = typer.Typer(
    help="Run and configure the foreground ccrelay gateway.",
    invoke_without_command=True,
    no_args_is_help=False,
)
service_app = typer.Typer(help="Manage the gateway with Homebrew Services.")
codex_app_cli = typer.Typer(help="Switch Codex App between ccrelay and its previous provider.")
app.add_typer(proxy_app, name="proxy")
app.add_typer(service_app, name="service")
app.add_typer(codex_app_cli, name="codex-app")


def _version_callback(value: bool) -> bool:
    if value:
        typer.echo(f"ccrelay {__version__}")
        raise typer.Exit()
    return value


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Print the ccrelay version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Route Codex model requests to GitHub Copilot while preserving built-in imagegen."""


@app.command()
def doctor(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option("--strict", help="Exit with an error when any check warns."),
    ] = False,
    online: Annotated[
        bool,
        typer.Option("--online", help="Also check GitHub connectivity without model requests."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Online check timeout in seconds."),
    ] = 5.0,
) -> None:
    """Check local prerequisites without sending a model request."""
    checks = collect_checks()
    if online:
        checks.extend(collect_online_checks(timeout=timeout))

    required = {"LiteLLM"}
    required_failed = any(not check.ok and check.name in required for check in checks)
    any_failed = any(not check.ok for check in checks)
    exit_failed = required_failed or (strict and any_failed)

    if json_output:
        _echo_json(
            {
                "version": __version__,
                "ok": not any_failed,
                "exit_code": 1 if exit_failed else 0,
                "strict": strict,
                "online": online,
                "checks": [
                    {"name": check.name, "ok": check.ok, "detail": check.detail} for check in checks
                ],
            }
        )
    else:
        for check in checks:
            marker = "OK" if check.ok else "WARN"
            typer.echo(f"[{marker}] {check.name}: {check.detail}")
        typer.echo(
            "\nEntitlement, Responses compatibility, and billing are not tested. "
            "Run 'ccrelay auth' and then an explicit smoke test."
        )
    if exit_failed:
        raise typer.Exit(1)


@app.command("version")
def version_command() -> None:
    """Print the ccrelay version."""
    typer.echo(f"ccrelay {__version__}")


@app.command()
def auth() -> None:
    """Authenticate GitHub Copilot with OAuth device flow."""
    try:
        authenticate_copilot()
    except (CopilotAuthenticationError, OSError) as exc:
        typer.echo(f"Authentication failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Authentication succeeded.")


@proxy_app.callback(invoke_without_command=True)
def proxy_default(
    ctx: typer.Context,
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Mirror redacted LiteLLM logs to stderr."),
    ] = False,
    startup_timeout: Annotated[
        float,
        typer.Option("--startup-timeout", min=0.1, help="Startup timeout in seconds."),
    ] = 90.0,
    log_level: Annotated[
        LogLevel,
        typer.Option("--log-level", case_sensitive=False, help="LiteLLM log level."),
    ] = LogLevel.ERROR,
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", dir_okay=False, help="Write redacted logs to this file."),
    ] = None,
) -> None:
    """Run the proxy when no proxy subcommand is given (legacy-compatible)."""
    if ctx.invoked_subcommand is None:
        _run_proxy(
            port=port,
            verbose=verbose,
            startup_timeout=startup_timeout,
            log_level=log_level,
            log_file=log_file,
        )


@proxy_app.command("run")
def proxy_run(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Mirror redacted LiteLLM logs to stderr."),
    ] = False,
    startup_timeout: Annotated[
        float,
        typer.Option("--startup-timeout", min=0.1, help="Startup timeout in seconds."),
    ] = 90.0,
    log_level: Annotated[
        LogLevel,
        typer.Option("--log-level", case_sensitive=False, help="LiteLLM log level."),
    ] = LogLevel.ERROR,
    log_file: Annotated[
        Path | None,
        typer.Option("--log-file", dir_okay=False, help="Write redacted logs to this file."),
    ] = None,
) -> None:
    """Run the persistent proxy in the foreground."""
    _run_proxy(
        port=port,
        verbose=verbose,
        startup_timeout=startup_timeout,
        log_level=log_level,
        log_file=log_file,
    )


@proxy_app.command("setenv")
def proxy_setenv(
    shell: Annotated[
        ShellMode,
        typer.Option("--shell", case_sensitive=False, help="Shell syntax to print."),
    ] = ShellMode.AUTO,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
) -> None:
    """Print credentials and configuration for a running proxy."""
    _print_proxy_environment(shell=shell, json_output=json_output)


def _run_proxy(
    *,
    port: int | None,
    verbose: bool,
    startup_timeout: float,
    log_level: LogLevel,
    log_file: Path | None,
) -> None:
    try:
        settings = load_service_settings(port=port)
        if port is not None:
            _sync_codex_app(settings)
        if log_file is not None:
            settings = replace(settings, log_path=log_file.expanduser())
        typer.echo(f"Serving all requested models on {settings.base_url}", err=True)
        run_proxy_until_stopped(
            settings,
            show_logs=verbose,
            startup_timeout=startup_timeout,
            log_level=log_level.value,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Unable to run LiteLLM: {exc}", err=True)
        raise typer.Exit(1) from exc


def _configure_service(port: int | None) -> RuntimeSettings:
    try:
        settings = load_service_settings(port=port)
        if port is not None:
            _sync_codex_app(settings)
        return settings
    except (RuntimeError, ValueError) as exc:
        typer.echo(f"Unable to configure proxy: {exc}", err=True)
        raise typer.Exit(1) from exc


def _sync_codex_app(settings: RuntimeSettings) -> None:
    if get_codex_app_status().enabled:
        enable_codex_app(settings)
        typer.echo("Updated the enabled Codex App provider; restart Codex App.", err=True)


@service_app.command("run")
def service_run(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait/--no-wait", help="Wait until the proxy is healthy."),
    ] = True,
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Startup wait timeout in seconds."),
    ] = 90.0,
) -> None:
    """Run in the background without registering at login."""
    _configure_service(port)
    _run_service_action("run", wait=wait, timeout=timeout)


@service_app.command("start")
def service_start(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait/--no-wait", help="Wait until the proxy is healthy."),
    ] = True,
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Startup wait timeout in seconds."),
    ] = 90.0,
) -> None:
    """Start in the background and register the proxy to run at login."""
    _configure_service(port)
    _run_service_action("start", wait=wait, timeout=timeout)


@service_app.command("stop")
def service_stop() -> None:
    """Stop the Homebrew-managed proxy."""
    _run_service_action("stop", wait=False, timeout=90.0)


@service_app.command("restart")
def service_restart(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait/--no-wait", help="Wait until the proxy is healthy."),
    ] = True,
    timeout: Annotated[
        float,
        typer.Option("--timeout", min=0.1, help="Startup wait timeout in seconds."),
    ] = 90.0,
) -> None:
    """Restart the Homebrew-managed proxy and apply configuration changes."""
    _configure_service(port)
    _run_service_action("restart", wait=wait, timeout=timeout)


@service_app.command("status")
def service_status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress output and use only the exit status."),
    ] = False,
) -> None:
    """Show the configured endpoint and whether it is responding."""
    try:
        settings = load_service_settings()
    except RuntimeError as exc:
        typer.echo(f"Unable to read proxy settings: {exc}", err=True)
        raise typer.Exit(1) from exc
    running = proxy_is_healthy(settings)
    state = "running" if running else "stopped"
    if not quiet:
        if json_output:
            _echo_json(
                {
                    "status": state,
                    "running": running,
                    "base_url": settings.base_url,
                    "port": settings.port,
                    "log_path": str(settings.log_path),
                }
            )
        else:
            typer.echo(f"{state}: {settings.base_url}")
    if not running:
        raise typer.Exit(1)


@service_app.command("logs")
def service_logs(
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Continue printing new log lines."),
    ] = False,
    lines: Annotated[
        int,
        typer.Option("--lines", "-n", min=0, help="Number of existing lines to print."),
    ] = 100,
) -> None:
    """Print redacted proxy logs."""
    try:
        log_path = load_service_settings().log_path
    except RuntimeError as exc:
        typer.echo(f"Unable to read proxy settings: {exc}", err=True)
        raise typer.Exit(1) from exc
    if not log_path.exists():
        typer.echo(f"No proxy log was found at {log_path}", err=True)
        raise typer.Exit(1)
    command = ["tail", "-n", str(lines)]
    if follow:
        command.append("-f")
    command.append(str(log_path))
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        typer.echo(f"Unable to read proxy logs: {exc}", err=True)
        raise typer.Exit(1) from exc
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


def _run_service_action(action: str, *, wait: bool, timeout: float) -> None:
    try:
        output = run_brew_service(action)
        if output:
            typer.echo(output)
        if wait:
            wait_for_proxy(load_service_settings(), timeout=timeout)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@codex_app_cli.command("enable")
def codex_app_enable(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and describe changes without writing files."),
    ] = False,
) -> None:
    """Route Codex App requests through the persistent ccrelay endpoint."""
    try:
        settings = load_service_settings(persist=not dry_run)
        if dry_run:
            _print_codex_preview(preview_enable_codex_app(settings))
            return
        status = enable_codex_app(settings)
    except RuntimeError as exc:
        typer.echo(f"Unable to configure Codex App: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Codex App now uses {status.base_url}.")
    selected_model = status.model or "unset"
    typer.echo(f"Codex model setting remains {selected_model}.")
    if not proxy_is_healthy(settings):
        typer.echo("Warning: the proxy is not running; run 'ccrelay service start'.", err=True)
    typer.echo("Restart Codex App to apply the change.")


@codex_app_cli.command("disable")
def codex_app_disable(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Validate and describe changes without writing files."),
    ] = False,
) -> None:
    """Restore the model provider used before ccrelay was enabled."""
    try:
        if dry_run:
            _print_codex_preview(preview_disable_codex_app())
            return
        status = disable_codex_app()
    except RuntimeError as exc:
        typer.echo(f"Unable to restore Codex App configuration: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Restored Codex configuration at {status.config_path}.")
    if status.preserved_changes:
        typer.echo(
            "Preserved user changes: " + ", ".join(status.preserved_changes) + ".",
            err=True,
        )
    typer.echo("Restart Codex App to apply the change.")


@codex_app_cli.command("status")
def codex_app_status(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable JSON."),
    ] = False,
) -> None:
    """Show the provider currently selected in the Codex configuration."""
    try:
        status = get_codex_app_status()
    except RuntimeError as exc:
        typer.echo(f"Unable to read Codex App configuration: {exc}", err=True)
        raise typer.Exit(1) from exc
    if json_output:
        _echo_json(
            {
                "enabled": status.enabled,
                "base_url": status.base_url,
                "model": status.model,
                "config_path": str(status.config_path),
            }
        )
        return
    state = "enabled" if status.enabled else "disabled"
    detail = f": {status.base_url}" if status.enabled else ""
    typer.echo(f"{state}{detail}")
    typer.echo(f"Model: {status.model or 'unset'}")
    typer.echo(f"Config: {status.config_path}")


def _print_proxy_environment(*, shell: ShellMode, json_output: bool) -> None:
    try:
        settings = load_service_settings()
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not proxy_is_healthy(settings):
        raise typer.BadParameter("No running ccrelay proxy was found")
    if json_output:
        _echo_json(
            {
                "base_url": f"{settings.base_url}/v1",
                "environment": {"CCRELAY_PROXY_KEY": settings.proxy_key},
            }
        )
        return
    selected_shell = _detected_shell() if shell is ShellMode.AUTO else shell
    if selected_shell is ShellMode.FISH:
        typer.echo(f"set -gx CCRELAY_PROXY_KEY {shlex.quote(settings.proxy_key)}")
    else:
        typer.echo(f"export CCRELAY_PROXY_KEY={shlex.quote(settings.proxy_key)}")
    typer.echo(f'# config.toml: base_url = "{settings.base_url}/v1"')


def _detected_shell() -> ShellMode:
    name = Path(os.environ.get("SHELL", "bash")).name.lower()
    try:
        return ShellMode(name)
    except ValueError:
        return ShellMode.BASH


def _print_codex_preview(preview: CodexAppPreview) -> None:
    if preview.action == "preserve removal":
        typer.echo(f"Would leave the removed Codex configuration absent at {preview.config_path}.")
    else:
        typer.echo(f"Would {preview.action} Codex configuration at {preview.config_path}.")
    if preview.base_url is not None:
        typer.echo(f"Provider URL: {preview.base_url}")
    if preview.target_mode is not None:
        typer.echo(f"Target permissions: {preview.target_mode:04o}")
    if preview.preserved_changes:
        typer.echo("Would preserve: " + ", ".join(preview.preserved_changes) + ".")
    typer.echo("No files were changed.")


def _echo_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
