"use client";

import { RefreshCw, Plus, DollarSign, Trash2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import type {
  FinancialAssumptionData,
  FinancialAssumptionType,
  FinancialImpactData,
  ScenarioData,
  NewAssumptionState,
} from "./types";

interface FinancialTabProps {
  scenarios: ScenarioData[];
  financialScenarioId: string;
  assumptions: FinancialAssumptionData[];
  financialImpact: FinancialImpactData | null;
  loadingFinancial: boolean;
  showAssumptionForm: boolean;
  newAssumption: NewAssumptionState;
  onScenarioChange: (id: string) => void;
  onLoadFinancial: () => void;
  onToggleAssumptionForm: () => void;
  onNewAssumptionChange: (updated: NewAssumptionState) => void;
  onCreateAssumption: () => void;
  onCancelAssumptionForm: () => void;
  onDeleteAssumption: (assumptionId: string) => void;
}

export default function FinancialTab({
  scenarios,
  financialScenarioId,
  assumptions,
  financialImpact,
  loadingFinancial,
  showAssumptionForm,
  newAssumption,
  onScenarioChange,
  onLoadFinancial,
  onToggleAssumptionForm,
  onNewAssumptionChange,
  onCreateAssumption,
  onCancelAssumptionForm,
  onDeleteAssumption,
}: FinancialTabProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Financial Assumptions & Impact</CardTitle>
            <CardDescription>
              Manage cost assumptions and view financial impact estimation
            </CardDescription>
          </div>
          {financialScenarioId && (
            <Button size="sm" variant="outline" onClick={onToggleAssumptionForm}>
              <Plus className="h-3 w-3 mr-1.5" />
              Add Assumption
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label htmlFor="financial-select" className="text-sm font-medium mb-1 block">
              Select Scenario
            </label>
            <select
              id="financial-select"
              value={financialScenarioId}
              onChange={(e) => onScenarioChange(e.target.value)}
              className="border rounded px-3 py-1.5 text-sm w-full"
            >
              <option value="">Select scenario...</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            onClick={onLoadFinancial}
            disabled={loadingFinancial || !financialScenarioId}
          >
            {loadingFinancial ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <DollarSign className="h-3 w-3 mr-1.5" />
            )}
            Load
          </Button>
        </div>

        {showAssumptionForm && (
          <div className="border rounded-lg p-4 space-y-3 bg-muted/30">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <input
                type="text"
                placeholder="Name"
                value={newAssumption.name}
                onChange={(e) =>
                  onNewAssumptionChange({ ...newAssumption, name: e.target.value })
                }
                className="border rounded px-3 py-1.5 text-sm"
              />
              <select
                value={newAssumption.assumption_type}
                onChange={(e) =>
                  onNewAssumptionChange({
                    ...newAssumption,
                    assumption_type: e.target.value as FinancialAssumptionType,
                  })
                }
                className="border rounded px-3 py-1.5 text-sm"
              >
                <option value="cost_per_role">Cost Per Role</option>
                <option value="technology_cost">Technology Cost</option>
                <option value="volume_forecast">Volume Forecast</option>
                <option value="implementation_cost">Implementation Cost</option>
              </select>
              <input
                type="number"
                placeholder="Value"
                value={newAssumption.value || ""}
                onChange={(e) =>
                  onNewAssumptionChange({
                    ...newAssumption,
                    value: parseFloat(e.target.value) || 0,
                  })
                }
                className="border rounded px-3 py-1.5 text-sm"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Unit (e.g. USD/month)"
                value={newAssumption.unit}
                onChange={(e) =>
                  onNewAssumptionChange({ ...newAssumption, unit: e.target.value })
                }
                className="border rounded px-3 py-1.5 text-sm"
              />
              <div className="flex items-center gap-2">
                <label className="text-sm">Confidence:</label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={newAssumption.confidence}
                  onChange={(e) =>
                    onNewAssumptionChange({
                      ...newAssumption,
                      confidence: parseFloat(e.target.value),
                    })
                  }
                  className="flex-1"
                />
                <span className="text-sm font-medium w-12">
                  {(newAssumption.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={onCreateAssumption}
                disabled={!newAssumption.name.trim() || !newAssumption.unit.trim()}
              >
                Create
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancelAssumptionForm}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {assumptions.length > 0 && (
          <div>
            <h3 className="text-sm font-medium mb-2">Assumptions</h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Value</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assumptions.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-medium text-sm">{a.name}</TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {a.assumption_type.replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">{a.value.toLocaleString()}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{a.unit}</TableCell>
                    <TableCell className="text-sm">
                      {(a.confidence * 100).toFixed(0)}%
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onDeleteAssumption(a.id)}
                      >
                        <Trash2 className="h-3 w-3 text-muted-foreground" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {financialImpact && (
          <div className="space-y-3">
            <h3 className="text-sm font-medium">Financial Impact</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-emerald-600">
                    ${financialImpact.cost_range.optimistic.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">Optimistic</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold">
                    ${financialImpact.cost_range.expected.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">Expected</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-red-600">
                    ${financialImpact.cost_range.pessimistic.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">Pessimistic</div>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
