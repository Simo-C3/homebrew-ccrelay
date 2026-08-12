from __future__ import annotations

import importlib.metadata
import os
import platform
from dataclasses import dataclass

import httpx

from ccrelay.settings import copilot_token_directory


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def collect_checks() -> list[Check]:
    checks: list[Check] = []
    try:
        version = importlib.metadata.version("litellm")
        checks.append(Check("LiteLLM", True, version))
    except importlib.metadata.PackageNotFoundError:
        checks.append(Check("LiteLLM", False, "not installed"))
    checks.append(Check("Python", True, platform.python_version()))
    token_dir = copilot_token_directory()
    token_files = [path for path in token_dir.iterdir() if path.is_file()]
    checks.append(
        Check(
            "Copilot OAuth cache",
            bool(token_files),
            (
                f"{len(token_files)} file(s)"
                if token_files
                else "not authenticated through ccrelay yet"
            ),
        )
    )
    checks.append(
        Check(
            "Loopback policy",
            os.environ.get("CCRELAY_ALLOW_NON_LOOPBACK") is None,
            "127.0.0.1 only",
        )
    )
    return checks


def collect_online_checks(*, timeout: float) -> list[Check]:
    """Check network reachability without authenticating or sending a model request."""
    try:
        response = httpx.get(
            "https://github.com/login/device",
            follow_redirects=True,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return [Check("GitHub device endpoint", False, str(exc))]
    ok = response.status_code < 500
    detail = f"HTTP {response.status_code}"
    return [Check("GitHub device endpoint", ok, detail)]
