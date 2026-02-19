"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { ShieldAlert } from "lucide-react";

interface RequireRoleProps {
  role: string;
  children: ReactNode;
}

/**
 * Client-side route guard that checks for a valid auth token and required role.
 *
 * Reads the token from sessionStorage ("kmflow_access_token") and decodes its
 * JWT payload to check for the role in the "roles" claim array.
 *
 * This is a defense-in-depth measure — the backend MUST also enforce role-based
 * access control on admin endpoints.
 */
export default function RequireRole({ role, children }: RequireRoleProps) {
  const [state, setState] = useState<"loading" | "authorized" | "denied">(
    "loading",
  );

  useEffect(() => {
    const token = sessionStorage.getItem("kmflow_access_token");
    if (!token) {
      setState("denied");
      return;
    }

    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const roles: string[] = payload.roles || payload.realm_access?.roles || [];
      setState(roles.includes(role) ? "authorized" : "denied");
    } catch {
      setState("denied");
    }
  }, [role]);

  if (state === "loading") {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <p className="text-muted-foreground">Verifying access...</p>
      </div>
    );
  }

  if (state === "denied") {
    return (
      <div className="p-6 flex items-center justify-center min-h-[50vh]">
        <Card className="max-w-md border-destructive/50">
          <CardContent className="pt-6">
            <div className="flex flex-col items-center gap-4 text-center">
              <ShieldAlert className="h-12 w-12 text-destructive" />
              <div>
                <h2 className="text-lg font-semibold">Access Denied</h2>
                <p className="text-sm text-muted-foreground mt-2">
                  This page requires the{" "}
                  <code className="bg-muted px-1.5 py-0.5 rounded text-xs">
                    {role}
                  </code>{" "}
                  role. Please sign in with an authorized account.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}
