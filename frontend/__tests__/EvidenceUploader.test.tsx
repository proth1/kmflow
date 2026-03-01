/**
 * Tests for the EvidenceUploader component.
 *
 * The component uses direct fetch() for uploads with a setInterval progress
 * simulator. We mock global.fetch and use fake timers to control progress.
 */

import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";

import EvidenceUploader from "@/components/EvidenceUploader";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeFile(name: string, sizeBytes: number, type = "application/pdf"): File {
  const content = new Uint8Array(sizeBytes);
  return new File([content], name, { type });
}

const ENGAGEMENT_ID = "eng-123";

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

let originalFetch: typeof global.fetch;

beforeEach(() => {
  originalFetch = global.fetch;
  jest.useFakeTimers();
  localStorage.clear();
});

afterEach(() => {
  global.fetch = originalFetch;
  jest.useRealTimers();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EvidenceUploader", () => {
  describe("initial render", () => {
    it("renders drop zone with prompt text", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      expect(screen.getByText(/Drag & drop files or click to browse/)).toBeInTheDocument();
      expect(screen.getByText(/PDF, DOCX, XLSX, CSV, PNG, JPG/)).toBeInTheDocument();
    });

    it("has an accessible drop zone", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const dropZone = screen.getByRole("button", { name: "Upload evidence files" });
      expect(dropZone).toHaveAttribute("tabIndex", "0");
    });

    it("has a hidden file input", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });
      expect(input).toHaveAttribute("type", "file");
      expect(input).toHaveClass("hidden");
    });

    it("shows no validation error or upload list initially", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      expect(screen.queryByText(/not allowed/)).not.toBeInTheDocument();
      expect(screen.queryByText("Done")).not.toBeInTheDocument();
      expect(screen.queryByText("Failed")).not.toBeInTheDocument();
    });
  });

  describe("drag feedback", () => {
    it("shows drop text on dragover", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const dropZone = screen.getByRole("button", { name: "Upload evidence files" });
      fireEvent.dragOver(dropZone);

      expect(screen.getByText("Drop files here")).toBeInTheDocument();
    });

    it("restores prompt on dragleave", () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const dropZone = screen.getByRole("button", { name: "Upload evidence files" });
      fireEvent.dragOver(dropZone);
      fireEvent.dragLeave(dropZone);

      expect(screen.getByText(/Drag & drop files or click to browse/)).toBeInTheDocument();
    });
  });

  describe("validation", () => {
    it("rejects unsupported file types", async () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });
      const badFile = makeFile("virus.exe", 100, "application/octet-stream");

      fireEvent.change(input, { target: { files: [badFile] } });

      expect(screen.getByText(/not allowed/)).toBeInTheDocument();
    });

    it("rejects oversized files", async () => {
      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });
      const bigFile = makeFile("huge.pdf", 60 * 1024 * 1024);

      fireEvent.change(input, { target: { files: [bigFile] } });

      expect(screen.getByText(/too large/)).toBeInTheDocument();
    });

    it("clears validation error on next valid file", async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            id: "ev-1",
            file_name: "good.pdf",
            file_size: 1024,
            category: "documents",
            fragments_extracted: 2,
            status: "success",
          }),
      });

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      // First: bad file
      fireEvent.change(input, { target: { files: [makeFile("bad.exe", 100)] } });
      expect(screen.getByText(/not allowed/)).toBeInTheDocument();

      // Second: valid file — error should clear
      await act(async () => {
        fireEvent.change(input, { target: { files: [makeFile("good.pdf", 1024)] } });
      });

      expect(screen.queryByText(/not allowed/)).not.toBeInTheDocument();
    });
  });

  describe("successful upload", () => {
    it("shows filename, progress, then Done", async () => {
      const uploadResult = {
        id: "ev-1",
        file_name: "report.pdf",
        file_size: 2048,
        category: "documents",
        fragments_extracted: 5,
        status: "success",
      };

      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(uploadResult),
      });

      const onComplete = jest.fn();
      render(
        <EvidenceUploader
          engagementId={ENGAGEMENT_ID}
          onUploadComplete={onComplete}
        />,
      );

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      // Trigger upload
      fireEvent.change(input, {
        target: { files: [makeFile("report.pdf", 2048)] },
      });

      // File name should appear
      expect(screen.getByText("report.pdf")).toBeInTheDocument();

      // Advance timers incrementally and flush promises
      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        expect(screen.getByText("Done")).toBeInTheDocument();
      });

      expect(screen.getByText(/5 fragments/)).toBeInTheDocument();
      expect(onComplete).toHaveBeenCalledWith(uploadResult);

      // Verify fetch was called with correct URL and credentials
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/portal/${ENGAGEMENT_ID}/upload`),
        expect.objectContaining({
          method: "POST",
          credentials: "include",
        }),
      );
    });

    it("uses cookie-based auth (credentials: include) for uploads", async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            id: "ev-1",
            file_name: "doc.pdf",
            file_size: 100,
            category: "documents",
            fragments_extracted: 1,
            status: "success",
          }),
      });

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      fireEvent.change(input, {
        target: { files: [makeFile("doc.pdf", 100)] },
      });

      // Advance timers and flush promises
      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.any(String),
          expect.objectContaining({
            credentials: "include",
          }),
        );
      });
    });
  });

  describe("upload error", () => {
    it("shows Failed on non-OK response", async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: false,
        status: 413,
        json: () => Promise.resolve({ detail: "Payload too large" }),
      });

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      await act(async () => {
        fireEvent.change(input, {
          target: { files: [makeFile("big.pdf", 1024)] },
        });
      });

      // Flush the progress interval and allow the fetch promise to settle
      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      // Allow any remaining microtasks (fetch .json() chain) to resolve
      await act(async () => {
        jest.advanceTimersByTime(0);
      });

      await waitFor(() => {
        expect(screen.getByText("Failed")).toBeInTheDocument();
      });
      expect(screen.getByText(/Payload too large/)).toBeInTheDocument();
    });

    it("shows Failed on network error", async () => {
      global.fetch = jest.fn().mockRejectedValue(new TypeError("Network error"));

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      fireEvent.change(input, {
        target: { files: [makeFile("doc.pdf", 100)] },
      });

      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        expect(screen.getByText("Failed")).toBeInTheDocument();
      });
    });

    it("does not call onUploadComplete on error", async () => {
      global.fetch = jest.fn().mockRejectedValue(new Error("fail"));

      const onComplete = jest.fn();
      render(
        <EvidenceUploader
          engagementId={ENGAGEMENT_ID}
          onUploadComplete={onComplete}
        />,
      );

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      fireEvent.change(input, {
        target: { files: [makeFile("doc.pdf", 100)] },
      });

      await act(async () => {
        jest.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        expect(screen.getByText("Failed")).toBeInTheDocument();
      });
      expect(onComplete).not.toHaveBeenCalled();
    });
  });

  describe("file size display", () => {
    it("shows KB for small files", async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            id: "ev-1",
            file_name: "small.pdf",
            file_size: 5120,
            category: "documents",
            fragments_extracted: 1,
            status: "success",
          }),
      });

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      await act(async () => {
        fireEvent.change(input, {
          target: { files: [makeFile("small.pdf", 5120)] },
        });
      });

      expect(screen.getByText(/5\.0 KB/)).toBeInTheDocument();
    });

    it("shows MB for larger files", async () => {
      global.fetch = jest.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            id: "ev-1",
            file_name: "large.pdf",
            file_size: 2 * 1024 * 1024,
            category: "documents",
            fragments_extracted: 10,
            status: "success",
          }),
      });

      render(<EvidenceUploader engagementId={ENGAGEMENT_ID} />);

      const input = screen.getByLabelText("Upload evidence files", {
        selector: "input",
      });

      await act(async () => {
        fireEvent.change(input, {
          target: { files: [makeFile("large.pdf", 2 * 1024 * 1024)] },
        });
      });

      expect(screen.getByText(/2\.0 MB/)).toBeInTheDocument();
    });
  });
});
