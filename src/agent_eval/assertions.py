"""Assertions: turn a trace into a list of human-readable failures."""

from __future__ import annotations

import re

from .models import Scenario, Trace


def _is_subsequence(required: list[str], actual: list[str]) -> bool:
    cursor = 0
    for tool in actual:
        if cursor < len(required) and tool == required[cursor]:
            cursor += 1
    return cursor == len(required)


def evaluate(scenario: Scenario, trace: Trace, duration_ms: float) -> list[str]:
    failures: list[str] = []
    assertions = scenario.assertions
    budgets = scenario.budgets
    tools = [step.tool for step in trace.steps]

    # Trajectory: order matters, repetition does not.
    if assertions.required_tools and not _is_subsequence(assertions.required_tools, tools):
        failures.append(
            f"expected tools in order {assertions.required_tools}, got {tools}"
        )

    for forbidden in assertions.forbidden_tools:
        if forbidden in tools:
            failures.append(f"forbidden tool called: {forbidden}")

    for tool, expected in assertions.arg_contains.items():
        matching = [step for step in trace.steps if step.tool == tool]
        if not matching:
            failures.append(f"no call to {tool}; cannot check arguments")
            continue
        for key, value in expected.items():
            if not any(step.arguments.get(key) == value for step in matching):
                failures.append(f"{tool} never called with {key}={value!r}")

    # Answer quality.
    for needle in assertions.answer_contains:
        if needle.lower() not in trace.answer.lower():
            failures.append(f"answer missing {needle!r}")

    if assertions.answer_regex and not re.search(assertions.answer_regex, trace.answer):
        failures.append(f"answer does not match /{assertions.answer_regex}/")

    # Behavioural budgets.
    if assertions.max_tool_calls is not None and trace.tool_calls > assertions.max_tool_calls:
        failures.append(f"{trace.tool_calls} tool calls exceeds limit {assertions.max_tool_calls}")
    if assertions.no_tool_errors:
        broken = [step.tool for step in trace.steps if not step.ok]
        if broken:
            failures.append(f"tool errors from {sorted(set(broken))}")
    if trace.errors:
        failures.append(f"agent reported errors: {trace.errors[0]}")

    # Cost, step, and latency budgets.
    if trace.tool_calls > budgets.max_tool_calls:
        failures.append(f"{trace.tool_calls} tool calls exceeds budget {budgets.max_tool_calls}")
    if trace.cost_usd > budgets.max_cost_usd:
        failures.append(f"cost ${trace.cost_usd:.4f} exceeds budget ${budgets.max_cost_usd:.4f}")
    if duration_ms > budgets.max_latency_ms:
        failures.append(f"duration {duration_ms:.0f}ms exceeds budget {budgets.max_latency_ms:.0f}ms")
    if not trace.answer.strip():
        failures.append("empty final answer")

    return failures
