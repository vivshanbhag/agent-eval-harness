"""Scenario loading.

A scenarios file is either a JSON list or an object with a `scenarios` key. A
directory is loaded in sorted order so reports are byte-identical between runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Scenario


def _scenarios_from_json(payload: object, source: Path) -> list[Scenario]:
    if isinstance(payload, dict):
        items = payload.get("scenarios")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a list or an object with a 'scenarios' list")
    scenarios = [Scenario.from_dict(item) for item in items]

    seen: set[str] = set()
    for scenario in scenarios:
        if scenario.id in seen:
            raise ValueError(f"{source}: duplicate scenario id {scenario.id!r}")
        seen.add(scenario.id)
    return scenarios


def load_scenarios(path: str | Path) -> list[Scenario]:
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"no such scenarios path: {target}")

    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    scenarios: list[Scenario] = []
    for file in files:
        scenarios.extend(_scenarios_from_json(json.loads(file.read_text(encoding="utf-8")), file))

    if not scenarios:
        raise ValueError(f"{target}: no scenarios found")
    return scenarios
