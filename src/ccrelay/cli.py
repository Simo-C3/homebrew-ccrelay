from __future__ import annotations

import shlex
from typing import Annotated

import typer

from ccrelay import __version__
from ccrelay.codex_app import disable_codex_app, enable_codex_app, get_codex_app_status
from ccrelay.diagnostics import collect_checks
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

app = typer.Typer(
    name="ccrelay",
    help="Relay Codex requests to GitHub Copilot through a local LiteLLM proxy.",
    no_args_is_help=True,
)
service_app = typer.Typer(help="Manage the proxy with Homebrew Services.")
codex_app_cli = typer.Typer(help="Switch Codex App between ccrelay and its previous provider.")
app.add_typer(service_app, name="service")
app.add_typer(codex_app_cli, name="codex-app")


@app.command()
def doctor() -> None:
    """Check local prerequisites without sending a model request."""
    checks = collect_checks()
    for check in checks:
        marker = "OK" if check.ok else "WARN"
        typer.echo(f"[{marker}] {check.name}: {check.detail}")
    required = {"LiteLLM"}
    if any(not check.ok and check.name in required for check in checks):
        raise typer.Exit(1)
    typer.echo(
        "\nNetwork, entitlement, Responses compatibility, and billing are not tested. "
        "Run 'ccrelay auth' and then an explicit smoke test."
    )


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


@app.command()
def proxy(
    action: Annotated[
        str,
        typer.Argument(help="Use 'setenv' to print exports for a running proxy."),
    ] = "start",
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", help="Mirror redacted LiteLLM logs to stderr."),
    ] = False,
    shell: Annotated[
        str,
        typer.Option("--shell", help="Shell syntax for 'setenv': bash, zsh, or fish."),
    ] = "bash",
) -> None:
    """Run the persistent proxy in the foreground."""
    if action == "setenv":
        _print_proxy_environment(shell)
        return
    if action != "start":
        typer.echo(f"Unknown proxy action: {action}", err=True)
        raise typer.Exit(2)
    try:
        settings = load_service_settings(port=port)
        if port is not None:
            _sync_codex_app(settings)
        typer.echo(f"Serving all requested models on {settings.base_url}", err=True)
        run_proxy_until_stopped(settings, show_logs=verbose)
    except (RuntimeError, ValueError) as exc:
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
) -> None:
    """Run in the background without registering at login."""
    _configure_service(port)
    _run_service_action("run", wait=True)


@service_app.command("start")
def service_start(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
) -> None:
    """Start in the background and register the proxy to run at login."""
    _configure_service(port)
    _run_service_action("restart", wait=True)


@service_app.command("stop")
def service_stop() -> None:
    """Stop the Homebrew-managed proxy."""
    _run_service_action("stop", wait=False)


@service_app.command("restart")
def service_restart(
    port: Annotated[
        int | None,
        typer.Option("--port", min=1, max=65535, help="Loopback port for the proxy."),
    ] = None,
) -> None:
    """Restart the Homebrew-managed proxy and apply configuration changes."""
    _configure_service(port)
    _run_service_action("restart", wait=True)


@service_app.command("status")
def service_status() -> None:
    """Show the configured endpoint and whether it is responding."""
    try:
        settings = load_service_settings()
    except RuntimeError as exc:
        typer.echo(f"Unable to read proxy settings: {exc}", err=True)
        raise typer.Exit(1) from exc
    state = "running" if proxy_is_healthy(settings) else "stopped"
    typer.echo(f"{state}: {settings.base_url}")
    if state == "stopped":
        raise typer.Exit(1)


def _run_service_action(action: str, *, wait: bool) -> None:
    try:
        output = run_brew_service(action)
        if output:
            typer.echo(output)
        if wait:
            wait_for_proxy(load_service_settings())
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc


@codex_app_cli.command("enable")
def codex_app_enable() -> None:
    """Route Codex App requests through the persistent ccrelay endpoint."""
    try:
        settings = load_service_settings()
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
def codex_app_disable() -> None:
    """Restore the model provider used before ccrelay was enabled."""
    try:
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
def codex_app_status() -> None:
    """Show the provider currently selected in the Codex configuration."""
    try:
        status = get_codex_app_status()
    except RuntimeError as exc:
        typer.echo(f"Unable to read Codex App configuration: {exc}", err=True)
        raise typer.Exit(1) from exc
    state = "enabled" if status.enabled else "disabled"
    detail = f": {status.base_url}" if status.enabled else ""
    typer.echo(f"{state}{detail}")
    typer.echo(f"Model: {status.model or 'unset'}")
    typer.echo(f"Config: {status.config_path}")


def _print_proxy_environment(shell: str) -> None:
    if shell not in {"bash", "zsh", "fish"}:
        raise typer.BadParameter("--shell must be bash, zsh, or fish")
    try:
        settings = load_service_settings()
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not proxy_is_healthy(settings):
        raise typer.BadParameter("No running ccrelay proxy was found")
    if shell == "fish":
        typer.echo(f"set -gx CCRELAY_PROXY_KEY {shlex.quote(settings.proxy_key)}")
    else:
        typer.echo(f"export CCRELAY_PROXY_KEY={shlex.quote(settings.proxy_key)}")
    typer.echo(f'# config.toml: base_url = "{settings.base_url}/v1"')


if __name__ == "__main__":
    app()
