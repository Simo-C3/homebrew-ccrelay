from __future__ import annotations

import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_path, user_state_path

DEFAULT_PROXY_PORT = 4141
PROVIDER_ID = "ccrelay"


def make_proxy_key() -> str:
    return f"sk-ccrelay-{secrets.token_urlsafe(32)}"


def ensure_private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(stat.S_IRWXU)
    return path


def state_directory() -> Path:
    override = os.environ.get("CCRELAY_STATE_DIR")
    return ensure_private_directory(
        Path(override).expanduser() if override else user_state_path("ccrelay")
    )


def cache_directory() -> Path:
    override = os.environ.get("CCRELAY_CACHE_DIR")
    return ensure_private_directory(
        Path(override).expanduser() if override else user_cache_path("ccrelay")
    )


def copilot_token_directory() -> Path:
    return ensure_private_directory(state_directory() / "github-copilot")


def service_state_directory() -> Path:
    return ensure_private_directory(state_directory() / "service")


def service_cache_directory() -> Path:
    return ensure_private_directory(cache_directory() / "service")


@dataclass(frozen=True)
class RuntimeSettings:
    port: int
    proxy_key: str
    token_directory: Path
    config_path: Path
    log_path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"
