"""Inject reproducible demo defects into a disposable Git worktree.

Never modifies `main`/`master` in place. Default target is
`.worktrees/scenario-<id>` on branch `demo/failure-<id>`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROTECTED_BRANCHES = {"main", "master"}
WORKTREE_ROOT = REPO_ROOT / ".worktrees"

SCENARIOS: dict[str, dict] = {
    "A": {
        "title": "Rename the order response field `total` to `amount`",
        "injected_defect": (
            "OrderResponse serializes `amount` instead of `total`. "
            "A compatibility property keeps invoice math working so the "
            "primary signal is a contract violation."
        ),
        "expected_detection": "Contract violation on GET /orders/{id}",
        "correct_outcome": (
            "GET /orders/{id} returns `total` and matches contracts/order.json. "
            "OrderResponse.model_dump() includes `total`, not `amount`."
        ),
        "expected_failing_tests": [
            "tests/unit/test_services.py::test_order_service_returns_sample_order",
            "tests/integration/test_api.py::test_api_responses_match_contracts[/orders/101-order.json]",
            "tests/integration/test_api.py::test_order_invoice_and_report_share_consistent_totals",
            "tests/integration/test_api.py::test_create_order_updates_invoice_and_revenue_services",
        ],
        "expected_passing_areas": [
            "Invoice tax math still uses order.total via a property",
            "Revenue aggregation still uses invoice totals",
        ],
    },
    "B": {
        "title": "Change order-total calculation logic",
        "injected_defect": (
            "Stored order totals are silently reduced by 10%. Invoices and "
            "revenue reports inherit the wrong amounts."
        ),
        "expected_detection": (
            "Incorrect invoice values and failed business assertions"
        ),
        "correct_outcome": (
            "Order 101 total is 499.0, invoice INV-101 is amount=499.0 / "
            "tax=49.9 / total=548.9, and revenue is 823.9."
        ),
        "expected_failing_tests": [
            "tests/unit/test_services.py::test_order_service_returns_sample_order",
            "tests/unit/test_services.py::test_invoice_service_calculates_from_order_total",
            "tests/unit/test_services.py::test_revenue_report_aggregates_invoice_totals",
            "tests/integration/test_api.py::test_order_invoice_and_report_share_consistent_totals",
            "tests/integration/test_api.py::test_create_order_updates_invoice_and_revenue_services",
        ],
        "expected_passing_areas": [
            "Order JSON Schema still matches (field names and types are unchanged)",
            "Invoice and report contracts still validate as objects",
        ],
    },
    "C": {
        "title": "Break a shared invoice service used by revenue reporting",
        "injected_defect": (
            "Invoice totals omit tax (`total = amount` instead of "
            "`amount + tax`). Revenue reporting aggregates the broken totals."
        ),
        "expected_detection": "Downstream regression in invoices and revenue reports",
        "correct_outcome": (
            "Invoice totals include tax, and GET /reports/revenue returns "
            "total_revenue=823.9 for the sample data."
        ),
        "expected_failing_tests": [
            "tests/unit/test_services.py::test_invoice_service_calculates_from_order_total",
            "tests/unit/test_services.py::test_revenue_report_aggregates_invoice_totals",
            "tests/integration/test_api.py::test_order_invoice_and_report_share_consistent_totals",
            "tests/integration/test_api.py::test_create_order_updates_invoice_and_revenue_services",
        ],
        "expected_passing_areas": [
            "Order unit tests and the order contract remain green",
            "Invoice JSON Schema still matches field names and types",
        ],
    },
}


def run_git(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd or REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def worktree_path(scenario_id: str) -> Path:
    return WORKTREE_ROOT / f"scenario-{scenario_id.lower()}"


def branch_name(scenario_id: str) -> str:
    return f"demo/failure-{scenario_id.lower()}"


def print_scenario(scenario_id: str) -> None:
    scenario = SCENARIOS[scenario_id]
    print(f"Scenario {scenario_id}: {scenario['title']}")
    print(f"  Injected defect: {scenario['injected_defect']}")
    print(f"  Expected detection: {scenario['expected_detection']}")
    print(f"  Correct outcome: {scenario['correct_outcome']}")
    print("  Expected failing tests:")
    for test in scenario["expected_failing_tests"]:
        print(f"    - {test}")
    print("  Should still work:")
    for item in scenario["expected_passing_areas"]:
        print(f"    - {item}")


def replace_in_file(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Could not find expected text in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply_scenario_a(target: Path) -> None:
    replace_in_file(
        target / "app" / "schemas" / "orders.py",
        '    total: float = Field(ge=0, examples=[499.0])\n    status: str = Field(examples=["shipped"])\n',
        '    amount: float = Field(ge=0, examples=[499.0])\n    status: str = Field(examples=["shipped"])\n\n    @property\n    def total(self) -> float:\n        return self.amount\n',
    )
    replace_in_file(
        target / "app" / "services" / "orders.py",
        """_ORDERS = {
    101: OrderResponse(id=101, total=499.0, status="shipped"),
    102: OrderResponse(id=102, total=250.0, status="paid"),
}


def create_order(order_data: OrderCreateRequest) -> OrderResponse | None:
    if order_data.id in _ORDERS:
        return None
    order = OrderResponse(**order_data.model_dump())
""",
        """_ORDERS = {
    101: OrderResponse(id=101, amount=499.0, status="shipped"),
    102: OrderResponse(id=102, amount=250.0, status="paid"),
}


def create_order(order_data: OrderCreateRequest) -> OrderResponse | None:
    if order_data.id in _ORDERS:
        return None
    order = OrderResponse(
        id=order_data.id,
        amount=order_data.total,
        status=order_data.status,
    )
""",
    )


def apply_scenario_b(target: Path) -> None:
    replace_in_file(
        target / "app" / "services" / "orders.py",
        """from app.schemas.orders import OrderCreateRequest, OrderResponse

_ORDERS = {
    101: OrderResponse(id=101, total=499.0, status="shipped"),
    102: OrderResponse(id=102, total=250.0, status="paid"),
}


def create_order(order_data: OrderCreateRequest) -> OrderResponse | None:
    if order_data.id in _ORDERS:
        return None
    order = OrderResponse(**order_data.model_dump())
""",
        """from app.schemas.orders import OrderCreateRequest, OrderResponse


def _calculated_total(amount: float) -> float:
    # Injected defect: apply an unintended 10% discount to stored totals.
    return round(amount * 0.9, 2)


_ORDERS = {
    101: OrderResponse(id=101, total=_calculated_total(499.0), status="shipped"),
    102: OrderResponse(id=102, total=_calculated_total(250.0), status="paid"),
}


def create_order(order_data: OrderCreateRequest) -> OrderResponse | None:
    if order_data.id in _ORDERS:
        return None
    payload = order_data.model_dump()
    payload["total"] = _calculated_total(payload["total"])
    order = OrderResponse(**payload)
""",
    )


def apply_scenario_c(target: Path) -> None:
    replace_in_file(
        target / "app" / "services" / "invoices.py",
        "                total=round(order.total + tax, 2),",
        "                total=round(order.total, 2),",
    )


APPLIERS = {
    "A": apply_scenario_a,
    "B": apply_scenario_b,
    "C": apply_scenario_c,
}


def ensure_not_protected_in_place(target: Path) -> None:
    if target.resolve() != REPO_ROOT.resolve():
        return
    branch = current_branch()
    if branch in PROTECTED_BRANCHES:
        raise SystemExit(
            f"Refusing to inject a bug in place on protected branch '{branch}'. "
            "Omit --in-place so a disposable worktree is used."
        )


def create_worktree(scenario_id: str, force: bool) -> Path:
    target = worktree_path(scenario_id)
    branch = branch_name(scenario_id)
    if target.exists():
        if not force:
            raise SystemExit(
                f"Worktree already exists at {target}. "
                "Pass --force to recreate it, or --cleanup first."
            )
        remove_worktree(scenario_id)

    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        run_git(["worktree", "add", "-b", branch, str(target), "HEAD"])
    except subprocess.CalledProcessError as exc:
        combined = f"{exc.stdout}\n{exc.stderr}"
        if "already exists" in combined:
            run_git(["worktree", "add", str(target), branch])
        else:
            raise
    return target


def remove_worktree(scenario_id: str) -> None:
    target = worktree_path(scenario_id)
    branch = branch_name(scenario_id)
    if target.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(target)],
            cwd=REPO_ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=REPO_ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    run_git(["worktree", "prune"])


def commit_injection(target: Path, scenario_id: str) -> None:
    run_git(["add", "app"], cwd=target)
    message = f"demo: inject failure scenario {scenario_id}"
    run_git(["commit", "-m", message], cwd=target)


def cmd_list() -> int:
    print("Available failure scenarios (injected only in a worktree by default):\n")
    for scenario_id in SCENARIOS:
        print_scenario(scenario_id)
        print()
    print("Usage:")
    print("  python scripts/inject_bug.py A")
    print("  python -m pytest  # run from the printed worktree path")
    print("  python scripts/inject_bug.py --cleanup A")
    return 0


def cmd_inject(scenario_id: str, in_place: bool, force: bool, no_commit: bool) -> int:
    scenario_id = scenario_id.upper()
    if scenario_id not in SCENARIOS:
        raise SystemExit(f"Unknown scenario '{scenario_id}'. Choose A, B, or C.")

    if in_place:
        target = REPO_ROOT
        ensure_not_protected_in_place(target)
        print(f"Injecting scenario {scenario_id} in place on branch '{current_branch()}'.")
    else:
        target = create_worktree(scenario_id, force=force)
        print(f"Created disposable worktree: {target}")
        print(f"Branch: {branch_name(scenario_id)}")

    APPLIERS[scenario_id](target)

    if not in_place and not no_commit:
        commit_injection(target, scenario_id)
        print("Committed the injected defect on the demo branch only.")

    print()
    print_scenario(scenario_id)
    print()
    print("Next:")
    print(f"  cd {target}")
    print(f"  {sys.executable} -m pytest")
    print("The original application on main is unchanged.")
    return 0


def cmd_cleanup(scenario_id: str | None, cleanup_all: bool) -> int:
    ids = list(SCENARIOS) if cleanup_all else [scenario_id.upper()]
    for item in ids:
        if item not in SCENARIOS:
            raise SystemExit(f"Unknown scenario '{item}'. Choose A, B, or C.")
        remove_worktree(item)
        print(f"Removed worktree and demo branch for scenario {item}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inject a known demo defect into a disposable Git worktree."
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        help="Scenario id: A, B, or C",
    )
    parser.add_argument("--list", action="store_true", help="Show scenarios and expected failures")
    parser.add_argument("--cleanup", metavar="ID", help="Remove the worktree and demo branch")
    parser.add_argument("--cleanup-all", action="store_true", help="Remove all scenario worktrees")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Apply the defect in this checkout (refuses main/master)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recreate the worktree if it already exists",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Leave the injected defect uncommitted in the worktree",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.list:
            return cmd_list()
        if args.cleanup_all:
            return cmd_cleanup(None, cleanup_all=True)
        if args.cleanup:
            return cmd_cleanup(args.cleanup, cleanup_all=False)
        if not args.scenario:
            parser.print_help()
            return 1
        return cmd_inject(args.scenario, args.in_place, args.force, args.no_commit)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr or str(exc))
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
