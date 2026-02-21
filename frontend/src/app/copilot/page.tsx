"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  contextTokens?: number;
};

type Citation = {
  source_id: string;
  source_type: string;
  content_preview: string;
  similarity_score: number;
};

type QueryType =
  | "general"
  | "process_discovery"
  | "evidence_traceability"
  | "gap_analysis"
  | "regulatory";

export default function CopilotChat() {
  const [engagementId, setEngagementId] = useState("");
  const [query, setQuery] = useState("");
  const [queryType, setQueryType] = useState<QueryType>("general");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!query.trim() || !engagementId.trim()) {
      return;
    }

    const userMessage: Message = {
      role: "user",
      content: query,
    };

    setMessages((prev) => [...prev, userMessage]);
    setQuery("");
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/copilot/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          engagement_id: engagementId,
          query: query,
          query_type: queryType,
        }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();

      const assistantMessage: Message = {
        role: "assistant",
        content: data.answer,
        citations: data.citations || [],
        contextTokens: data.context_tokens_used,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Error: ${error instanceof Error ? error.message : "Failed to get response"}`,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          KMFlow Copilot
        </h1>

        <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label htmlFor="copilot-engagement-id" className="block text-sm font-medium text-gray-700">
              Engagement ID
            </label>
            <input
              id="copilot-engagement-id"
              type="text"
              value={engagementId}
              onChange={(e) => setEngagementId(e.target.value)}
              placeholder="Enter engagement UUID"
              className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
            />
          </div>

          <div>
            <label htmlFor="copilot-query-type" className="block text-sm font-medium text-gray-700">
              Query Type
            </label>
            <select
              id="copilot-query-type"
              value={queryType}
              onChange={(e) => setQueryType(e.target.value as QueryType)}
              className="mt-1 block w-full rounded-md border border-gray-300 p-2 text-sm"
            >
              <option value="general">General</option>
              <option value="process_discovery">Process Discovery</option>
              <option value="evidence_traceability">
                Evidence Traceability
              </option>
              <option value="gap_analysis">Gap Analysis</option>
              <option value="regulatory">Regulatory</option>
            </select>
          </div>
        </div>

        <div className="rounded-lg bg-white p-6 shadow">
          <div className="mb-4 h-96 overflow-y-auto rounded border border-gray-200 p-4">
            {messages.length === 0 && (
              <p className="text-sm text-gray-500">
                Enter an engagement ID and start asking questions about the
                engagement, processes, evidence, or gaps.
              </p>
            )}

            {messages.map((message, index) => (
              <div
                key={index}
                className={`mb-4 ${
                  message.role === "user" ? "text-right" : "text-left"
                }`}
              >
                <div
                  className={`inline-block max-w-3xl rounded-lg p-3 ${
                    message.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-900"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm">
                    {message.content}
                  </p>
                </div>

                {message.role === "assistant" && message.citations && message.citations.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <p className="text-xs font-medium text-gray-600">
                      Citations:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {message.citations.map((citation, citIndex) => (
                        <div
                          key={citIndex}
                          className="rounded bg-gray-200 px-2 py-1 text-xs"
                          title={citation.content_preview}
                        >
                          <span className="font-medium">
                            {citation.source_type}
                          </span>
                          {" · "}
                          <span className="text-gray-600">
                            {Math.round(citation.similarity_score * 100)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {message.role === "assistant" && message.contextTokens && (
                  <p className="mt-1 text-xs text-gray-500">
                    Context tokens: {message.contextTokens}
                  </p>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="text-left">
                <div className="inline-block max-w-3xl rounded-lg bg-gray-100 p-3">
                  <p className="text-sm text-gray-600">Thinking...</p>
                </div>
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask a question..."
              disabled={isLoading || !engagementId}
              aria-label="Chat message"
              className="flex-1 rounded-md border border-gray-300 p-2 text-sm disabled:bg-gray-100"
            />
            <button
              type="submit"
              disabled={isLoading || !query.trim() || !engagementId.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-gray-300"
            >
              {isLoading ? "Sending..." : "Send"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
