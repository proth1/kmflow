/**
 * Tests for the Sidebar (element detail) component.
 *
 * This is the slide-in detail panel for process element information, not the
 * AppShell navigation sidebar. It receives an ElementDetail object and renders
 * confidence, evidence, and contradiction data.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import Sidebar from "@/components/Sidebar";
import type { ElementDetail } from "@/components/Sidebar";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const fullElement: ElementDetail = {
  name: "Review Application",
  elementType: "task",
  confidenceScore: 0.87,
  evidenceCount: 4,
  evidenceIds: ["doc-001", "email-042", "interview-07"],
  contradictions: [
    "Stakeholder A says 3 days SLA; Stakeholder B says 5 days",
    "Process map shows manual step but system log shows automated",
  ],
  metadata: { lane: "Credit Team", system: "LoanOS" },
};

const minimalElement: ElementDetail = {
  name: "Start Event",
  elementType: "startEvent",
  confidenceScore: 0.95,
  evidenceCount: 0,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Sidebar", () => {
  describe("when element is null", () => {
    it("renders nothing", () => {
      const { container } = render(<Sidebar element={null} onClose={jest.fn()} />);
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe("element details rendering", () => {
    it("renders the sidebar panel when an element is provided", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByTestId("element-sidebar")).toBeInTheDocument();
    });

    it("renders the 'Element Details' header", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("Element Details")).toBeInTheDocument();
    });

    it("displays the element name", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("Review Application")).toBeInTheDocument();
    });

    it("displays the element type", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("task")).toBeInTheDocument();
    });

    it("renders the confidence badge", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      // ConfidenceBadge renders with data-testid="confidence-badge"
      expect(screen.getByTestId("confidence-badge")).toBeInTheDocument();
    });

    it("renders the evidence count badge", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      // EvidenceBadge renders with data-testid="evidence-badge"
      expect(screen.getByTestId("evidence-badge")).toBeInTheDocument();
    });
  });

  describe("evidence IDs list", () => {
    it("renders each evidence ID as a list item", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("doc-001")).toBeInTheDocument();
      expect(screen.getByText("email-042")).toBeInTheDocument();
      expect(screen.getByText("interview-07")).toBeInTheDocument();
    });

    it("shows 'No evidence items linked.' when evidenceIds is empty", () => {
      render(<Sidebar element={minimalElement} onClose={jest.fn()} />);
      expect(screen.getByText("No evidence items linked.")).toBeInTheDocument();
    });

    it("shows 'No evidence items linked.' when evidenceIds is undefined", () => {
      const elementWithoutIds: ElementDetail = {
        ...fullElement,
        evidenceIds: undefined,
      };
      render(<Sidebar element={elementWithoutIds} onClose={jest.fn()} />);
      expect(screen.getByText("No evidence items linked.")).toBeInTheDocument();
    });
  });

  describe("contradictions section", () => {
    it("renders each contradiction as a list item", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(
        screen.getByText("Stakeholder A says 3 days SLA; Stakeholder B says 5 days")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Process map shows manual step but system log shows automated")
      ).toBeInTheDocument();
    });

    it("shows a contradiction count in the section heading", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("Contradictions (2)")).toBeInTheDocument();
    });

    it("does not render the contradictions section when there are none", () => {
      render(<Sidebar element={minimalElement} onClose={jest.fn()} />);
      expect(screen.queryByText(/Contradictions/)).not.toBeInTheDocument();
    });

    it("does not render the contradictions section when the array is empty", () => {
      const elementNoContradictions: ElementDetail = {
        ...fullElement,
        contradictions: [],
      };
      render(<Sidebar element={elementNoContradictions} onClose={jest.fn()} />);
      expect(screen.queryByText(/Contradictions/)).not.toBeInTheDocument();
    });
  });

  describe("close button", () => {
    it("renders the close button with an accessible label", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByRole("button", { name: /close sidebar/i })).toBeInTheDocument();
    });

    it("calls onClose when the close button is clicked", () => {
      const onClose = jest.fn();
      render(<Sidebar element={fullElement} onClose={onClose} />);
      fireEvent.click(screen.getByRole("button", { name: /close sidebar/i }));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("does not call onClose before interaction", () => {
      const onClose = jest.fn();
      render(<Sidebar element={fullElement} onClose={onClose} />);
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe("confidence badge values", () => {
    it("displays the correct percentage for a high-confidence element", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      // ConfidenceBadge renders "87% High"
      const badge = screen.getByTestId("confidence-badge");
      expect(badge.textContent).toContain("87%");
    });

    it("displays the correct percentage for a very-high-confidence element", () => {
      render(<Sidebar element={minimalElement} onClose={jest.fn()} />);
      const badge = screen.getByTestId("confidence-badge");
      expect(badge.textContent).toContain("95%");
    });
  });

  describe("section labels", () => {
    it("renders the Name, Type, Confidence Score, and Evidence section labels", () => {
      render(<Sidebar element={fullElement} onClose={jest.fn()} />);
      expect(screen.getByText("Name")).toBeInTheDocument();
      expect(screen.getByText("Type")).toBeInTheDocument();
      expect(screen.getByText("Confidence Score")).toBeInTheDocument();
      // "Evidence" label sits in a flex container next to the EvidenceBadge child;
      // use regex to match the text node regardless of surrounding whitespace.
      expect(screen.getByText(/^Evidence/)).toBeInTheDocument();
    });
  });
});
