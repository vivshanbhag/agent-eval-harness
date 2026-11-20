# High-Level Design — Agent Eval Harness

## 1. Problem

Agent quality is usually judged by demos: a prompt, a happy path, a screenshot. That breaks down for four reasons:

1. **Lucky guesses.** An agent that answers correctly without investigating passes an answer-only check.
2. **Unsafe success.** Paging an engineer for a healthy system still "works" if the summary looks good.
3. **Nondeterminism.** One green run says little; the interesting question is whether it is green *consistently*.
4. **Cost drift.** Prompts and models change token spend per task, and nothing notices until the invoice.

The harness makes the trajectory the unit of correctness, then reports the statistics a reviewer needs.

## 2. Goals and non-goals

**Goals**

- Express correctness as assertions over tool calls, arguments, answers, and budgets.
- Produce pass@1, pass@k, stability, step count, and cost from the same run.
- Run identically in CI without a model, via recorded cassettes.
- Fail a build on regression with a single exit code.

**Non-goals**

- Hosting or orchestrating agents.
- Judging free-form prose quality.
- Replacing unit tests: this checks behaviour of a stochastic system, not pure functions.

## 3. Architecture

```
                 ┌──────────────────────────────┐
scenarios.json ─▶│ loader    parse + validate   │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐        ┌────────────────────┐
                 │ Runner    repeat × scenario  │───────▶│ Agent              │
                 │                              │◀───────│ run(task, budgets) │
                 └──────────────┬───────────────┘ Trace  └────────────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ assertions  trajectory+budget │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │ Report  JSON · Markdown · gate│
                 └──────────────────────────────┘
```

Everything between the agent and the report is pure: same trace in, same verdict out. That is what makes replay trustworthy.

## 4. Key decisions

| Decision | Alternative | Why |
| --- | --- | --- |
| Assert on ordered tool subsequence | Exact sequence equality | Agents legitimately add read-only calls; forbidding them makes tests brittle |
| Separate `required` and `forbidden` tools | One allowlist | Safety is a different question from completeness |
| Budgets fail the run | Budgets warn | A cost regression is a regression |
| Replay instead of judge | LLM-as-judge | A gate must be reproducible and cheap |
| Cassette keyed by task text | Keyed by scenario id | Forces a recording to be invalidated when the task changes |
| Repeat + pass@k | Single run | Stochastic systems need a stability number |

## 5. Statistical model

For `k` attempts per scenario:

- **pass@1** = scenarios whose first attempt passes / scenarios.
- **pass@k** = scenarios passing at least once in k attempts / scenarios.
- **stability** = scenarios where all attempts agree / scenarios.

Reporting all three avoids the classic trap of quoting pass@k while shipping a 40% flake rate. `pass@1 == pass@k == 1.0` is the only configuration that means "this works".

## 6. Failure modes

| Failure | Detection | Behaviour |
| --- | --- | --- |
| Agent raises | Not caught by the runner | Surfaces as a test error; the run aborts loudly (a crashed agent is not a failed scenario) |
| Agent returns no trace | Empty trace | Fails on `empty final answer` |
| Scenario file invalid | Loader | `ValueError` with file and reason, before any model call |
| Duplicate scenario ids | Loader | Rejected at load |
| Cassette miss | Replay agent | Trace with an error, so the scenario fails with a clear reason |
| Cassette version drift | Loader | Rejected rather than guessed |
| Threshold not met | CLI | Exit 1, Markdown report written |

A deliberate asymmetry: scenario mistakes are loud and early; agent mistakes are recorded as failed runs. Confusing the two wastes hours.

## 7. CI integration

```yaml
name: agent-eval
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: PYTHONPATH=src python3 -m unittest discover -s tests
      - run: |
          PYTHONPATH=src python3 -m agent_eval run \
            --scenarios examples/scenarios.json \
            --replay reports/nightly.cassette.json \
            --md report.md --fail-under 0.95
```

Replay keeps pull-request runs deterministic and free. A nightly job re-records against the live model and opens a follow-up commit when traces drift.

## 8. Scale

- Scenarios are independent, so a run parallelises across scenarios trivially; the current runner is sequential for readable output.
- Cassettes grow with scenarios × attempts; keying by task text keeps them compressible and diff-friendly.
- For large suites, sharding by tag (`--tag` filter is the natural next flag) keeps a single job under the runner limit.

## 9. What this proves to a reviewer

That the author thinks about agents as production systems: correctness is behavioural, safety is asserted, cost is a first-class metric, and the gate runs on every pull request rather than in a demo.
