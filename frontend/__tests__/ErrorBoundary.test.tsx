/**
 * Tests for the ErrorBoundary component.
 *
 * ErrorBoundary is a class component that catches render-time errors thrown
 * by its children and shows a fallback UI. React logs caught errors to
 * console.error; we suppress those logs here to keep test output clean.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// ---------------------------------------------------------------------------
// Helper: a component that throws on demand
// ---------------------------------------------------------------------------

interface ThrowingProps {
  shouldThrow: boolean;
  message?: string;
}

function ThrowingChild({ shouldThrow, message = "Test error" }: ThrowingProps) {
  if (shouldThrow) {
    throw new Error(message);
  }
  return <div data-testid="child-content">Rendered successfully</div>;
}

// ---------------------------------------------------------------------------
// Suppress React's expected error output for caught errors
// ---------------------------------------------------------------------------

let originalConsoleError: typeof console.error;

beforeEach(() => {
  originalConsoleError = console.error;
  console.error = jest.fn();
});

afterEach(() => {
  console.error = originalConsoleError;
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ErrorBoundary", () => {
  describe("normal operation (no error)", () => {
    it("renders children when no error is thrown", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByTestId("child-content")).toBeInTheDocument();
      expect(screen.getByText("Rendered successfully")).toBeInTheDocument();
    });

    it("does not show the fallback UI when children are healthy", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
    });
  });

  describe("default fallback UI", () => {
    it("shows the default error heading when a child throws", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });

    it("shows the instructional message when a child throws", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(
        screen.getByText("An unexpected error occurred. Please try refreshing the page.")
      ).toBeInTheDocument();
    });

    it("renders a 'Try again' button in the default fallback", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });

    it("does not render children in the default fallback state", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.queryByTestId("child-content")).not.toBeInTheDocument();
    });
  });

  describe("custom fallback prop", () => {
    it("renders the custom fallback node when provided and a child throws", () => {
      render(
        <ErrorBoundary fallback={<div data-testid="custom-fallback">Custom error UI</div>}>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.getByTestId("custom-fallback")).toBeInTheDocument();
      expect(screen.getByText("Custom error UI")).toBeInTheDocument();
    });

    it("does not render the default 'Something went wrong' with a custom fallback", () => {
      render(
        <ErrorBoundary fallback={<div>Custom error UI</div>}>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
    });

    it("does not render children when using a custom fallback and error occurred", () => {
      render(
        <ErrorBoundary fallback={<div>Custom error UI</div>}>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.queryByTestId("child-content")).not.toBeInTheDocument();
    });
  });

  describe("recovery via Try again", () => {
    it("resets error state and re-renders children after clicking Try again", () => {
      // We use a stateful wrapper so we can swap shouldThrow after clicking
      // Try again. The boundary resets its hasError state to false, which
      // causes the children to re-render with the current prop values.
      function RecoveryWrapper() {
        const [shouldThrow, setShouldThrow] = React.useState(true);
        return (
          <ErrorBoundary>
            {shouldThrow ? (
              <ThrowingChild
                shouldThrow
                message="initial error"
              />
            ) : (
              <div data-testid="recovered-content">Recovered</div>
            )}
          </ErrorBoundary>
        );
      }

      render(<RecoveryWrapper />);

      // Boundary is in error state
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /try again/i }));

      // After clicking Try again the boundary resets. The RecoveryWrapper
      // still renders ThrowingChild with shouldThrow=true, so the error
      // boundary will catch again immediately. Verify the button reappears.
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });

    it("renders children successfully after reset when children no longer throw", () => {
      let externalShouldThrow = true;

      function DynamicChild() {
        if (externalShouldThrow) throw new Error("will recover");
        return <div data-testid="healthy-child">All good</div>;
      }

      const { rerender } = render(
        <ErrorBoundary>
          <DynamicChild />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();

      // Prevent the next render from throwing
      externalShouldThrow = false;

      // Click Try again — the boundary clears hasError
      fireEvent.click(screen.getByRole("button", { name: /try again/i }));

      // Re-render to trigger a fresh children render with the updated external state
      rerender(
        <ErrorBoundary>
          <DynamicChild />
        </ErrorBoundary>
      );

      expect(screen.getByTestId("healthy-child")).toBeInTheDocument();
      expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
    });
  });

  describe("console logging", () => {
    it("logs the caught error to console.error", () => {
      render(
        <ErrorBoundary>
          <ThrowingChild shouldThrow message="Logged error" />
        </ErrorBoundary>
      );

      // console.error is mocked; React calls it for caught errors AND
      // ErrorBoundary's componentDidCatch also calls it directly.
      expect(console.error).toHaveBeenCalled();

      const calls = (console.error as jest.Mock).mock.calls;
      const boundaryCall = calls.find((args: unknown[]) =>
        typeof args[0] === "string" && args[0].includes("ErrorBoundary caught an error")
      );
      expect(boundaryCall).toBeDefined();
    });
  });

  describe("multiple children", () => {
    it("renders multiple healthy children without error", () => {
      render(
        <ErrorBoundary>
          <div data-testid="child-a">Child A</div>
          <div data-testid="child-b">Child B</div>
        </ErrorBoundary>
      );

      expect(screen.getByTestId("child-a")).toBeInTheDocument();
      expect(screen.getByTestId("child-b")).toBeInTheDocument();
    });

    it("shows fallback when any child throws, hiding all children", () => {
      render(
        <ErrorBoundary>
          <div data-testid="healthy-sibling">Healthy</div>
          <ThrowingChild shouldThrow />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(screen.queryByTestId("healthy-sibling")).not.toBeInTheDocument();
    });
  });
});
