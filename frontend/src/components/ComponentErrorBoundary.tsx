"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";

interface ComponentErrorBoundaryProps {
  children: ReactNode;
  componentName: string;
}

interface ComponentErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * Per-component Error Boundary for complex visualizations.
 *
 * Isolates crashes in heavy components (BPMNViewer, GraphExplorer,
 * monitoring dashboard) so they don't propagate to the app root.
 * Displays the failed component name and a reload button.
 */
export class ComponentErrorBoundary extends Component<
  ComponentErrorBoundaryProps,
  ComponentErrorBoundaryState
> {
  constructor(props: ComponentErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(
    error: Error,
  ): ComponentErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      `ComponentErrorBoundary: "${this.props.componentName}" crashed`,
      error,
      errorInfo,
    );
  }

  private handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          className="flex min-h-[300px] flex-col items-center justify-center rounded-xl border border-red-200 bg-red-50 p-8 text-center"
        >
          <h3 className="mb-1 text-base font-semibold text-red-700">
            {this.props.componentName} failed to render
          </h3>
          <p className="mb-4 text-sm text-red-600">
            An unexpected error occurred in this component.
          </p>
          {this.state.error && (
            <p className="mb-4 font-mono text-xs text-red-500 max-w-md break-all">
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={this.handleRetry}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
