"""Deterministic dependency and blast-radius graph construction."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field

from .python_ast import PythonAnalysis


@dataclass(slots=True, frozen=True)
class GraphNode:
    id: str
    label: str
    kind: str
    path: str | None = None
    changed: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class GraphEdge:
    source: str
    target: str
    edge_type: str
    confidence: float = 1.0


@dataclass(slots=True)
class BlastRadius:
    changed: tuple[str, ...]
    direct: tuple[str, ...]
    one_hop: tuple[str, ...]
    transitive: tuple[str, ...]
    distances: dict[str, int]

    @property
    def all_impacted(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.direct) | set(self.one_hop) | set(self.transitive)))


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._edge_keys: set[tuple[str, str, str]] = set()

    def add_node(self, node: GraphNode) -> None:
        existing = self.nodes.get(node.id)
        if existing is None or (node.changed and not existing.changed):
            self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source == edge.target:
            return
        key = (edge.source, edge.target, edge.edge_type)
        if key not in self._edge_keys:
            self.edges.append(edge)
            self._edge_keys.add(key)

    def fan_in(self, node_id: str, *, edge_types: set[str] | None = None) -> int:
        return len(
            {
                edge.source
                for edge in self.edges
                if edge.target == node_id and (edge_types is None or edge.edge_type in edge_types)
            }
        )

    def fan_out(self, node_id: str) -> int:
        return len({edge.target for edge in self.edges if edge.source == node_id})

    def blast_radius(self, changed: Iterable[str], *, max_depth: int = 4) -> BlastRadius:
        changed_set = {item for item in changed if item in self.nodes}
        reverse: dict[str, set[str]] = defaultdict(set)
        for edge in self.edges:
            reverse[edge.target].add(edge.source)
        distances: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque((node, 0) for node in sorted(changed_set))
        visited = set(changed_set)
        while queue:
            current, distance = queue.popleft()
            if distance >= max_depth:
                continue
            for dependent in sorted(reverse.get(current, ())):
                if dependent in visited:
                    continue
                visited.add(dependent)
                distances[dependent] = distance + 1
                queue.append((dependent, distance + 1))
        direct = tuple(sorted(node for node, distance in distances.items() if distance == 1))
        one_hop = tuple(sorted(node for node, distance in distances.items() if distance == 2))
        transitive = tuple(sorted(node for node, distance in distances.items() if distance >= 3))
        return BlastRadius(tuple(sorted(changed_set)), direct, one_hop, transitive, distances)

    def to_visualization(
        self,
        *,
        blast_radius: BlastRadius | None = None,
        max_nodes: int = 2_000,
    ) -> dict[str, object]:
        impacted = set(blast_radius.all_impacted) if blast_radius else set()
        distances = blast_radius.distances if blast_radius else {}
        ordered_ids = sorted(
            self.nodes,
            key=lambda node_id: (
                0 if self.nodes[node_id].changed else 1,
                distances.get(node_id, max_nodes + 1),
                node_id,
            ),
        )[:max_nodes]
        selected = set(ordered_ids)
        nodes = []
        for node_id in ordered_ids:
            value = asdict(self.nodes[node_id])
            value["impacted"] = node_id in impacted
            value["distance"] = distances.get(node_id)
            nodes.append(value)
        edges = [
            asdict(edge)
            for edge in sorted(
                self.edges, key=lambda item: (item.source, item.target, item.edge_type)
            )
            if edge.source in selected and edge.target in selected
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "truncated": len(self.nodes) > max_nodes,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }


class PythonGraphBuilder:
    def build(
        self,
        analyses: Iterable[PythonAnalysis],
        *,
        changed_symbols: Iterable[str] = (),
    ) -> DependencyGraph:
        analysis_list = list(analyses)
        changed = set(changed_symbols)
        graph = DependencyGraph()
        modules = {analysis.module for analysis in analysis_list}
        symbol_by_short: dict[str, set[str]] = defaultdict(set)
        symbol_ids: set[str] = set()
        for analysis in analysis_list:
            module_id = f"module:{analysis.module}"
            graph.add_node(GraphNode(module_id, analysis.module, "module", analysis.path))
            for symbol in analysis.symbols:
                symbol_id = f"symbol:{symbol.qualified_name}"
                symbol_ids.add(symbol_id)
                symbol_by_short[symbol.name].add(symbol_id)
                graph.add_node(
                    GraphNode(
                        symbol_id,
                        symbol.qualified_name,
                        symbol.symbol_type,
                        symbol.path,
                        changed=symbol.qualified_name in changed or symbol_id in changed,
                        metadata={
                            "complexity": symbol.complexity,
                            "exported": symbol.exported,
                            "signature": symbol.signature,
                        },
                    )
                )
                graph.add_edge(GraphEdge(module_id, symbol_id, "defines"))
        for analysis in analysis_list:
            for symbol in analysis.symbols:
                for base in symbol.bases:
                    target = _resolve_symbol(base, symbol_by_short, symbol_ids)
                    if target:
                        graph.add_edge(
                            GraphEdge(f"symbol:{symbol.qualified_name}", target, "inherits", 0.8)
                        )
        for analysis in analysis_list:
            source_module = f"module:{analysis.module}"
            for imported in analysis.imports:
                target_module = _resolve_module(analysis.module, imported.source_module)
                imported_module = (
                    f"{target_module}.{imported.imported_name}"
                    if target_module and imported.imported_name
                    else imported.imported_name or ""
                )
                if imported_module in modules:
                    target_module = imported_module
                if target_module in modules:
                    graph.add_edge(
                        GraphEdge(source_module, f"module:{target_module}", "imports", 1.0)
                    )
            for call in analysis.calls:
                source = _resolve_caller(call.caller, symbol_ids, source_module)
                target = _resolve_symbol(call.target, symbol_by_short, symbol_ids)
                if target:
                    graph.add_edge(GraphEdge(source, target, "calls", 0.9))
        return graph


def _resolve_caller(caller: str, symbols: set[str], module_id: str) -> str:
    candidate = f"symbol:{caller}"
    return candidate if candidate in symbols else module_id


def _resolve_symbol(
    target: str,
    by_short: dict[str, set[str]],
    symbol_ids: set[str],
) -> str | None:
    exact = f"symbol:{target}"
    if exact in symbol_ids:
        return exact
    matches = by_short.get(target.rsplit(".", 1)[-1], set())
    return next(iter(matches)) if len(matches) == 1 else None


def _resolve_module(current: str, imported: str) -> str:
    if not imported.startswith("."):
        return imported
    level = len(imported) - len(imported.lstrip("."))
    remainder = imported[level:]
    parts = current.split(".")[:-level]
    if remainder:
        parts.extend(remainder.split("."))
    return ".".join(parts)
