from __future__ import annotations

from types import SimpleNamespace

import httpx

from ccrelay.diagnostics import collect_online_checks


def test_online_check_reports_github_response(monkeypatch) -> None:
    observed: list[tuple[str, float]] = []

    def fake_get(url: str, *, follow_redirects: bool, timeout: float) -> object:
        assert follow_redirects
        observed.append((url, timeout))
        return SimpleNamespace(status_code=200)

    monkeypatch.setattr("ccrelay.diagnostics.httpx.get", fake_get)

    checks = collect_online_checks(timeout=1.5)

    assert observed == [("https://github.com/login/device", 1.5)]
    assert checks[0].ok
    assert checks[0].detail == "HTTP 200"


def test_online_check_reports_network_failure(monkeypatch) -> None:
    request = httpx.Request("GET", "https://github.com/login/device")

    def fail(*_args: object, **_kwargs: object) -> object:
        raise httpx.ConnectError("offline", request=request)

    monkeypatch.setattr("ccrelay.diagnostics.httpx.get", fail)

    checks = collect_online_checks(timeout=1.0)

    assert not checks[0].ok
    assert "offline" in checks[0].detail
