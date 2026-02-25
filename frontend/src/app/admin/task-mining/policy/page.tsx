"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchCaptureConfig,
  updateCaptureConfig,
  type CaptureConfig,
} from "@/lib/api/taskmining";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Sliders,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Plus,
  X,
  ShieldAlert,
  Save,
} from "lucide-react";

const BUNDLE_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9-]*(\.[a-zA-Z0-9][a-zA-Z0-9-]*)+$/;

function isValidBundleId(id: string): boolean {
  return BUNDLE_ID_PATTERN.test(id);
}

interface AppListEditorProps {
  label: string;
  description: string;
  apps: string[];
  onChange: (apps: string[]) => void;
}

function AppListEditor({ label, description, apps, onChange }: AppListEditorProps) {
  const [newApp, setNewApp] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);

  function handleAdd() {
    const trimmed = newApp.trim();
    if (!trimmed) return;
    if (!isValidBundleId(trimmed)) {
      setInputError("Invalid bundle ID format (e.g. com.vendor.AppName)");
      return;
    }
    if (apps.includes(trimmed)) {
      setInputError("Already in the list");
      return;
    }
    onChange([...apps, trimmed]);
    setNewApp("");
    setInputError(null);
  }

  function handleRemove(app: string) {
    onChange(apps.filter((a) => a !== app));
  }

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-medium">{label}</h3>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="com.vendor.AppName"
          value={newApp}
          onChange={(e) => {
            setNewApp(e.target.value);
            setInputError(null);
          }}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          className="max-w-xs"
          aria-label={`Add to ${label}`}
        />
        <Button size="sm" variant="outline" onClick={handleAdd}>
          <Plus className="h-3 w-3 mr-1" />
          Add
        </Button>
      </div>
      {inputError && (
        <p className="text-xs text-destructive">{inputError}</p>
      )}
      {apps.length === 0 ? (
        <p className="text-xs text-muted-foreground italic">No apps configured</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {apps.map((app) => (
            <Badge key={app} variant="secondary" className="gap-1.5">
              {app}
              <button
                onClick={() => handleRemove(app)}
                className="hover:text-destructive"
                aria-label={`Remove ${app}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CapturePolicyPage() {
  const [engagementId, setEngagementId] = useState("");
  const debouncedEngagementId = useDebouncedValue(engagementId, 400);
  const [config, setConfig] = useState<CaptureConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmKeystroke, setConfirmKeystroke] = useState(false);

  // Working copies of editable fields
  const [allowedApps, setAllowedApps] = useState<string[]>([]);
  const [blockedApps, setBlockedApps] = useState<string[]>([]);
  const [keystrokeMode, setKeystrokeMode] = useState("action_level");
  const [granularity, setGranularity] = useState("full");

  const loadConfig = useCallback(async () => {
    if (!debouncedEngagementId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchCaptureConfig(debouncedEngagementId);
      setConfig(result);
      setAllowedApps(result.allowed_apps);
      setBlockedApps(result.blocked_apps);
      setKeystrokeMode(result.keystroke_mode);
      setGranularity(result.capture_granularity);
      setDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load config");
    } finally {
      setLoading(false);
    }
  }, [debouncedEngagementId]);

  useEffect(() => {
    if (debouncedEngagementId.length >= 8) {
      loadConfig();
    }
  }, [debouncedEngagementId, loadConfig]);

  useEffect(() => {
    if (!successMsg) return;
    const timer = setTimeout(() => setSuccessMsg(null), 5000);
    return () => clearTimeout(timer);
  }, [successMsg]);

  function markDirty() {
    setDirty(true);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateCaptureConfig(engagementId, {
        allowed_apps: allowedApps,
        blocked_apps: blockedApps,
        keystroke_mode: keystrokeMode,
        capture_granularity: granularity,
      });
      setConfig(updated);
      setDirty(false);
      setSuccessMsg("Capture policy saved — agents will pick up changes on next check-in");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save config");
    } finally {
      setSaving(false);
    }
  }

  function handleKeystrokeToggle(mode: string) {
    if (mode === "content_level" && keystrokeMode !== "content_level") {
      setConfirmKeystroke(true);
      return;
    }
    setKeystrokeMode(mode);
    markDirty();
  }

  function confirmContentLevel() {
    setKeystrokeMode("content_level");
    setConfirmKeystroke(false);
    markDirty();
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Capture Policy</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure what is captured — app scope, keystroke mode, and PII sensitivity
          </p>
        </div>
        <Sliders className="h-8 w-8 text-muted-foreground" />
      </div>

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

      {successMsg && (
        <Card className="border-green-200 bg-green-50/50">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
              <p className="text-sm text-green-800">{successMsg}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-4">
        <Input
          placeholder="Enter engagement ID to load policy..."
          value={engagementId}
          onChange={(e) => setEngagementId(e.target.value)}
          className="max-w-sm"
          aria-label="Engagement ID"
        />
        {dirty && (
          <Badge variant="outline" className="bg-yellow-50 text-yellow-800 border-yellow-200">
            Unsaved changes
          </Badge>
        )}
      </div>

      {config && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">App Allowlist</CardTitle>
              <CardDescription>
                Only capture events from these applications. Leave empty to capture all.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AppListEditor
                label="Allowed Applications"
                description="Bundle IDs of apps to capture (e.g. com.salesforce.Salesforce)"
                apps={allowedApps}
                onChange={(apps) => {
                  setAllowedApps(apps);
                  markDirty();
                }}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">App Blocklist</CardTitle>
              <CardDescription>
                Never capture events from these applications.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <AppListEditor
                label="Blocked Applications"
                description="Bundle IDs to exclude (e.g. com.1password.1password)"
                apps={blockedApps}
                onChange={(apps) => {
                  setBlockedApps(apps);
                  markDirty();
                }}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Keystroke Mode</CardTitle>
              <CardDescription>
                Controls whether actual keystroke content is captured
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="keystroke_mode"
                    checked={keystrokeMode === "action_level"}
                    onChange={() => handleKeystrokeToggle("action_level")}
                    className="accent-primary"
                  />
                  <div>
                    <span className="text-sm font-medium">Action Level</span>
                    <span className="text-xs text-muted-foreground ml-2">(Recommended)</span>
                    <p className="text-xs text-muted-foreground">
                      Only metadata: "typed 47 chars in 12.3s in field Customer Name"
                    </p>
                  </div>
                </label>
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="radio"
                    name="keystroke_mode"
                    checked={keystrokeMode === "content_level"}
                    onChange={() => handleKeystrokeToggle("content_level")}
                    className="accent-primary"
                  />
                  <div>
                    <span className="text-sm font-medium">Content Level</span>
                    <p className="text-xs text-muted-foreground">
                      Captures actual characters with mandatory PII filtering at L1+L2
                    </p>
                  </div>
                </label>
              </div>

              {confirmKeystroke && (
                <div className="border border-yellow-200 bg-yellow-50 rounded-lg p-4 space-y-3">
                  <div className="flex items-start gap-2">
                    <ShieldAlert className="h-5 w-5 text-yellow-600 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-yellow-800">
                        Content-level capture records actual characters typed
                      </p>
                      <p className="text-xs text-yellow-700 mt-1">
                        Ensure your engagement DPA permits this. PII filtering is mandatory
                        and runs at Layers 1+2 on-device before content leaves the machine.
                      </p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={confirmContentLevel}>
                      I confirm — enable content capture
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setConfirmKeystroke(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">PII Detection</CardTitle>
              <CardDescription>
                Pattern version and capture granularity settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium">PII Pattern Version</p>
                  <p className="text-xs text-muted-foreground">
                    Current: {config.pii_patterns_version}
                  </p>
                </div>
                <Badge variant="outline">{config.pii_patterns_version}</Badge>
              </div>
              <div>
                <p className="text-sm font-medium mb-2">Capture Granularity</p>
                <select
                  value={granularity}
                  onChange={(e) => {
                    setGranularity(e.target.value);
                    markDirty();
                  }}
                  className="border rounded-md px-3 py-1.5 text-sm bg-background"
                  aria-label="Capture granularity"
                >
                  <option value="full">Full — all event types</option>
                  <option value="metadata_only">Metadata Only — counts and timing</option>
                </select>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {config && (
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving || !dirty}>
            {saving ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <Save className="h-3 w-3 mr-1.5" />
            )}
            Save Policy
          </Button>
        </div>
      )}
    </div>
  );
}

export { isValidBundleId };
