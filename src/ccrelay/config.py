from __future__ import annotations

import json
import os
from typing import Any

from ccrelay.settings import RuntimeSettings

# LiteLLM's Copilot Responses gate looks up concrete provider/model keys. A
# wildcard deployment alone does not register those keys and falls back to chat.
COPILOT_RESPONSES_ONLY_MODELS = (
    "gpt-5.3-codex",
    "gpt-5.5",
    "gpt-5.6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "mai-code-1-flash-picker",
)

# Codex uses this hidden model ID for automatic approval reviews. GitHub
# Copilot does not expose it, so route reviews to a compatible reasoning model.
CODEX_AUTO_REVIEW_MODEL = "codex-auto-review"
COPILOT_AUTO_REVIEW_MODEL = "gpt-5.6-sol"


def build_litellm_config(settings: RuntimeSettings) -> dict[str, Any]:
    return {
        "model_list": [
            *[
                {
                    "model_name": model,
                    "model_info": {"mode": "responses"},
                    "litellm_params": {"model": f"github_copilot/{model}"},
                }
                for model in COPILOT_RESPONSES_ONLY_MODELS
            ],
            {
                "model_name": CODEX_AUTO_REVIEW_MODEL,
                "model_info": {"mode": "responses"},
                "litellm_params": {
                    "model": f"github_copilot/{COPILOT_AUTO_REVIEW_MODEL}"
                },
            },
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
