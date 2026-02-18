"use client";

import { useParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api";
import BPMNViewerComponent from "@/components/BPMNViewer";

interface ProcessData {
  models: Array<{
    model_id: string;
    name: string;
    bpmn_xml: string;
    element_confidences: Record<string, number>;
  }>;
  evidence_map: Record<string, string[]>;
}

export default function ProcessExplorerPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;
  const [data, setData] = useState<ProcessData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<number>(0);
  const [selectedElement, setSelectedElement] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const result = await apiGet<ProcessData>(
          `/api/v1/portal/${engagementId}/process`,
        );
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load process data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  const handleElementClick = useCallback((elementId: string, elementName: string) => {
    setSelectedElement(elementName);
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-gray-500">Loading process models...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  const models = data?.models ?? [];
  const currentModel = models[selectedModel];
  const evidenceMap = data?.evidence_map ?? {};

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Process Explorer
      </h2>

      {models.length > 1 && (
        <div className="mb-4">
          <select
            value={selectedModel}
            onChange={(e) => { setSelectedModel(Number(e.target.value)); setSelectedElement(null); }}
            className="rounded-md border border-gray-300 p-2 text-sm"
          >
            {models.map((m, i) => (
              <option key={m.model_id} value={i}>{m.name}</option>
            ))}
          </select>
        </div>
      )}

      <div className="flex gap-6">
        <div className="flex-1 rounded-lg border border-gray-200 bg-white shadow">
          {currentModel ? (
            <div className="h-[500px]">
              <BPMNViewerComponent
                bpmnXml={currentModel.bpmn_xml}
                elementConfidences={currentModel.element_confidences}
                showConfidenceOverlay={true}
                onElementClick={handleElementClick}
              />
            </div>
          ) : (
            <div className="flex h-96 items-center justify-center">
              <span className="text-gray-400">No process models available</span>
            </div>
          )}
        </div>

        {selectedElement && (
          <div className="w-80 rounded-lg border border-gray-200 bg-white p-4 shadow">
            <h3 className="mb-3 text-sm font-semibold text-gray-900">
              {selectedElement}
            </h3>
            {currentModel && currentModel.element_confidences[selectedElement] !== undefined && (
              <p className="mb-2 text-xs text-gray-500">
                Confidence: {Math.round(currentModel.element_confidences[selectedElement] * 100)}%
              </p>
            )}
            <h4 className="mb-2 text-xs font-medium uppercase text-gray-400">
              Linked Evidence
            </h4>
            {evidenceMap[selectedElement] ? (
              <ul className="space-y-1">
                {evidenceMap[selectedElement].map((eid) => (
                  <li key={eid} className="text-xs text-blue-600">{eid}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">No evidence linked</p>
            )}
            <button
              onClick={() => setSelectedElement(null)}
              className="mt-4 text-xs text-gray-400 hover:text-gray-600"
            >
              Close panel
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
