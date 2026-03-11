"use client";

import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { OntologyClass, OntologyProperty } from "@/lib/api/ontology";

interface OntologyGraphProps {
  classes: OntologyClass[];
  properties: OntologyProperty[];
}

export default function OntologyGraph({ classes, properties }: OntologyGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || classes.length === 0) return;

    const elements: cytoscape.ElementDefinition[] = [];

    // Add class nodes
    for (const cls of classes) {
      elements.push({
        data: {
          id: cls.id,
          label: cls.name,
          instances: cls.instance_count,
          confidence: cls.confidence,
        },
      });
    }

    // Build name → id map for property edges
    const nameToId = new Map(classes.map((c) => [c.name, c.id]));

    // Add property edges
    for (const prop of properties) {
      if (prop.domain && prop.range) {
        const sourceId = nameToId.get(prop.domain);
        const targetId = nameToId.get(prop.range);
        if (sourceId && targetId) {
          elements.push({
            data: {
              id: `prop-${prop.id}`,
              source: sourceId,
              target: targetId,
              label: prop.name,
              usage: prop.usage_count,
            },
          });
        }
      }
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": "#4F46E5",
            color: "#1F2937",
            "text-valign": "bottom",
            "text-margin-y": 8,
            "font-size": "12px",
            width: "mapData(instances, 0, 50, 30, 80)",
            height: "mapData(instances, 0, 50, 30, 80)",
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(label)",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "line-color": "#94A3B8",
            "target-arrow-color": "#94A3B8",
            "font-size": "10px",
            color: "#64748B",
            width: 2,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        nodeDimensionsIncludeLabels: true,
      },
    });

    return () => {
      cy.destroy();
    };
  }, [classes, properties]);

  if (classes.length === 0) {
    return <p className="text-muted-foreground text-sm">No classes to visualize</p>;
  }

  return <div ref={containerRef} style={{ width: "100%", height: "500px" }} />;
}
