"use client";

import { useState, useEffect, useRef } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ReferenceModel {
  id: string;
  name: string;
  industry: string;
  process_area: string;
  created_at: string;
}

interface ConformanceResult {
  fitness: number;
  precision: number;
  f1_score: number;
  matching_elements: number;
  total_reference_elements: number;
  total_observed_elements: number;
  deviations: Deviation[];
}

interface Deviation {
  element_name: string;
  deviation_type: string;
  severity: "high" | "medium" | "low";
  description: string;
}

export default function ConformanceDashboard() {
  const [referenceModels, setReferenceModels] = useState<ReferenceModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Upload form state
  const [uploadForm, setUploadForm] = useState({
    name: "",
    industry: "",
    process_area: "",
    bpmn_xml: "",
  });

  // Check form state
  const [checkForm, setCheckForm] = useState({
    engagement_id: "",
    reference_model_id: "",
    observed_bpmn_xml: "",
  });

  // Results state
  const [conformanceResult, setConformanceResult] =
    useState<ConformanceResult | null>(null);

  // Load reference models on mount
  useEffect(() => {
    loadReferenceModels();
    return () => {
      abortRef.current?.abort();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadReferenceModels = async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setModelsLoading(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/conformance/reference-models`,
        { signal: controller.signal, credentials: "include" }
      );
      if (!response.ok) throw new Error("Failed to load reference models");
      const data = await response.json();
      if (!controller.signal.aborted) {
        setReferenceModels(data.items ?? data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    } finally {
      if (!controller.signal.aborted) {
        setModelsLoading(false);
      }
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/conformance/reference-models`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(uploadForm),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to upload reference model");
      }

      setSuccess("Reference model uploaded successfully");
      setUploadForm({ name: "", industry: "", process_area: "", bpmn_xml: "" });
      await loadReferenceModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);
    setConformanceResult(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/conformance/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(checkForm),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Conformance check failed");
      }

      const result = await response.json();
      setConformanceResult(result);
      setSuccess("Conformance check completed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const getScoreBadgeClass = (score: number) => {
    if (score >= 0.8) return "bg-green-100 text-green-800";
    if (score >= 0.5) return "bg-yellow-100 text-yellow-800";
    return "bg-red-100 text-red-800";
  };

  const getSeverityBadgeClass = (severity: string) => {
    if (severity === "high") return "bg-red-100 text-red-800";
    if (severity === "medium") return "bg-yellow-100 text-yellow-800";
    return "bg-green-100 text-green-800";
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          Conformance Checking Dashboard
        </h1>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 p-4 text-red-800">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 rounded-lg bg-green-50 p-4 text-green-800">
            {success}
          </div>
        )}

        {/* Upload Reference Model Section */}
        <section className="mb-6 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">
            Upload Reference Model
          </h2>
          <form onSubmit={handleUploadSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <label htmlFor="upload-name" className="block text-sm font-medium text-gray-700">
                  Name
                </label>
                <input
                  id="upload-name"
                  type="text"
                  value={uploadForm.name}
                  onChange={(e) =>
                    setUploadForm({ ...uploadForm, name: e.target.value })
                  }
                  required
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                />
              </div>

              <div>
                <label htmlFor="upload-industry" className="block text-sm font-medium text-gray-700">
                  Industry
                </label>
                <input
                  id="upload-industry"
                  type="text"
                  value={uploadForm.industry}
                  onChange={(e) =>
                    setUploadForm({ ...uploadForm, industry: e.target.value })
                  }
                  required
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                />
              </div>

              <div>
                <label htmlFor="upload-process-area" className="block text-sm font-medium text-gray-700">
                  Process Area
                </label>
                <input
                  id="upload-process-area"
                  type="text"
                  value={uploadForm.process_area}
                  onChange={(e) =>
                    setUploadForm({
                      ...uploadForm,
                      process_area: e.target.value,
                    })
                  }
                  required
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                />
              </div>
            </div>

            <div>
              <label htmlFor="upload-bpmn-xml" className="block text-sm font-medium text-gray-700">
                BPMN XML
              </label>
              <textarea
                id="upload-bpmn-xml"
                value={uploadForm.bpmn_xml}
                onChange={(e) =>
                  setUploadForm({ ...uploadForm, bpmn_xml: e.target.value })
                }
                required
                rows={6}
                className="mt-1 block w-full rounded-md border border-gray-300 p-2 font-mono text-sm"
                placeholder="Paste BPMN XML here..."
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? "Uploading..." : "Upload Reference Model"}
            </button>
          </form>
        </section>

        {/* Reference Models List Section */}
        <section className="mb-6 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">Reference Models</h2>
          {modelsLoading ? (
            <div className="flex items-center justify-center p-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900" />
            </div>
          ) : referenceModels.length === 0 ? (
            <p className="text-sm text-gray-500">
              No reference models uploaded yet
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Name
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Industry
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Process Area
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                      Created At
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 bg-white">
                  {referenceModels.map((model) => (
                    <tr key={model.id}>
                      <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                        {model.name}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                        {model.industry}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                        {model.process_area}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                        {new Date(model.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Run Conformance Check Section */}
        <section className="mb-6 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">
            Run Conformance Check
          </h2>
          <form onSubmit={handleCheckSubmit} className="space-y-4">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="check-engagement-id" className="block text-sm font-medium text-gray-700">
                  Engagement ID
                </label>
                <input
                  id="check-engagement-id"
                  type="text"
                  value={checkForm.engagement_id}
                  onChange={(e) =>
                    setCheckForm({
                      ...checkForm,
                      engagement_id: e.target.value,
                    })
                  }
                  required
                  placeholder="Enter engagement UUID"
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                />
              </div>

              <div>
                <label htmlFor="check-reference-model" className="block text-sm font-medium text-gray-700">
                  Reference Model
                </label>
                <select
                  id="check-reference-model"
                  value={checkForm.reference_model_id}
                  onChange={(e) =>
                    setCheckForm({
                      ...checkForm,
                      reference_model_id: e.target.value,
                    })
                  }
                  required
                  className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
                >
                  <option value="">Select a reference model</option>
                  {referenceModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} - {model.industry} - {model.process_area}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor="check-observed-bpmn" className="block text-sm font-medium text-gray-700">
                Observed BPMN XML
              </label>
              <textarea
                id="check-observed-bpmn"
                value={checkForm.observed_bpmn_xml}
                onChange={(e) =>
                  setCheckForm({
                    ...checkForm,
                    observed_bpmn_xml: e.target.value,
                  })
                }
                required
                rows={6}
                className="mt-1 block w-full rounded-md border border-gray-300 p-2 font-mono text-sm"
                placeholder="Paste observed BPMN XML here..."
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? "Checking..." : "Run Conformance Check"}
            </button>
          </form>
        </section>

        {/* Results Display Section */}
        {conformanceResult && (
          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Conformance Results</h2>

            {/* Score Badges */}
            <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-gray-200 p-4">
                <p className="mb-2 text-sm font-medium text-gray-500">
                  Fitness Score
                </p>
                <div className="flex items-center justify-between">
                  <p className="text-2xl font-bold text-gray-900">
                    {conformanceResult.fitness.toFixed(3)}
                  </p>
                  <span
                    className={`rounded-full px-3 py-1 text-sm font-semibold ${getScoreBadgeClass(conformanceResult.fitness)}`}
                  >
                    {conformanceResult.fitness >= 0.8
                      ? "Good"
                      : conformanceResult.fitness >= 0.5
                        ? "Fair"
                        : "Poor"}
                  </span>
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 p-4">
                <p className="mb-2 text-sm font-medium text-gray-500">
                  Precision Score
                </p>
                <div className="flex items-center justify-between">
                  <p className="text-2xl font-bold text-gray-900">
                    {conformanceResult.precision.toFixed(3)}
                  </p>
                  <span
                    className={`rounded-full px-3 py-1 text-sm font-semibold ${getScoreBadgeClass(conformanceResult.precision)}`}
                  >
                    {conformanceResult.precision >= 0.8
                      ? "Good"
                      : conformanceResult.precision >= 0.5
                        ? "Fair"
                        : "Poor"}
                  </span>
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 p-4">
                <p className="mb-2 text-sm font-medium text-gray-500">
                  F1 Score
                </p>
                <div className="flex items-center justify-between">
                  <p className="text-2xl font-bold text-gray-900">
                    {conformanceResult.f1_score.toFixed(3)}
                  </p>
                  <span
                    className={`rounded-full px-3 py-1 text-sm font-semibold ${getScoreBadgeClass(conformanceResult.f1_score)}`}
                  >
                    {conformanceResult.f1_score >= 0.8
                      ? "Good"
                      : conformanceResult.f1_score >= 0.5
                        ? "Fair"
                        : "Poor"}
                  </span>
                </div>
              </div>
            </div>

            {/* Element Counts */}
            <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg bg-gray-50 p-4">
                <p className="text-sm font-medium text-gray-500">
                  Matching Elements
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {conformanceResult.matching_elements}
                </p>
              </div>

              <div className="rounded-lg bg-gray-50 p-4">
                <p className="text-sm font-medium text-gray-500">
                  Reference Elements
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {conformanceResult.total_reference_elements}
                </p>
              </div>

              <div className="rounded-lg bg-gray-50 p-4">
                <p className="text-sm font-medium text-gray-500">
                  Observed Elements
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900">
                  {conformanceResult.total_observed_elements}
                </p>
              </div>
            </div>

            {/* Deviations Table */}
            <div>
              <h3 className="mb-3 text-base font-semibold">Deviations</h3>
              {conformanceResult.deviations.length === 0 ? (
                <p className="text-sm text-gray-500">No deviations found</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                          Element Name
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                          Deviation Type
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                          Severity
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                          Description
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 bg-white">
                      {conformanceResult.deviations.map((deviation, idx) => (
                        <tr key={idx}>
                          <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                            {deviation.element_name}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                            {deviation.deviation_type}
                          </td>
                          <td className="whitespace-nowrap px-6 py-4 text-sm">
                            <span
                              className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${getSeverityBadgeClass(deviation.severity)}`}
                            >
                              {deviation.severity}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500">
                            {deviation.description}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
