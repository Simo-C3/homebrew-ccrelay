from __future__ import annotations

import stat

from ccrelay.settings import ensure_private_directory, make_proxy_key


def test_proxy_keys_are_random_and_prefixed() -> None:
    first = make_proxy_key()
    second = make_proxy_key()
    assert first.startswith("sk-ccrelay-")
    assert second.startswith("sk-ccrelay-")
    assert first != second


def test_private_directory_permissions(tmp_path) -> None:
    path = ensure_private_directory(tmp_path / "state")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o700
