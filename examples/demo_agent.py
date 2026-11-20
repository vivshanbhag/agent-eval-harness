"""A deterministic stand-in for a real agent.

It exists so the repository can be cloned and exercised end to end without API
keys. A real integration replaces `build()` with an adapter around the agent
under test; nothing else about the harness changes.
"""

from __future__ import annotations

from agent_eval import Budgets, Step, Trace


class DemoTriageAgent:
    def run(self, task: str, budgets: Budgets) -> Trace:
        text = task.lower()
        steps: list[Step] = []

        if "page" in text:
            steps.append(Step("metrics_query", {"service": "database", "metric": "availability"}, {"availability": 0.0}))
            steps.append(
                Step(
                    "page_oncall",
                    {"severity": "sev1", "summary": "primary database unavailable"},
                    {"paged": True},
                )
            )
            answer = "Confirmed the primary database is unavailable and paged the on-call engineer at sev1."

        elif "deploy" in text:
            steps.append(
                Step("deploy_history", {"service": "checkout", "window": "2h"}, {"deploys": [{"version": "v42", "at": "-40m"}]})
            )
            steps.append(Step("logs_search", {"query": "error", "window": "1h"}, {"matches": 12}))
            answer = "The error spike starts six minutes after deploy v42, so the deploy is the likely trigger."

        elif "latency" in text:
            steps.append(Step("metrics_query", {"service": "checkout", "metric": "p99_latency"}, {"value_ms": 2400}))
            steps.append(Step("logs_search", {"query": "timeout", "window": "30m"}, {"matches": 31}))
            answer = "Root cause: a saturated cache pool caused downstream timeouts, which drove the p99 latency spike."

        else:
            steps.append(Step("metrics_query", {"service": "all", "metric": "error_rate"}, {"value": 0.001}))
            answer = "All services look healthy: the error rate is flat and no alerts are firing."

        return Trace(steps=steps, answer=answer, tokens=120 + 35 * len(steps), cost_usd=0.002 * len(steps))


def build() -> DemoTriageAgent:
    return DemoTriageAgent()
