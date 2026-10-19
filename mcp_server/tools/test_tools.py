"""Run pytest and return structured results. These tools do not edit code."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from fastmcp import FastMCP

from mcp_server.dependencies import FAILURE_TEXT_LIMIT, repo_root, test_suite_targets, truncate
from mcp_server.fingerprint import source_token
from mcp_server.results_cache import get as cache_get
from mcp_server.results_cache import put as cache_put
from mcp_server.tools.git_tools import get_recent_changes
from mcp_server.tools.health_tools import check_api_health, violations_from_health

_TIMEOUT_SECONDS = 180


def run_targeted_tests(nodeids: list[str]) -> dict:
    """Run the given pytest node ids and return structured pass/fail results.

    Pass the `recommended_nodeids` from analyze_impact. This does not run the
    full suite. A repeat call for the same node ids and the same tree reuses
    the previous result.
    """
    selected = [nodeid.strip() for nodeid in nodeids if nodeid and nodeid.strip()]
    if not selected:
        return {
            "ok": False,
            "error": (
                "Provide at least one pytest node id. "
                "Use run_full_tests for the repository suite."
            ),
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "tests": [],
        }
    return _run_pytest(selected)


def run_full_tests() -> dict:
    """Run the repository suite and return structured results.

    Uses ``tests/unit`` and ``tests/integration`` when those directories exist.
    Other layouts are discovered, and ``GUARDIAN_TEST_PATHS`` overrides them.
    A repository with no tests returns a passing empty result instead of a
    pytest error. A repeat call for the same tree reuses the previous result.
    """
    targets = test_suite_targets()
    if not targets:
        return {
            "ok": True,
            "error": None,
            "message": "No test suite was found in this repository.",
            "command": [],
            "exit_code": 0,
            "all_passed": True,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "tests": [],
            "suite": [],
        }
    report = _run_pytest(targets)
    report["suite"] = targets
    return report


def get_failure_evidence(
    nodeids: list[str] | None = None,
    base_url: str | None = None,
) -> dict:
    """Collect contract violations, the latest Git change, and failing tests.

    When node ids are provided, only those tests run. Otherwise the repository
    suite runs. The contract report and the health report come from one probe.
    Application evidence is the live probe response, because this sample API
    does not write a separate log file.
    """
    if nodeids:
        test_run = run_targeted_tests(nodeids)
    else:
        test_run = run_full_tests()

    health = check_api_health(base_url)
    violations = violations_from_health(health)
    changes = get_recent_changes(limit=1)
    failures = [
        test
        for test in test_run.get("tests", [])
        if test["outcome"] != "passed"
    ]
    latest = (changes.get("recent_commits") or [None])[0]

    return {
        "summary": _evidence_summary(test_run, violations, len(failures)),
        "test_failures": failures,
        "test_run": {
            "ok": test_run.get("ok"),
            "passed": test_run.get("passed", 0),
            "failed": test_run.get("failed", 0),
            "errors": test_run.get("errors", 0),
            "exit_code": test_run.get("exit_code"),
            "error": test_run.get("error"),
        },
        "contract_violations": violations,
        "api_health": health,
        "recent_change": {
            "branch": changes.get("branch"),
            "head": changes.get("head"),
            "latest_commit": latest,
            "working_tree_dirty": changes.get("working_tree_dirty"),
            "latest_diff": changes.get("latest_diff"),
        },
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(run_targeted_tests)
    mcp.tool(run_full_tests)
    mcp.tool(get_failure_evidence)


def _run_pytest(targets: list[str]) -> dict:
    key = ("pytest", str(repo_root()), tuple(targets), source_token())
    cached = cache_get(key)
    if isinstance(cached, dict):
        return cached
    report = _run_pytest_uncached(targets)
    cache_put(key, report)
    return report


def _run_pytest_uncached(targets: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="guardian-pytest-") as directory:
        junit_path = Path(directory) / "junit.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--tb=short",
            f"--junitxml={junit_path}",
            *targets,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repo_root(),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": f"pytest exceeded {_TIMEOUT_SECONDS} seconds",
                "command": command,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "tests": [],
            }

        parsed = _parse_junit(junit_path) if junit_path.exists() else _empty_parse()
        collected_nothing = completed.returncode == 5
        return {
            "ok": True,
            "error": None,
            "message": "No tests were collected." if collected_nothing else None,
            "command": command,
            "exit_code": completed.returncode,
            "all_passed": parsed["failed"] == 0
            and parsed["errors"] == 0
            and (completed.returncode == 0 or collected_nothing),
            "stdout_tail": truncate(completed.stdout, FAILURE_TEXT_LIMIT),
            "stderr_tail": truncate(completed.stderr, FAILURE_TEXT_LIMIT),
            **parsed,
        }


def _parse_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    tests = []
    for case in root.findall(".//testcase"):
        classname = case.attrib.get("classname", "")
        name = case.attrib.get("name", "")
        nodeid = f"{classname.replace('.', '/')}.py::{name}" if classname else name
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            outcome = "failed"
            message = _failure_text(failure)
        elif error is not None:
            outcome = "error"
            message = _failure_text(error)
        elif skipped is not None:
            outcome = "skipped"
            message = skipped.attrib.get("message", "")
        else:
            outcome = "passed"
            message = ""
        tests.append(
            {
                "nodeid": nodeid,
                "outcome": outcome,
                "time_seconds": float(case.attrib.get("time", "0") or 0),
                "message": truncate(message, FAILURE_TEXT_LIMIT),
            }
        )

    return {
        "passed": sum(1 for test in tests if test["outcome"] == "passed"),
        "failed": sum(1 for test in tests if test["outcome"] == "failed"),
        "errors": sum(1 for test in tests if test["outcome"] == "error"),
        "skipped": sum(1 for test in tests if test["outcome"] == "skipped"),
        "tests": tests,
    }


def _empty_parse() -> dict:
    return {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "tests": []}


def _failure_text(element: ET.Element) -> str:
    message = element.attrib.get("message", "")
    body = (element.text or "").strip()
    if message and body:
        return f"{message}\n{body}"
    return message or body


def _evidence_summary(test_run: dict, violations: dict, failure_count: int) -> str:
    if not test_run.get("ok", False):
        test_status = test_run.get("error") or "test run failed"
    else:
        test_status = (
            f"{test_run.get('passed', 0)} passed, "
            f"{test_run.get('failed', 0)} failed, "
            f"{test_run.get('errors', 0)} errors"
        )
    if not violations.get("reachable", False):
        contract_status = "API unreachable"
    else:
        contract_status = f"{violations.get('violation_count', 0)} contract violations"
    return f"{test_status}; {contract_status}; {failure_count} failing tests collected."
