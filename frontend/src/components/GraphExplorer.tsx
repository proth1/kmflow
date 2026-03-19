"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { Core, NodeSingular, EventObject } from "cytoscape";

interface CytoscapeNodeData {
  data: {
    id: string;
    label: string;
    type: string;
    [key: string]: unknown;
  };
}

interface CytoscapeEdgeData {
  data: {
    id: string;
    source: string;
    target: string;
    label: string;
    [key: string]: unknown;
  };
}

interface GraphExplorerProps {
  nodes: CytoscapeNodeData[];
  edges: CytoscapeEdgeData[];
}

const NODE_COLORS: Record<string, string> = {
  Process: "#3b82f6",
  Activity: "#22c55e",
  Evidence: "#f59e0b",
  Entity: "#8b5cf6",
  Document: "#ec4899",
  Person: "#06b6d4",
  Organization: "#10b981",
  Role: "#6366f1",
};

type LayoutName = "cose" | "breadthfirst" | "circle" | "grid";

export default function GraphExplorer({ nodes, edges }: GraphExplorerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [layout, setLayout] = useState<LayoutName>("cose");
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<Record<string, unknown> | null>(null);
  const [nodeTypes, setNodeTypes] = useState<string[]>([]);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  const [graphReady, setGraphReady] = useState(false);

  // Extract unique node types
  useEffect(() => {
    const types = [...new Set(nodes.map((n) => n.data.type))];
    setNodeTypes(types);
    setActiveTypes(new Set(types));
  }, [nodes]);

  const initCytoscape = useCallback(async () => {
    if (!containerRef.current) return;

    setGraphReady(false);
    const cytoscape = (await import("cytoscape")).default;

    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const filteredNodes = nodes.filter((n) => activeTypes.has(n.data.type));
    const nodeIds = new Set(filteredNodes.map((n) => n.data.id));
    const filteredEdges = edges.filter(
      (e) => nodeIds.has(e.data.source) && nodeIds.has(e.data.target),
    );

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...filteredNodes.map((n) => ({ group: "nodes" as const, data: n.data })),
        ...filteredEdges.map((e) => ({ group: "edges" as const, data: e.data })),
      ],
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 6,
            "font-size": "11px",
            "font-weight": "bold" as any,
            "text-wrap": "wrap",
            "text-max-width": "100px",
            width: 50,
            height: 50,
            "background-color": (ele: NodeSingular) => NODE_COLORS[ele.data("type") as string] ?? "#9ca3af",
            "border-width": 2,
            "border-color": (ele: NodeSingular) => {
              const base = NODE_COLORS[ele.data("type")] ?? "#9ca3af";
              return base;
            },
            "border-opacity": 0.3,
            color: "#1f2937",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px" as any,
            "text-background-shape": "roundrectangle",
          },
        },
        {
          selector: "node:active",
          style: {
            "overlay-opacity": 0.1,
          },
        },
        {
          selector: "edge",
          style: {
            label: "",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "line-color": "#cbd5e1",
            "target-arrow-color": "#cbd5e1",
            width: 1.5,
            opacity: 0.6,
          },
        },
        {
          selector: "edge:active, edge.hover",
          style: {
            label: "data(label)",
            "font-size": "10px",
            "text-rotation": "autorotate",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.95,
            "text-background-padding": "3px" as any,
            "text-background-shape": "roundrectangle",
            color: "#374151",
            "line-color": "#6366f1",
            "target-arrow-color": "#6366f1",
            width: 2.5,
            opacity: 1,
            "z-index": 10,
          },
        },
        {
          selector: "node.highlight",
          style: {
            "border-width": 3,
            "border-color": "#2563eb",
            "border-opacity": 1,
          },
        },
        {
          selector: "edge.highlight",
          style: {
            label: "data(label)",
            "font-size": "10px",
            "text-rotation": "autorotate",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.95,
            "text-background-padding": "3px" as any,
            "text-background-shape": "roundrectangle",
            color: "#374151",
            "line-color": "#6366f1",
            "target-arrow-color": "#6366f1",
            width: 2.5,
            opacity: 1,
          },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 3,
            "border-color": "#2563eb",
          },
        },
        {
          selector: ".faded",
          style: {
            opacity: 0.15,
          },
        },
      ],
      layout: {
        name: layout,
        animate: true,
        ...(layout === "cose"
          ? {
              idealEdgeLength: 120,
              nodeOverlap: 30,
              nodeRepulsion: 8000 as any,
              gravity: 0.4,
              padding: 50,
            }
          : {}),
        ...(layout === "breadthfirst" ? { spacingFactor: 1.5, padding: 30 } : {}),
        ...(layout === "circle" ? { spacingFactor: 1.3, padding: 30 } : {}),
        ...(layout === "grid" ? { spacingFactor: 1.5, padding: 30 } : {}),
      },
    });

    cy.on("tap", "node", (event: EventObject) => {
      const data = (event.target as NodeSingular).data();
      setSelectedNode(data as Record<string, unknown>);
    });

    cy.on("tap", (event: EventObject) => {
      if (event.target === cy) {
        setSelectedNode(null);
      }
    });

    // Hover: highlight connected edges + show their labels
    cy.on("mouseover", "node", (event: EventObject) => {
      const node = event.target as NodeSingular;
      node.addClass("highlight");
      node.connectedEdges().addClass("highlight");
      node.neighborhood("node").addClass("highlight");
    });

    cy.on("mouseout", "node", (event: EventObject) => {
      const node = event.target as NodeSingular;
      node.removeClass("highlight");
      node.connectedEdges().removeClass("highlight");
      node.neighborhood("node").removeClass("highlight");
    });

    cy.on("mouseover", "edge", (event: EventObject) => {
      (event.target as NodeSingular).addClass("hover");
    });

    cy.on("mouseout", "edge", (event: EventObject) => {
      (event.target as NodeSingular).removeClass("hover");
    });

    cyRef.current = cy;
    setGraphReady(true);
  }, [nodes, edges, layout, activeTypes]);

  useEffect(() => {
    initCytoscape();
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [initCytoscape]);

  // Search handler
  useEffect(() => {
    if (!cyRef.current || !search) {
      cyRef.current?.elements().removeClass("faded");
      return;
    }
    const cy = cyRef.current;
    const lower = search.toLowerCase();
    cy.elements().addClass("faded");
    cy.nodes().filter((n: NodeSingular) => {
      const label = ((n.data("label") as string) || "").toLowerCase();
      return label.includes(lower);
    }).removeClass("faded").connectedEdges().removeClass("faded");
  }, [search]);

  const toggleType = (type: string) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  };

  return (
    <div className="flex h-full gap-4">
      <div className="flex flex-1 flex-col">
        <div className="mb-3 flex items-center gap-3">
          <label htmlFor="graph-layout" className="sr-only">Graph layout</label>
          <select
            id="graph-layout"
            value={layout}
            onChange={(e) => setLayout(e.target.value as LayoutName)}
            aria-label="Graph layout"
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="cose">Force-directed</option>
            <option value="breadthfirst">Hierarchical</option>
            <option value="circle">Circular</option>
            <option value="grid">Grid</option>
          </select>
          <label htmlFor="graph-search" className="sr-only">Search nodes</label>
          <input
            id="graph-search"
            type="text"
            placeholder="Search nodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search nodes"
            className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          {nodeTypes.map((type) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
              aria-label={`${activeTypes.has(type) ? "Hide" : "Show"} ${type} nodes`}
              aria-pressed={activeTypes.has(type)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                activeTypes.has(type)
                  ? "text-white"
                  : "bg-gray-200 text-gray-500"
              }`}
              style={activeTypes.has(type) ? { backgroundColor: NODE_COLORS[type] ?? "#9ca3af" } : {}}
            >
              {type}
            </button>
          ))}
        </div>

        <div className="relative flex-1">
          {!graphReady && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg border border-gray-200 bg-white">
              <div className="text-center">
                <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-gray-300 border-t-blue-600" />
                <p className="text-sm text-gray-500">Rendering graph...</p>
              </div>
            </div>
          )}
          <div
            ref={containerRef}
            className="h-full rounded-lg border border-gray-200 bg-white min-h-[500px]"
          />
        </div>
      </div>

      {selectedNode && (
        <div className="w-72 rounded-lg border border-gray-200 bg-white p-4 shadow">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">
              {String(selectedNode.label || selectedNode.id)}
            </h3>
            <button
              onClick={() => setSelectedNode(null)}
              aria-label="Close node details"
              className="text-gray-400 hover:text-gray-600"
            >
              x
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">Type: {String(selectedNode.type)}</p>
          <div className="mt-3 space-y-1">
            {Object.entries(selectedNode)
              .filter(([k]) => !["id", "label", "type"].includes(k))
              .map(([key, value]) => (
                <div key={key} className="text-xs">
                  <span className="font-medium text-gray-600">{key}:</span>{" "}
                  <span className="text-gray-500">{String(value)}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
