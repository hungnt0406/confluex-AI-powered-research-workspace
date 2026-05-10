"use client";

import { useState, useCallback, useEffect } from "react";
import { getQaReport, suggestSources, SourceCandidate } from "@/lib/api";

interface QaTodo {
  section_id?: string;
  text?: string;
  context?: string;
  [key: string]: unknown;
}

interface WriterQAPanelProps {
  documentId: string;
  token: string;
}

function TodoItem({
  todo,
  onSearchSources,
}: {
  todo: QaTodo;
  onSearchSources: (query: string) => void;
}) {
  const text = todo.text ?? todo.context ?? JSON.stringify(todo);
  const query = typeof text === "string" ? text.slice(0, 120) : "";

  return (
    <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3 space-y-2">
      <div className="flex items-start gap-2">
        <span
          className="material-symbols-outlined mt-0.5 shrink-0 text-amber-500"
          style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
          aria-hidden="true"
        >
          warning
        </span>
        <p className="text-[11px] text-on-surface leading-relaxed flex-1">{text}</p>
      </div>
      {todo.section_id && (
        <p className="text-[10px] text-hint font-mono">Section: {todo.section_id}</p>
      )}
      <button
        type="button"
        onClick={() => onSearchSources(query)}
        className="inline-flex items-center gap-1 rounded-lg border border-outline/25 px-2.5 py-1 text-[10px] font-semibold text-primary hover:bg-primary/5 hover:border-primary/30 transition-colors"
      >
        <span className="material-symbols-outlined" style={{ fontSize: "10px" }}>search</span>
        Search sources
      </button>
    </div>
  );
}

export function WriterQAPanel({ documentId, token }: WriterQAPanelProps) {
  const [todos, setTodos] = useState<QaTodo[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Source search state
  const [searchQuery, setSearchQuery] = useState("");
  const [candidates, setCandidates] = useState<SourceCandidate[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { unresolved_todos, total_count } = await getQaReport(documentId, token);
      setTodos(unresolved_todos as QaTodo[]);
      setTotalCount(total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load QA report.");
    } finally {
      setLoading(false);
    }
  }, [documentId, token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query);
    if (!query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const { candidates: results } = await suggestSources(documentId, query, token);
      setCandidates(results);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }, [documentId, token]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="shrink-0 border-b border-outline/20 px-3 py-3">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint">QA Report</p>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-semibold text-primary hover:bg-primary/5 transition-colors disabled:opacity-50"
          >
            <span
              className={`material-symbols-outlined ${loading ? "animate-spin" : ""}`}
              style={{ fontSize: "12px" }}
            >
              refresh
            </span>
            Refresh
          </button>
        </div>

        <div className="mt-2 flex items-center gap-3">
          <div className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
            totalCount === 0
              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
              : "bg-amber-50 text-amber-700 border border-amber-200"
          }`}>
            <span
              className="material-symbols-outlined"
              style={{ fontSize: "12px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
            >
              {totalCount === 0 ? "check_circle" : "warning"}
            </span>
            {totalCount === 0 ? "All resolved" : `${totalCount} unresolved`}
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="shrink-0 mx-3 mt-2 rounded-lg border border-rose-500/20 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
        </div>
      )}

      {/* Todos list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3 space-y-2">
        {loading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => (
              <div key={i} className="h-20 rounded-xl skeleton-shimmer" />
            ))}
          </div>
        ) : todos.length === 0 ? (
          <div className="py-8 text-center">
            <span
              className="material-symbols-outlined text-emerald-500"
              style={{ fontSize: "32px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 32" }}
              aria-hidden="true"
            >
              check_circle
            </span>
            <p className="mt-2 text-xs font-semibold text-on-surface">No unresolved TODOs</p>
            <p className="mt-0.5 text-[11px] text-hint">Your document is QA-clean.</p>
          </div>
        ) : (
          todos.map((todo, i) => (
            <TodoItem key={i} todo={todo} onSearchSources={handleSearch} />
          ))
        )}
      </div>

      {/* Source search results (shown after clicking "Search sources") */}
      {(searchQuery || candidates.length > 0) && (
        <div className="shrink-0 border-t border-outline/20 max-h-64 overflow-y-auto custom-scrollbar">
          <div className="px-3 py-2 border-b border-outline/15">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint">Source Suggestions</p>
              <button
                type="button"
                onClick={() => { setCandidates([]); setSearchQuery(""); }}
                className="text-hint hover:text-on-surface transition-colors"
                aria-label="Clear suggestions"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "12px" }}>close</span>
              </button>
            </div>
            {searchQuery && (
              <p className="mt-0.5 text-[10px] text-hint truncate">Query: {searchQuery}</p>
            )}
          </div>

          {searching && (
            <div className="px-3 py-3 text-center">
              <span className="material-symbols-outlined animate-spin text-hint" style={{ fontSize: "18px" }}>
                progress_activity
              </span>
            </div>
          )}

          {searchError && (
            <div className="mx-3 my-2 rounded-lg border border-rose-500/20 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
              {searchError}
            </div>
          )}

          <div className="px-3 py-2 space-y-2">
            {candidates.slice(0, 5).map((c, i) => (
              <div key={i} className="rounded-lg border border-outline/15 bg-surface-container-lowest px-2.5 py-2">
                <p className="text-[11px] font-semibold text-on-surface line-clamp-2">{c.title}</p>
                {c.authors.length > 0 && (
                  <p className="text-[10px] text-hint truncate mt-0.5">
                    {c.authors.slice(0, 2).join(", ")}{c.year ? ` · ${c.year}` : ""}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
