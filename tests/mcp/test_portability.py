"""The guardian follows whatever FastAPI repository it is pointed at."""

import json
from pathlib import Path

from git import Actor, Repo

from mcp_server.contracts import build_probes, compare_with_contract, discover_probes
from mcp_server.discover import load_fastapi_app
from mcp_server.tools.health_tools import check_api_health, compare_with_contract as _compare
from mcp_server.tools.test_tools import run_full_tests
from mcp_server.tools.verify_tools import verify_repair

ORDER_TEST = "tests/unit/test_services.py::test_order_service_returns_sample_order"


def test_nested_refs_in_a_list_schema_validate_each_item() -> None:
    spec = {
        "paths": {
            "/books": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Book"},
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Author": {
                    "title": "Author",
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                },
                "Book": {
                    "title": "Book",
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "author"],
                    "properties": {
                        "title": {"type": "string"},
                        "author": {"$ref": "#/components/schemas/Author"},
                    },
                },
            }
        },
    }

    probes, skipped = build_probes(spec, {})

    assert skipped == []
    assert probes[0]["path"] == "/books"
    assert "$ref" not in json.dumps(probes[0]["schema"])
    good = [{"title": "Dune", "author": {"name": "Frank"}}]
    assert compare_with_contract(
        good,
        probes[0]["schema"],
        path="/books",
        contract_name="openapi:Book",
    ) == []
    bad = compare_with_contract(
        [{"title": "Dune", "author": "Frank"}],
        probes[0]["schema"],
        path="/books",
        contract_name="openapi:Book",
    )
    assert any(item["kind"] == "incorrect_type" and item["message"].startswith("Item 0:") for item in bad)


def test_list_routes_use_the_item_contract_even_when_a_detail_route_exists(tmp_path: Path) -> None:
    package = tmp_path / "bookstore"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from pydantic import BaseModel, Field\n"
        "\n"
        "class Author(BaseModel):\n"
        "    name: str\n"
        "\n"
        "class Book(BaseModel):\n"
        "    id: int = Field(examples=[1])\n"
        "    title: str\n"
        "    author: Author\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "@app.get('/books', response_model=list[Book])\n"
        "def read_books() -> list[Book]:\n"
        "    return [Book(id=1, title='Dune', author=Author(name='Frank'))]\n"
        "\n"
        "@app.get('/books/{book_id}', response_model=Book)\n"
        "def read_book(book_id: int) -> Book:\n"
        "    return Book(id=book_id, title='Dune', author=Author(name='Frank'))\n",
        encoding="utf-8",
    )
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "book.json").write_text(
        json.dumps(
            {
                "title": "Book",
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "headline", "author"],
                "properties": {
                    "id": {"type": "integer", "examples": [1]},
                    "headline": {"type": "string"},
                    "author": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name"],
                        "properties": {"name": {"type": "string"}},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    discovered = discover_probes(tmp_path)

    assert discovered["ok"] is True
    by_path = {probe["path"]: probe for probe in discovered["probes"]}
    assert "/books" in by_path
    assert by_path["/books"]["contract"] == "book.json"
    assert by_path["/books/1"]["contract"] == "book.json"
    violations = compare_with_contract(
        [{"id": 1, "title": "Dune", "author": {"name": "Frank"}}],
        by_path["/books"]["schema"],
        path="/books",
        contract_name="book.json",
    )
    found = {(item["kind"], item["field"]) for item in violations}
    assert ("missing_field", "headline") in found
    assert ("unexpected_field", "title") in found


def test_one_route_validation_error_does_not_drop_the_others(
    monkeypatch, healthy_api_url: str
) -> None:
    real = _compare

    def explode(payload, schema, *, path, contract_name):
        if path == "/orders/101":
            raise RuntimeError("unresolved $ref")
        return real(payload, schema, path=path, contract_name=contract_name)

    monkeypatch.setattr("mcp_server.tools.health_tools.compare_with_contract", explode)
    report = check_api_health(healthy_api_url)

    assert report["reachable"] is True
    assert report["healthy"] is False
    by_path = {check["path"]: check for check in report["checks"]}
    assert by_path["/reports/revenue"]["valid"] is True
    assert by_path["/orders/101"]["valid"] is False
    assert "unresolved $ref" in by_path["/orders/101"]["violations"][0]["message"]


def test_edited_application_is_imported_again(tmp_path: Path) -> None:
    package = tmp_path / "catalog"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    main = package / "main.py"
    main.write_text(
        "from fastapi import FastAPI\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Item(BaseModel):\n"
        "    name: str\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "@app.get('/items', response_model=list[Item])\n"
        "def read_items() -> list[Item]:\n"
        "    return []\n",
        encoding="utf-8",
    )

    first = load_fastapi_app(tmp_path)
    assert "name" in first.openapi()["components"]["schemas"]["Item"]["properties"]

    main.write_text(
        "from fastapi import FastAPI\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class Item(BaseModel):\n"
        "    label: str\n"
        "\n"
        "app = FastAPI()\n"
        "\n"
        "@app.get('/items', response_model=list[Item])\n"
        "def read_items() -> list[Item]:\n"
        "    return []\n",
        encoding="utf-8",
    )
    second = load_fastapi_app(tmp_path)
    properties = second.openapi()["components"]["schemas"]["Item"]["properties"]
    assert "label" in properties
    assert "name" not in properties


def test_missing_suite_and_custom_test_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GUARDIAN_REPO_ROOT", str(tmp_path))
    empty = run_full_tests()
    assert empty["ok"] is True
    assert empty["all_passed"] is True
    assert empty["message"] == "No test suite was found in this repository."

    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_one.py").write_text("def test_one():\n    assert True\n", encoding="utf-8")
    monkeypatch.setenv("GUARDIAN_TEST_PATHS", "checks")
    report = run_full_tests()
    assert report["all_passed"] is True
    assert report["passed"] == 1
    assert report["suite"] == ["checks"]


def test_failed_contract_skips_the_full_suite(monkeypatch, tmp_path, broken_api_url: str) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))

    def fail_if_called():
        raise AssertionError("full suite should not run after a contract failure")

    monkeypatch.setattr("mcp_server.tools.verify_tools.run_full_tests", fail_if_called)
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.run_targeted_tests",
        lambda nodeids: {
            "ok": True,
            "all_passed": True,
            "passed": 1,
            "failed": 0,
            "errors": 0,
            "tests": [],
        },
    )

    report = verify_repair([ORDER_TEST], base_url=broken_api_url)

    assert report["accepted"] is False
    assert report["full_ok"] is False
    assert report["full_tests"]["skipped"] is True
    assert "full suite skipped" in report["summary"]


def test_repeat_verification_reuses_the_same_run(monkeypatch, tmp_path, healthy_api_url: str) -> None:
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path))
    calls = {"targeted": 0, "full": 0}

    def targeted(nodeids):
        calls["targeted"] += 1
        return {"ok": True, "all_passed": True, "passed": 1, "failed": 0, "errors": 0, "tests": []}

    def full():
        calls["full"] += 1
        return {"ok": True, "all_passed": True, "passed": 1, "failed": 0, "errors": 0, "tests": []}

    monkeypatch.setattr("mcp_server.tools.verify_tools.run_targeted_tests", targeted)
    monkeypatch.setattr("mcp_server.tools.verify_tools.run_full_tests", full)

    first = verify_repair([ORDER_TEST], base_url=healthy_api_url)
    second = verify_repair([ORDER_TEST], base_url=healthy_api_url)

    assert first["accepted"] is True
    assert second["accepted"] is True
    assert first["attempt"] == 1
    assert second["attempt"] == 1
    assert calls == {"targeted": 1, "full": 1}


def test_third_failure_restores_unaccepted_changes(monkeypatch, tmp_path: Path) -> None:
    repo = Repo.init(tmp_path)
    tracked = tmp_path / "widget.py"
    tracked.write_text("VALUE = 'base'\n", encoding="utf-8")
    repo.index.add(["widget.py"])
    actor = Actor("Guardian Test", "guardian@example.com")
    repo.index.commit("baseline", author=actor, committer=actor)

    monkeypatch.setenv("GUARDIAN_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("GUARDIAN_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setattr(
        "mcp_server.tools.verify_tools.get_contract_violations",
        lambda base_url=None: {
            "base_url": base_url,
            "reachable": True,
            "healthy": False,
            "violation_count": 1,
            "violations": [
                {
                    "path": "/items",
                    "contract": "item.json",
                    "kind": "missing_field",
                    "field": "name",
                    "message": "name is required",
                }
            ],
            "error": None,
        },
    )

    report = {}
    for attempt in range(1, 4):
        tracked.write_text(f"VALUE = 'bad{attempt}'\n", encoding="utf-8")
        if attempt == 3:
            (tmp_path / "scratch.py").write_text("x = 1\n", encoding="utf-8")
        report = verify_repair([], base_url="http://127.0.0.1:9")
        assert report["attempt"] == attempt
        assert report["accepted"] is False

    assert tracked.read_text(encoding="utf-8") == "VALUE = 'base'\n"
    assert not (tmp_path / "scratch.py").exists()
    assert report["escalated"] is True
    assert report["rollback"]["ok"] is True
    assert Path(report["escalation_report"]["markdown_report"]).is_file()

    stopped = verify_repair([], base_url="http://127.0.0.1:9")
    assert stopped["escalated"] is True
    assert stopped["attempt"] == 3
    assert "Do not edit" in stopped["next_action"]
