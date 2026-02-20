"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import {
  fetchProcessDefinitions,
  fetchProcessInstances,
  fetchCamundaTasks,
  startProcess,
  type ProcessDefinition,
  type ProcessInstance,
  type CamundaTask,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Workflow, Play, RefreshCw, AlertCircle, Clock } from "lucide-react";

export default function ProcessesPage() {
  const [definitions, setDefinitions] = useState<ProcessDefinition[]>([]);
  const [instances, setInstances] = useState<ProcessInstance[]>([]);
  const [tasks, setTasks] = useState<CamundaTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const isInitialLoad = useRef(true);

  const loadData = useCallback(async (silent = false) => {
    setLoading(true);
    setError(null);
    try {
      const [defs, insts, tks] = await Promise.all([
        fetchProcessDefinitions(),
        fetchProcessInstances(),
        fetchCamundaTasks(),
      ]);
      setDefinitions(defs);
      setInstances(insts);
      setTasks(tks);
    } catch (err) {
      if (!silent) {
        setError(
          err instanceof Error ? err.message : "Failed to connect to Camunda engine",
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const silent = isInitialLoad.current;
    isInitialLoad.current = false;
    loadData(silent);
  }, [loadData]);

  async function handleStart(key: string) {
    setStarting(key);
    try {
      await startProcess(key);
      await loadData(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start process",
      );
    } finally {
      setStarting(null);
    }
  }

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold">Process Management</h1>
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading process data from CIB7...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold">Process Management</h1>
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <div>
                <p className="font-medium text-destructive">
                  Camunda Engine Unavailable
                </p>
                <p className="text-sm text-muted-foreground mt-1">{error}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  onClick={() => loadData(false)}
                >
                  <RefreshCw className="h-3 w-3 mr-1.5" />
                  Retry
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Process Management</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Deploy and manage BPMN process models via CIB7
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => loadData(false)}>
          <RefreshCw className="h-3 w-3 mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Process Definitions</CardDescription>
            <CardTitle className="text-3xl">{definitions.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Deployed BPMN models
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active Instances</CardDescription>
            <CardTitle className="text-3xl">{instances.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Running process instances
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Open Tasks</CardDescription>
            <CardTitle className="text-3xl">{tasks.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Pending user tasks
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabbed content */}
      <Tabs defaultValue="definitions">
        <TabsList>
          <TabsTrigger value="definitions">
            <Workflow className="h-4 w-4 mr-1.5" />
            Definitions
          </TabsTrigger>
          <TabsTrigger value="instances">
            <Play className="h-4 w-4 mr-1.5" />
            Instances
          </TabsTrigger>
          <TabsTrigger value="tasks">
            <Clock className="h-4 w-4 mr-1.5" />
            Tasks
          </TabsTrigger>
        </TabsList>

        <TabsContent value="definitions">
          <Card>
            <CardHeader>
              <CardTitle>Deployed Process Definitions</CardTitle>
              <CardDescription>
                BPMN models deployed to the CIB7 engine (latest versions)
              </CardDescription>
            </CardHeader>
            <CardContent>
              {definitions.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No process definitions deployed. Run{" "}
                  <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
                    scripts/seed-bpmn.sh
                  </code>{" "}
                  to deploy models.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Key</TableHead>
                      <TableHead>Version</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {definitions.map((def) => (
                      <TableRow key={def.id}>
                        <TableCell className="font-medium">
                          {def.name || def.key}
                        </TableCell>
                        <TableCell>
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {def.key}
                          </code>
                        </TableCell>
                        <TableCell>v{def.version}</TableCell>
                        <TableCell>
                          <Badge
                            variant={def.suspended ? "destructive" : "default"}
                          >
                            {def.suspended ? "Suspended" : "Active"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleStart(def.key)}
                            disabled={
                              def.suspended || starting === def.key
                            }
                          >
                            {starting === def.key ? (
                              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
                            ) : (
                              <Play className="h-3 w-3 mr-1.5" />
                            )}
                            Start
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="instances">
          <Card>
            <CardHeader>
              <CardTitle>Running Process Instances</CardTitle>
              <CardDescription>
                Active process instances across all definitions
              </CardDescription>
            </CardHeader>
            <CardContent>
              {instances.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No active process instances.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Instance ID</TableHead>
                      <TableHead>Definition</TableHead>
                      <TableHead>Business Key</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {instances.map((inst) => (
                      <TableRow key={inst.id}>
                        <TableCell>
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {inst.id.substring(0, 8)}...
                          </code>
                        </TableCell>
                        <TableCell className="text-sm">
                          {inst.definitionId.split(":")[0]}
                        </TableCell>
                        <TableCell>
                          {inst.businessKey || (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              inst.suspended
                                ? "destructive"
                                : inst.ended
                                  ? "secondary"
                                  : "default"
                            }
                          >
                            {inst.suspended
                              ? "Suspended"
                              : inst.ended
                                ? "Ended"
                                : "Active"}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tasks">
          <Card>
            <CardHeader>
              <CardTitle>User Tasks</CardTitle>
              <CardDescription>
                Pending tasks requiring human action
              </CardDescription>
            </CardHeader>
            <CardContent>
              {tasks.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No pending tasks.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Task Name</TableHead>
                      <TableHead>Assignee</TableHead>
                      <TableHead>Process</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tasks.map((task) => (
                      <TableRow key={task.id}>
                        <TableCell className="font-medium">
                          {task.name}
                        </TableCell>
                        <TableCell>
                          {task.assignee || (
                            <span className="text-muted-foreground">
                              Unassigned
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">
                          {task.processDefinitionId.split(":")[0]}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {new Date(task.created).toLocaleDateString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
