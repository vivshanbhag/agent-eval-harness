"""Record and replay traces.

Replay is the difference between an eval suite that runs on every pull request
and one that runs when someone remembers to pay for tokens.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Trace


class Cassette:
    def __init__(self, entries: dict[str, dict[str, Any]] | None = None) -> None:
        self._entries: dict[str, dict[str, Any]] = entries or {}

    def record(self, key: str, trace: Trace) -> None:
        self._entries[key] = trace.to_dict()

    def get(self, key: str) -> dict[str, Any] | None:
        return self._entries.get(key)

    def __len__(self) -> int:
        return len(self._entries)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": self._entries}
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Cassette":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError(f"unsupported cassette version: {data.get('version')!r}")
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise ValueError("cassette is missing its entries map")
        return cls(entries)
