"""Python AST extraction with tolerant syntax handling and stable graph inputs."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .diff import DiffFile


@dataclass(slots=True, frozen=True)
class AnalyzerWarning:
    rule_id: str
    message: str
    path: str
    line: int | None = None


@dataclass(slots=True, frozen=True)
class ImportReference:
    source_module: str
    imported_name: str | None
    alias: str | None
    line: int
    wildcard: bool = False
    dynamic: bool = False


@dataclass(slots=True, frozen=True)
class CallReference:
    caller: str
    target: str
    line: int


@dataclass(slots=True)
class PythonSymbol:
    qualified_name: str
    name: str
    symbol_type: str
    module: str
    path: str
    start_line: int
    end_line: int
    signature: str
    decorators: tuple[str, ...] = ()
    bases: tuple[str, ...] = ()
    complexity: int = 1
    exported: bool = True
    owner: str | None = None
    is_async: bool = False
    return_shapes: tuple[str, ...] = ()
    raises: tuple[str, ...] = ()


@dataclass(slots=True)
class PythonAnalysis:
    path: str
    module: str
    symbols: list[PythonSymbol] = field(default_factory=list)
    imports: list[ImportReference] = field(default_factory=list)
    calls: list[CallReference] = field(default_factory=list)
    warnings: list[AnalyzerWarning] = field(default_factory=list)
    syntax_error: str | None = None

    @property
    def valid(self) -> bool:
        return self.syntax_error is None


@runtime_checkable
class LanguageAnalyzer(Protocol):
    language: str

    def analyze_path(self, path: Path, root: Path) -> PythonAnalysis:
        """Analyze one source file into normalized symbols and relationships."""


class PythonAnalyzer:
    language = "python"

    def __init__(self, *, max_file_bytes: int = 2_000_000) -> None:
        self.max_file_bytes = max_file_bytes

    def discover(self, root: Path, *, max_files: int = 10_000) -> list[Path]:
        resolved_root = root.resolve()
        paths: list[Path] = []
        for candidate in sorted(resolved_root.rglob("*.py")):
            if len(paths) >= max_files:
                raise ValueError(f"Python file count exceeds the limit of {max_files}")
            if candidate.is_symlink() or not candidate.is_file():
                continue
            try:
                candidate.resolve().relative_to(resolved_root)
            except ValueError:
                continue
            if candidate.stat().st_size <= self.max_file_bytes:
                paths.append(candidate)
        return paths

    def analyze_path(self, path: Path, root: Path) -> PythonAnalysis:
        resolved_root = root.resolve()
        resolved_path = path.resolve()
        try:
            relative = resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("Python source path is outside the analysis root") from exc
        if resolved_path.stat().st_size > self.max_file_bytes:
            raise ValueError("Python source file exceeds the configured size limit")
        source = resolved_path.read_text(encoding="utf-8", errors="replace")
        return self.analyze_source(source, path=relative.as_posix())

    def analyze_source(self, source: str, *, path: str = "module.py") -> PythonAnalysis:
        module = _module_name(path)
        result = PythonAnalysis(path=path, module=module)
        try:
            tree = ast.parse(source, filename=path, type_comments=True)
        except SyntaxError as exc:
            result.syntax_error = f"{exc.msg} at line {exc.lineno or 0}"
            result.warnings.append(
                AnalyzerWarning(
                    "python.syntax-error",
                    "Python syntax could not be analyzed safely.",
                    path,
                    exc.lineno,
                )
            )
            return result
        visitor = _ExtractionVisitor(result)
        visitor.visit(tree)
        _apply_exports(tree, result.symbols)
        return result

    def analyze_repository(self, root: Path, *, max_files: int = 10_000) -> list[PythonAnalysis]:
        return [self.analyze_path(path, root) for path in self.discover(root, max_files=max_files)]

    @staticmethod
    def changed_symbols(analysis: PythonAnalysis, diff_file: DiffFile) -> list[PythonSymbol]:
        ranges = diff_file.changed_new_ranges
        if diff_file.change_type.value == "added" and not ranges:
            return list(analysis.symbols)
        return [
            symbol
            for symbol in analysis.symbols
            if any(start <= symbol.end_line and end >= symbol.start_line for start, end in ranges)
        ]


class _ExtractionVisitor(ast.NodeVisitor):
    def __init__(self, result: PythonAnalysis) -> None:
        self.result = result
        self.scope: list[str] = []
        self.scope_kinds: list[str] = []
        self.class_owners: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.result.imports.append(ImportReference(alias.name, None, alias.asname, node.lineno))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        prefix = "." * node.level
        module = prefix + (node.module or "")
        for alias in node.names:
            wildcard = alias.name == "*"
            self.result.imports.append(
                ImportReference(module, alias.name, alias.asname, node.lineno, wildcard=wildcard)
            )
            if wildcard:
                self.result.warnings.append(
                    AnalyzerWarning(
                        "python.wildcard-import",
                        f"Wildcard import from {module} obscures dependency analysis.",
                        self.result.path,
                        node.lineno,
                    )
                )

    def visit_Call(self, node: ast.Call) -> None:
        target = _name(node.func)
        if target:
            self.result.calls.append(CallReference(self._current_scope(), target, node.lineno))
        if target in {"importlib.import_module", "__import__"}:
            imported = "<dynamic>"
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                imported = node.args[0].value
            self.result.imports.append(
                ImportReference(imported, None, None, node.lineno, dynamic=True)
            )
            self.result.warnings.append(
                AnalyzerWarning(
                    "python.dynamic-import",
                    "Dynamic import may hide runtime dependencies.",
                    self.result.path,
                    node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = self._qualify(node.name)
        symbol = PythonSymbol(
            qualified_name=qualified,
            name=node.name,
            symbol_type="class",
            module=self.result.module,
            path=self.result.path,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=f"class {node.name}",
            decorators=tuple(filter(None, (_name(item) for item in node.decorator_list))),
            bases=tuple(filter(None, (_name(item) for item in node.bases))),
            complexity=_complexity(node),
            exported=not node.name.startswith("_"),
            owner=self.class_owners[-1] if self.class_owners else None,
        )
        self.result.symbols.append(symbol)
        self.scope.append(node.name)
        self.scope_kinds.append("class")
        self.class_owners.append(qualified)
        self.generic_visit(node)
        self.class_owners.pop()
        self.scope_kinds.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        owner = (
            self.class_owners[-1]
            if self.class_owners and self.scope_kinds and self.scope_kinds[-1] == "class"
            else None
        )
        qualified = self._qualify(node.name)
        prefix = "async " if is_async else ""
        try:
            rendered_args = ast.unparse(node.args)
        except Exception:
            rendered_args = "..."
        returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
        return_shapes, raises = _function_behavior(node)
        self.result.symbols.append(
            PythonSymbol(
                qualified_name=qualified,
                name=node.name,
                symbol_type="method" if owner else "function",
                module=self.result.module,
                path=self.result.path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                signature=f"{prefix}{node.name}({rendered_args}){returns}",
                decorators=tuple(filter(None, (_name(item) for item in node.decorator_list))),
                complexity=_complexity(node),
                exported=not node.name.startswith("_"),
                owner=owner,
                is_async=is_async,
                return_shapes=return_shapes,
                raises=raises,
            )
        )
        self.scope.append(node.name)
        self.scope_kinds.append("function")
        self.generic_visit(node)
        self.scope_kinds.pop()
        self.scope.pop()

    def _qualify(self, name: str) -> str:
        parts = [self.result.module, *self.scope, name]
        return ".".join(part for part in parts if part)

    def _current_scope(self) -> str:
        parts = [self.result.module, *self.scope]
        return ".".join(part for part in parts if part)


def _complexity(node: ast.AST) -> int:
    score = 1
    branching = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.IfExp,
        ast.ExceptHandler,
        ast.Assert,
        ast.comprehension,
        ast.Match,
    )
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, branching):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
    return score


class _BehaviorVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.return_shapes: set[str] = set()
        self.raises: set[str] = set()

    def visit_Return(self, node: ast.Return) -> None:
        self.return_shapes.add(_return_shape(node.value))

    def visit_Raise(self, node: ast.Raise) -> None:
        exception = node.exc
        if isinstance(exception, ast.Call):
            exception = exception.func
        rendered = _name(exception)
        self.raises.add(rendered or "dynamic_exception")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return None


def _function_behavior(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    visitor = _BehaviorVisitor()
    for statement in node.body:
        visitor.visit(statement)
    return tuple(sorted(visitor.return_shapes)), tuple(sorted(visitor.raises))


def _return_shape(node: ast.AST | None) -> str:
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
        return "none"
    if isinstance(node, ast.Constant):
        return f"constant:{type(node.value).__name__}"
    if isinstance(node, ast.Name):
        return f"name:{node.id}"
    if isinstance(node, ast.Call):
        return f"call:{_name(node.func) or 'dynamic'}"
    if isinstance(node, ast.Dict):
        return "mapping"
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return "sequence"
    if isinstance(node, ast.Yield | ast.YieldFrom):
        return "generator"
    return type(node).__name__.lower()


def _name(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr
    if isinstance(node, ast.Subscript):
        return _name(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _module_name(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.endswith(".py"):
        normalized = normalized[:-3]
    parts = [part for part in normalized.split("/") if part and part != "__init__"]
    return ".".join(parts)


def _apply_exports(tree: ast.Module, symbols: list[PythonSymbol]) -> None:
    explicit: set[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in _targets(node)
        ):
            value = node.value
            if isinstance(value, ast.List | ast.Tuple | ast.Set):
                explicit = {
                    item.value
                    for item in value.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                }
    if explicit is not None:
        for symbol in symbols:
            if symbol.owner is None:
                symbol.exported = symbol.name in explicit


def _targets(node: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    return [node.target]
