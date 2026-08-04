from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_private_json(path: Path, payload: dict[str, Any]) -> None:
    write_private_text(path, json.dumps(payload, indent=2) + "\n")


def write_private_text(path: Path, content: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
        temporary_path.replace(path)
        path.chmod(mode)
    finally:
        temporary_path.unlink(missing_ok=True)
