from __future__ import annotations

import json
import os
from typing import Any

from ccrelay.settings import RuntimeSettings


def build_litellm_config(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "model_list": [
            {
                "model_name": "*",
                "model_info": {"mode": "responses"},
                "litellm_params": {"model": "github_copilot/*"},
            }
        ],
        "general_settings": {
            "master_key": f"os.environ/{proxy_key_environment_name()}",
        },
        "litellm_settings": {
            "set_verbose": False,
            "json_logs": True,
        },
    }


def write_litellm_config(settings: RuntimeSettings) -> None:
    # JSON is valid YAML and avoids adding another parser just to generate this file.
    payload = json.dumps(build_litellm_config(settings), indent=2)
    settings.config_path.write_text(payload + "\n", encoding="utf-8")
    settings.config_path.chmod(0o600)


def proxy_key_environment_name() -> str:
    return "CCRELAY_PROXY_KEY"


def build_proxy_environment(settings: RuntimeSettings) -> dict[str, str]:
    env = os.environ.copy()
    env[proxy_key_environment_name()] = settings.proxy_key
    env["GITHUB_COPILOT_TOKEN_DIR"] = str(settings.token_directory)
    env.setdefault("LITELLM_LOG", "ERROR")
    return env
