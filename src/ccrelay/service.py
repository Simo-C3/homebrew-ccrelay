from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from ccrelay.settings import (
    DEFAULT_PROXY_PORT,
    RuntimeSettings,
    copilot_token_directory,
    make_proxy_key,
    service_cache_directory,
    service_state_directory,
)
from ccrelay.storage import write_private_json

SERVICE_SETTINGS_VERSION = 2
BREW_SERVICE_ACTIONS = {"run", "start", "stop", "restart"}


def load_service_settings(
    *,
    port: int | None = None,
) -> RuntimeSettings:
    state_dir = service_state_directory()
    cache_dir = service_cache_directory()
    settings_path = state_dir / "settings.json"

    if settings_path.exists():
        payload = _read_settings(settings_path)
        saved_port = _required_port(payload)
        proxy_key = _required_string(payload, "proxy_key")
    else:
        payload = {}
        saved_port = DEFAULT_PROXY_PORT
        proxy_key = make_proxy_key()

    selected_port = port if port is not None else saved_port
    if not 1 <= selected_port <= 65535:
        raise ValueError("Proxy port must be between 1 and 65535")

    if payload.get("version") != SERVICE_SETTINGS_VERSION or selected_port != saved_port:
        write_private_json(
            settings_path,
            {
                "version": SERVICE_SETTINGS_VERSION,
                "port": selected_port,
                "proxy_key": proxy_key,
            },
        )
    return RuntimeSettings(
        port=selected_port,
        proxy_key=proxy_key,
        token_directory=copilot_token_directory(),
        config_path=state_dir / "litellm.json",
        log_path=cache_dir / "proxy.log",
    )


def proxy_is_healthy(settings: RuntimeSettings, *, timeout: float = 0.5) -> bool:
    try:
        response = httpx.get(
            f"{settings.base_url}/health/liveliness",
            headers={"Authorization": f"Bearer {settings.proxy_key}"},
            timeout=timeout,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def wait_for_proxy(settings: RuntimeSettings, *, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proxy_is_healthy(settings):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Proxy did not become ready at {settings.base_url} within {timeout:.0f}s")


def run_brew_service(action: str) -> str:
    if action not in BREW_SERVICE_ACTIONS:
        raise ValueError(f"Unsupported Homebrew service action: {action}")
    brew = os.environ.get("CCRELAY_BREW_BIN") or shutil.which("brew")
    if not brew:
        raise RuntimeError(
            "Homebrew was not found; install ccrelay with Homebrew or run 'ccrelay proxy'"
        )
    formula = os.environ.get("CCRELAY_BREW_FORMULA", "ccrelay")
    result = subprocess.run(
        [brew, "services", action, formula],
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        detail = output or f"exit {result.returncode}"
        raise RuntimeError(f"'brew services {action} {formula}' failed: {detail}")
    return output


def _read_settings(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read service settings at {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
        raise RuntimeError(f"Unsupported service settings at {path}")
    return payload


def _required_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid {name!r} in service settings")
    return value


def _required_port(payload: dict[str, Any]) -> int:
    value = payload.get("port")
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 65535:
        raise RuntimeError("Invalid 'port' in service settings")
    return value
