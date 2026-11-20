"""Core data model.

A scenario is the test; a trace is what the agent actually did. Everything the
harness reports is derived from those two objects, which keeps the runner
deterministic and the reporters trivial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    ok: bool = True
    latency_ms: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        return cls(
            tool=data["tool"],
            arguments=dict(data.get("arguments") or {}),
            result=data.get("result"),
            ok=bool(data.get("ok", True)),
            latency_ms=float(data.get("latency_ms", 0.0)),
        )


@dataclass
class Trace:
    steps: list[Step] = field(default_factory=list)
    answer: str = ""
    tokens: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def tool_calls(self) -> int:
        return len(self.steps)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trace":
        return cls(
            steps=[Step.from_dict(step) for step in data.get("steps", [])],
            answer=data.get("answer", ""),
            tokens=int(data.get("tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            errors=list(data.get("errors", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [
                {"tool": s.tool, "arguments": s.arguments, "result": s.result, "ok": s.ok, "latency_ms": s.latency_ms}
                for s in self.steps
            ],
            "answer": self.answer,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "errors": self.errors,
        }


@dataclass
class Budgets:
    max_steps: int = 12
    max_tool_calls: int = 8
    max_cost_usd: float = 0.10
    max_latency_ms: float = 30_000.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Budgets":
        data = data or {}
        return cls(
            max_steps=int(data.get("max_steps", 12)),
            max_tool_calls=int(data.get("max_tool_calls", 8)),
            max_cost_usd=float(data.get("max_cost_usd", 0.10)),
            max_latency_ms=float(data.get("max_latency_ms", 30_000.0)),
        )


@dataclass
class Assertions:
    """What a correct trajectory must look like.

    Trajectory assertions are the point: checking only the final answer lets a
    lucky guess pass, and lets an unsafe tool call hide behind a good summary.
    """

    required_tools: list[str] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)
    arg_contains: dict[str, dict[str, Any]] = field(default_factory=dict)
    answer_contains: list[str] = field(default_factory=list)
    answer_regex: str | None = None
    max_tool_calls: int | None = None
    no_tool_errors: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Assertions":
        data = data or {}
        return cls(
            required_tools=list(data.get("required_tools", [])),
            forbidden_tools=list(data.get("forbidden_tools", [])),
            arg_contains={tool: dict(values) for tool, values in (data.get("arg_contains") or {}).items()},
            answer_contains=list(data.get("answer_contains", [])),
            answer_regex=data.get("answer_regex"),
            max_tool_calls=data.get("max_tool_calls"),
            no_tool_errors=bool(data.get("no_tool_errors", True)),
        )


@dataclass
class Scenario:
    id: str
    task: str
    assertions: Assertions = field(default_factory=Assertions)
    budgets: Budgets = field(default_factory=Budgets)
    tags: list[str] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        return cls(
            id=data["id"],
            task=data["task"],
            assertions=Assertions.from_dict(data.get("assert")),
            budgets=Budgets.from_dict(data.get("budgets")),
            tags=list(data.get("tags", [])),
            description=data.get("description", ""),
        )


@dataclass
class Run:
    """One attempt at one scenario."""

    scenario_id: str
    trace: Trace
    duration_ms: float
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass
class Report:
    runs: list[Run]

    # -- aggregates -------------------------------------------------------

    def by_scenario(self) -> dict[str, list[Run]]:
        grouped: dict[str, list[Run]] = {}
        for run in self.runs:
            grouped.setdefault(run.scenario_id, []).append(run)
        return grouped

    @property
    def total(self) -> int:
        return len(self.runs)

    @property
    def passed(self) -> int:
        return sum(1 for run in self.runs if run.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def pass_at_k(self, k: int) -> float:
        """Fraction of scenarios that pass in at least one of their first k runs."""
        scores = []
        for runs in self.by_scenario().values():
            attempts = runs[:k]
            scores.append(1.0 if any(run.passed for run in attempts) else 0.0)
        return sum(scores) / len(scores) if scores else 0.0

    def stability(self) -> float:
        """Fraction of scenarios whose runs all agree with each other."""
        stable = 0
        groups = self.by_scenario()
        for runs in groups.values():
            outcomes = {run.passed for run in runs}
            stable += 1 if len(outcomes) == 1 else 0
        return stable / len(groups) if groups else 0.0

    def mean_tool_calls(self) -> float:
        if not self.runs:
            return 0.0
        return sum(run.trace.tool_calls for run in self.runs) / len(self.runs)

    def total_cost(self) -> float:
        return sum(run.trace.cost_usd for run in self.runs)
