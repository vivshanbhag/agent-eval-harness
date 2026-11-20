# Agent Eval Harness

Deterministic evaluation for tool-using agents. Scenarios define what a correct **trajectory** looks like — which tools, in what order, with which arguments, inside which budgets — and the harness turns runs into pass rates, pass@k, stability, cost, and a CI gate.

An agent that reaches the right answer by paging the on-call engineer for a healthy system has not passed. Answer-only evals cannot see that; trajectory evals can.

```
scenarios.json ──▶ Runner ──▶ Agent.run(task, budgets) ──▶ Trace (steps, answer, cost)
                     │                                          │
                     └───────── assertions + budgets ◀──────────┘
                                    │
                     pass@1 · pass@k · stability · cost · Markdown report · exit 1
```

## Quick start

No dependencies, Python 3.11+.

```bash
PYTHONPATH=src python3 -m agent_eval run \
  --scenarios examples/scenarios.json \
  --agent examples.demo_agent:build \
  --repeat 2
```

```
## Agent evaluation — PASS

- Runs: 8 · passed 8 (100%)
- pass@1 100% · pass@k 100% · stability 100%
- Mean tool calls 1.75 · total cost $0.0280

| Scenario | Runs | Passed | Stable | Mean steps | Mean ms |
| --- | ---: | ---: | :---: | ---: | ---: |
| `latency-alarm` | 2 | 2 | yes | 2.0 | 0 |
| `deploy-correlation` | 2 | 2 | yes | 2.0 | 0 |
| `escalation` | 2 | 2 | yes | 2.0 | 0 |
| `quiet-period` | 2 | 2 | yes | 1.0 | 0 |
```

The bundled demo agent is deterministic so the repository runs without API keys. Swap `--agent` for your own `module:factory` and nothing else changes.

## Scenarios

```json
{
  "id": "escalation",
  "task": "The primary database is unavailable and customers are affected. Page the on-call engineer.",
  "assert": {
    "required_tools": ["metrics_query", "page_oncall"],
    "arg_contains": { "page_oncall": { "severity": "sev1" } },
    "answer_contains": ["paged"],
    "max_tool_calls": 5
  },
  "budgets": { "max_tool_calls": 6, "max_cost_usd": 0.05 }
}
```

| Assertion | Meaning |
| --- | --- |
| `required_tools` | Must appear as an ordered subsequence; extra calls allowed |
| `forbidden_tools` | Any call fails the scenario, regardless of the answer |
| `arg_contains` | Every listed key/value must appear on a call to that tool |
| `answer_contains` / `answer_regex` | Final-answer checks, case-insensitive for `contains` |
| `max_tool_calls` | Trajectory length ceiling |
| `no_tool_errors` | No step may fail |

Budgets add `max_steps`, `max_cost_usd`, and `max_latency_ms`. Budget violations fail the run, so cost regressions are caught the same way correctness regressions are.

## Metrics

| Metric | Definition | Why it matters |
| --- | --- | --- |
| **pass@1** | Scenarios passing on the first attempt | The number a user experiences |
| **pass@k** | Scenarios passing at least once in k attempts | Separates "can do it" from "does it reliably" |
| **stability** | Scenarios whose attempts all agree | A flaky agent is worse than a slow one |
| **mean tool calls** | Steps per run | Detects agents that thrash |
| **total cost** | Summed `cost_usd` from traces | Keeps evals from becoming the budget |

## Record and replay

```bash
# Hit the model once, record every trajectory.
PYTHONPATH=src python3 -m agent_eval run --scenarios examples/scenarios.json \
  --agent my_agent:build --record reports/nightly.cassette.json

# Every CI run after that replays the recording: seconds, no tokens.
PYTHONPATH=src python3 -m agent_eval run --scenarios examples/scenarios.json \
  --replay reports/nightly.cassette.json --fail-under 0.95
```

A missing recording is reported as an error, never as an empty pass — a renamed scenario must not silently succeed.

## CI gate

```yaml
- run: PYTHONPATH=src python3 -m agent_eval run \
    --scenarios examples/scenarios.json \
    --replay reports/nightly.cassette.json \
    --md report.md --fail-under 0.95
```

Exit codes: `0` at or above the threshold, `1` below it, `2` for usage errors.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

11 tests cover ordering semantics, forbidden tools, argument checks, answer and budget failures, pass@k and stability, cassette round-trips, replay-miss behaviour, and both CLI exit paths.

## Design documents

- [`docs/HLD.md`](docs/HLD.md) — why trajectory evals, architecture, statistical model, failure modes, CI design.
- [`docs/LLD.md`](docs/LLD.md) — module contracts, scenario schema, assertion semantics, cassette format, extension guide.

## Limitations

- The harness evaluates; it does not host agents. Wiring a real model means implementing `run(task, budgets) -> Trace`.
- LLM-as-judge scoring is deliberately absent: it is nondeterministic, and this repository's value is that the gate is reproducible.
- Cassettes are keyed by task text; changing a scenario's wording invalidates its recording, by design.
- Latency budgets measure wall-clock time in the harness, which includes the agent's own overhead.
