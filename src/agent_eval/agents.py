"""Agent adapters.

The harness does not care how an agent is built, only that it exposes
`run(task, budgets) -> Trace`. That narrow interface is what lets the same
scenario suite evaluate a scripted baseline, a hosted model, and a replay of a
recorded run.
"""

from __future__ import annotations

from typing import Any, Protocol

from .cassette import Cassette
from .models import Budgets, Step, Trace


class Agent(Protocol):
    def run(self, task: str, budgets: Budgets) -> Trace: ...


class ScriptedAgent:
    """Returns a fixed trace. Used for tests, demos, and regression baselines."""

    def __init__(self, steps: list[Step], answer: str, *, tokens: int = 0, cost_usd: float = 0.0) -> None:
        self.steps = steps
        self.answer = answer
        self.tokens = tokens
        self.cost_usd = cost_usd

    def run(self, task: str, budgets: Budgets) -> Trace:
        return Trace(
            steps=[Step(**vars(step)) for step in self.steps],
            answer=self.answer,
            tokens=self.tokens,
            cost_usd=self.cost_usd,
        )


class RecordingAgent:
    """Wraps a real agent and records every trace for later replay."""

    def __init__(self, inner: Agent, cassette: Cassette) -> None:
        self.inner = inner
        self.cassette = cassette

    def run(self, task: str, budgets: Budgets) -> Trace:
        trace = self.inner.run(task, budgets)
        self.cassette.record(task, trace)
        return trace


class ReplayAgent:
    """Replays a recorded trace, so the suite can run in CI without a model.

    A missing recording is a failure, never a silent empty trace: otherwise a
    renamed scenario would pass by accident.
    """

    def __init__(self, cassette: Cassette) -> None:
        self.cassette = cassette

    def run(self, task: str, budgets: Budgets) -> Trace:
        recorded: dict[str, Any] | None = self.cassette.get(task)
        if recorded is None:
            return Trace(answer="", errors=[f"no cassette entry for task: {task[:60]}"])
        return Trace.from_dict(recorded)
