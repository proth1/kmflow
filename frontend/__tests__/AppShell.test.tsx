/**
 * Tests for AppShell sidebar navigation rendering.
 */

import React from "react";
import { render, screen } from "@testing-library/react";

// Mock next/navigation
jest.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

// Mock next-themes
jest.mock("next-themes", () => ({
  useTheme: () => ({ theme: "dark", setTheme: jest.fn() }),
}));

import { AppShell } from "@/components/shell/AppShell";

describe("AppShell", () => {
  it("renders KMFlow branding in sidebar", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    // Desktop + mobile sidebar brand
    const brandElements = screen.getAllByText("KMFlow");
    expect(brandElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders all expected navigation sections", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    const sectionLabels = [
      "Analytics",
      "Evidence",
      "Analysis",
      "Operations",
      "Governance",
      "Integrations",
      "AI",
      "Client",
      "Admin",
    ];
    for (const label of sectionLabels) {
      const elements = screen.getAllByText(label);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("renders key navigation links", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    const navLabels = [
      "Dashboard",
      "Evidence Upload",
      "Monitoring",
      "Conformance",
      "Copilot",
      "Portal",
      "Governance",
      "Reports",
      "Connectors",
      "Shelf Requests",
      "Patterns",
      "Simulations",
      "Data Lineage",
      "Admin",
    ];
    for (const label of navLabels) {
      // Use getAllByText since some labels match both section and nav item
      const elements = screen.getAllByText(label);
      expect(elements.length).toBeGreaterThanOrEqual(1);
    }
  });

  it("renders children content", () => {
    render(
      <AppShell>
        <div data-testid="child-content">Hello</div>
      </AppShell>
    );
    expect(screen.getByTestId("child-content")).toBeInTheDocument();
  });

  it("highlights active route for Dashboard", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>
    );
    const dashboardLinks = screen.getAllByRole("link", { name: /Dashboard/i });
    // The main Dashboard link (href="/") should be highlighted on the "/" route
    const mainDashboard = dashboardLinks.find((el) => el.getAttribute("href") === "/");
    expect(mainDashboard).toBeDefined();
    expect(mainDashboard).toHaveClass("bg-[hsl(var(--primary))]/20");
  });
});
