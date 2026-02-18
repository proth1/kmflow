"use client";

import { useEffect, useRef, useState, useCallback } from "react";

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
  const cyRef = useRef<any>(null);
  const [layout, setLayout] = useState<LayoutName>("cose");
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<Record<string, unknown> | null>(null);
  const [nodeTypes, setNodeTypes] = useState<string[]>([]);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());

  // Extract unique node types
  useEffect(() => {
    const types = [...new Set(nodes.map((n) => n.data.type))];
    setNodeTypes(types);
    setActiveTypes(new Set(types));
  }, [nodes]);

  const initCytoscape = useCallback(async () => {
    if (!containerRef.current) return;

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
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "10px",
            "text-wrap": "wrap",
            "text-max-width": "80px",
            width: 40,
            height: 40,
            "background-color": (ele: any) => NODE_COLORS[ele.data("type")] ?? "#9ca3af",
            color: "#1f2937",
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(label)",
            "font-size": "8px",
            "text-rotation": "autorotate",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "line-color": "#d1d5db",
            "target-arrow-color": "#d1d5db",
            width: 1,
            color: "#9ca3af",
          },
        },
        {
          selector: ":selected",
          style: {
            "border-width": 3,
            "border-color": "#2563eb",
          },
        },
      ],
      layout: { name: layout, animate: true },
    });

    cy.on("tap", "node", (event: any) => {
      const data = event.target.data();
      setSelectedNode(data);
    });

    cy.on("tap", (event: any) => {
      if (event.target === cy) {
        setSelectedNode(null);
      }
    });

    cyRef.current = cy;
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
    cy.nodes().filter((n: any) => {
      const label = (n.data("label") || "").toLowerCase();
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
          <select
            value={layout}
            onChange={(e) => setLayout(e.target.value as LayoutName)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="cose">Force-directed</option>
            <option value="breadthfirst">Hierarchical</option>
            <option value="circle">Circular</option>
            <option value="grid">Grid</option>
          </select>
          <input
            type="text"
            placeholder="Search nodes..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
          />
        </div>

        <div className="mb-3 flex flex-wrap gap-2">
          {nodeTypes.map((type) => (
            <button
              key={type}
              onClick={() => toggleType(type)}
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

        <div
          ref={containerRef}
          className="flex-1 rounded-lg border border-gray-200 bg-white"
          style={{ minHeight: "500px" }}
        />
      </div>

      {selectedNode && (
        <div className="w-72 rounded-lg border border-gray-200 bg-white p-4 shadow">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-900">
              {String(selectedNode.label || selectedNode.id)}
            </h3>
            <button
              onClick={() => setSelectedNode(null)}
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
