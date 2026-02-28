"use client";

import { useState, useCallback } from "react";
import { Check, X, Pencil } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { EngagementAssumptionData } from "@/lib/api/simulations";

interface AssumptionTableProps {
  assumptions: EngagementAssumptionData[];
  onSave: (id: string, updates: { value?: number; confidence?: number }) => Promise<void>;
  readonly?: boolean;
}

function confidenceColor(confidence: number): string {
  if (confidence >= 0.8) return "bg-emerald-100 text-emerald-700";
  if (confidence >= 0.5) return "bg-yellow-100 text-yellow-700";
  return "bg-red-100 text-red-700";
}

interface EditState {
  id: string;
  value: number;
  confidence: number;
}

export default function AssumptionTable({
  assumptions,
  onSave,
  readonly = false,
}: AssumptionTableProps) {
  const [editing, setEditing] = useState<EditState | null>(null);
  const [saving, setSaving] = useState(false);

  const startEdit = useCallback((a: EngagementAssumptionData) => {
    setEditing({ id: a.id, value: a.value, confidence: a.confidence });
  }, []);

  const cancelEdit = useCallback(() => setEditing(null), []);

  const saveEdit = useCallback(async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await onSave(editing.id, { value: editing.value, confidence: editing.confidence });
      setEditing(null);
    } finally {
      setSaving(false);
    }
  }, [editing, onSave]);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Value</TableHead>
          <TableHead>Unit</TableHead>
          <TableHead>Confidence</TableHead>
          {!readonly && <TableHead className="w-20">Actions</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {assumptions.map((a) => {
          const isEditing = editing?.id === a.id;
          return (
            <TableRow key={a.id}>
              <TableCell className="font-medium text-sm">{a.name}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {a.assumption_type.replace(/_/g, " ")}
                </Badge>
              </TableCell>
              <TableCell className="text-sm">
                {isEditing ? (
                  <input
                    type="number"
                    value={editing.value}
                    onChange={(e) =>
                      setEditing({ ...editing, value: parseFloat(e.target.value) || 0 })
                    }
                    className="border rounded px-2 py-1 text-sm w-24"
                    data-testid="edit-value-input"
                  />
                ) : (
                  a.value.toLocaleString()
                )}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">{a.unit}</TableCell>
              <TableCell>
                {isEditing ? (
                  <div className="flex items-center gap-1">
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={editing.confidence}
                      onChange={(e) =>
                        setEditing({ ...editing, confidence: parseFloat(e.target.value) })
                      }
                      className="w-16"
                      data-testid="edit-confidence-input"
                    />
                    <span className="text-xs w-8">{(editing.confidence * 100).toFixed(0)}%</span>
                  </div>
                ) : (
                  <span className={`text-xs px-2 py-0.5 rounded ${confidenceColor(a.confidence)}`}>
                    {(a.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </TableCell>
              {!readonly && (
                <TableCell>
                  {isEditing ? (
                    <div className="flex gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={saveEdit}
                        disabled={saving}
                        data-testid="save-edit-btn"
                      >
                        <Check className="h-3 w-3 text-emerald-600" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={cancelEdit} data-testid="cancel-edit-btn">
                        <X className="h-3 w-3 text-muted-foreground" />
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => startEdit(a)}
                      data-testid="edit-btn"
                    >
                      <Pencil className="h-3 w-3 text-muted-foreground" />
                    </Button>
                  )}
                </TableCell>
              )}
            </TableRow>
          );
        })}
        {assumptions.length === 0 && (
          <TableRow>
            <TableCell colSpan={readonly ? 5 : 6} className="text-center text-muted-foreground text-sm py-6">
              No assumptions configured
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}
