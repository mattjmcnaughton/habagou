"""Verify workflow test coverage from test report artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORKFLOW_ID = re.compile(r"WF-\d{2}")


@dataclass(frozen=True)
class Workflow:
    id: str
    title: str
    minimum_layers: tuple[str, ...]


@dataclass(frozen=True)
class TaggedTest:
    workflow: str
    layer: str
    name: str
    status: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workflows", type=Path, default=Path("src/habagou/workflows.yml")
    )
    parser.add_argument("--reports", type=Path, default=Path(".artifacts/test-results"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".artifacts/traceability/workflow-matrix.md"),
    )
    args = parser.parse_args()

    workflows = parse_workflows(args.workflows)
    tests = collect_reports(args.reports)
    markdown, failures = build_matrix(workflows, tests)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(f"Traceability matrix written to {args.output}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Traceability matrix written to {args.output}")


def parse_workflows(path: Path) -> list[Workflow]:
    workflows: list[Workflow] = []
    current_id: str | None = None
    current_title: str | None = None
    current_layers: tuple[str, ...] | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            if current_id is not None:
                workflows.append(_workflow(current_id, current_title, current_layers))
            current_id = stripped.removeprefix("- id:").strip()
            current_title = None
            current_layers = None
        elif stripped.startswith("title:"):
            current_title = stripped.removeprefix("title:").strip()
        elif stripped.startswith("minimum_layers:"):
            current_layers = _parse_layers(stripped)

    if current_id is not None:
        workflows.append(_workflow(current_id, current_title, current_layers))

    return workflows


def collect_reports(reports_dir: Path) -> list[TaggedTest]:
    if not reports_dir.exists():
        raise SystemExit(f"test report directory does not exist: {reports_dir}")

    tests: list[TaggedTest] = []
    for path in sorted(reports_dir.rglob("*.xml")):
        tests.extend(parse_junit(path))
    for path in sorted(reports_dir.rglob("*.json")):
        tests.extend(parse_playwright_json(path))
    return tests


def parse_junit(path: Path) -> list[TaggedTest]:
    root = ET.parse(path).getroot()
    tests: list[TaggedTest] = []
    for testcase in root.iter("testcase"):
        properties = _properties(testcase)
        workflows = properties.get("workflow", [])
        layer = _one(properties.get("layer", []), default=_layer_from_report_name(path))
        name = _testcase_name(testcase)
        status = _junit_status(testcase)
        for workflow in workflows:
            tests.append(
                TaggedTest(
                    workflow=workflow,
                    layer=layer,
                    name=name,
                    status=status,
                )
            )
    return tests


def parse_playwright_json(path: Path) -> list[TaggedTest]:
    document = json.loads(path.read_text(encoding="utf-8"))
    tests: list[TaggedTest] = []
    for item in _walk_json(document):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        workflows = WORKFLOW_ID.findall(title)
        if not workflows:
            continue
        status = _playwright_status(item)
        for workflow in workflows:
            tests.append(
                TaggedTest(
                    workflow=workflow,
                    layer="e2e",
                    name=title,
                    status=status,
                )
            )
    return tests


def build_matrix(
    workflows: list[Workflow], tests: list[TaggedTest]
) -> tuple[str, list[str]]:
    by_workflow: dict[str, dict[str, list[TaggedTest]]] = {}
    failures: list[str] = []

    for test in tests:
        by_workflow.setdefault(test.workflow, {}).setdefault(test.layer, []).append(
            test
        )
        if test.status != "passed":
            failures.append(
                f"{test.workflow} has non-passing tagged test in {test.layer}: "
                f"{test.name} ({test.status})"
            )

    lines = [
        "# Workflow Traceability Matrix",
        "",
        "| Workflow | Title | Required layers | Status | Tagged tests |",
        "|---|---|---|---|---|",
    ]

    for workflow in workflows:
        present = by_workflow.get(workflow.id, {})
        missing = [
            layer
            for layer in workflow.minimum_layers
            if not any(test.status == "passed" for test in present.get(layer, []))
        ]
        if missing:
            failures.append(
                f"{workflow.id} missing required layer(s): {', '.join(missing)}"
            )
        lines.append(
            "| "
            + " | ".join(
                [
                    workflow.id,
                    workflow.title,
                    ", ".join(workflow.minimum_layers),
                    "missing " + ", ".join(missing) if missing else "ok",
                    _format_test_counts(present),
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n", failures


def _workflow(
    workflow_id: str,
    title: str | None,
    layers: tuple[str, ...] | None,
) -> Workflow:
    if title is None or layers is None:
        raise ValueError(f"incomplete workflow catalog entry: {workflow_id}")
    return Workflow(id=workflow_id, title=title, minimum_layers=layers)


def _parse_layers(line: str) -> tuple[str, ...]:
    raw = line.removeprefix("minimum_layers:").strip()
    if not raw.startswith("[") or not raw.endswith("]"):
        raise ValueError(f"unsupported minimum_layers syntax: {line}")
    return tuple(part.strip() for part in raw[1:-1].split(",") if part.strip())


def _properties(testcase: ET.Element) -> dict[str, list[str]]:
    properties: dict[str, list[str]] = {}
    for prop in testcase.findall("./properties/property"):
        name = prop.attrib.get("name")
        value = prop.attrib.get("value")
        if name and value:
            properties.setdefault(name, []).append(value)
    return properties


def _one(values: list[str], *, default: str) -> str:
    return values[0] if values else default


def _layer_from_report_name(path: Path) -> str:
    name = path.stem
    for layer in ("unit", "integration", "e2e"):
        if layer in name:
            return layer
    return "unknown"


def _testcase_name(testcase: ET.Element) -> str:
    classname = testcase.attrib.get("classname", "")
    name = testcase.attrib.get("name", "")
    return f"{classname}.{name}" if classname else name


def _junit_status(testcase: ET.Element) -> str:
    if testcase.find("failure") is not None:
        return "failed"
    if testcase.find("error") is not None:
        return "error"
    if testcase.find("skipped") is not None:
        return "skipped"
    return "passed"


def _walk_json(value: Any) -> list[Any]:
    found = [value]
    if isinstance(value, dict):
        for child in value.values():
            found.extend(_walk_json(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_walk_json(child))
    return found


def _playwright_status(item: dict[str, Any]) -> str:
    status = item.get("status")
    if isinstance(status, str):
        return "passed" if status in {"passed", "expected"} else status
    if item.get("ok") is True:
        return "passed"
    return "unknown"


def _format_test_counts(tests_by_layer: dict[str, list[TaggedTest]]) -> str:
    if not tests_by_layer:
        return "-"
    return ", ".join(
        f"{layer}: {sum(test.status == 'passed' for test in tests)}"
        for layer, tests in sorted(tests_by_layer.items())
    )


if __name__ == "__main__":
    main()
