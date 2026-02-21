/**
 * Auth API: current user profile.
 */

import { apiGet } from "./client";

// -- Types --------------------------------------------------------------------

export type UserRole =
  | "platform_admin"
  | "engagement_lead"
  | "process_analyst"
  | "evidence_reviewer"
  | "client_viewer";

export interface UserProfile {
  id: string;
  email: string;
  role: UserRole;
  name: string;
}

// -- API functions ------------------------------------------------------------

export async function fetchCurrentUser(): Promise<UserProfile> {
  return apiGet<UserProfile>("/api/v1/auth/me");
}
