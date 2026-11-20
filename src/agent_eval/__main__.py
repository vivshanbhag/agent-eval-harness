"""Command line entry point.

    agent-eval run --scenarios examples/scenarios.json \
        --agent examples.demo_agent:build --repeat 3 \
        --md report.md --fail-under 0.9
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from .agents import RecordingAgent, ReplayAgent
from .cassette import Cassette
from .loader import load_scenarios
from .report import to_json, to_markdown
from .runner import Runner


def load_agent(spec: str):
    if ":" not in spec:
        raise SystemExit(f"--agent must look like 'module:factory', got {spec!r}")
    module_name, factory_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SystemExit(f"could not import {module_name!r}: {exc}") from exc
    factory = getattr(module, factory_name, None)
    if factory is None:
        raise SystemExit(f"{module_name!r} has no attribute {factory_name!r}")
    return factory()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-eval", description="Deterministic evaluation for tool-using agents")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="run a scenario suite")
    run.add_argument("--scenarios", required=True, help="scenario JSON file or directory")
    run.add_argument("--agent", help="agent factory as module:callable")
    run.add_argument("--repeat", type=int, default=1, help="attempts per scenario (default 1)")
    run.add_argument("--record", help="write recorded traces to this cassette")
    run.add_argument("--replay", help="replay traces from this cassette instead of calling a model")
    run.add_argument("--json", dest="json_out", help="write the JSON report here")
    run.add_argument("--md", dest="md_out", help="write the Markdown report here")
    run.add_argument("--fail-under", type=float, default=0.0, help="exit 1 when pass rate falls below this")
    run.add_argument("--quiet", action="store_true", help="do not print the report")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["run", *argv]
    args = build_parser().parse_args(argv)
    if args.command != "run":
        build_parser().print_help()
        return 2

    if not args.agent and not args.replay:
        raise SystemExit("provide --agent module:factory (or --replay cassette.json)")

    scenarios = load_scenarios(args.scenarios)

    if args.replay:
        agent = ReplayAgent(Cassette.load(args.replay))
    else:
        agent = load_agent(args.agent)

    cassette = None
    if args.record:
        cassette = Cassette()
        agent = RecordingAgent(agent, cassette)

    report = Runner(scenarios, agent).run(repeat=args.repeat)

    if cassette is not None:
        cassette.save(args.record)

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(to_json(report) + "\n", encoding="utf-8")
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(to_markdown(report), encoding="utf-8")
    if not args.quiet:
        sys.stdout.write(to_markdown(report))

    if report.pass_rate < args.fail_under:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
