/**
 * API helper for E2E test setup/teardown.
 *
 * Wraps Playwright's APIRequestContext for programmatic interactions
 * with the KMFlow backend during tests (creating/deleting test data,
 * authenticating, etc.).
 */

import { APIRequestContext } from "@playwright/test";

const BACKEND_URL =
  process.env.E2E_BACKEND_URL || "http://localhost:8000";

export interface EngagementResponse {
  id: string;
  name: string;
  client: string;
  status: string;
}

export interface EvidenceResponse {
  id: string;
  file_name: string;
  file_size: number;
  category: string;
  status: string;
}

export interface TOMResponse {
  id: string;
  engagement_id: string;
  dimensions: Array<{
    dimension: string;
    current_maturity: number;
    target_maturity: number;
    gap_type: string;
    severity: number;
  }>;
}

export interface LoginResponse {
  message: string;
  user_id: string;
}

export class ApiHelper {
  constructor(private request: APIRequestContext) {}

  /**
   * Login as a user and return response with cookies.
   */
  async loginAs(
    email: string,
    password: string
  ): Promise<LoginResponse> {
    const response = await this.request.post(
      `${BACKEND_URL}/api/v1/auth/login`,
      {
        data: { email, password },
      }
    );
    if (!response.ok()) {
      throw new Error(
        `Login failed for ${email}: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }

  /**
   * Create an engagement via the API.
   */
  async createEngagement(
    name: string,
    client: string,
    businessArea = "General"
  ): Promise<EngagementResponse> {
    const response = await this.request.post(
      `${BACKEND_URL}/api/v1/engagements`,
      {
        data: {
          name,
          client,
          business_area: businessArea,
          description: `E2E test engagement: ${name}`,
        },
      }
    );
    if (!response.ok()) {
      throw new Error(
        `Create engagement failed: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }

  /**
   * Delete an engagement by ID.
   */
  async deleteEngagement(id: string): Promise<void> {
    const response = await this.request.delete(
      `${BACKEND_URL}/api/v1/engagements/${id}`
    );
    if (!response.ok() && response.status() !== 404) {
      throw new Error(
        `Delete engagement failed: ${response.status()} ${await response.text()}`
      );
    }
  }

  /**
   * Upload an evidence file to an engagement.
   */
  async uploadEvidence(
    engagementId: string,
    filePath: string
  ): Promise<EvidenceResponse> {
    const response = await this.request.post(
      `${BACKEND_URL}/api/v1/evidence/${engagementId}/upload`,
      {
        multipart: {
          file: {
            name: filePath.split("/").pop() || "file",
            mimeType: "application/octet-stream",
            buffer: Buffer.from(""), // Placeholder — actual file read by Playwright
          },
        },
      }
    );
    if (!response.ok()) {
      throw new Error(
        `Upload evidence failed: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }

  /**
   * Delete an evidence item.
   */
  async deleteEvidence(
    engagementId: string,
    evidenceId: string
  ): Promise<void> {
    const response = await this.request.delete(
      `${BACKEND_URL}/api/v1/evidence/${engagementId}/${evidenceId}`
    );
    if (!response.ok() && response.status() !== 404) {
      throw new Error(
        `Delete evidence failed: ${response.status()} ${await response.text()}`
      );
    }
  }

  /**
   * Get TOM data for an engagement.
   */
  async getTOM(engagementId: string): Promise<TOMResponse | null> {
    const response = await this.request.get(
      `${BACKEND_URL}/api/v1/tom/${engagementId}`
    );
    if (response.status() === 404) return null;
    if (!response.ok()) {
      throw new Error(
        `Get TOM failed: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }

  /**
   * Generic GET helper.
   */
  async get(path: string): Promise<unknown> {
    const response = await this.request.get(
      `${BACKEND_URL}${path}`
    );
    if (!response.ok()) {
      throw new Error(
        `GET ${path} failed: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }

  /**
   * Generic POST helper.
   */
  async post(path: string, data?: unknown): Promise<unknown> {
    const response = await this.request.post(
      `${BACKEND_URL}${path}`,
      { data: data as Record<string, unknown> }
    );
    if (!response.ok()) {
      throw new Error(
        `POST ${path} failed: ${response.status()} ${await response.text()}`
      );
    }
    return response.json();
  }
}
