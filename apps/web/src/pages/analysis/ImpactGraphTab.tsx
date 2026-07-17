import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import { GitFork, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";

import { api } from "../../api/client";
import type { GraphNode } from "../../api/types";
import { titleCase } from "../../components/format";
import { Badge, Card, EmptyState, ErrorState, LoadingState, cx } from "../../components/ui";
import type { AnalysisOutletContext } from "../AnalysisPage";

const limit = 350;

export function ImpactGraphTab() {
  const { analysis } = useOutletContext<AnalysisOutletContext>();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const query = useQuery({
    queryKey: ["analysis", analysis.id, "graph"],
    queryFn: () => api.analyses.graph(analysis.id),
  });

  const view = useMemo(() => {
    const sourceNodes = (query.data?.nodes ?? []).slice(0, limit);
    const visibleIds = new Set(sourceNodes.map((node) => node.id));
    const graphNodes: Node[] = sourceNodes.map((node, index) => {
      const columns = Math.max(3, Math.ceil(Math.sqrt(sourceNodes.length * 1.7)));
      const isMatch =
        !search ||
        `${node.label ?? node.name ?? ""} ${node.file_path ?? ""}`
          .toLowerCase()
          .includes(search.toLowerCase());
      return {
        id: node.id,
        position: { x: (index % columns) * 210, y: Math.floor(index / columns) * 115 },
        data: { label: node.label ?? node.name ?? node.id },
        className: cx(
          "graph-node",
          `graph-node--${node.type ?? "symbol"}`,
          node.changed && "graph-node--changed",
          node.blast_radius && "graph-node--blast",
          !isMatch && "graph-node--dim",
        ),
      };
    });
    const graphEdges: Edge[] = (query.data?.edges ?? [])
      .filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target))
      .map((edge, index) => ({
        id: edge.id ?? `${edge.source}-${edge.target}-${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.edge_type ?? edge.type,
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--graph-edge)" },
        style: { stroke: "var(--graph-edge)", strokeWidth: 1.25 },
        labelStyle: { fill: "var(--text-muted)", fontSize: 10 },
      }));
    return { graphNodes, graphEdges, sourceNodes };
  }, [query.data, search]);

  const onNodeClick: NodeMouseHandler = (_event, node) =>
    setSelected(view.sourceNodes.find((item) => item.id === node.id) ?? null);

  if (query.isLoading) return <LoadingState label="Building the impact graph…" />;
  if (query.isError) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  if (!query.data?.nodes.length)
    return (
      <EmptyState
        icon={<GitFork />}
        title="No dependency graph available"
        description="No supported symbols or dependency edges were discovered for this change."
      />
    );

  return (
    <div className="graph-tab">
      <Card className="graph-toolbar">
        <label className="search-field">
          <Search size={17} />
          <span className="sr-only">Search graph</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Find a file or symbol…"
          />
        </label>
        <div className="graph-legend">
          <span>
            <i className="legend-file" /> File
          </span>
          <span>
            <i className="legend-symbol" /> Symbol
          </span>
          <span>
            <i className="legend-changed" /> Changed
          </span>
          <span>
            <i className="legend-blast" /> Blast radius
          </span>
        </div>
        <span className="result-count">
          {Math.min(query.data.nodes.length, limit)} nodes · {query.data.edges.length} edges
        </span>
      </Card>
      {query.data.nodes.length > limit || query.data.truncated ? (
        <div className="notice">
          Large graph protection is active. Showing {limit} of{" "}
          {query.data.total_nodes ?? query.data.nodes.length} nodes. Search and server filters can
          narrow the view.
        </div>
      ) : null}
      <Card className="graph-canvas" aria-label="Code impact graph">
        <ReactFlow
          nodes={view.graphNodes}
          edges={view.graphEdges}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.15}
          maxZoom={2}
          nodesDraggable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="var(--chart-grid)" gap={24} size={1} />
          <MiniMap
            nodeColor={(node) =>
              node.className?.includes("changed")
                ? "#f2674e"
                : node.className?.includes("file")
                  ? "#bd6a54"
                  : "#8f8791"
            }
            pannable
            zoomable
          />
          <Controls showInteractive={false} />
        </ReactFlow>
        {selected ? (
          <aside className="node-detail">
            <button
              className="icon-button"
              aria-label="Close node details"
              onClick={() => setSelected(null)}
            >
              <X size={16} />
            </button>
            <Badge tone={selected.changed ? "warn" : "neutral"}>{selected.type ?? "symbol"}</Badge>
            <h2>{selected.label ?? selected.name ?? selected.id}</h2>
            {selected.file_path ? <p>{selected.file_path}</p> : null}
            <dl>
              <div>
                <dt>Changed</dt>
                <dd>{selected.changed ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt>Blast radius</dt>
                <dd>{selected.blast_radius ? "Potentially affected" : "Not marked"}</dd>
              </div>
              <div>
                <dt>Risk score</dt>
                <dd>{selected.risk_score ?? "—"}</dd>
              </div>
            </dl>
            {selected.metadata ? (
              <div className="metadata-list">
                {Object.entries(selected.metadata)
                  .slice(0, 8)
                  .map(([key, value]) => (
                    <div key={key}>
                      <small>{titleCase(key)}</small>
                      <span>{String(value)}</span>
                    </div>
                  ))}
              </div>
            ) : null}
          </aside>
        ) : null}
      </Card>
    </div>
  );
}
