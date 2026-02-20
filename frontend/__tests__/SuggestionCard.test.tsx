import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SuggestionCard from "@/components/SuggestionCard";
import type { AlternativeSuggestionData } from "@/lib/api";

const baseSuggestion: AlternativeSuggestionData = {
  id: "sug-1",
  scenario_id: "sc-1",
  suggestion_text: "Consider consolidating approval steps",
  rationale: "Reduces cycle time by eliminating redundant approvals",
  governance_flags: { compliance_risk: "low" },
  evidence_gaps: { timing_data: "Need additional process timing evidence" },
  disposition: "pending",
  disposition_notes: null,
  created_at: "2026-02-19T00:00:00Z",
};

describe("SuggestionCard", () => {
  it("renders suggestion text and rationale", () => {
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(
      screen.getByText("Consider consolidating approval steps"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Reduces cycle time by eliminating redundant approvals",
      ),
    ).toBeInTheDocument();
  });

  it("renders governance flags", () => {
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(screen.getByText(/compliance_risk/)).toBeInTheDocument();
  });

  it("renders evidence gaps", () => {
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(screen.getByText(/timing_data/)).toBeInTheDocument();
  });

  it("shows accept/reject buttons for pending suggestions", () => {
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(screen.getByText("Accept")).toBeInTheDocument();
    expect(screen.getByText("Reject")).toBeInTheDocument();
  });

  it("hides action buttons for non-pending suggestions", () => {
    const accepted = { ...baseSuggestion, disposition: "accepted" as const };
    render(
      <SuggestionCard
        suggestion={accepted}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(screen.queryByText("Accept")).not.toBeInTheDocument();
    expect(screen.queryByText("Reject")).not.toBeInTheDocument();
  });

  it("calls onDispositionChange with accepted", async () => {
    const handler = jest.fn().mockResolvedValue(undefined);
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={handler}
      />,
    );
    fireEvent.click(screen.getByText("Accept"));
    await waitFor(() => {
      expect(handler).toHaveBeenCalledWith("sug-1", "accepted", undefined);
    });
  });

  it("calls onDispositionChange with rejected", async () => {
    const handler = jest.fn().mockResolvedValue(undefined);
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={handler}
      />,
    );
    fireEvent.click(screen.getByText("Reject"));
    await waitFor(() => {
      expect(handler).toHaveBeenCalledWith("sug-1", "rejected", undefined);
    });
  });

  it("renders disposition badge", () => {
    render(
      <SuggestionCard
        suggestion={baseSuggestion}
        onDispositionChange={jest.fn()}
      />,
    );
    expect(screen.getByText("pending")).toBeInTheDocument();
  });
});
