"""Reporters.

Two formats on purpose: JSON for tooling and history, Markdown for the pull
request comment a reviewer actually reads.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import Report


def to_dict(report: Report) -> dict:
    groups = report.by_scenario()
    scenarios = []
    for scenario_id, runs in groups.items():
        scenarios.append(
            {
                "scenario": scenario_id,
                "runs": len(runs),
                "passed": sum(1 for run in runs if run.passed),
                "stable": len({run.passed for run in runs}) == 1,
                "failures": sorted({failure for run in runs for failure in run.failures}),
                "mean_tool_calls": sum(run.trace.tool_calls for run in runs) / len(runs),
                "mean_duration_ms": round(sum(run.duration_ms for run in runs) / len(runs), 1),
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "summary": {
            "runs": report.total,
            "passed": report.passed,
            "pass_rate": round(report.pass_rate, 4),
            "pass_at_1": round(report.pass_at_k(1), 4),
            "pass_at_k": round(report.pass_at_k(max(len(r) for r in groups.values())), 4),
            "stability": round(report.stability(), 4),
            "mean_tool_calls": round(report.mean_tool_calls(), 2),
            "total_cost_usd": round(report.total_cost(), 4),
        },
        "scenarios": scenarios,
    }


def to_json(report: Report) -> str:
    return json.dumps(to_dict(report), indent=2, sort_keys=True)


def to_markdown(report: Report) -> str:
    data = to_dict(report)
    summary = data["summary"]
    verdict = "PASS" if report.pass_rate == 1.0 else "FAIL"
    lines = [
        f"## Agent evaluation — {verdict}",
        "",
        f"- Runs: **{summary['runs']}** · passed **{summary['passed']}** ({summary['pass_rate'] * 100:.0f}%)",
        f"- pass@1 **{summary['pass_at_1'] * 100:.0f}%** · pass@k **{summary['pass_at_k'] * 100:.0f}%** · stability **{summary['stability'] * 100:.0f}%**",
        f"- Mean tool calls **{summary['mean_tool_calls']}** · total cost **${summary['total_cost_usd']:.4f}**",
        "",
        "| Scenario | Runs | Passed | Stable | Mean steps | Mean ms |",
        "| --- | ---: | ---: | :---: | ---: | ---: |",
    ]
    for scenario in data["scenarios"]:
        lines.append(
            f"| `{scenario['scenario']}` | {scenario['runs']} | {scenario['passed']} | "
            f"{'yes' if scenario['stable'] else 'no'} | {scenario['mean_tool_calls']:.1f} | {scenario['mean_duration_ms']:.0f} |"
        )
    failures = [(s["scenario"], f) for s in data["scenarios"] for f in s["failures"]]
    if failures:
        lines += ["", "### Failures", ""]
        for scenario_id, failure in failures:
            lines.append(f"- `{scenario_id}` — {failure}")
    return "\n".join(lines) + "\n"
