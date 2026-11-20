"""The runner: scenarios in, runs out."""

from __future__ import annotations

import time
from typing import Iterable

from .assertions import evaluate
from .models import Report, Run, Scenario
from .agents import Agent


class Runner:
    def __init__(self, scenarios: Iterable[Scenario], agent: Agent) -> None:
        self.scenarios = list(scenarios)
        if not self.scenarios:
            raise ValueError("no scenarios to run")
        self.agent = agent

    def run(self, repeat: int = 1) -> Report:
        """Run every scenario `repeat` times.

        Repeats exist because a single pass from a stochastic agent says very
        little; pass@k and stability are the numbers worth gating on.
        """
        if repeat < 1:
            raise ValueError("repeat must be at least 1")

        runs: list[Run] = []
        for scenario in self.scenarios:
            for _attempt in range(repeat):
                started = time.perf_counter()
                trace = self.agent.run(scenario.task, scenario.budgets)
                duration_ms = (time.perf_counter() - started) * 1000
                failures = evaluate(scenario, trace, duration_ms)
                runs.append(Run(scenario_id=scenario.id, trace=trace, duration_ms=duration_ms, failures=failures))
        return Report(runs=runs)
