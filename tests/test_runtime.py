from __future__ import annotations

from ccrelay.runtime import (
    is_auth_instruction,
    litellm_command,
    redact,
    resolve_binary,
)


def test_redact_common_secrets() -> None:
    text = (
        "Authorization: Bearer abc123\n"
        '"access_token":"token-value"\n'
        '"api_key": "key-value"\n'
        "generated sk-ccrelay-this-is-secret"
    )
    safe = redact(text)
    assert "abc123" not in safe
    assert "token-value" not in safe
    assert "key-value" not in safe
    assert "sk-ccrelay-this-is-secret" not in safe
    assert safe.count("[REDACTED]") == 4


def test_device_flow_instruction_is_detected() -> None:
    assert is_auth_instruction(
        "Please visit https://github.com/login/device and enter code ABCD-1234 to authenticate."
    )
    assert not is_auth_instruction("No existing access token found")


def test_resolve_binary_honors_override(monkeypatch) -> None:
    monkeypatch.setenv("CCRELAY_TEST_BIN", "/custom/tool")
    assert resolve_binary("ignored", "CCRELAY_TEST_BIN") == "/custom/tool"


def test_litellm_command_uses_sibling_tool_binary(monkeypatch, tmp_path) -> None:
    python = tmp_path / "python"
    litellm = tmp_path / "litellm"
    python.write_text("", encoding="utf-8")
    litellm.write_text("", encoding="utf-8")
    litellm.chmod(0o700)
    monkeypatch.setattr("ccrelay.runtime.sys.executable", str(python))
    monkeypatch.delenv("CCRELAY_LITELLM_BIN", raising=False)
    monkeypatch.setattr("ccrelay.runtime.shutil.which", lambda *_args: None)

    assert litellm_command() == [str(litellm)]
