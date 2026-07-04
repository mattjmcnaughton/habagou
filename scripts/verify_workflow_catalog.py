"""Validate the machine-readable workflow catalog."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from verify_traceability import Workflow, parse_workflows

ALLOWED_LAYERS = frozenset({"e2e", "integration", "unit"})
WORKFLOW_ID = re.compile(r"^WF-\d{2}$")

EXPECTED_WORKFLOWS = (
    Workflow(id="WF-01", title="Bootstrap", minimum_layers=("integration",)),
    Workflow(id="WF-02", title="Browse library", minimum_layers=("integration", "e2e")),
    Workflow(
        id="WF-03",
        title="Trace a pack",
        minimum_layers=("unit", "integration", "e2e"),
    ),
    Workflow(
        id="WF-04",
        title="Match a pack",
        minimum_layers=("unit", "integration", "e2e"),
    ),
    Workflow(
        id="WF-05",
        title="Sentence a pack",
        minimum_layers=("unit", "integration", "e2e"),
    ),
    Workflow(id="WF-06", title="Serve strokes", minimum_layers=("integration", "e2e")),
    Workflow(
        id="WF-07", title="Review progress", minimum_layers=("integration", "e2e")
    ),
    Workflow(id="WF-08", title="Reset progress", minimum_layers=("integration", "e2e")),
    Workflow(id="WF-09", title="Admin curate", minimum_layers=("integration",)),
    Workflow(id="WF-10", title="Deploy and serve", minimum_layers=("e2e",)),
)


def validate_catalog(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        workflows = parse_workflows(path)
    except Exception as exc:
        return [f"{path}: failed to parse workflow catalog: {exc}"]

    seen: set[str] = set()
    for workflow in workflows:
        if not WORKFLOW_ID.match(workflow.id):
            errors.append(f"{path}: invalid workflow id {workflow.id!r}")
        if workflow.id in seen:
            errors.append(f"{path}: duplicate workflow id {workflow.id}")
        seen.add(workflow.id)
        if not workflow.title:
            errors.append(f"{path}: {workflow.id} has empty title")
        if not workflow.minimum_layers:
            errors.append(f"{path}: {workflow.id} has no minimum_layers")
        invalid_layers = set(workflow.minimum_layers) - ALLOWED_LAYERS
        if invalid_layers:
            errors.append(
                f"{path}: {workflow.id} has invalid minimum_layers "
                f"{sorted(invalid_layers)}"
            )

    if tuple(workflows) != EXPECTED_WORKFLOWS:
        errors.append(
            f"{path}: catalog does not match docs/verification.md workflow table"
        )

    return errors


def main() -> int:
    docs_path = Path("docs/workflows.yml")
    packaged_path = Path("src/habagou/workflows.yml")
    errors = validate_catalog(docs_path)
    errors.extend(validate_catalog(packaged_path))

    if docs_path.read_text(encoding="utf-8") != packaged_path.read_text(
        encoding="utf-8"
    ):
        errors.append("docs/workflows.yml and src/habagou/workflows.yml differ")

    if errors:
        print("workflow catalog validation failed", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("workflow catalog validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
