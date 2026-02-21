"use client";

import { RefreshCw, Plus, Play } from "lucide-react";
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
import type { ScenarioData } from "./types";

const SIMULATION_TYPES = ["what_if", "capacity", "process_change", "control_removal"];

interface ScenariosTabProps {
  scenarios: ScenarioData[];
  showCreate: boolean;
  newName: string;
  newType: string;
  newDescription: string;
  creating: boolean;
  running: string | null;
  onToggleCreate: () => void;
  onNewNameChange: (value: string) => void;
  onNewTypeChange: (value: string) => void;
  onNewDescriptionChange: (value: string) => void;
  onCreate: () => void;
  onCancelCreate: () => void;
  onRun: (scenarioId: string) => void;
}

export default function ScenariosTab({
  scenarios,
  showCreate,
  newName,
  newType,
  newDescription,
  creating,
  running,
  onToggleCreate,
  onNewNameChange,
  onNewTypeChange,
  onNewDescriptionChange,
  onCreate,
  onCancelCreate,
  onRun,
}: ScenariosTabProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Simulation Scenarios</CardTitle>
            <CardDescription>
              Define scenarios for process simulation and what-if analysis
            </CardDescription>
          </div>
          <Button size="sm" variant="outline" onClick={onToggleCreate}>
            <Plus className="h-3 w-3 mr-1.5" />
            New Scenario
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {showCreate && (
          <div className="border rounded-lg p-4 mb-4 space-y-3 bg-muted/30">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Scenario name"
                value={newName}
                onChange={(e) => onNewNameChange(e.target.value)}
                className="border rounded px-3 py-1.5 text-sm w-full"
              />
              <select
                value={newType}
                onChange={(e) => onNewTypeChange(e.target.value)}
                className="border rounded px-3 py-1.5 text-sm w-full"
              >
                {SIMULATION_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <input
              type="text"
              placeholder="Description (optional)"
              value={newDescription}
              onChange={(e) => onNewDescriptionChange(e.target.value)}
              className="border rounded px-3 py-1.5 text-sm w-full"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={onCreate}
                disabled={creating || !newName.trim() || !scenarios[0]?.engagement_id}
              >
                {creating ? "Creating..." : "Create"}
              </Button>
              <Button size="sm" variant="ghost" onClick={onCancelCreate}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {scenarios.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No scenarios defined. Create one to get started.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {scenarios.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{s.simulation_type}</Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                    {s.description || "\u2014"}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {new Date(s.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      onClick={() => onRun(s.id)}
                      disabled={running === s.id}
                    >
                      {running === s.id ? (
                        <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
                      ) : (
                        <Play className="h-3 w-3 mr-1.5" />
                      )}
                      Run
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
