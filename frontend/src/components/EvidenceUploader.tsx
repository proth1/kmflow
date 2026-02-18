/**
 * Evidence upload component with drag-and-drop, validation, and progress.
 *
 * Used in the client portal for uploading evidence files to an engagement.
 */
"use client";

import { useCallback, useState, useRef } from "react";

const ALLOWED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"];
const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface UploadResult {
  id: string;
  file_name: string;
  file_size: number;
  category: string;
  fragments_extracted: number;
  status: string;
}

interface UploadState {
  file: File;
  progress: number;
  status: "pending" | "uploading" | "success" | "error";
  result?: UploadResult;
  error?: string;
}

interface EvidenceUploaderProps {
  engagementId: string;
  onUploadComplete?: (result: UploadResult) => void;
}

function getFileExtension(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx >= 0 ? name.slice(idx).toLowerCase() : "";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validateFile(file: File): string | null {
  const ext = getFileExtension(file.name);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `File type "${ext}" not allowed. Accepted: ${ALLOWED_EXTENSIONS.join(", ")}`;
  }
  if (file.size > MAX_FILE_SIZE) {
    return `File too large (${formatFileSize(file.size)}). Maximum: ${formatFileSize(MAX_FILE_SIZE)}`;
  }
  return null;
}

export default function EvidenceUploader({ engagementId, onUploadComplete }: EvidenceUploaderProps) {
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      setValidationError(null);
      const newUploads: UploadState[] = [];

      for (const file of Array.from(files)) {
        const error = validateFile(file);
        if (error) {
          setValidationError(error);
          continue;
        }
        newUploads.push({ file, progress: 0, status: "pending" });
      }

      if (newUploads.length > 0) {
        setUploads((prev) => [...prev, ...newUploads]);
        // Start uploading each file
        newUploads.forEach((upload, idx) => {
          const uploadIdx = uploads.length + idx;
          uploadFile(upload.file, uploadIdx);
        });
      }
    },
    [uploads.length, engagementId],
  );

  const uploadFile = async (file: File, index: number) => {
    setUploads((prev) =>
      prev.map((u, i) => (i === index ? { ...u, status: "uploading", progress: 10 } : u)),
    );

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Simulate progress updates
      const progressInterval = setInterval(() => {
        setUploads((prev) =>
          prev.map((u, i) =>
            i === index && u.status === "uploading"
              ? { ...u, progress: Math.min(u.progress + 15, 90) }
              : u,
          ),
        );
      }, 300);

      const response = await fetch(
        `${API_BASE}/api/v1/portal/${engagementId}/upload`,
        { method: "POST", body: formData },
      );

      clearInterval(progressInterval);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(errorData.detail || `Upload failed (${response.status})`);
      }

      const result: UploadResult = await response.json();
      setUploads((prev) =>
        prev.map((u, i) => (i === index ? { ...u, status: "success", progress: 100, result } : u)),
      );
      onUploadComplete?.(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setUploads((prev) =>
        prev.map((u, i) => (i === index ? { ...u, status: "error", error: message } : u)),
      );
    }
  };

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragActive(false);
  }, []);

  return (
    <div>
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInputRef.current?.click(); } }}
        tabIndex={0}
        role="button"
        aria-label="Upload evidence files"
        style={{
          border: `2px dashed ${dragActive ? "#3b82f6" : "#d1d5db"}`,
          borderRadius: "12px",
          padding: "48px 24px",
          textAlign: "center",
          cursor: "pointer",
          backgroundColor: dragActive ? "#eff6ff" : "#f9fafb",
          transition: "all 0.2s ease",
        }}
      >
        <div style={{ fontSize: "36px", marginBottom: "8px" }}>
          {dragActive ? "\u{1F4E5}" : "\u{1F4C1}"}
        </div>
        <p style={{ margin: "0 0 4px 0", fontSize: "15px", fontWeight: 500, color: "#374151" }}>
          {dragActive ? "Drop files here" : "Drag & drop files or click to browse"}
        </p>
        <p style={{ margin: 0, fontSize: "13px", color: "#9ca3af" }}>
          PDF, DOCX, XLSX, CSV, PNG, JPG — Max 50MB
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(",")}
          onChange={(e) => e.target.files && addFiles(e.target.files)}
          style={{ display: "none" }}
        />
      </div>

      {/* Validation error */}
      {validationError && (
        <div
          style={{
            marginTop: "12px",
            padding: "10px 14px",
            backgroundColor: "#fef2f2",
            border: "1px solid #fecaca",
            borderRadius: "8px",
            fontSize: "13px",
            color: "#dc2626",
          }}
        >
          {validationError}
        </div>
      )}

      {/* Upload list */}
      {uploads.length > 0 && (
        <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
          {uploads.map((upload, idx) => (
            <div
              key={`${upload.file.name}-${idx}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                padding: "12px 14px",
                backgroundColor: "#ffffff",
                border: "1px solid #e5e7eb",
                borderRadius: "8px",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 500,
                    color: "#111827",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {upload.file.name}
                </div>
                <div style={{ fontSize: "12px", color: "#9ca3af" }}>
                  {formatFileSize(upload.file.size)}
                  {upload.result && ` — ${upload.result.fragments_extracted} fragments`}
                  {upload.error && ` — ${upload.error}`}
                </div>
                {/* Progress bar */}
                {upload.status === "uploading" && (
                  <div
                    style={{
                      marginTop: "6px",
                      height: "4px",
                      backgroundColor: "#f3f4f6",
                      borderRadius: "2px",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      role="progressbar"
                      aria-valuenow={upload.progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Uploading ${upload.file.name}`}
                      style={{
                        height: "100%",
                        width: `${upload.progress}%`,
                        backgroundColor: "#3b82f6",
                        borderRadius: "2px",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                )}
              </div>
              <div
                style={{
                  fontSize: "13px",
                  fontWeight: 500,
                  color:
                    upload.status === "success"
                      ? "#16a34a"
                      : upload.status === "error"
                        ? "#dc2626"
                        : upload.status === "uploading"
                          ? "#3b82f6"
                          : "#9ca3af",
                }}
              >
                {upload.status === "success"
                  ? "Done"
                  : upload.status === "error"
                    ? "Failed"
                    : upload.status === "uploading"
                      ? `${upload.progress}%`
                      : "Pending"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
