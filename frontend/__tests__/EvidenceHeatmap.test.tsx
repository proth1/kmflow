/**
 * Tests for the EvidenceHeatmap component.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import EvidenceHeatmap from "@/components/EvidenceHeatmap";
import type { ElementCoverageData } from "@/lib/api";

const brightElement: ElementCoverageData = {
  element_id: "e1",
  element_name: "Review Application",
  classification: "bright",
  evidence_count: 4,
  confidence: 0.85,
  is_added: false,
  is_removed: false,
  is_modified: false,
};

const dimElement: ElementCoverageData = {
  element_id: "e2",
  element_name: "Validate Data",
  classification: "dim",
  evidence_count: 1,
  confidence: 0.5,
  is_added: false,
  is_removed: false,
  is_modified: true,
};

const darkElement: ElementCoverageData = {
  element_id: "e3",
  element_name: "New Process Step",
  classification: "dark",
  evidence_count: 0,
  confidence: 0.0,
  is_added: true,
  is_removed: false,
  is_modified: false,
};

const removedElement: ElementCoverageData = {
  element_id: "e4",
  element_name: "Old Step",
  classification: "dim",
  evidence_count: 2,
  confidence: 0.6,
  is_added: false,
  is_removed: true,
  is_modified: false,
};

describe("EvidenceHeatmap", () => {
  it("renders all active elements", () => {
    render(
      <EvidenceHeatmap
        elements={[brightElement, dimElement, darkElement]}
      />,
    );
    expect(screen.getByText("Review Application")).toBeInTheDocument();
    expect(screen.getByText("Validate Data")).toBeInTheDocument();
    expect(screen.getByText("New Process Step")).toBeInTheDocument();
  });

  it("hides removed elements", () => {
    render(
      <EvidenceHeatmap
        elements={[brightElement, removedElement]}
      />,
    );
    expect(screen.getByText("Review Application")).toBeInTheDocument();
    expect(screen.queryByText("Old Step")).not.toBeInTheDocument();
  });

  it("renders correct classification styling for bright", () => {
    render(<EvidenceHeatmap elements={[brightElement]} />);
    const tile = screen.getByTestId("heatmap-tile-bright");
    expect(tile).toBeInTheDocument();
    expect(tile.className).toContain("bg-emerald");
  });

  it("renders correct classification styling for dim", () => {
    render(<EvidenceHeatmap elements={[dimElement]} />);
    const tile = screen.getByTestId("heatmap-tile-dim");
    expect(tile).toBeInTheDocument();
    expect(tile.className).toContain("bg-amber");
  });

  it("renders correct classification styling for dark", () => {
    render(<EvidenceHeatmap elements={[darkElement]} />);
    const tile = screen.getByTestId("heatmap-tile-dark");
    expect(tile).toBeInTheDocument();
    expect(tile.className).toContain("bg-slate");
  });

  it("shows New badge for added elements", () => {
    render(<EvidenceHeatmap elements={[darkElement]} />);
    expect(screen.getByText("New")).toBeInTheDocument();
  });

  it("shows Modified badge for modified elements", () => {
    render(<EvidenceHeatmap elements={[dimElement]} />);
    expect(screen.getByText("Modified")).toBeInTheDocument();
  });

  it("shows evidence count per element", () => {
    render(<EvidenceHeatmap elements={[brightElement]} />);
    expect(screen.getByText("4 sources")).toBeInTheDocument();
  });

  it("shows confidence percentage", () => {
    render(<EvidenceHeatmap elements={[brightElement]} />);
    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  it("shows empty state when no active elements", () => {
    render(<EvidenceHeatmap elements={[removedElement]} />);
    expect(
      screen.getByText("No process elements found for this scenario."),
    ).toBeInTheDocument();
  });

  it("renders heatmap grid container", () => {
    render(<EvidenceHeatmap elements={[brightElement]} />);
    expect(screen.getByTestId("evidence-heatmap")).toBeInTheDocument();
  });
});
