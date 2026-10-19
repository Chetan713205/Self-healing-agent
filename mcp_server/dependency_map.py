"""Impact map discovered from route declarations and imports.

A changed module affects the route handlers and tests that reference it, plus
modules that import it. Nothing here is specific to one API's endpoints.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from mcp_server.dependencies import contracts_dir, repo_root
from mcp_server.discover import is_test_file, iter_python_files, module_name

_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_TEMPLATE = re.compile(r"\{[^}]+\}")


def analyze(root: Path, changed_files: list[str]) -> dict:
    index = _build_index(root)
    changed_modules: set[str] = set()
    unmapped: list[str] = []
    rationale: list[str] = []

    for relative in changed_files:
        module = index.modules_by_path.get(relative)
        if module:
            changed_modules.add(module)
            rationale.append(f"{relative} is Python module {module}.")
            continue
        linked = index.contracts_by_path.get(relative, [])
        if linked:
            changed_modules.update(linked)
            rationale.append(
                f"{relative} matches schema {', '.join(linked)} by title."
            )
            continue
        unmapped.append(relative)
        rationale.append(f"{relative} is not a Python module or a titled contract schema.")

    affected = _importers_closure(changed_modules, index.importers)
    selected_routes = []
    for route in index.routes:
        file_changed = route.path in changed_files
        references_changed = bool(route.modules & changed_modules) or file_changed
        references_affected = bool(route.modules & affected)
        if not references_changed and not references_affected:
            continue
        reason = "direct" if references_changed else "downstream"
        selected_routes.append((route, reason))
        rationale.append(
            f"{route.method} {route.template} is {reason} through {route.module}."
        )

    direct_services = sorted({route.service for route, reason in selected_routes if reason == "direct"})
    affected_services = sorted({route.service for route, _reason in selected_routes})
    endpoints = [
        {
            "endpoint": f"{route.method} {route.template}",
            "service": route.service,
            "reason": reason,
        }
        for route, reason in sorted(selected_routes, key=lambda item: (item[0].method, item[0].template))
    ]

    relevant = []
    changed_set = set(changed_files)
    for test in index.tests:
        file_changed = test.path in changed_set
        matched = [
            (route, reason)
            for route, reason in selected_routes
            if any(_path_matches(candidate, route.template) for candidate in test.paths)
        ]
        modules_hit = test.modules & affected
        if not file_changed and not matched and not modules_hit:
            continue
        direct = file_changed or bool(test.modules & changed_modules) or any(
            reason == "direct" for _route, reason in matched
        )
        services = sorted(
            {route.service for route, _reason in matched}
            | _services_for_modules(test.modules & affected, selected_routes)
        )
        relevant.append(
            {
                "nodeid": test.nodeid,
                "priority": 1 if direct else 2,
                "services": services,
                "reason": (
                    "references a directly changed module"
                    if direct
                    else "references a downstream module"
                ),
            }
        )

    relevant.sort(key=lambda item: (item["priority"], item["nodeid"]))
    return {
        "changed_files": changed_files,
        "unmapped_files": unmapped,
        "directly_changed_services": direct_services,
        "affected_services": affected_services,
        "affected_endpoints": endpoints,
        "relevant_tests": relevant,
        "recommended_nodeids": [item["nodeid"] for item in relevant],
        "run_full_suite_still_required": True,
        "rationale": rationale,
        "analysis": "import_graph",
    }


class _Route:
    def __init__(self, path: str, module: str, method: str, template: str, service: str, modules: set[str]):
        self.path = path
        self.module = module
        self.method = method
        self.template = template
        self.service = service
        self.modules = modules


class _TestCase:
    def __init__(self, path: str, nodeid: str, modules: set[str], paths: set[str]):
        self.path = path
        self.nodeid = nodeid
        self.modules = modules
        self.paths = paths


class _Index:
    def __init__(self):
        self.modules_by_path: dict[str, str] = {}
        self.importers: dict[str, set[str]] = {}
        self.contracts_by_path: dict[str, list[str]] = {}
        self.routes: list[_Route] = []
        self.tests: list[_TestCase] = []


def _build_index(root: Path) -> _Index:
    parsed: list[tuple[str, str, ast.AST]] = []
    module_names: set[str] = set()
    for path in iter_python_files(root):
        relative = path.relative_to(root).as_posix()
        name = module_name(root, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, SyntaxError):
            continue
        parsed.append((relative, name, tree))
        module_names.add(name)

    index = _Index()
    classes: dict[str, set[str]] = {}
    for relative, name, tree in parsed:
        index.modules_by_path[relative] = name
        imports, imported_names, assigned = _imports(tree, name, module_names)
        for dependency in imports:
            index.importers.setdefault(dependency, set()).add(name)
        classes[name] = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
        if is_test_file(relative):
            index.tests.extend(_tests(relative, tree, imported_names, assigned))
            continue
        index.routes.extend(_routes(relative, name, tree, imported_names, assigned))

    directory = contracts_dir() if root.resolve() == repo_root().resolve() else root / "contracts"
    contract_paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
    for path in contract_paths:
        try:
            schema = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        title = schema.get("title")
        if not isinstance(title, str):
            continue
        owners = [module for module, defined in classes.items() if title in defined]
        if owners:
            index.contracts_by_path[path.relative_to(root).as_posix()] = owners
    return index


def _imports(tree: ast.AST, current: str, known: set[str]):
    imports: set[str] = set()
    imported_names: dict[str, str] = {}

    def remember(local: str, module: str | None) -> None:
        if module and module in known:
            imports.add(module)
            imported_names[local] = module

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if target not in known:
                    parent = target
                    while "." in parent and parent not in known:
                        parent = parent.rsplit(".", 1)[0]
                    target = parent if parent in known else None
                remember(alias.asname or alias.name.split(".")[0], target if isinstance(target, str) else None)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from(current, node.module, node.level)
            if base is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                submodule = f"{base}.{alias.name}" if base else alias.name
                if submodule in known:
                    remember(alias.asname or alias.name, submodule)
                else:
                    remember(alias.asname or alias.name, base if base in known else None)

    assigned: dict[str, set[str]] = {}
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        modules = _modules_from_names(_names(node.value), imported_names, assigned)
        if not modules:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                assigned[target.id] = set(modules)
    return imports, imported_names, assigned


def _resolve_from(current: str, module: str | None, level: int) -> str | None:
    if level == 0:
        return module
    package = current.split(".")[:-1]
    if level > 1:
        package = package[: -(level - 1)]
    if module:
        return ".".join([*package, module]) if package else module
    return ".".join(package) if package else None


def _routes(relative: str, module: str, tree: ast.AST, imported_names: dict[str, str], assigned: dict[str, set[str]]):
    routers: dict[str, str] = {}
    apps: set[str] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call_name = _call_name(node.value)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if call_name == "APIRouter":
                routers[target.id] = _keyword_str(node.value, "prefix") or ""
            elif call_name == "FastAPI":
                apps.add(target.id)

    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        referenced = _modules_from_names(_names(node), imported_names, assigned)
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            owner = decorator.func.value
            if method not in _METHODS or not isinstance(owner, ast.Name):
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            if not isinstance(decorator.args[0].value, str):
                continue
            route_path = decorator.args[0].value
            if owner.id in routers:
                template = _join_paths(routers[owner.id], route_path)
                service = _service_name(routers[owner.id], template, module)
            elif owner.id in apps:
                template = _join_paths("", route_path)
                service = _service_name("", template, module)
            else:
                continue
            routes.append(_Route(relative, module, method, template, service, referenced))
    return routes


def _tests(relative: str, tree: ast.AST, imported_names: dict[str, str], assigned: dict[str, set[str]]):
    cases = []
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        parent = parents.get(node)
        class_name = parent.name if isinstance(parent, ast.ClassDef) else None
        modules = _modules_from_names(_names(node), imported_names, assigned)
        rows = _parametrize_rows(node)
        if not rows:
            rows = [("", set())]
        for suffix, paths in rows:
            head = f"{relative}::{class_name}::{node.name}" if class_name else f"{relative}::{node.name}"
            nodeid = f"{head}[{suffix}]" if suffix else head
            cases.append(_TestCase(relative, nodeid, modules, paths))
    return cases


def _parametrize_rows(func: ast.AST) -> list[tuple[str, set[str]]]:
    rows: list[tuple[str, set[str]]] = []
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return rows
    for decorator in func.decorator_list:
        if not isinstance(decorator, ast.Call) or _call_name(decorator) != "parametrize":
            continue
        if len(decorator.args) < 2 or not isinstance(decorator.args[1], (ast.List, ast.Tuple)):
            continue
        parsed: list[tuple[str, set[str]]] = []
        for element in decorator.args[1].elts:
            values = _constant_row(element)
            if values is None:
                parsed = []
                break
            suffix = "-".join(str(value) for value in values)
            paths = {value for value in values if isinstance(value, str) and value.startswith("/")}
            parsed.append((suffix, paths))
        if not parsed:
            continue
        if not rows:
            rows = parsed
            continue
        combined = []
        for left_id, left_paths in rows:
            for right_id, right_paths in parsed:
                suffix = "-".join(part for part in (left_id, right_id) if part)
                combined.append((suffix, left_paths | right_paths))
        rows = combined
    return rows


def _constant_row(node: ast.AST) -> list[object] | None:
    if isinstance(node, ast.Constant):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List)) and all(isinstance(item, ast.Constant) for item in node.elts):
        return [item.value for item in node.elts if isinstance(item, ast.Constant)]
    return None


def _modules_from_names(names: set[str], imported_names: dict[str, str], assigned: dict[str, set[str]]) -> set[str]:
    modules: set[str] = set()
    for name in names:
        if name in imported_names:
            modules.add(imported_names[name])
        elif name in assigned:
            modules.update(assigned[name])
    return modules


def _names(node: ast.AST) -> set[str]:
    return {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}


def _importers_closure(seeds: set[str], importers: dict[str, set[str]]) -> set[str]:
    affected = set(seeds)
    frontier = set(seeds)
    while frontier:
        nxt = set()
        for module in frontier:
            for importer in importers.get(module, ()):
                if importer not in affected:
                    affected.add(importer)
                    nxt.add(importer)
        frontier = nxt
    return affected


def _services_for_modules(modules: set[str], routes: list[tuple[_Route, str]]) -> set[str]:
    return {route.service for route, _reason in routes if route.module in modules or route.modules & modules}


def _path_matches(candidate: str, template: str) -> bool:
    if candidate == template:
        return True
    pieces = _TEMPLATE.split(template)
    pattern = "[^/]+".join(re.escape(piece) for piece in pieces)
    return re.fullmatch(pattern, candidate) is not None


def _join_paths(prefix: str, route: str) -> str:
    prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""
    if not route or route == "/":
        return prefix or "/"
    if not route.startswith("/"):
        route = "/" + route
    return f"{prefix}{route}" or "/"


def _service_name(prefix: str, template: str, module: str) -> str:
    for source in (prefix, template):
        parts = [part for part in source.strip("/").split("/") if part and not part.startswith("{")]
        if parts:
            return parts[0]
    return module.rsplit(".", 1)[-1]


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _keyword_str(node: ast.Call, name: str) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value
    return None
