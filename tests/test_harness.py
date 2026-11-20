"""Tests for assertions, metrics, replay, and the CLI gate."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_eval import (
    Budgets,
    Cassette,
    ReplayAgent,
    Runner,
    Scenario,
    ScriptedAgent,
    Step,
    Trace,
    to_markdown,
)
from agent_eval.__main__ import main
from agent_eval.assertions import evaluate
from agent_eval.models import Assertions


def scenario(**overrides) -> Scenario:
    base = Scenario(id="s1", task="do the thing")
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


class AssertionTests(unittest.TestCase):
    def test_required_tools_must_appear_in_order(self) -> None:
        trace = Trace(steps=[Step("a"), Step("b")], answer="done")
        self.assertEqual(evaluate(scenario(assertions=Assertions(required_tools=["a", "b"])), trace, 1.0), [])
        failures = evaluate(scenario(assertions=Assertions(required_tools=["b", "a"])), trace, 1.0)
        self.assertTrue(any("expected tools in order" in f for f in failures))

    def test_forbidden_tool_fails_even_with_a_good_answer(self) -> None:
        trace = Trace(steps=[Step("page_oncall")], answer="all good")
        failures = evaluate(scenario(assertions=Assertions(forbidden_tools=["page_oncall"], answer_contains=["good"])), trace, 1.0)
        self.assertTrue(any("forbidden tool" in f for f in failures))

    def test_argument_assertions(self) -> None:
        trace = Trace(steps=[Step("query", {"metric": "p99"})], answer="ok")
        self.assertEqual(evaluate(scenario(assertions=Assertions(arg_contains={"query": {"metric": "p99"}})), trace, 1.0), [])
        failures = evaluate(scenario(assertions=Assertions(arg_contains={"query": {"metric": "p50"}})), trace, 1.0)
        self.assertTrue(any("p50" in f for f in failures))

    def test_answer_and_budget_checks(self) -> None:
        trace = Trace(steps=[Step("a")] * 3, answer="short", cost_usd=0.5)
        failures = evaluate(
            scenario(
                assertions=Assertions(answer_contains=["root cause"], answer_regex=r"RC-\d+", max_tool_calls=2),
                budgets=Budgets(max_cost_usd=0.1),
            ),
            trace,
            50_000,
        )
        joined = " | ".join(failures)
        self.assertIn("answer missing", joined)
        self.assertIn("does not match", joined)
        self.assertIn("exceeds limit", joined)
        self.assertIn("exceeds budget", joined)

    def test_empty_answer_and_tool_errors(self) -> None:
        trace = Trace(steps=[Step("a", ok=False)], answer="")
        failures = evaluate(scenario(), trace, 1.0)
        self.assertTrue(any("empty final answer" in f for f in failures))
        self.assertTrue(any("tool errors" in f for f in failures))


class FlakyAgent:
    """Fails the first attempt, passes the second: pass@1 < pass@2."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, task: str, budgets: Budgets) -> Trace:
        self.calls += 1
        if self.calls == 1:
            return Trace(steps=[], answer="")
        return Trace(steps=[Step("a")], answer="ok")


class RunnerTests(unittest.TestCase):
    def test_pass_at_k_and_stability(self) -> None:
        scenarios = [Scenario(id="s1", task="t", assertions=Assertions(required_tools=["a"], answer_contains=["ok"]))]
        report = Runner(scenarios, FlakyAgent()).run(repeat=2)
        self.assertEqual(report.total, 2)
        self.assertAlmostEqual(report.pass_at_k(1), 0.0)
        self.assertAlmostEqual(report.pass_at_k(2), 1.0)
        self.assertAlmostEqual(report.stability(), 0.0)

    def test_markdown_contains_summary_and_failures(self) -> None:
        scenarios = [Scenario(id="broken", task="t", assertions=Assertions(required_tools=["missing"]))]
        report = Runner(scenarios, ScriptedAgent([], "done")).run()
        markdown = to_markdown(report)
        self.assertIn("Agent evaluation — FAIL", markdown)
        self.assertIn("`broken`", markdown)


class CassetteTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        cassette = Cassette()
        cassette.record("task text", Trace(steps=[Step("a", {"x": 1})], answer="ok", tokens=5))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cassette.json"
            cassette.save(path)
            restored = Cassette.load(path)
        self.assertEqual(len(restored), 1)
        replayed = ReplayAgent(restored).run("task text", Budgets())
        self.assertEqual(replayed.answer, "ok")
        self.assertEqual(replayed.steps[0].arguments, {"x": 1})

    def test_missing_entry_is_an_error_not_an_empty_pass(self) -> None:
        trace = ReplayAgent(Cassette()).run("unknown task", Budgets())
        self.assertTrue(trace.errors)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_demo_suite_passes_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            markdown_path = Path(tmp) / "report.md"
            code = main(
                [
                    "run",
                    "--scenarios",
                    str(self.root / "examples" / "scenarios.json"),
                    "--agent",
                    "examples.demo_agent:build",
                    "--repeat",
                    "2",
                    "--md",
                    str(markdown_path),
                    "--fail-under",
                    "1.0",
                    "--quiet",
                ]
            )
            report = markdown_path.read_text()
        self.assertEqual(code, 0)
        self.assertIn("Agent evaluation — PASS", report)

    def test_gate_fails_when_a_scenario_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenarios = Path(tmp) / "scenarios.json"
            scenarios.write_text(
                json.dumps({"scenarios": [{"id": "impossible", "task": "t", "assert": {"required_tools": ["never_called"]}}]})
            )
            code = main(
                [
                    "run",
                    "--scenarios",
                    str(scenarios),
                    "--agent",
                    "examples.demo_agent:build",
                    "--fail-under",
                    "0.9",
                    "--quiet",
                ]
            )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
