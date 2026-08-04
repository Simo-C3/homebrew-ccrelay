from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from tomlkit import TOMLDocument, dumps, parse, table
from tomlkit.items import Table

from ccrelay.settings import PROVIDER_ID, RuntimeSettings, service_state_directory
from ccrelay.storage import write_private_json, write_private_text

BACKUP_VERSION = 3
PROVIDER_NAME = "ccrelay GitHub Copilot"


@dataclass(frozen=True)
class CodexAppStatus:
    enabled: bool
    config_path: Path
    model: str | None
    base_url: str | None
    preserved_changes: tuple[str, ...] = ()


def codex_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    root = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return root / "config.toml"


def enable_codex_app(settings: RuntimeSettings) -> CodexAppStatus:
    config_path = codex_config_path()
    backup_path = _backup_path()
    document = _read_document(config_path)
    providers = _providers(document, create=True)
    assert providers is not None

    if backup_path.exists():
        backup = _read_backup(backup_path, config_path)
        provider = providers.get(PROVIDER_ID)
        if backup["version"] in {1, 2}:
            if (
                document.get("model_provider") != PROVIDER_ID
                or not isinstance(provider, Table)
                or not _provider_looks_managed(provider)
            ):
                raise RuntimeError(
                    "Codex configuration changed after ccrelay was enabled; "
                    "run 'ccrelay codex-app disable' to preserve those changes"
                )
            if backup["version"] == 1:
                _restore_value(document, "model", backup["model"])
            backup = _upgrade_backup(backup)
        else:
            conflicts = _applied_conflicts(config_path, document, provider, backup["applied"])
            if conflicts:
                detail = ", ".join(conflicts)
                raise RuntimeError(
                    f"Codex configuration changed in ccrelay-managed fields ({detail}); "
                    "run 'ccrelay codex-app disable' to preserve those changes"
                )
    else:
        if PROVIDER_ID in providers:
            raise RuntimeError(
                f"Codex already has a model_providers.{PROVIDER_ID} table not managed by ccrelay"
            )
        backup = {
            "version": BACKUP_VERSION,
            "config_path": str(config_path),
            "config_existed": config_path.exists(),
            "config_mode": (
                stat.S_IMODE(config_path.stat().st_mode) if config_path.exists() else 0o600
            ),
            "trailing_newlines": _trailing_newlines(config_path),
            "model_provider": _snapshot_value(document, "model_provider"),
        }

    document["model_provider"] = PROVIDER_ID
    provider = _provider_table(settings)
    providers[PROVIDER_ID] = provider
    content = dumps(document)
    backup["version"] = BACKUP_VERSION
    backup["applied"] = {
        "model_provider": PROVIDER_ID,
        "provider_fingerprint": _provider_fingerprint(provider),
        "token_fingerprint": _text_fingerprint(settings.proxy_key),
        "config_mode": 0o600,
        "trailing_newlines": _count_trailing_newlines(content),
    }
    write_private_json(backup_path, backup)
    write_private_text(config_path, content)
    return get_codex_app_status()


def disable_codex_app() -> CodexAppStatus:
    config_path = codex_config_path()
    backup_path = _backup_path()
    if not backup_path.exists():
        raise RuntimeError("ccrelay is not enabled in the Codex configuration")

    backup = _read_backup(backup_path, config_path)
    if not config_path.exists():
        backup_path.unlink()
        return replace(
            get_codex_app_status(),
            preserved_changes=("config file removal",),
        )

    document = _read_document(config_path)
    providers = _providers(document, create=False)
    provider = providers.get(PROVIDER_ID) if providers is not None else None
    preserved: list[str] = []

    if document.get("model_provider") == PROVIDER_ID:
        _restore_value(document, "model_provider", backup["model_provider"])
    else:
        preserved.append("model_provider")

    if backup["version"] == BACKUP_VERSION:
        expected_fingerprint = backup["applied"]["provider_fingerprint"]
        if isinstance(provider, Table) and _provider_fingerprint(provider) == expected_fingerprint:
            assert providers is not None
            del providers[PROVIDER_ID]
            if not providers:
                del document["model_providers"]
        elif isinstance(provider, Table):
            token = provider.get("experimental_bearer_token")
            if (
                isinstance(token, str)
                and _text_fingerprint(token) == backup["applied"]["token_fingerprint"]
            ):
                del provider["experimental_bearer_token"]
            preserved.append(f"model_providers.{PROVIDER_ID}")
        elif provider is not None:
            preserved.append(f"model_providers.{PROVIDER_ID}")
        else:
            preserved.append(f"model_providers.{PROVIDER_ID} removal")
    elif provider is not None:
        preserved.append(f"model_providers.{PROVIDER_ID} (legacy backup)")

    current_mode = stat.S_IMODE(config_path.stat().st_mode)
    current_trailing_newlines = _trailing_newlines(config_path)
    if backup["version"] == BACKUP_VERSION:
        applied = backup["applied"]
        permissions_changed = current_mode != applied["config_mode"]
        if current_mode == applied["config_mode"]:
            target_mode = backup["config_mode"]
        else:
            target_mode = current_mode
        if current_trailing_newlines == applied["trailing_newlines"]:
            target_trailing_newlines = backup["trailing_newlines"]
        else:
            target_trailing_newlines = current_trailing_newlines
            preserved.append("trailing newlines")
    else:
        target_mode = current_mode
        target_trailing_newlines = current_trailing_newlines

    provider_has_token = (
        isinstance(provider, Table)
        and providers is not None
        and PROVIDER_ID in providers
        and "experimental_bearer_token" in provider
    )
    if provider_has_token and target_mode & 0o077:
        target_mode = 0o600
        preserved.append("file permissions (restricted to protect the preserved token)")
    elif backup["version"] == BACKUP_VERSION and permissions_changed:
        preserved.append("file permissions")

    serialized = dumps(document)
    content = serialized.rstrip("\n") + ("\n" * target_trailing_newlines)
    if not backup["config_existed"] and not content and not preserved:
        config_path.unlink(missing_ok=True)
    else:
        write_private_text(config_path, content, mode=target_mode)
    backup_path.unlink()
    return replace(
        get_codex_app_status(),
        preserved_changes=tuple(preserved),
    )


def get_codex_app_status() -> CodexAppStatus:
    path = codex_config_path()
    document = _read_document(path)
    providers = _providers(document, create=False)
    provider = providers.get(PROVIDER_ID) if providers is not None else None
    model = document.get("model")
    base_url = provider.get("base_url") if isinstance(provider, Table) else None
    enabled = document.get("model_provider") == PROVIDER_ID and isinstance(provider, Table)
    return CodexAppStatus(
        enabled=enabled,
        config_path=path,
        model=model if isinstance(model, str) else None,
        base_url=base_url if isinstance(base_url, str) else None,
    )


def _provider_table(settings: RuntimeSettings) -> Table:
    provider = table()
    provider["name"] = PROVIDER_NAME
    provider["base_url"] = f"{settings.base_url}/v1"
    provider["experimental_bearer_token"] = settings.proxy_key
    provider["wire_api"] = "responses"
    provider["stream_idle_timeout_ms"] = 300000
    return provider


def _provider_looks_managed(provider: Table) -> bool:
    return (
        provider.get("name") == PROVIDER_NAME
        and provider.get("wire_api") == "responses"
        and isinstance(provider.get("base_url"), str)
        and isinstance(provider.get("experimental_bearer_token"), str)
    )


def _provider_fingerprint(provider: Table) -> str:
    return sha256(provider.as_string().encode("utf-8")).hexdigest()


def _text_fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _applied_conflicts(
    config_path: Path,
    document: TOMLDocument,
    provider: object,
    applied: dict[str, Any],
) -> list[str]:
    conflicts: list[str] = []
    if document.get("model_provider") != applied["model_provider"]:
        conflicts.append("model_provider")
    if (
        not isinstance(provider, Table)
        or _provider_fingerprint(provider) != applied["provider_fingerprint"]
    ):
        conflicts.append(f"model_providers.{PROVIDER_ID}")
    if not config_path.exists():
        conflicts.append("config file")
        return conflicts
    if stat.S_IMODE(config_path.stat().st_mode) != applied["config_mode"]:
        conflicts.append("file permissions")
    if _trailing_newlines(config_path) != applied["trailing_newlines"]:
        conflicts.append("trailing newlines")
    return conflicts


def _read_document(path: Path) -> TOMLDocument:
    if not path.exists():
        return TOMLDocument()
    try:
        return parse(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Unable to read Codex configuration at {path}: {exc}") from exc


def _providers(document: TOMLDocument, *, create: bool) -> Table | None:
    value = document.get("model_providers")
    if value is None and create:
        value = table()
        document["model_providers"] = value
    if value is not None and not isinstance(value, Table):
        raise RuntimeError("Codex 'model_providers' configuration is not a table")
    return value


def _snapshot_value(document: TOMLDocument, name: str) -> dict[str, Any]:
    if name not in document:
        return {"present": False}
    value = document[name]
    if not isinstance(value, str):
        raise RuntimeError(f"Codex {name!r} must be a string")
    return {"present": True, "value": value}


def _restore_value(document: TOMLDocument, name: str, snapshot: object) -> None:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("present"), bool):
        raise RuntimeError(f"Invalid saved Codex value for {name!r}")
    if snapshot["present"]:
        value = snapshot.get("value")
        if not isinstance(value, str):
            raise RuntimeError(f"Invalid saved Codex value for {name!r}")
        document[name] = value
    elif name in document:
        del document[name]


def _backup_path() -> Path:
    return service_state_directory() / "codex-app-backup.json"


def _read_backup(path: Path, config_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read Codex backup at {path}: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") not in {1, 2, BACKUP_VERSION}
        or payload.get("config_path") != str(config_path)
        or "model_provider" not in payload
        or (payload.get("version") == 1 and "model" not in payload)
        or not _valid_backup_metadata(payload)
        or not _valid_snapshot(payload.get("model_provider"))
        or (payload.get("version") == 1 and not _valid_snapshot(payload.get("model")))
        or (payload.get("version") == BACKUP_VERSION and not _valid_applied(payload.get("applied")))
    ):
        raise RuntimeError(f"Invalid Codex backup at {path}")
    return payload


def _upgrade_backup(backup: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": BACKUP_VERSION,
        "config_path": backup["config_path"],
        "config_existed": backup["config_existed"],
        "config_mode": backup["config_mode"],
        "trailing_newlines": backup["trailing_newlines"],
        "model_provider": backup["model_provider"],
    }


def _valid_backup_metadata(backup: dict[str, Any]) -> bool:
    config_existed = backup.get("config_existed")
    config_mode = backup.get("config_mode")
    trailing_newlines = backup.get("trailing_newlines")
    return (
        isinstance(config_existed, bool)
        and isinstance(config_mode, int)
        and not isinstance(config_mode, bool)
        and 0 <= config_mode <= 0o777
        and isinstance(trailing_newlines, int)
        and not isinstance(trailing_newlines, bool)
        and trailing_newlines >= 0
    )


def _valid_snapshot(snapshot: object) -> bool:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("present"), bool):
        return False
    return not snapshot["present"] or isinstance(snapshot.get("value"), str)


def _valid_applied(applied: object) -> bool:
    if not isinstance(applied, dict):
        return False
    fingerprint = applied.get("provider_fingerprint")
    token_fingerprint = applied.get("token_fingerprint")
    return (
        applied.get("model_provider") == PROVIDER_ID
        and isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and all(character in "0123456789abcdef" for character in fingerprint)
        and isinstance(token_fingerprint, str)
        and len(token_fingerprint) == 64
        and all(character in "0123456789abcdef" for character in token_fingerprint)
        and applied.get("config_mode") == 0o600
        and isinstance(applied.get("trailing_newlines"), int)
        and not isinstance(applied.get("trailing_newlines"), bool)
        and applied["trailing_newlines"] >= 0
    )


def _count_trailing_newlines(content: str) -> int:
    return len(content) - len(content.rstrip("\n"))


def _trailing_newlines(path: Path) -> int:
    if not path.exists():
        return 0
    content = path.read_text(encoding="utf-8")
    return _count_trailing_newlines(content)
