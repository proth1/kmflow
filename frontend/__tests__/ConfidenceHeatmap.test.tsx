import { render, screen, fireEvent } from "@testing-library/react";
import ConfidenceHeatmapOverlay, {
  brightnessToOverlayColor,
  brightnessLabel,
  BRIGHTNESS_COLORS,
} from "@/components/ConfidenceHeatmapOverlay";
import type {
  ElementConfidenceEntry,
  ConfidenceSummaryData,
} from "@/lib/api/dashboard";

// -- Test data ----------------------------------------------------------------

const sampleElements: Record<string, ElementConfidenceEntry> = {
  "elem-1": { score: 0.92, brightness: "bright", grade: "A" },
  "elem-2": { score: 0.55, brightness: "dim", grade: "B" },
  "elem-3": { score: 0.25, brightness: "dark", grade: "D" },
};

const sampleSummary: ConfidenceSummaryData = {
  engagement_id: "eng-1",
  model_version: 3,
  total_elements: 10,
  bright_count: 5,
  bright_percentage: 50.0,
  dim_count: 3,
  dim_percentage: 30.0,
  dark_count: 2,
  dark_percentage: 20.0,
  overall_confidence: 0.72,
};

// -- Helper -------------------------------------------------------------------

function renderOverlay(overrides?: Partial<React.ComponentProps<typeof ConfidenceHeatmapOverlay>>) {
  const defaults = {
    elements: sampleElements,
    summary: sampleSummary,
    active: true,
    onToggle: jest.fn(),
    csvDownloadUrl: "/api/v1/pov/engagement/eng-1/confidence/summary?format=csv",
    hoveredElement: null,
    tooltipPosition: null,
  };
  return render(<ConfidenceHeatmapOverlay {...defaults} {...overrides} />);
}

// -- Utility function tests ---------------------------------------------------

describe("brightnessToOverlayColor", () => {
  it("returns green for bright", () => {
    expect(brightnessToOverlayColor("bright")).toBe("#22c55e");
  });

  it("returns amber for dim", () => {
    expect(brightnessToOverlayColor("dim")).toBe("#eab308");
  });

  it("returns red for dark", () => {
    expect(brightnessToOverlayColor("dark")).toBe("#ef4444");
  });

  it("returns fallback for unknown brightness", () => {
    expect(brightnessToOverlayColor("unknown")).toBe("#94a3b8");
  });
});

describe("brightnessLabel", () => {
  it("returns capitalized label", () => {
    expect(brightnessLabel("bright")).toBe("Bright");
    expect(brightnessLabel("dim")).toBe("Dim");
    expect(brightnessLabel("dark")).toBe("Dark");
  });

  it("returns raw value for unknown brightness", () => {
    expect(brightnessLabel("unknown")).toBe("unknown");
  });
});

// -- ConfidenceHeatmapOverlay tests -------------------------------------------

describe("ConfidenceHeatmapOverlay", () => {
  it("renders toggle button showing 'Hide Heatmap' when active", () => {
    renderOverlay({ active: true });
    expect(screen.getByTestId("heatmap-toggle")).toHaveTextContent("Hide Heatmap");
  });

  it("renders toggle button showing 'Show Heatmap' when inactive", () => {
    renderOverlay({ active: false });
    expect(screen.getByTestId("heatmap-toggle")).toHaveTextContent("Show Heatmap");
  });

  it("calls onToggle when toggle button clicked", () => {
    const onToggle = jest.fn();
    renderOverlay({ onToggle });
    fireEvent.click(screen.getByTestId("heatmap-toggle"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("renders legend with three brightness tiers when active", () => {
    renderOverlay({ active: true });
    const legend = screen.getByTestId("heatmap-legend");
    expect(legend).toBeInTheDocument();
    expect(legend).toHaveTextContent("Bright");
    expect(legend).toHaveTextContent("Dim");
    expect(legend).toHaveTextContent("Dark");
  });

  it("hides legend when inactive", () => {
    renderOverlay({ active: false });
    expect(screen.queryByTestId("heatmap-legend")).not.toBeInTheDocument();
  });

  it("renders summary card with distribution counts when active", () => {
    renderOverlay({ active: true });
    const card = screen.getByTestId("heatmap-summary-card");
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent("10"); // total
    expect(card).toHaveTextContent("5"); // bright
    expect(card).toHaveTextContent("50%"); // bright pct
    expect(card).toHaveTextContent("3"); // dim
    expect(card).toHaveTextContent("30%"); // dim pct
    expect(card).toHaveTextContent("2"); // dark
    expect(card).toHaveTextContent("20%"); // dark pct
    expect(card).toHaveTextContent("72%"); // overall confidence
  });

  it("hides summary card when inactive", () => {
    renderOverlay({ active: false });
    expect(screen.queryByTestId("heatmap-summary-card")).not.toBeInTheDocument();
  });

  it("renders tooltip with confidence, brightness, and grade on hover", () => {
    renderOverlay({
      active: true,
      hoveredElement: {
        elementId: "elem-1",
        score: 0.92,
        brightness: "bright",
        grade: "A",
      },
      tooltipPosition: { x: 200, y: 300 },
    });

    const tooltip = screen.getByTestId("heatmap-tooltip");
    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveTextContent("Confidence: 92%");
    expect(tooltip).toHaveTextContent("Bright");
    expect(tooltip).toHaveTextContent("Grade: A");
  });

  it("does not render tooltip when no element is hovered", () => {
    renderOverlay({ active: true, hoveredElement: null });
    expect(screen.queryByTestId("heatmap-tooltip")).not.toBeInTheDocument();
  });

  it("does not render tooltip when inactive even if element is hovered", () => {
    renderOverlay({
      active: false,
      hoveredElement: {
        elementId: "elem-1",
        score: 0.92,
        brightness: "bright",
        grade: "A",
      },
      tooltipPosition: { x: 200, y: 300 },
    });
    expect(screen.queryByTestId("heatmap-tooltip")).not.toBeInTheDocument();
  });

  it("renders export buttons", () => {
    renderOverlay();
    expect(screen.getByTestId("export-json-btn")).toBeInTheDocument();
    expect(screen.getByTestId("export-csv-btn")).toBeInTheDocument();
  });

  it("disables JSON export when summary is null", () => {
    renderOverlay({ summary: null });
    expect(screen.getByTestId("export-json-btn")).toBeDisabled();
  });

  it("triggers JSON download on click", () => {
    const createObjectURL = jest.fn().mockReturnValue("blob:test");
    const revokeObjectURL = jest.fn();
    Object.defineProperty(URL, "createObjectURL", { value: createObjectURL, writable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectURL, writable: true });

    renderOverlay();
    fireEvent.click(screen.getByTestId("export-json-btn"));

    expect(createObjectURL).toHaveBeenCalled();
  });

  it("shows element count in legend", () => {
    renderOverlay({ active: true });
    expect(screen.getByTestId("heatmap-legend")).toHaveTextContent("3 elements");
  });
});
