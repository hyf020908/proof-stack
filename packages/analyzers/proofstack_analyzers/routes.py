"""FastAPI route extraction and compatibility comparison."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass(slots=True, frozen=True)
class FastAPIRoute:
    path: str
    method: str
    handler: str
    request_models: tuple[str, ...]
    response_model: str | None
    status_code: int | None
    dependencies: tuple[str, ...]
    line: int

    @property
    def identity(self) -> tuple[str, str]:
        return self.method, self.path


@dataclass(slots=True, frozen=True)
class RouteChange:
    change_type: str
    route: FastAPIRoute
    previous: FastAPIRoute | None
    breaking: bool
    explanation: str


class FastAPIRouteExtractor:
    methods: ClassVar[set[str]] = {
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "options",
        "head",
        "trace",
    }

    def extract(self, source: str) -> list[FastAPIRoute]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign | ast.AnnAssign):
                value = node.value
                if isinstance(value, ast.Call) and _name(value.func).endswith("APIRouter"):
                    prefix = _keyword_literal(value, "prefix")
                    for target in _targets(node):
                        if isinstance(target, ast.Name):
                            prefixes[target.id] = prefix if isinstance(prefix, str) else ""
        routes: list[FastAPIRoute] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                decorator_name = _name(decorator.func)
                if "." not in decorator_name:
                    continue
                router_name, method = decorator_name.rsplit(".", 1)
                if method.lower() not in self.methods:
                    continue
                raw_path = _literal(decorator.args[0]) if decorator.args else ""
                if not isinstance(raw_path, str):
                    continue
                request_models: list[str] = []
                dependencies: list[str] = []
                for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                    annotation = _name(argument.annotation)
                    default = _argument_default(node.args, argument)
                    if isinstance(default, ast.Call) and _name(default.func).endswith("Depends"):
                        dependencies.append(_name(default.args[0]) if default.args else "Depends")
                    elif annotation and annotation not in {
                        "Request",
                        "Response",
                        "str",
                        "int",
                        "float",
                        "bool",
                        "bytes",
                    }:
                        request_models.append(annotation)
                declared_dependencies = _keyword_node(decorator, "dependencies")
                if isinstance(declared_dependencies, ast.List | ast.Tuple):
                    for item in declared_dependencies.elts:
                        if isinstance(item, ast.Call):
                            dependencies.append(
                                _name(item.args[0]) if item.args else _name(item.func)
                            )
                prefix = prefixes.get(router_name, "")
                routes.append(
                    FastAPIRoute(
                        path=_join_path(prefix, raw_path),
                        method=method.upper(),
                        handler=node.name,
                        request_models=tuple(dict.fromkeys(filter(None, request_models))),
                        response_model=_keyword_name(decorator, "response_model"),
                        status_code=_as_int(_keyword_literal(decorator, "status_code")),
                        dependencies=tuple(dict.fromkeys(filter(None, dependencies))),
                        line=node.lineno,
                    )
                )
        return sorted(routes, key=lambda item: (item.path, item.method, item.handler))


def compare_routes(
    previous: list[FastAPIRoute],
    current: list[FastAPIRoute],
) -> list[RouteChange]:
    old = {route.identity: route for route in previous}
    new = {route.identity: route for route in current}
    changes: list[RouteChange] = []
    for identity in sorted(old.keys() - new.keys()):
        route = old[identity]
        changes.append(RouteChange("removed", route, route, True, "A public route was removed."))
    for identity in sorted(new.keys() - old.keys()):
        route = new[identity]
        changes.append(RouteChange("added", route, None, False, "A public route was added."))
    for identity in sorted(old.keys() & new.keys()):
        before = old[identity]
        after = new[identity]
        differences: list[str] = []
        breaking = False
        if before.request_models != after.request_models:
            differences.append("request model changed")
            breaking = True
        if before.response_model != after.response_model:
            differences.append("response model changed")
            breaking = True
        if before.status_code != after.status_code:
            differences.append("status code changed")
            breaking = True
        if before.dependencies != after.dependencies:
            differences.append("dependencies changed")
        if differences:
            changes.append(
                RouteChange(
                    "modified",
                    after,
                    before,
                    breaking,
                    "; ".join(differences).capitalize() + ".",
                )
            )
    return changes


def _join_path(prefix: str, path: str) -> str:
    value = "/" + "/".join(part for part in (prefix + "/" + path).split("/") if part)
    return value if value else "/"


def _name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        return None


def _keyword_node(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _keyword_literal(call: ast.Call, name: str) -> Any:
    return _literal(_keyword_node(call, name))


def _keyword_name(call: ast.Call, name: str) -> str | None:
    value = _keyword_node(call, name)
    rendered = _name(value)
    return rendered or None


def _as_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _targets(node: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    return list(node.targets) if isinstance(node, ast.Assign) else [node.target]


def _argument_default(arguments: ast.arguments, argument: ast.arg) -> ast.expr | None:
    positional = [*arguments.posonlyargs, *arguments.args]
    if argument in positional:
        defaults_start = len(positional) - len(arguments.defaults)
        index = positional.index(argument)
        return arguments.defaults[index - defaults_start] if index >= defaults_start else None
    if argument in arguments.kwonlyargs:
        return arguments.kw_defaults[arguments.kwonlyargs.index(argument)]
    return None
