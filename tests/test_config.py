from __future__ import annotations

import json
from pathlib import Path

from litellm.router_utils.pattern_match_deployments import PatternMatchRouter

from ccrelay.config import (
    build_litellm_config,
    write_litellm_config,
)
from ccrelay.settings import RuntimeSettings


def settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        port=4567,
        proxy_key="sk-ccrelay-secret",
        token_directory=tmp_path / "tokens",
        config_path=tmp_path / "litellm.json",
        log_path=tmp_path / "proxy.log",
    )


def test_litellm_config_routes_all_responses_models(tmp_path) -> None:
    payload = build_litellm_config(settings(tmp_path))
    deployment = payload["model_list"][0]
    assert deployment["model_name"] == "*"
    assert deployment["model_info"]["mode"] == "responses"
    assert deployment["litellm_params"]["model"] == "github_copilot/*"
    assert payload["general_settings"]["master_key"] == "os.environ/CCRELAY_PROXY_KEY"
    assert "sk-ccrelay-secret" not in json.dumps(payload)


def test_litellm_wildcard_preserves_requested_model(tmp_path) -> None:
    deployment = build_litellm_config(settings(tmp_path))["model_list"][0]
    router = PatternMatchRouter()
    router.add_pattern(deployment["model_name"], deployment)

    for model in ("gpt-5.6-luna", "claude-sonnet-4.6"):
        matched = router.route(model)
        assert matched is not None
        assert matched[0]["litellm_params"]["model"] == f"github_copilot/{model}"


def test_written_config_is_private_json_yaml(tmp_path) -> None:
    runtime = settings(tmp_path)
    write_litellm_config(runtime)
    assert json.loads(runtime.config_path.read_text())["model_list"]
    assert runtime.config_path.stat().st_mode & 0o077 == 0
