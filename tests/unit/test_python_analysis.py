from __future__ import annotations

from proofstack_analyzers import (
    FastAPIRouteExtractor,
    ImpactAnalyzer,
    PythonAnalyzer,
    PythonGraphBuilder,
    compare_routes,
)


def test_python_analyzer_extracts_symbols_imports_calls_and_complexity() -> None:
    source = """
import importlib
from tools import *

class Parent:
    pass

class Service(Parent):
    @staticmethod
    async def calculate(value: int, flag: bool = False) -> int:
        if value and flag:
            return helper(value)
        return 0

def helper(value: int) -> int:
    importlib.import_module("plugins.demo")
    return value
"""
    analysis = PythonAnalyzer().analyze_source(source, path="app/service.py")

    assert analysis.valid
    symbols = {item.qualified_name: item for item in analysis.symbols}
    method = symbols["app.service.Service.calculate"]
    assert method.symbol_type == "method"
    assert method.owner == "app.service.Service"
    assert method.is_async
    assert method.complexity >= 3
    assert method.decorators == ("staticmethod",)
    assert any(item.target == "helper" for item in analysis.calls)
    assert any(item.dynamic for item in analysis.imports)
    assert {item.rule_id for item in analysis.warnings} == {
        "python.dynamic-import",
        "python.wildcard-import",
    }


def test_nested_function_is_not_misclassified_as_method() -> None:
    analysis = PythonAnalyzer().analyze_source(
        "def outer():\n    def inner():\n        return 1\n    return inner()\n",
        path="module.py",
    )

    inner = next(item for item in analysis.symbols if item.name == "inner")
    assert inner.symbol_type == "function"
    assert inner.owner is None


def test_python_analyzer_tolerates_syntax_errors() -> None:
    analysis = PythonAnalyzer().analyze_source("def broken(:\n", path="broken.py")

    assert not analysis.valid
    assert analysis.syntax_error
    assert analysis.warnings[0].rule_id == "python.syntax-error"


def test_dependency_graph_calculates_reverse_blast_radius() -> None:
    analyses = [
        PythonAnalyzer().analyze_source(
            "def core():\n    return 1\n",
            path="core.py",
        ),
        PythonAnalyzer().analyze_source(
            "from core import core\ndef middle():\n    return core()\n",
            path="middle.py",
        ),
        PythonAnalyzer().analyze_source(
            "from middle import middle\ndef endpoint():\n    return middle()\n",
            path="api.py",
        ),
    ]
    graph = PythonGraphBuilder().build(analyses, changed_symbols=["core.core"])
    radius = graph.blast_radius(["symbol:core.core"])

    assert "symbol:middle.middle" in radius.direct
    assert "symbol:api.endpoint" in radius.one_hop
    visualization = graph.to_visualization(blast_radius=radius)
    assert any(node["changed"] for node in visualization["nodes"])
    assert visualization["total_edges"] >= 4


def test_impact_analyzer_reports_signature_return_and_exception_changes() -> None:
    analyzer = PythonAnalyzer()
    before = [
        analyzer.analyze_source(
            "def convert(value: str) -> int:\n    return 1\n", path="service.py"
        )
    ]
    after = [
        analyzer.analyze_source(
            "def convert(value: str, strict: bool = True) -> int:\n"
            "    if strict:\n        raise ValueError('invalid')\n"
            "    return int(value)\n",
            path="service.py",
        )
    ]
    graph = PythonGraphBuilder().build(after, changed_symbols=["service.convert"])
    result = ImpactAnalyzer().analyze(before, after, graph, ["service.convert"])
    rules = {item.rule_id for item in result.findings}

    assert "impact.python-signature-changed" in rules
    assert "impact.python-behavior-changed" in rules


def test_fastapi_routes_include_models_status_dependencies_and_breaking_changes() -> None:
    before = """
from fastapi import APIRouter, Depends
router = APIRouter(prefix="/v1")
@router.post("/items", response_model=ItemOut, status_code=201)
def create(item: ItemIn, user=Depends(auth)):
    return item
"""
    after = before.replace("ItemOut", "NewItemOut").replace("status_code=201", "status_code=202")
    extractor = FastAPIRouteExtractor()
    routes = extractor.extract(before)

    assert routes[0].path == "/v1/items"
    assert routes[0].method == "POST"
    assert routes[0].request_models == ("ItemIn",)
    assert routes[0].dependencies == ("auth",)
    changes = compare_routes(routes, extractor.extract(after))
    assert changes[0].breaking
    assert "response model changed" in changes[0].explanation.lower()
