"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Settings, Trash2, Key, RefreshCw, AlertCircle, ShieldAlert } from "lucide-react";

interface RetentionResult {
  dry_run: boolean;
  would_clean_up?: number;
  cleaned_up?: number;
  engagements?: { id: string; name: string }[];
  status: string;
}

interface RotationResult {
  rotated: number;
  total: number;
  status: string;
}

export default function AdminPage() {
  const [retentionResult, setRetentionResult] =
    useState<RetentionResult | null>(null);
  const [rotationResult, setRotationResult] =
    useState<RotationResult | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRotationConfirm, setShowRotationConfirm] = useState(false);

  async function runRetentionPreview() {
    setLoading("retention");
    setError(null);
    try {
      const result = await apiPost<RetentionResult>(
        "/api/v1/admin/retention-cleanup?dry_run=true",
        {},
      );
      setRetentionResult(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to run retention preview",
      );
    } finally {
      setLoading(null);
    }
  }

  async function runKeyRotation() {
    setShowRotationConfirm(false);
    setLoading("rotation");
    setError(null);
    try {
      const result = await apiPost<RotationResult>(
        "/api/v1/admin/rotate-encryption-key",
        {},
      );
      setRotationResult(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to rotate encryption key",
      );
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Platform Administration</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Data retention, encryption key management, and platform operations
          </p>
        </div>
        <Settings className="h-8 w-8 text-muted-foreground" />
      </div>

      <Card className="border-yellow-200 bg-yellow-50/50">
        <CardContent className="pt-6">
          <div className="flex items-start gap-3">
            <ShieldAlert className="h-5 w-5 text-yellow-600 mt-0.5" />
            <div>
              <p className="font-medium text-yellow-800">Admin Access Required</p>
              <p className="text-sm text-yellow-700 mt-1">
                Operations on this page require the <code className="bg-yellow-100 px-1 py-0.5 rounded text-xs">platform_admin</code> role.
                All actions are logged when the backend audit service is configured.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Retention Cleanup */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trash2 className="h-5 w-5" />
              Data Retention Cleanup
            </CardTitle>
            <CardDescription>
              Find and archive engagements past their retention period.
              Preview first with dry run, then execute.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={runRetentionPreview}
              disabled={loading === "retention"}
              variant="outline"
            >
              {loading === "retention" ? (
                <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" aria-label="Loading" />
              ) : (
                <Trash2 className="h-3 w-3 mr-1.5" />
              )}
              Preview Cleanup (Dry Run)
            </Button>

            {retentionResult && (
              <div className="bg-muted rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant={retentionResult.dry_run ? "outline" : "default"}>
                    {retentionResult.dry_run ? "Dry Run" : "Executed"}
                  </Badge>
                  <Badge variant="secondary">{retentionResult.status}</Badge>
                </div>
                <p className="text-sm">
                  {retentionResult.dry_run
                    ? `Would clean up ${retentionResult.would_clean_up} engagements`
                    : `Cleaned up ${retentionResult.cleaned_up} engagements`}
                </p>
                {retentionResult.engagements &&
                  retentionResult.engagements.length > 0 && (
                    <ul className="text-xs text-muted-foreground space-y-1 mt-2">
                      {retentionResult.engagements.map((eng) => (
                        <li key={eng.id}>
                          {eng.name} ({eng.id.substring(0, 8)}...)
                        </li>
                      ))}
                    </ul>
                  )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Key Rotation */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              Encryption Key Rotation
            </CardTitle>
            <CardDescription>
              Re-encrypt all integration credentials with the current key.
              Requires ENCRYPTION_KEY and ENCRYPTION_KEY_PREVIOUS env vars.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {!showRotationConfirm ? (
              <Button
                onClick={() => setShowRotationConfirm(true)}
                disabled={loading === "rotation"}
                variant="outline"
              >
                {loading === "rotation" ? (
                  <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" aria-label="Loading" />
                ) : (
                  <Key className="h-3 w-3 mr-1.5" />
                )}
                Rotate Keys
              </Button>
            ) : (
              <div className="border border-destructive/50 bg-destructive/5 rounded-lg p-4 space-y-3">
                <p className="text-sm font-medium text-destructive">
                  Are you sure you want to rotate the encryption key?
                </p>
                <p className="text-xs text-muted-foreground">
                  This action cannot be undone and will require re-encryption
                  of existing data. Ensure ENCRYPTION_KEY_PREVIOUS is set to
                  the current key before proceeding.
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={runKeyRotation}
                  >
                    <Key className="h-3 w-3 mr-1.5" />
                    Rotate Key
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setShowRotationConfirm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {rotationResult && (
              <div className="bg-muted rounded-lg p-4 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="default">{rotationResult.status}</Badge>
                </div>
                <p className="text-sm">
                  Rotated {rotationResult.rotated} of {rotationResult.total} credentials
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
