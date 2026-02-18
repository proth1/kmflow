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
        className={`border-2 border-dashed rounded-xl p-12 px-6 text-center cursor-pointer transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] ${
          dragActive
            ? "border-blue-400 bg-blue-50"
            : "border-[hsl(var(--border))] bg-gray-50 hover:border-blue-300 hover:bg-blue-50/50"
        }`}
      >
        <div className="text-4xl mb-2">
          {dragActive ? "\u{1F4E5}" : "\u{1F4C1}"}
        </div>
        <p className="m-0 mb-1 text-[15px] font-medium text-[hsl(var(--foreground))]">
          {dragActive ? "Drop files here" : "Drag & drop files or click to browse"}
        </p>
        <p className="m-0 text-sm text-[hsl(var(--muted-foreground))]">
          PDF, DOCX, XLSX, CSV, PNG, JPG — Max 50MB
        </p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(",")}
          onChange={(e) => e.target.files && addFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {/* Validation error */}
      {validationError && (
        <div className="mt-3 p-2.5 px-3.5 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
          {validationError}
        </div>
      )}

      {/* Upload list */}
      {uploads.length > 0 && (
        <div className="mt-4 flex flex-col gap-2">
          {uploads.map((upload, idx) => (
            <div
              key={`${upload.file.name}-${idx}`}
              className="flex items-center gap-3 p-3 px-3.5 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                  {upload.file.name}
                </div>
                <div className="text-xs text-[hsl(var(--muted-foreground))]">
                  {formatFileSize(upload.file.size)}
                  {upload.result && ` — ${upload.result.fragments_extracted} fragments`}
                  {upload.error && ` — ${upload.error}`}
                </div>
                {/* Progress bar */}
                {upload.status === "uploading" && (
                  <div className="mt-1.5 h-1 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      role="progressbar"
                      aria-valuenow={upload.progress}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Uploading ${upload.file.name}`}
                      className="h-full bg-blue-500 rounded-full transition-[width] duration-300"
                      style={{ width: `${upload.progress}%` }}
                    />
                  </div>
                )}
              </div>
              <div
                className={`text-sm font-medium ${
                  upload.status === "success"
                    ? "text-green-600"
                    : upload.status === "error"
                      ? "text-red-600"
                      : upload.status === "uploading"
                        ? "text-blue-600"
                        : "text-[hsl(var(--muted-foreground))]"
                }`}
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
