"use client";

import { useState, useCallback, useRef } from "react";
import {
  SourceCandidate,
  WriterDocumentRead,
  WriterSourcePaper,
  ReferenceFileRead,
  attachSource,
  removeSource,
  suggestSources,
  uploadWriterDocumentSource,
} from "@/lib/api";

interface WriterSourcesPanelProps {
  document: WriterDocumentRead;
  token: string;
  onDocumentUpdate: (doc: WriterDocumentRead) => void;
}

function sourceLabel(source: WriterSourcePaper | null, paperId: string) {
  return source?.title?.trim() || paperId;
}

function sourceMeta(source: WriterSourcePaper | null) {
  if (!source) return null;
  const authors = source.authors.slice(0, 2).join(", ");
  const year = source.year ? String(source.year) : null;
  const provider =
    source.source === "semantic_scholar"
      ? "Semantic Scholar"
      : source.source === "user_upload"
        ? "Uploaded PDF"
        : source.source.replace(/_/g, " ");
  return [authors, year, provider].filter(Boolean).join(" · ");
}

function sourceFromCandidate(paperId: string, candidate: SourceCandidate): WriterSourcePaper {
  return {
    id: paperId,
    title: candidate.title,
    authors: candidate.authors,
    year: candidate.year,
    source: candidate.source,
    source_paper_id: candidate.source_paper_id,
    source_url: candidate.source_url,
    pdf_url: candidate.pdf_url,
    reference_file_id: null,
  };
}

function sourceFromReferenceFile(paperId: string, reference: ReferenceFileRead): WriterSourcePaper {
  return {
    id: paperId,
    title: reference.extracted_title || reference.original_filename,
    authors: reference.extracted_authors,
    year: reference.extracted_year,
    source: "user_upload",
    source_paper_id: reference.id,
    source_url: null,
    pdf_url: null,
    reference_file_id: reference.id,
  };
}

function upsertSourcePaper(sources: WriterSourcePaper[], source: WriterSourcePaper) {
  const existingIndex = sources.findIndex((item) => item.id === source.id);
  if (existingIndex === -1) return [...sources, source];
  return sources.map((item, index) => (index === existingIndex ? source : item));
}

function SourceCard({
  candidate,
  isAttached,
  isAttaching,
  onAttach,
}: {
  candidate: SourceCandidate;
  isAttached: boolean;
  isAttaching: boolean;
  onAttach: () => void;
}) {
  return (
    <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3 space-y-1.5">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-on-surface leading-snug line-clamp-2">{candidate.title}</p>
          {candidate.authors.length > 0 && (
            <p className="mt-0.5 text-[10px] text-hint truncate">
              {candidate.authors.slice(0, 3).join(", ")}
              {candidate.authors.length > 3 ? " et al." : ""}
              {candidate.year ? ` · ${candidate.year}` : ""}
            </p>
          )}
        </div>
        <span
          className={`shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${
            candidate.source === "semantic_scholar"
              ? "bg-sky-50 text-sky-600 border border-sky-200"
              : "bg-violet-50 text-violet-600 border border-violet-200"
          }`}
        >
          {candidate.source === "semantic_scholar" ? "S2" : candidate.source.toUpperCase().slice(0, 4)}
        </span>
      </div>

      {candidate.abstract && (
        <p className="text-[10px] text-on-surface-variant leading-relaxed line-clamp-3">{candidate.abstract}</p>
      )}

      <div className="flex items-center gap-1.5">
        {candidate.pdf_available && (
          <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700 border border-emerald-200">
            <span className="material-symbols-outlined" style={{ fontSize: "10px" }}>description</span>
            PDF
          </span>
        )}
        {candidate.source_url && (
          <a
            href={candidate.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[9px] font-medium text-primary hover:underline"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "10px" }}>open_in_new</span>
            View
          </a>
        )}
        <div className="flex-1" />
        <button
          type="button"
          onClick={onAttach}
          disabled={isAttached || isAttaching}
          className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px] font-semibold transition-colors ${
            isAttached
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200 cursor-default"
              : "bg-primary text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          }`}
        >
          {isAttaching ? (
            <span className="material-symbols-outlined animate-spin" style={{ fontSize: "10px" }}>
              progress_activity
            </span>
          ) : isAttached ? (
            <span className="material-symbols-outlined" style={{ fontSize: "10px" }}>check</span>
          ) : (
            <span className="material-symbols-outlined" style={{ fontSize: "10px" }}>add</span>
          )}
          {isAttached ? "Attached" : isAttaching ? "Attaching…" : "Attach"}
        </button>
      </div>
    </div>
  );
}

export function WriterSourcesPanel({ document, token, onDocumentUpdate }: WriterSourcesPanelProps) {
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<SourceCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [attachingIds, setAttachingIds] = useState<Set<string>>(new Set());
  const [attachedCandidateIds, setAttachedCandidateIds] = useState<Record<string, string>>({});
  const [removingIds, setRemovingIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const attachedSourceById = new Map(document.source_papers.map((source) => [source.id, source]));
  const handlePdfUpload = useCallback(async (file: File) => {
    setUploading(true);
    setUploadStatus(null);
    try {
      const result: ReferenceFileRead = await uploadWriterDocumentSource(document.id, file, token);
      if (!result.linked_paper_id) {
        setUploadStatus({ type: "error", message: "PDF uploaded but paper extraction failed" });
        return;
      }
      const existingIds = document.source_paper_ids_json ?? [];
      onDocumentUpdate({
        ...document,
        source_paper_ids_json: existingIds.includes(result.linked_paper_id)
          ? existingIds
          : [...existingIds, result.linked_paper_id],
        source_papers: upsertSourcePaper(
          document.source_papers,
          sourceFromReferenceFile(result.linked_paper_id, result),
        ),
      });
      setUploadStatus({ type: "success", message: `"${file.name}" attached successfully.` });
    } catch (err) {
      setUploadStatus({ type: "error", message: err instanceof Error ? err.message : "Upload failed." });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [document, token, onDocumentUpdate]);

  const attachedIds = new Set(document.source_paper_ids_json ?? []);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const result = await suggestSources(document.id, query.trim(), token);
      setCandidates(result.candidates);
      setWarnings(result.warnings);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }, [document.id, query, token]);

  const handleAttach = useCallback(async (candidate: SourceCandidate) => {
    const key = candidate.source_paper_id ?? candidate.title;
    setAttachingIds((prev) => new Set(prev).add(key));
    try {
      const result = await attachSource(document.id, candidate, token);
      if (result.paper_id) {
        const paperId = result.paper_id;
        const existingIds = document.source_paper_ids_json ?? [];
        onDocumentUpdate({
          ...document,
          source_paper_ids_json: existingIds.includes(paperId)
            ? existingIds
            : [...existingIds, paperId],
          source_papers: upsertSourcePaper(document.source_papers, sourceFromCandidate(paperId, candidate)),
        });
        setAttachedCandidateIds((prev) => ({ ...prev, [key]: paperId }));
      }
      if (result.requires_upload) {
        setWarnings((prev) => [...prev, result.message]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach failed.");
    } finally {
      setAttachingIds((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  }, [document, token, onDocumentUpdate]);

  const handleRemove = useCallback(async (paperId: string) => {
    setRemovingIds((prev) => new Set(prev).add(paperId));
    try {
      await removeSource(document.id, paperId, token);
      onDocumentUpdate({
        ...document,
        source_paper_ids_json: (document.source_paper_ids_json ?? []).filter((id) => id !== paperId),
        source_papers: document.source_papers.filter((source) => source.id !== paperId),
      });
      setAttachedCandidateIds((prev) =>
        Object.fromEntries(Object.entries(prev).filter(([, attachedId]) => attachedId !== paperId)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Remove failed.");
    } finally {
      setRemovingIds((prev) => {
        const next = new Set(prev);
        next.delete(paperId);
        return next;
      });
    }
  }, [document, token, onDocumentUpdate]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Attached sources */}
      <div className="shrink-0 border-b border-outline/20 px-3 py-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint mb-2">
          Attached Sources ({attachedIds.size})
        </p>
        {attachedIds.size === 0 ? (
          <p className="text-[11px] text-hint">No sources attached yet.</p>
        ) : (
          <div className="space-y-1 max-h-32 overflow-y-auto custom-scrollbar">
            {[...attachedIds].map((paperId) => {
              const source = attachedSourceById.get(paperId) ?? null;
              const label = sourceLabel(source, paperId);
              const meta = sourceMeta(source);
              return (
                <div
                  key={paperId}
                  title={source ? paperId : undefined}
                  className="flex items-center justify-between gap-2 rounded-lg border border-outline/15 bg-surface-container-lowest px-2.5 py-1.5"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[11px] font-medium text-on-surface">{label}</p>
                    {meta && <p className="truncate text-[9px] text-hint">{meta}</p>}
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRemove(paperId)}
                    disabled={removingIds.has(paperId)}
                    className="shrink-0 flex items-center justify-center w-5 h-5 rounded-full text-hint hover:text-error hover:bg-error/10 transition-colors disabled:opacity-50"
                    aria-label={`Remove source ${label}`}
                  >
                    {removingIds.has(paperId) ? (
                      <span className="material-symbols-outlined animate-spin" style={{ fontSize: "12px" }}>
                        progress_activity
                      </span>
                    ) : (
                      <span className="material-symbols-outlined" style={{ fontSize: "12px" }}>close</span>
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* PDF Upload */}
      <div className="shrink-0 border-b border-outline/20 px-3 py-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint mb-2">Upload PDF</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          aria-label="Upload PDF file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handlePdfUpload(file);
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex h-8 items-center gap-1.5 rounded-lg border border-outline/30 bg-surface-container-lowest px-3 text-xs font-medium text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {uploading ? (
            <>
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
              Uploading…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>file_upload</span>
              Upload PDF
            </>
          )}
        </button>
        {uploadStatus && (
          <p
            className={`mt-2 text-[11px] ${
              uploadStatus.type === "success" ? "text-emerald-700" : "text-rose-700"
            }`}
          >
            {uploadStatus.message}
          </p>
        )}
      </div>

      {/* Search */}
      <div className="shrink-0 px-3 py-3 border-b border-outline/20">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint mb-2">Search Sources</p>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void handleSearch(); }}
            placeholder="Search by topic or keyword…"
            className="h-8 flex-1 min-w-0 rounded-lg border border-outline/30 bg-background px-3 text-xs text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors"
          />
          <button
            type="button"
            onClick={() => void handleSearch()}
            disabled={searching || !query.trim()}
            className="flex h-8 items-center gap-1 rounded-lg bg-primary px-3 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {searching ? (
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
            ) : (
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>search</span>
            )}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="shrink-0 mx-3 mt-2 rounded-lg border border-rose-500/20 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="shrink-0 mx-3 mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 space-y-0.5">
          {warnings.map((w, i) => <p key={i}>{w}</p>)}
        </div>
      )}

      {/* Candidates */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-2 space-y-2">
        {candidates.length === 0 && !searching && (
          <div className="py-8 text-center">
            <span
              className="material-symbols-outlined text-hint"
              style={{ fontSize: "28px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 28" }}
              aria-hidden="true"
            >
              search
            </span>
            <p className="mt-2 text-xs text-hint">Search to find papers to attach.</p>
          </div>
        )}
        {candidates.map((c, i) => {
          const key = c.source_paper_id ?? c.title;
          return (
            <SourceCard
              key={`${key}-${i}`}
              candidate={c}
              isAttached={attachedIds.has(key) || Boolean(attachedCandidateIds[key])}
              isAttaching={attachingIds.has(key)}
              onAttach={() => void handleAttach(c)}
            />
          );
        })}
      </div>
    </div>
  );
}
