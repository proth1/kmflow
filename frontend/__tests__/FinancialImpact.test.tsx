import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import CostRangeDisplay from "@/app/simulations/components/CostRangeDisplay";
import type { CostRange } from "@/app/simulations/components/CostRangeDisplay";
import AssumptionTable from "@/app/simulations/components/AssumptionTable";
import ScenarioFinancialColumn from "@/app/simulations/components/ScenarioFinancialColumn";
import ScenarioDeltaHighlight from "@/app/simulations/components/ScenarioDeltaHighlight";
import type { EngagementAssumptionData, SensitivityEntryData } from "@/lib/api/simulations";

// -- Test data ----------------------------------------------------------------

const sampleRange: CostRange = {
  low: 50000,
  mid: 75000,
  high: 100000,
};

const sampleAssumptions: EngagementAssumptionData[] = [
  {
    id: "a-1",
    engagement_id: "eng-1",
    assumption_type: "cost_per_role",
    name: "Analyst Rate",
    value: 100,
    unit: "USD/hour",
    confidence: 0.85,
    confidence_range: 0.1,
    source_evidence_id: null,
    confidence_explanation: "Based on market data",
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "a-2",
    engagement_id: "eng-1",
    assumption_type: "technology_cost",
    name: "Platform License",
    value: 50000,
    unit: "USD/year",
    confidence: 0.6,
    confidence_range: 0.2,
    source_evidence_id: null,
    confidence_explanation: "Vendor quote",
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const sampleSensitivities: SensitivityEntryData[] = [
  {
    assumption_name: "Analyst Rate",
    base_value: 100,
    impact_range: { optimistic: 45000, expected: 75000, pessimistic: 105000 },
  },
];

// -- CostRangeDisplay tests ---------------------------------------------------

describe("CostRangeDisplay", () => {
  it("renders low, mid, and high values", () => {
    render(<CostRangeDisplay range={sampleRange} />);
    expect(screen.getByText("$50,000")).toBeInTheDocument();
    expect(screen.getByText("$75,000")).toBeInTheDocument();
    expect(screen.getByText("$100,000")).toBeInTheDocument();
  });

  it("renders labels for each value", () => {
    render(<CostRangeDisplay range={sampleRange} />);
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("Mid")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("renders optional label", () => {
    render(<CostRangeDisplay range={sampleRange} label="Cost Range" />);
    expect(screen.getByText("Cost Range")).toBeInTheDocument();
  });

  it("enforces CostRange type at compile time — never a number", () => {
    // This is a compile-time check:
    // @ts-expect-error - CostRangeDisplay rejects number props
    const _invalid = <CostRangeDisplay range={50000} />;
    // If this test compiles, the type system is working correctly.
    // The actual render would fail, but TypeScript prevents it.
    expect(_invalid).toBeDefined();
  });
});

// -- AssumptionTable tests ----------------------------------------------------

describe("AssumptionTable", () => {
  it("renders assumption rows with name, type, value, confidence", () => {
    render(<AssumptionTable assumptions={sampleAssumptions} onSave={jest.fn()} />);

    expect(screen.getByText("Analyst Rate")).toBeInTheDocument();
    expect(screen.getByText("cost per role")).toBeInTheDocument();
    expect(screen.getByText("USD/hour")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();

    expect(screen.getByText("Platform License")).toBeInTheDocument();
    expect(screen.getByText("technology cost")).toBeInTheDocument();
  });

  it("shows empty state when no assumptions", () => {
    render(<AssumptionTable assumptions={[]} onSave={jest.fn()} />);
    expect(screen.getByText("No assumptions configured")).toBeInTheDocument();
  });

  it("enters edit mode on pencil click", () => {
    render(<AssumptionTable assumptions={sampleAssumptions} onSave={jest.fn()} />);

    const editButtons = screen.getAllByTestId("edit-btn");
    fireEvent.click(editButtons[0]);

    expect(screen.getByTestId("edit-value-input")).toBeInTheDocument();
    expect(screen.getByTestId("edit-confidence-input")).toBeInTheDocument();
    expect(screen.getByTestId("save-edit-btn")).toBeInTheDocument();
    expect(screen.getByTestId("cancel-edit-btn")).toBeInTheDocument();
  });

  it("calls onSave with updated values", async () => {
    const onSave = jest.fn().mockResolvedValue(undefined);
    render(<AssumptionTable assumptions={sampleAssumptions} onSave={onSave} />);

    const editButtons = screen.getAllByTestId("edit-btn");
    fireEvent.click(editButtons[0]);

    const valueInput = screen.getByTestId("edit-value-input") as HTMLInputElement;
    fireEvent.change(valueInput, { target: { value: "120" } });

    fireEvent.click(screen.getByTestId("save-edit-btn"));

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith("a-1", { value: 120, confidence: 0.85 });
    });
  });

  it("cancels edit without saving", () => {
    const onSave = jest.fn();
    render(<AssumptionTable assumptions={sampleAssumptions} onSave={onSave} />);

    const editButtons = screen.getAllByTestId("edit-btn");
    fireEvent.click(editButtons[0]);
    fireEvent.click(screen.getByTestId("cancel-edit-btn"));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByTestId("edit-value-input")).not.toBeInTheDocument();
  });

  it("hides edit controls in readonly mode", () => {
    render(<AssumptionTable assumptions={sampleAssumptions} onSave={jest.fn()} readonly />);
    expect(screen.queryByTestId("edit-btn")).not.toBeInTheDocument();
    expect(screen.queryByText("Actions")).not.toBeInTheDocument();
  });
});

// -- ScenarioFinancialColumn tests --------------------------------------------

describe("ScenarioFinancialColumn", () => {
  it("renders scenario name and cost range", () => {
    render(
      <ScenarioFinancialColumn
        scenarioName="As-Is Process"
        costRange={sampleRange}
        topSensitivities={sampleSensitivities}
        overallConfidence={0.75}
        assumptions={sampleAssumptions}
        onAssumptionSave={jest.fn()}
      />,
    );
    expect(screen.getByText("As-Is Process")).toBeInTheDocument();
    expect(screen.getByText("75% confidence")).toBeInTheDocument();
    expect(screen.getByText("$50,000")).toBeInTheDocument();
    expect(screen.getByText("$75,000")).toBeInTheDocument();
    expect(screen.getByText("$100,000")).toBeInTheDocument();
  });

  it("renders top sensitivities", () => {
    render(
      <ScenarioFinancialColumn
        scenarioName="As-Is"
        costRange={sampleRange}
        topSensitivities={sampleSensitivities}
        overallConfidence={0.8}
        assumptions={sampleAssumptions}
        onAssumptionSave={jest.fn()}
      />,
    );
    expect(screen.getByText("Top Sensitivities")).toBeInTheDocument();
    // "Analyst Rate" appears in both assumptions table and sensitivities
    expect(screen.getAllByText("Analyst Rate")).toHaveLength(2);
  });
});

// -- ScenarioDeltaHighlight tests ---------------------------------------------

describe("ScenarioDeltaHighlight", () => {
  const scenarioA = { name: "As-Is", costRange: sampleRange };
  const scenarioB = {
    name: "To-Be",
    costRange: { low: 30000, mid: 50000, high: 70000 } as CostRange,
  };

  it("renders delta range label for savings (green)", () => {
    render(<ScenarioDeltaHighlight scenarioA={scenarioA} scenarioB={scenarioB} />);

    // B - A = negative deltas (savings)
    expect(screen.getByText("To-Be vs As-Is")).toBeInTheDocument();
    // Should show "Save" since mid delta is negative
    expect(screen.getByText(/Save/)).toBeInTheDocument();
  });

  it("renders delta range label for cost increase (red)", () => {
    const expensiveB = {
      name: "Premium",
      costRange: { low: 80000, mid: 120000, high: 160000 } as CostRange,
    };
    render(<ScenarioDeltaHighlight scenarioA={scenarioA} scenarioB={expensiveB} />);

    expect(screen.getByText("Premium vs As-Is")).toBeInTheDocument();
    expect(screen.getByText(/Cost increase/)).toBeInTheDocument();
  });

  it("renders computation method when provided", () => {
    render(
      <ScenarioDeltaHighlight
        scenarioA={scenarioA}
        scenarioB={scenarioB}
        method="to-be minus as-is staffing cost"
      />,
    );
    expect(screen.getByText("Method: to-be minus as-is staffing cost")).toBeInTheDocument();
  });

  it("renders low, mid, and high deltas", () => {
    render(<ScenarioDeltaHighlight scenarioA={scenarioA} scenarioB={scenarioB} />);

    // Low delta: 30000 - 50000 = -20000
    expect(screen.getByText("-$20,000")).toBeInTheDocument();
    // Mid delta: 50000 - 75000 = -25000
    expect(screen.getByText("-$25,000")).toBeInTheDocument();
    // High delta: 70000 - 100000 = -30000
    expect(screen.getByText("-$30,000")).toBeInTheDocument();
  });
});
