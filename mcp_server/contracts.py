"""Build API probes from the FastAPI app and compare responses with schemas.

Contract files under contracts/ are optional. A file is used when its schema
title matches an OpenAPI response schema, so the same rule works in any
FastAPI project. Projects without that folder are checked against the
OpenAPI response schemas themselves.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from mcp_server.dependencies import repo_root
from mcp_server.discover import load_fastapi_app

_QUOTED = re.compile(r"'([^']+)'")
_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def contracts_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "contracts"


def load_contract(name: str, root: Path | None = None) -> dict:
    path = contracts_dir(root) / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def discover_probes(root: Path | None = None) -> dict:
    """Return concrete GET urls discovered from the FastAPI application."""
    project = root or repo_root()
    try:
        application = load_fastapi_app(project)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Could not import the FastAPI application: {exc}",
            "probes": [],
            "skipped": [],
        }
    if application is None:
        return {
            "ok": False,
            "error": "No FastAPI() application was found in this repository.",
            "probes": [],
            "skipped": [],
        }
    probes, skipped = build_probes(application.openapi(), _contracts_by_title(project))
    return {"ok": True, "error": None, "probes": probes, "skipped": skipped}


def build_probes(spec: dict, contracts_by_title: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    operations = []
    for template, path_item in (spec.get("paths") or {}).items():
        path_params = [
            parameter
            for parameter in path_item.get("parameters") or []
            if isinstance(parameter, dict)
        ]
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            if method != "get":
                continue
            schema = _response_schema(spec, operation)
            parameters = path_params + [
                parameter
                for parameter in operation.get("parameters") or []
                if isinstance(parameter, dict)
            ]
            operations.append(
                {
                    "method": method.upper(),
                    "template": template,
                    "parameters": parameters,
                    "schema": schema,
                }
            )

    object_titles = set()
    prepared = []
    for operation in operations:
        schema = operation["schema"]
        object_schema = schema
        is_array = bool(schema and schema.get("type") == "array")
        if is_array:
            object_schema = _resolve(schema.get("items") or {}, spec)
        title = object_schema.get("title") if isinstance(object_schema, dict) else None
        if title and not is_array:
            object_titles.add(title)
        contract = contracts_by_title.get(title) if title else None
        prepared.append(
            {
                **operation,
                "is_array": is_array,
                "object_schema": object_schema if isinstance(object_schema, dict) else {},
                "title": title,
                "contract": contract,
            }
        )

    probes = []
    skipped = []
    for operation in prepared:
        if operation["is_array"] and operation["title"] in object_titles:
            continue
        validation = operation["schema"] or {}
        contract_name = "openapi"
        if operation["contract"] and not operation["is_array"]:
            validation = operation["contract"]["schema"]
            contract_name = operation["contract"]["name"]
        elif operation["title"]:
            contract_name = f"openapi:{operation['title']}"

        concrete, missing = _fill_path(
            operation["template"],
            operation["parameters"],
            operation["object_schema"],
            operation["contract"]["schema"] if operation["contract"] else None,
        )
        if missing:
            skipped.append(
                {
                    "path": operation["template"],
                    "reason": f"No example value for path parameter {missing}",
                }
            )
            continue
        probes.append(
            {
                "name": f"{operation['method']} {operation['template']}",
                "path": concrete,
                "template": operation["template"],
                "contract": contract_name if validation else None,
                "schema": validation or None,
            }
        )

    probes.sort(key=lambda probe: probe["path"])
    return probes, skipped


def compare_with_contract(
    payload: object,
    schema: dict,
    *,
    path: str,
    contract_name: str,
) -> list[dict]:
    try:
        validator = Draft202012Validator(schema)
    except SchemaError as exc:
        return [
            {
                "path": path,
                "contract": contract_name,
                "kind": "schema_mismatch",
                "field": None,
                "message": f"Contract file could not be loaded as a schema: {exc.message}",
            }
        ]

    return [
        _classify(error, path=path, contract_name=contract_name)
        for error in validator.iter_errors(payload)
    ]


def _contracts_by_title(root: Path) -> dict[str, dict]:
    directory = contracts_dir(root)
    found: dict[str, dict] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        title = schema.get("title")
        if isinstance(title, str) and title not in found:
            found[title] = {"name": path.name, "schema": schema}
    return found


def _response_schema(spec: dict, operation: dict) -> dict | None:
    responses = operation.get("responses") or {}
    response = responses.get("200") or responses.get("201") or {}
    if not isinstance(response, dict):
        return None
    content = response.get("content") or {}
    json_content = None
    for key, value in content.items():
        if key.startswith("application/json"):
            json_content = value
            break
    if not isinstance(json_content, dict):
        return None
    schema = json_content.get("schema")
    if not isinstance(schema, dict):
        return None
    return _resolve(schema, spec)


def _resolve(schema: dict, spec: dict, depth: int = 0) -> dict:
    if depth > 8 or not isinstance(schema, dict):
        return {}
    ref = schema.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return schema
    node: object = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return schema
        node = node.get(part)
    if not isinstance(node, dict):
        return schema
    return _resolve(node, spec, depth + 1)


def _fill_path(
    template: str,
    parameters: list[dict],
    object_schema: dict,
    contract_schema: dict | None,
) -> tuple[str, str | None]:
    concrete = template
    for parameter in parameters:
        if parameter.get("in") != "path":
            continue
        name = str(parameter.get("name") or "")
        example = _example_for(name, parameter.get("schema") or {}, object_schema, contract_schema)
        if example is None:
            return template, name
        concrete = concrete.replace("{" + name + "}", _format_example(example))
    return concrete, None


def _example_for(
    param_name: str,
    param_schema: dict,
    object_schema: dict,
    contract_schema: dict | None,
) -> object | None:
    found = _first_example(param_schema)
    if found is not None:
        return found
    for schema in (contract_schema, object_schema):
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties") or {}
        if param_name in properties:
            found = _first_example(properties[param_name])
            if found is not None:
                return found
        if param_name.endswith("_id") and "id" in properties:
            found = _first_example(properties["id"])
            if found is not None:
                return found
    return None


def _first_example(schema: dict) -> object | None:
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    if "default" in schema:
        return schema["default"]
    return None


def _format_example(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _classify(error, *, path: str, contract_name: str) -> dict:
    field_path = ".".join(str(part) for part in error.path) or None
    kind = "schema_mismatch"
    field = field_path
    if error.validator == "required":
        kind = "missing_field"
        quoted = _QUOTED.findall(error.message)
        field = quoted[0] if quoted else field_path
    elif error.validator == "additionalProperties":
        kind = "unexpected_field"
        quoted = _QUOTED.findall(error.message)
        field = quoted[0] if quoted else field_path
    elif error.validator == "type":
        kind = "incorrect_type"
        field = field_path
    return {
        "path": path,
        "contract": contract_name,
        "kind": kind,
        "field": field,
        "message": error.message,
    }
