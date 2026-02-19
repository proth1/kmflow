"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchConnectorTypes,
  fetchConnections,
  testConnection,
  syncConnection,
  type ConnectorType,
  type IntegrationConnectionData,
} from "@/lib/api";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import {
  Plug,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Zap,
} from "lucide-react";

function statusBadge(status: string) {
  switch (status) {
    case "connected":
      return <Badge className="bg-green-100 text-green-800">Connected</Badge>;
    case "error":
      return <Badge variant="destructive">Error</Badge>;
    case "configured":
      return <Badge variant="outline">Configured</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export default function IntegrationsPage() {
  const [connectorTypes, setConnectorTypes] = useState<ConnectorType[]>([]);
  const [connections, setConnections] = useState<IntegrationConnectionData[]>(
    [],
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [types, conns] = await Promise.all([
        fetchConnectorTypes(),
        fetchConnections(),
      ]);
      setConnectorTypes(types);
      setConnections(conns.items);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load integration data",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleTest(connId: string) {
    setActionLoading(connId);
    try {
      const result = await testConnection(connId);
      if (!result.success) {
        setError(`Test failed: ${result.message}`);
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleSync(connId: string) {
    setActionLoading(connId);
    try {
      const result = await syncConnection(connId);
      if (result.errors.length > 0) {
        setError(`Sync errors: ${result.errors.join(", ")}`);
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setActionLoading(null);
    }
  }

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold">Integrations</h1>
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading integration data...
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Integrations</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage external system connectors and data sync
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData}>
          <RefreshCw className="h-3 w-3 mr-1.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <div>
                <p className="text-sm text-destructive">{error}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  onClick={() => setError(null)}
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Connector Types</CardDescription>
            <CardTitle className="text-3xl">{connectorTypes.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">Available integrations</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active Connections</CardDescription>
            <CardTitle className="text-3xl">
              {connections.filter((c) => c.status === "connected").length}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              Successfully connected
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Connections</CardDescription>
            <CardTitle className="text-3xl">{connections.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground">
              All configured connections
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="connections">
        <TabsList>
          <TabsTrigger value="connections">
            <Plug className="h-4 w-4 mr-1.5" />
            Connections
          </TabsTrigger>
          <TabsTrigger value="connectors">
            <Zap className="h-4 w-4 mr-1.5" />
            Available Connectors
          </TabsTrigger>
        </TabsList>

        <TabsContent value="connections">
          <Card>
            <CardHeader>
              <CardTitle>Integration Connections</CardTitle>
              <CardDescription>
                Configured data source connections
              </CardDescription>
            </CardHeader>
            <CardContent>
              {connections.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No connections configured. Create one via the API.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Last Sync</TableHead>
                      <TableHead>Records</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {connections.map((conn) => (
                      <TableRow key={conn.id}>
                        <TableCell className="font-medium">
                          {conn.name}
                        </TableCell>
                        <TableCell>
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                            {conn.connector_type}
                          </code>
                        </TableCell>
                        <TableCell>{statusBadge(conn.status)}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {conn.last_sync
                            ? new Date(conn.last_sync).toLocaleDateString()
                            : "Never"}
                        </TableCell>
                        <TableCell>{conn.last_sync_records}</TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleTest(conn.id)}
                            disabled={actionLoading === conn.id}
                          >
                            {actionLoading === conn.id ? (
                              <RefreshCw className="h-3 w-3 animate-spin" aria-label="Loading" />
                            ) : (
                              <CheckCircle2 className="h-3 w-3 mr-1" />
                            )}
                            Test
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleSync(conn.id)}
                            disabled={actionLoading === conn.id}
                          >
                            <RefreshCw className="h-3 w-3 mr-1" />
                            Sync
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

        <TabsContent value="connectors">
          <Card>
            <CardHeader>
              <CardTitle>Available Connector Types</CardTitle>
              <CardDescription>
                Supported external system integrations
              </CardDescription>
            </CardHeader>
            <CardContent>
              {connectorTypes.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No connector types registered
                </p>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {connectorTypes.map((ct) => (
                    <Card key={ct.type} className="border">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm flex items-center gap-2">
                          <Plug className="h-4 w-4" />
                          {ct.type}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-xs text-muted-foreground">
                          {ct.description}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
