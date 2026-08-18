from __future__ import annotations

import pytest

from ccrelay.gateway import GatewayRequestError, GatewayRouter


def router() -> GatewayRouter:
    return GatewayRouter(
        backend_base_url="http://127.0.0.1:54321",
        proxy_key="sk-ccrelay-secret",
        chatgpt_base_url="https://chatgpt.example/backend-api/codex",
    )


def test_normal_request_routes_to_litellm_without_chatgpt_identity() -> None:
    upstream = router().route(
        "/v1/responses?trace=1",
        {
            "x-ccrelay-key": "sk-ccrelay-secret",
            "Authorization": "Bearer chatgpt-access-token",
            "ChatGPT-Account-ID": "account-id",
            "X-OpenAI-Actor-Authorization": "actor-token",
            "X-OpenAI-Fedramp": "true",
            "X-Request-ID": "request-id",
        },
    )

    assert upstream.url == "http://127.0.0.1:54321/v1/responses?trace=1"
    assert not upstream.is_image_request
    assert upstream.headers["authorization"] == "Bearer sk-ccrelay-secret"
    assert upstream.headers["x-request-id"] == "request-id"
    assert "x-ccrelay-key" not in upstream.headers
    assert "chatgpt-account-id" not in upstream.headers
    assert "x-openai-actor-authorization" not in upstream.headers
    assert "x-openai-fedramp" not in upstream.headers


@pytest.mark.parametrize("path", ["/v1/images/generations", "/v1/images/edits"])
def test_image_request_routes_only_to_chatgpt(path: str) -> None:
    upstream = router().route(
        f"{path}?format=png",
        {
            "X-CCRelay-Key": "sk-ccrelay-secret",
            "Authorization": "Bearer chatgpt-access-token",
            "ChatGPT-Account-ID": "account-id",
        },
    )

    endpoint = path.removeprefix("/v1")
    assert upstream.url == f"https://chatgpt.example/backend-api/codex{endpoint}?format=png"
    assert upstream.is_image_request
    assert upstream.headers["authorization"] == "Bearer chatgpt-access-token"
    assert upstream.headers["chatgpt-account-id"] == "account-id"
    assert "x-ccrelay-key" not in upstream.headers


def test_legacy_bearer_key_authenticates_non_image_requests() -> None:
    upstream = router().route(
        "/health/liveliness",
        {"Authorization": "Bearer sk-ccrelay-secret"},
    )

    assert upstream.url == "http://127.0.0.1:54321/health/liveliness"
    assert upstream.headers["authorization"] == "Bearer sk-ccrelay-secret"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer chatgpt-access-token"},
        {"X-CCRelay-Key": "wrong-key"},
    ],
)
def test_invalid_local_credentials_are_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(GatewayRequestError, match="Invalid ccrelay credentials") as exc_info:
        router().route("/v1/responses", headers)

    assert exc_info.value.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"X-CCRelay-Key": "sk-ccrelay-secret"},
        {
            "X-CCRelay-Key": "sk-ccrelay-secret",
            "Authorization": "Bearer sk-ccrelay-secret",
        },
        {
            "X-CCRelay-Key": "sk-ccrelay-secret",
            "Authorization": "Basic not-chatgpt-auth",
        },
    ],
)
def test_image_request_without_chatgpt_auth_is_rejected(headers: dict[str, str]) -> None:
    with pytest.raises(GatewayRequestError, match="ChatGPT authentication is required") as exc_info:
        router().route("/v1/images/generations", headers)

    assert exc_info.value.status_code == 401
