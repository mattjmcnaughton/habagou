"""Eval harness CLI: ``uv run python -m evals`` (or ``just evals``).

Runs the generation dataset against one or more OpenRouter models and prints
a pydantic-evals report table per model. See docs/evals.md for the strategy
and docs/ci.md for the GitHub Actions wiring.

Exit codes:
    0  ran; every hard-floor assertion passed (soft scores never gate)
    1  a case failed the hard floor (corpus membership) or errored outright
    2  misconfiguration (no OPENROUTER_API_KEY and not --smoke)

Reads ``OPENROUTER_API_KEY`` via ``habagou.config.settings`` (environment or
``.env``). When ``$GITHUB_STEP_SUMMARY`` is set (GitHub Actions), the same
report tables are appended there as the job summary.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from evals.generation import (
    HARD_FLOOR_EVALUATOR,
    build_generation_task,
    load_generation_dataset,
    smoke_model,
)

if TYPE_CHECKING:
    from pydantic_ai.models import Model
    from pydantic_evals.reporting import EvaluationReport

# Wide enough that the report table never wraps mid-cell in CI logs.
_REPORT_WIDTH = 140


def _resolve_models(args: argparse.Namespace) -> list[tuple[str, Model]] | None:
    """The (label, model) pairs to evaluate, or None on misconfiguration."""
    if args.smoke:
        return [("smoke", smoke_model())]

    from habagou.config import settings

    if not settings.openrouter_api_key:
        print(
            "OPENROUTER_API_KEY is not set. Eval runs call the live provider; "
            "set the key (env or .env), or use --smoke for an offline "
            "plumbing check.",
            file=sys.stderr,
        )
        return None

    from habagou.services.openrouter import build_openrouter_model

    model_ids = [
        model_id.strip()
        for model_id in (args.models or "").split(",")
        if model_id.strip()
    ] or [settings.generation_model]
    return [(model_id, build_openrouter_model(model_id)) for model_id in model_ids]


def _case_payload(report: EvaluationReport[Any, Any, Any]) -> dict[str, Any]:
    """JSON-friendly per-case results for the --report artifact."""
    return {
        "cases": [
            {
                "name": case.name,
                "assertions": {
                    name: {"value": result.value, "reason": result.reason}
                    for name, result in case.assertions.items()
                },
                "metrics": dict(case.metrics),
                "task_duration": case.task_duration,
            }
            for case in report.cases
        ],
        "errors": [failure.name for failure in report.failures],
    }


def _hard_floor_failures(report: EvaluationReport[Any, Any, Any]) -> list[str]:
    """Case names that violated the hard floor or errored outright."""
    failed = [failure.name for failure in report.failures]
    for case in report.cases:
        result = case.assertions.get(HARD_FLOOR_EVALUATOR)
        if result is not None and not result.value:
            failed.append(case.name)
    return failed


def _append_step_summary(label: str, report: EvaluationReport[Any, Any, Any]) -> None:
    """Mirror the report table into the GitHub Actions job summary."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(
            f"## Generation evals — {label}\n\n"
            f"```\n{report.render(width=_REPORT_WIDTH, include_reasons=True)}```\n\n"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evals", description="Run the Habagou agent eval harness."
    )
    parser.add_argument(
        "--models",
        default="",
        help="comma-separated OpenRouter model ids "
        "(default: the configured generation model)",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="offline plumbing check with a stub model (no key, no network)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="also write the results as JSON to this path",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="concurrent cases per model (default: 4)",
    )
    args = parser.parse_args(argv)

    models = _resolve_models(args)
    if models is None:
        return 2

    dataset = load_generation_dataset()
    results: dict[str, Any] = {}
    hard_failures: dict[str, list[str]] = {}
    for label, model in models:
        report = asyncio.run(
            dataset.evaluate(
                build_generation_task(model),
                name=f"generation ({label})",
                max_concurrency=args.max_concurrency,
            )
        )
        report.print(width=_REPORT_WIDTH, include_reasons=True)
        _append_step_summary(label, report)
        results[label] = _case_payload(report)
        failed_cases = _hard_floor_failures(report)
        if failed_cases:
            hard_failures[label] = failed_cases

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps({"generation": results}, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {args.report}")

    if hard_failures:
        for label, case_names in hard_failures.items():
            print(
                f"HARD FLOOR FAILED [{label}]: {', '.join(case_names)} "
                f"(errored or drafted non-corpus glyphs after retries)",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
