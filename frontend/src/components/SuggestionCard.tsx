"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  type AlternativeSuggestionData,
  type SuggestionDispositionType,
} from "@/lib/api";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { useState } from "react";

interface SuggestionCardProps {
  suggestion: AlternativeSuggestionData;
  onDispositionChange: (
    suggestionId: string,
    disposition: SuggestionDispositionType,
    notes?: string,
  ) => Promise<void>;
}

const dispositionColor: Record<string, string> = {
  pending: "bg-slate-100 text-slate-700",
  accepted: "bg-emerald-100 text-emerald-800",
  modified: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
};

export default function SuggestionCard({
  suggestion,
  onDispositionChange,
}: SuggestionCardProps) {
  const [updating, setUpdating] = useState(false);
  const [notes, setNotes] = useState(suggestion.disposition_notes || "");

  async function handleDisposition(disposition: SuggestionDispositionType) {
    setUpdating(true);
    try {
      await onDispositionChange(suggestion.id, disposition, notes || undefined);
    } finally {
      setUpdating(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium leading-snug">
            {suggestion.suggestion_text}
          </CardTitle>
          <Badge className={dispositionColor[suggestion.disposition] || ""}>
            {suggestion.disposition}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground mb-1">
            Rationale
          </h4>
          <p className="text-sm">{suggestion.rationale}</p>
        </div>

        {suggestion.governance_flags &&
          Object.keys(suggestion.governance_flags).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-amber-700 mb-1 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                Governance Flags
              </h4>
              <ul className="text-xs space-y-0.5">
                {Object.entries(suggestion.governance_flags).map(
                  ([key, val]) => (
                    <li key={key} className="text-amber-800">
                      <span className="font-medium">{key}:</span>{" "}
                      {String(val)}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}

        {suggestion.evidence_gaps &&
          Object.keys(suggestion.evidence_gaps).length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-muted-foreground mb-1">
                Evidence Gaps
              </h4>
              <ul className="text-xs space-y-0.5">
                {Object.entries(suggestion.evidence_gaps).map(([key, val]) => (
                  <li key={key}>
                    <span className="font-medium">{key}:</span> {String(val)}
                  </li>
                ))}
              </ul>
            </div>
          )}

        {suggestion.disposition === "pending" && (
          <div className="space-y-2 pt-2 border-t">
            <input
              type="text"
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              aria-label="Notes (optional)"
              className="border rounded px-2 py-1 text-xs w-full"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleDisposition("accepted")}
                disabled={updating}
                className="text-emerald-700"
              >
                <CheckCircle className="h-3 w-3 mr-1" />
                Accept
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleDisposition("rejected")}
                disabled={updating}
                className="text-red-700"
              >
                <XCircle className="h-3 w-3 mr-1" />
                Reject
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
