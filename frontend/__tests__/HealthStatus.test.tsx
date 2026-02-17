/**
 * Tests for the HealthStatus component.
 */

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import HealthStatus from "@/components/HealthStatus";
import * as api from "@/lib/api";

jest.mock("@/lib/api");

const mockFetchHealth = api.fetchHealth as jest.MockedFunction<
  typeof api.fetchHealth
>;

describe("HealthStatus", () => {
  beforeEach(() => {
    mockFetchHealth.mockClear();
  });

  it("shows loading state initially", () => {
    mockFetchHealth.mockReturnValue(new Promise(() => {})); // Never resolves
    render(<HealthStatus />);
    expect(screen.getByTestId("health-loading")).toBeInTheDocument();
  });

  it("displays healthy status when all services are up", async () => {
    mockFetchHealth.mockResolvedValueOnce({
      status: "healthy",
      services: { postgres: "up", neo4j: "up", redis: "up" },
      version: "0.1.0",
    });

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("health-status")).toBeInTheDocument();
    });

    expect(screen.getByText(/healthy/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.1\.0/)).toBeInTheDocument();
  });

  it("displays error when backend is unreachable", async () => {
    mockFetchHealth.mockRejectedValueOnce(new Error("Network error"));

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByTestId("health-error")).toBeInTheDocument();
    });

    expect(screen.getByText(/Network error/)).toBeInTheDocument();
  });

  it("displays degraded status", async () => {
    mockFetchHealth.mockResolvedValueOnce({
      status: "degraded",
      services: { postgres: "up", neo4j: "up", redis: "down" },
      version: "0.1.0",
    });

    render(<HealthStatus />);

    await waitFor(() => {
      expect(screen.getByText(/degraded/i)).toBeInTheDocument();
    });
  });
});
