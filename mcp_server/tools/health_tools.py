"""Call the running API and compare responses with discovered schemas."""

from __future__ import annotations

import json

import httpx
from fastmcp import FastMCP

from mcp_server.contracts import compare_with_contract, discover_probes
from mcp_server.dependencies import api_base_url

_TIMEOUT = httpx.Timeout(5.0, connect=2.0)


def check_api_health(base_url: str | None = None) -> dict:
    """Call the local API and compare each discovered GET route with its schema.

    Routes come from the FastAPI app in this repository. A JSON file in
    contracts/ is used when its title matches the response schema. Path
    parameters are filled from schema examples.
    """
    return _probe(base_url)


def get_contract_violations(base_url: str | None = None) -> dict:
    """Return missing fields, unexpected fields, type errors, and schema mismatches.

    Uses the same discovered probes as check_api_health and keeps only the failing checks.
    """
    report = _probe(base_url)
    violations = [
        violation
        for check in report["checks"]
        for violation in check["violations"]
    ]
    return {
        "base_url": report["base_url"],
        "reachable": report["reachable"],
        "violation_count": len(violations),
        "violations": violations,
        "error": report["error"],
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(check_api_health)
    mcp.tool(get_contract_violations)


def _probe(base_url: str | None) -> dict:
    root = (base_url or api_base_url()).rstrip("/")
    discovered = discover_probes()
    if not discovered["ok"]:
        return {
            "base_url": root,
            "reachable": False,
            "healthy": False,
            "checks": [],
            "skipped": discovered["skipped"],
            "error": discovered["error"],
        }

    checks = []
    for probe in discovered["probes"]:
        path = str(probe["path"])
        try:
            response = httpx.get(f"{root}{path}", timeout=_TIMEOUT)
        except httpx.RequestError as exc:
            return {
                "base_url": root,
                "reachable": False,
                "healthy": False,
                "checks": checks,
                "skipped": discovered["skipped"],
                "error": f"Could not connect to {root}: {exc}",
            }
        checks.append(_check_response(path, probe, response))

    return {
        "base_url": root,
        "reachable": True,
        "healthy": all(check["valid"] for check in checks),
        "checks": checks,
        "skipped": discovered["skipped"],
        "error": None,
    }


def _check_response(path: str, probe: dict, response: httpx.Response) -> dict:
    contract_name = probe["contract"]
    violations: list[dict] = []
    payload: object | None = None

    if response.status_code != 200:
        violations.append(
            {
                "path": path,
                "contract": contract_name,
                "kind": "unexpected_status",
                "field": None,
                "message": f"Expected HTTP 200, received {response.status_code}",
            }
        )

    try:
        payload = response.json()
    except json.JSONDecodeError:
        violations.append(
            {
                "path": path,
                "contract": contract_name,
                "kind": "invalid_json",
                "field": None,
                "message": "Response body is not JSON",
            }
        )

    schema = probe.get("schema")
    if payload is not None and schema:
        violations.extend(
            compare_with_contract(
                payload,
                schema,
                path=path,
                contract_name=str(contract_name or "openapi"),
            )
        )

    return {
        "name": probe["name"],
        "path": path,
        "contract": contract_name,
        "status_code": response.status_code,
        "valid": not violations,
        "violations": violations,
        "body": payload,
    }
