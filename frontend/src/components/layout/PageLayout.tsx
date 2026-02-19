"use client";

import { ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { RefreshCw, AlertCircle } from "lucide-react";

interface PageLayoutProps {
  title: string;
  description: string;
  icon?: ReactNode;
  /** Engagement ID state — omit to skip the engagement card */
  engagementId?: string;
  onEngagementIdChange?: (id: string) => void;
  engagementIdError?: string | null;
  error?: string | null;
  loading?: boolean;
  loadingText?: string;
  children: ReactNode;
}

export function PageLayout({
  title,
  description,
  icon,
  engagementId,
  onEngagementIdChange,
  engagementIdError,
  error,
  loading,
  loadingText = "Loading...",
  children,
}: PageLayoutProps) {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{title}</h1>
          <p className="text-sm text-muted-foreground mt-1">{description}</p>
        </div>
        {icon}
      </div>

      {onEngagementIdChange !== undefined && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Engagement</CardTitle>
            <CardDescription>
              Enter an engagement ID to load data
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div>
              <Input
                type="text"
                value={engagementId ?? ""}
                onChange={(e) => onEngagementIdChange(e.target.value)}
                placeholder="e.g., 550e8400-e29b-41d4-a716-446655440000"
                className="max-w-md"
                aria-describedby="engagement-id-hint"
              />
              <p id="engagement-id-hint" className="text-xs text-muted-foreground mt-1">
                UUID format required (e.g., 550e8400-e29b-41d4-a716-446655440000)
              </p>
              {engagementIdError && (
                <p className="text-xs text-destructive mt-1">{engagementIdError}</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

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

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" aria-label="Loading" />
          {loadingText}
        </div>
      )}

      {children}
    </div>
  );
}
