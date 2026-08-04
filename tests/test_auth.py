from __future__ import annotations

import os

from ccrelay.runtime import authenticate_copilot


def test_authenticate_copilot_uses_private_token_directory(monkeypatch, tmp_path) -> None:
    observed: list[str | None] = []

    class FakeAuthenticator:
        def get_api_key(self) -> str:
            observed.append(os.environ.get("GITHUB_COPILOT_TOKEN_DIR"))
            return "unused-token"

    monkeypatch.setenv("CCRELAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GITHUB_COPILOT_TOKEN_DIR", "/previous")
    monkeypatch.setattr("ccrelay.runtime.Authenticator", FakeAuthenticator)

    authenticate_copilot()

    assert observed == [str(tmp_path / "state" / "github-copilot")]
    assert os.environ["GITHUB_COPILOT_TOKEN_DIR"] == "/previous"
