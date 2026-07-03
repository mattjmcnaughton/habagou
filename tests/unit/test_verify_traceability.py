from __future__ import annotations

from pathlib import Path

from scripts.verify_traceability import (
    TaggedTest,
    Workflow,
    build_matrix,
    parse_junit,
    parse_workflows,
)


def test_parse_workflows_reads_catalog() -> None:
    workflows = parse_workflows(Path("docs/workflows.yml"))

    assert workflows[0] == Workflow(
        id="WF-01",
        title="Bootstrap",
        minimum_layers=("integration",),
    )
    assert workflows[2] == Workflow(
        id="WF-03",
        title="Trace a pack",
        minimum_layers=("unit", "integration", "e2e"),
    )


def test_parse_junit_reads_workflow_properties(tmp_path: Path) -> None:
    report = tmp_path / "unit.xml"
    report.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite>
    <testcase classname="tests.unit.test_trace" name="test_trace">
      <properties>
        <property name="layer" value="unit" />
        <property name="workflow" value="WF-03" />
      </properties>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    assert parse_junit(report) == [
        TaggedTest(
            workflow="WF-03",
            layer="unit",
            name="tests.unit.test_trace.test_trace",
            status="passed",
        )
    ]


def test_build_matrix_reports_missing_layers() -> None:
    markdown, failures = build_matrix(
        [Workflow(id="WF-03", title="Trace", minimum_layers=("unit", "e2e"))],
        [
            TaggedTest(
                workflow="WF-03", layer="unit", name="test_trace", status="passed"
            )
        ],
    )

    assert "| WF-03 | Trace | unit, e2e | missing e2e | unit: 1 |" in markdown
    assert failures == ["WF-03 missing required layer(s): e2e"]


def test_build_matrix_reports_failed_tagged_tests() -> None:
    _markdown, failures = build_matrix(
        [Workflow(id="WF-03", title="Trace", minimum_layers=("unit",))],
        [
            TaggedTest(
                workflow="WF-03", layer="unit", name="test_trace", status="failed"
            )
        ],
    )

    assert failures == [
        "WF-03 has non-passing tagged test in unit: test_trace (failed)",
        "WF-03 missing required layer(s): unit",
    ]
