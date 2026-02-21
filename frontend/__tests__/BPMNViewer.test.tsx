/**
 * Tests for the BPMNViewer component.
 *
 * The component dynamically imports bpmn-js via `import("bpmn-js")` inside a
 * useEffect/useCallback. We mock the module so the default export is a
 * constructor that returns a fake viewer object.
 *
 * NOTE: The component runs initViewer() as fire-and-forget inside useEffect.
 * React's test mode does not automatically flush state updates from untracked
 * async chains. We therefore assert on mock interactions (which are reliably
 * observable via waitFor polling) rather than on derived DOM state like the
 * loading indicator disappearing.
 */

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";

// ---------------------------------------------------------------------------
// bpmn-js mock — must be declared before the component import
// ---------------------------------------------------------------------------

const mockImportXML = jest.fn().mockResolvedValue(undefined);
const mockZoom = jest.fn();
const mockDestroy = jest.fn();
const mockOverlaysAdd = jest.fn();
const mockEventBusOn = jest.fn();
const mockForEach = jest.fn();

function MockBpmnJS() {
  return {
    importXML: mockImportXML,
    destroy: mockDestroy,
    get(service: string) {
      if (service === "canvas") return { zoom: mockZoom };
      if (service === "overlays") return { add: mockOverlaysAdd };
      if (service === "elementRegistry") return { forEach: mockForEach };
      if (service === "eventBus") return { on: mockEventBusOn };
      return {};
    },
  };
}

jest.mock("bpmn-js", () => ({
  __esModule: true,
  default: MockBpmnJS,
}));

import BPMNViewer from "@/components/BPMNViewer";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SAMPLE_XML = `<?xml version="1.0"?><bpmn:definitions/>`;

/** Wait for the viewer's async init to complete (zoom is the last mock call). */
async function waitForViewerInit() {
  await waitFor(() => {
    expect(mockZoom).toHaveBeenCalled();
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockImportXML.mockResolvedValue(undefined);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("BPMNViewer", () => {
  it("shows loading indicator initially", () => {
    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    expect(screen.getByTestId("bpmn-loading")).toBeInTheDocument();
  });

  it("imports XML and fits viewport on successful init", async () => {
    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    await waitForViewerInit();

    expect(mockImportXML).toHaveBeenCalledWith(SAMPLE_XML);
    expect(mockZoom).toHaveBeenCalledWith("fit-viewport");
  });

  it("shows error when importXML rejects", async () => {
    mockImportXML.mockRejectedValueOnce(new Error("Bad XML"));

    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);

    await waitFor(() => {
      expect(screen.getByTestId("bpmn-error")).toBeInTheDocument();
    });
    expect(screen.getByText("Bad XML")).toBeInTheDocument();
  });

  it("shows generic error for non-Error throws", async () => {
    mockImportXML.mockRejectedValueOnce("string error");

    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);

    await waitFor(() => {
      expect(screen.getByTestId("bpmn-error")).toBeInTheDocument();
    });
    // Text appears in both <strong> header and error detail div
    expect(screen.getByTestId("bpmn-error")).toHaveTextContent("Failed to render BPMN diagram");
  });

  it("always renders the bpmn-container div", () => {
    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    // The container div is always present (loading overlays it, not replaces it)
    expect(screen.getByTestId("bpmn-container")).toBeInTheDocument();
  });

  it("applies confidence overlay when enabled", async () => {
    const elements = [
      { id: "task_1", businessObject: { name: "Review" } },
      { id: "task_2", businessObject: { name: "Approve" } },
      { id: "flow_1", businessObject: {} }, // no name — skipped
    ];
    mockForEach.mockImplementation((cb: (el: any) => void) => {
      elements.forEach(cb);
    });

    render(
      <BPMNViewer
        bpmnXml={SAMPLE_XML}
        showConfidenceOverlay
        elementConfidences={{ Review: 0.85, Approve: 0.4 }}
      />,
    );

    await waitFor(() => {
      expect(mockOverlaysAdd).toHaveBeenCalled();
    });

    // "Review" gets a confidence overlay
    expect(mockOverlaysAdd).toHaveBeenCalledWith(
      "task_1",
      "confidence",
      expect.objectContaining({ position: expect.any(Object) }),
    );
  });

  it("applies evidence overlay when enabled", async () => {
    const elements = [{ id: "task_1", businessObject: { name: "Review" } }];
    mockForEach.mockImplementation((cb: (el: any) => void) => {
      elements.forEach(cb);
    });

    render(
      <BPMNViewer
        bpmnXml={SAMPLE_XML}
        showEvidenceOverlay
        evidenceCounts={{ Review: 3 }}
      />,
    );

    await waitFor(() => {
      expect(mockOverlaysAdd).toHaveBeenCalled();
    });

    expect(mockOverlaysAdd).toHaveBeenCalledWith(
      "task_1",
      "evidence",
      expect.objectContaining({ position: expect.any(Object) }),
    );
  });

  it("does not apply overlays when disabled", async () => {
    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    await waitForViewerInit();

    expect(mockForEach).not.toHaveBeenCalled();
    expect(mockOverlaysAdd).not.toHaveBeenCalled();
  });

  it("registers element.click handler when onElementClick provided", async () => {
    const onClick = jest.fn();

    render(<BPMNViewer bpmnXml={SAMPLE_XML} onElementClick={onClick} />);

    await waitFor(() => {
      expect(mockEventBusOn).toHaveBeenCalledWith("element.click", expect.any(Function));
    });

    // Simulate a click event
    const handler = mockEventBusOn.mock.calls[0][1];
    handler({ element: { id: "task_1", businessObject: { name: "Review" } } });
    expect(onClick).toHaveBeenCalledWith("task_1", "Review");
  });

  it("does not fire onElementClick for elements without name", async () => {
    const onClick = jest.fn();

    render(<BPMNViewer bpmnXml={SAMPLE_XML} onElementClick={onClick} />);

    await waitFor(() => {
      expect(mockEventBusOn).toHaveBeenCalled();
    });

    const handler = mockEventBusOn.mock.calls[0][1];
    handler({ element: { id: "flow_1", businessObject: {} } });
    expect(onClick).not.toHaveBeenCalled();
  });

  it("does not register click handler when onElementClick not provided", async () => {
    render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    await waitForViewerInit();

    expect(mockEventBusOn).not.toHaveBeenCalled();
  });

  it("calls destroy on unmount", async () => {
    const { unmount } = render(<BPMNViewer bpmnXml={SAMPLE_XML} />);
    await waitForViewerInit();

    unmount();
    expect(mockDestroy).toHaveBeenCalled();
  });
});
