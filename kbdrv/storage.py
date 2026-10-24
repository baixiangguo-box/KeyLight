"""Atomic UTF-8 JSON persistence. Callers hold LOCK for read/modify/write."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

LOCK = threading.RLock()


def read_json(path: Path, default):
    with LOCK:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, type(default)) else default
        except (OSError, ValueError, UnicodeError):
            return default


def write_json(path: Path, data) -> None:
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
                json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
