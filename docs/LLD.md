# Low-Level Design — Agent Eval Harness

## 1. Module map

| Module | Responsibility | Depends on |
| --- | --- | --- |
| `models.py` | Dataclasses for scenarios, traces, runs, reports | stdlib |
| `loader.py` | Parse and validate scenario JSON | `models` |
| `assertions.py` | Pure `evaluate(scenario, trace, duration_ms) -> list[str]` | `models` |
| `runner.py` | Execute scenarios × repeats | `assertions`, `models` |
| `agents.py` | `ScriptedAgent`, `RecordingAgent`, `ReplayAgent` | `cassette`, `models` |
| `cassette.py` | Versioned trace store | `models` |
| `report.py` | JSON and Markdown rendering | `models` |
| `__main__.py` | Flag parsing, wiring, exit codes | all of the above |

`assertions.py` is deliberately pure: the same function decides the verdict for a live run and a replay.

## 2. Scenario schema

```jsonc
{
  "id": "latency-alarm",              // required, unique across the suite
  "task": "…",                        // required, sent verbatim to the agent
  "description": "…",                 // optional
  "tags": ["triage"],                 // optional, for filtering/reporting
  "assert": {                         // optional, defaults below
    "required_tools": [],             // ordered subsequence
    "forbidden_tools": [],            // any occurrence fails
    "arg_contains": {},               // tool -> {key: value}
    "answer_contains": [],            // case-insensitive
    "answer_regex": null,             // Python re.search
    "max_tool_calls": null,
    "no_tool_errors": true
  },
  "budgets": {
    "max_steps": 12,
    "max_tool_calls": 8,
    "max_cost_usd": 0.10,
    "max_latency_ms": 30000
  }
}
```

Validation performed at load: unique ids, `scenarios` list present, each entry has `id` and `task`. Assertion values are not schema-validated beyond coercion; a typo surfaces as a failed scenario rather than a crash.

## 3. Assertion semantics

| Check | Rule | Failure message |
| --- | --- | --- |
| `required_tools` | Greedy subsequence match over `trace.steps[].tool` | `expected tools in order [...], got [...]` |
| `forbidden_tools` | Set intersection must be empty | `forbidden tool called: x` |
| `arg_contains` | For each tool with calls, some call has every listed pair | `tool never called with k=v` |
| `answer_contains` | Lowercased substring | `answer missing 'x'` |
| `answer_regex` | `re.search` | `answer does not match /…/` |
| `max_tool_calls` | `len(steps) <= n` | `N tool calls exceeds limit n` |
| `no_tool_errors` | All `step.ok` | `tool errors from [...]` |
| budgets | steps, cost, wall clock | `… exceeds budget …` |
| non-empty answer | `answer.strip()` | `empty final answer` |

Ordering note: subsequence matching means `[a, b]` passes for `a, x, b` but fails for `b, a`. Repetition is allowed.

## 4. Runner contract

```python
Runner(scenarios, agent).run(repeat: int) -> Report
```

- One `Run` per (scenario, attempt), in scenario order, attempts sequential.
- Duration is measured around `agent.run`.
- Exceptions from the agent are not caught: a crashing agent aborts the run rather than being scored as a failure.
- `Report` exposes `pass_rate`, `pass_at_k(k)`, `stability()`, `mean_tool_calls()`, `total_cost()`.

## 5. Cassette format

```json
{
  "version": 1,
  "entries": {
    "<task text>": {
      "steps": [{"tool": "a", "arguments": {}, "result": {}, "ok": true, "latency_ms": 0}],
      "answer": "…",
      "tokens": 0,
      "cost_usd": 0.0,
      "errors": []
    }
  }
}
```

- Keyed by task text so editing a scenario invalidates its recording.
- `version` is checked; unknown versions are rejected.
- A miss yields `Trace(errors=[...])`, which fails the scenario.

## 6. CLI

| Flag | Default | Meaning |
| --- | --- | --- |
| `--scenarios` | required | File or directory of JSON |
| `--agent` | — | `module:factory`, required unless `--replay` |
| `--repeat` | 1 | Attempts per scenario |
| `--record` | — | Write cassette after the run |
| `--replay` | — | Read cassette instead of calling the agent |
| `--json` | — | JSON report path |
| `--md` | — | Markdown report path |
| `--fail-under` | 0.0 | Exit 1 below this pass rate |
| `--quiet` | false | Suppress stdout report |

`run` is optional in argv: `agent-eval --scenarios …` works too.

## 7. Test matrix

| Area | Cases |
| --- | --- |
| Ordering | correct order passes; reversed fails |
| Safety | forbidden tool fails despite a good answer |
| Arguments | matching pair passes; mismatched value fails |
| Answer/budget | missing phrase, regex miss, step limit, cost limit |
| Trace hygiene | empty answer, failed tool step |
| Statistics | pass@1 vs pass@2 on a flaky agent; stability on disagreement |
| Cassette | round-trip; miss is an error |
| CLI | demo suite exits 0; broken suite exits 1 |

## 8. Extension points

- **New assertion** — add a field to `Assertions`, a check in `evaluate`, and a test. Keep `evaluate` pure.
- **New reporter** — consume `Report`; do not recompute metrics.
- **Parallel execution** — replace the loop in `Runner.run` with a pool; `Run` is already independent, but ordering must be restored for deterministic Markdown.
- **Tag filtering** — filter `scenarios` in the CLI before constructing `Runner`; no model change needed.
