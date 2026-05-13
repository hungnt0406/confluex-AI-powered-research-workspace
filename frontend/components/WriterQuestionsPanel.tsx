"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  WriterSectionRead,
  getSectionQuestions,
  proposeSectionOutline,
  approveSectionOutline,
  submitSectionInputs,
  draftSection,
} from "@/lib/api";

interface WriterQuestionsPanelProps {
  documentId: string;
  documentPaperType: string;
  activeSection: WriterSectionRead | null;
  token: string;
  onSectionUpdate: (section: WriterSectionRead) => void;
}

function isApprovedSectionOutline(
  outlineText: string | null | undefined,
  sectionType: string | undefined,
  documentPaperType: string,
) {
  const outline = outlineText?.trim() ?? "";
  if (!outline) return false;
  const requiresStructuredOutline =
    (sectionType === "methods" || sectionType === "results")
    && (documentPaperType === "survey" || documentPaperType === "research");
  if (
    requiresStructuredOutline
  ) {
    return outline.includes("\\subsection{");
  }
  return true;
}

export function WriterQuestionsPanel({
  documentId,
  documentPaperType,
  activeSection,
  token,
  onSectionUpdate,
}: WriterQuestionsPanelProps) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [proposingOutline, setProposingOutline] = useState(false);
  const [approvingOutline, setApprovingOutline] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [outlineDraft, setOutlineDraft] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const warningDelayTimerRef = useRef<number | null>(null);

  const clearWarningDelay = useCallback(() => {
    if (!warningDelayTimerRef.current) return;
    window.clearTimeout(warningDelayTimerRef.current);
    warningDelayTimerRef.current = null;
  }, []);

  useEffect(() => {
    clearWarningDelay();
    setWarnings([]);

    if (!activeSection) {
      setQuestions([]);
      setAnswers({});
      setOutlineDraft("");
      return;
    }

    // Pre-fill answers from existing inputs
    setAnswers(activeSection.user_inputs_json ?? {});
    setOutlineDraft(activeSection.outline_text ?? "");

    let cancelled = false;
    setLoadingQuestions(true);
    setError(null);

    getSectionQuestions(documentId, activeSection.id, token)
      .then(({ questions: qs }) => {
        if (!cancelled) setQuestions(qs);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load questions.");
      })
      .finally(() => {
        if (!cancelled) setLoadingQuestions(false);
      });

    return () => { cancelled = true; };
  }, [documentId, activeSection?.id, token, clearWarningDelay]); // activeSection object excluded intentionally — only id triggers refetch

  useEffect(() => clearWarningDelay, [clearWarningDelay]);

  const handleSubmitInputs = useCallback(async () => {
    if (!activeSection) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await submitSectionInputs(documentId, activeSection.id, answers, token);
      onSectionUpdate(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submit failed.");
    } finally {
      setSubmitting(false);
    }
  }, [activeSection, documentId, answers, token, onSectionUpdate]);

  const hasApprovedOutline = isApprovedSectionOutline(
    activeSection?.outline_text,
    activeSection?.section_type,
    documentPaperType,
  );

  const handleProposeSectionOutline = useCallback(async () => {
    if (!activeSection) return;
    setProposingOutline(true);
    setError(null);
    setWarnings([]);
    try {
      const { outline_text, warnings: ws } = await proposeSectionOutline(
        documentId,
        activeSection.id,
        token,
      );
      setOutlineDraft(outline_text);
      setWarnings(ws);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Outline generation failed.");
    } finally {
      setProposingOutline(false);
    }
  }, [activeSection, documentId, token]);

  const handleApproveSectionOutline = useCallback(async () => {
    if (!activeSection) return;
    const normalizedOutline = outlineDraft.trim();
    if (!normalizedOutline) {
      setError("Section outline cannot be empty.");
      return;
    }
    setApprovingOutline(true);
    setError(null);
    try {
      const updated = await approveSectionOutline(
        documentId,
        activeSection.id,
        normalizedOutline,
        token,
      );
      setOutlineDraft(updated.outline_text ?? "");
      onSectionUpdate(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Outline approval failed.");
    } finally {
      setApprovingOutline(false);
    }
  }, [activeSection, documentId, outlineDraft, token, onSectionUpdate]);

  const handleDraftSection = useCallback(async () => {
    if (!activeSection || !hasApprovedOutline) return;
    setDrafting(true);
    setError(null);
    clearWarningDelay();
    setWarnings([]);
    try {
      const { section, warnings: ws } = await draftSection(documentId, activeSection.id, token);
      onSectionUpdate(section);
      warningDelayTimerRef.current = window.setTimeout(() => {
        setWarnings(ws);
        warningDelayTimerRef.current = null;
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Drafting failed.");
    } finally {
      setDrafting(false);
    }
  }, [activeSection, documentId, token, onSectionUpdate, clearWarningDelay, hasApprovedOutline]);

  if (!activeSection) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div>
          <span
            className="material-symbols-outlined text-hint"
            style={{ fontSize: "32px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 32" }}
            aria-hidden="true"
          >
            help_outline
          </span>
          <p className="mt-2 text-xs text-hint">Select a section from the outline to see its questions.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Section header */}
      <div className="shrink-0 border-b border-outline/20 px-3 py-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint">Section</p>
        <p className="mt-0.5 text-xs font-semibold text-on-surface truncate">{activeSection.title}</p>
        {activeSection.outline_text && (
          <p className="mt-1 whitespace-pre-line text-[11px] text-on-surface-variant leading-relaxed line-clamp-3">
            {activeSection.outline_text}
          </p>
        )}
      </div>

      {/* Questions */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-3 py-3 space-y-4">
        {!loadingQuestions && (
          <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <label className="text-[11px] font-semibold text-on-surface" htmlFor="section-outline">
                {hasApprovedOutline ? "Approved outline" : "Section outline"}
              </label>
              {hasApprovedOutline && (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700">
                  Approved
                </span>
              )}
            </div>
            <textarea
              id="section-outline"
              value={outlineDraft}
              onChange={(e) => setOutlineDraft(e.target.value)}
              placeholder="Generate or write the section outline..."
              rows={6}
              className="w-full rounded-lg border border-outline/30 bg-background px-3 py-2 font-mono text-[11px] leading-relaxed text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors resize-none"
            />
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {!hasApprovedOutline && (
                <button
                  type="button"
                  onClick={() => void handleProposeSectionOutline()}
                  disabled={proposingOutline || approvingOutline || drafting}
                  className="flex h-8 items-center justify-center gap-1.5 rounded-lg border border-outline/25 bg-surface-container-low px-3 text-[11px] font-semibold text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {proposingOutline ? (
                    <>
                      <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                        progress_activity
                      </span>
                      Generating…
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>account_tree</span>
                      Generate section outline
                    </>
                  )}
                </button>
              )}
              <button
                type="button"
                onClick={() => void handleApproveSectionOutline()}
                disabled={proposingOutline || approvingOutline || drafting || !outlineDraft.trim()}
                className="flex h-8 items-center justify-center gap-1.5 rounded-lg border border-outline/25 bg-surface-container-low px-3 text-[11px] font-semibold text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {approvingOutline ? (
                  <>
                    <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                      progress_activity
                    </span>
                    Approving…
                  </>
                ) : (
                  <>
                    <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>check_circle</span>
                    Approve outline
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {loadingQuestions ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="space-y-1.5">
                <div className="h-3 w-3/4 rounded skeleton-shimmer" />
                <div className="h-16 w-full rounded-lg skeleton-shimmer" />
              </div>
            ))}
          </div>
        ) : questions.length === 0 ? (
          <div className="py-6 text-center">
            <span
              className="material-symbols-outlined text-hint"
              style={{ fontSize: "24px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 24" }}
              aria-hidden="true"
            >
              quiz
            </span>
            <p className="mt-2 text-xs text-hint">No questions for this section.</p>
          </div>
        ) : (
          questions.map((question, index) => (
            <div key={index}>
              <label className="block text-[11px] font-semibold text-on-surface mb-1.5" htmlFor={`q-${index}`}>
                <span className="text-primary font-bold">{index + 1}.</span> {question}
              </label>
              <textarea
                id={`q-${index}`}
                value={answers[question] ?? ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, [question]: e.target.value }))}
                placeholder="Your answer…"
                rows={3}
                className="w-full rounded-lg border border-outline/30 bg-background px-3 py-2 text-xs text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors resize-none"
              />
            </div>
          ))
        )}

        {/* Additional context */}
        {!loadingQuestions && (
          <>
            <div className="border-t border-outline/20 pt-4">
              <label
                className="block text-[11px] font-semibold text-on-surface mb-1.5"
                htmlFor="q-notes"
              >
                Additional context / raw data{" "}
                <span className="font-normal text-hint">(optional)</span>
              </label>
              <textarea
                id="q-notes"
                value={answers["__notes__"] ?? ""}
                onChange={(e) => setAnswers((prev) => ({ ...prev, "__notes__": e.target.value }))}
                placeholder="Paste raw numbers, table data, model details, or any extra context for the AI..."
                rows={5}
                className="w-full rounded-lg border border-outline/30 bg-background px-3 py-2 text-xs text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors resize-none"
              />
            </div>
          </>
        )}
      </div>

      {/* Error / Warnings */}
      {error && (
        <div className="shrink-0 mx-3 mb-2 rounded-lg border border-rose-500/20 bg-rose-50 px-3 py-2 text-[11px] text-rose-700">
          {error}
        </div>
      )}
      {warnings.length > 0 && (
        <div className="shrink-0 mx-3 mb-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 space-y-0.5">
          {warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-amber-700">{w}</p>
          ))}
        </div>
      )}

      {/* Actions */}
      <div className="shrink-0 border-t border-outline/20 p-3 space-y-2">
        <button
          type="button"
          onClick={() => void handleSubmitInputs()}
          disabled={
            submitting
            || proposingOutline
            || approvingOutline
            || drafting
            || (questions.length === 0 && !answers["__notes__"]?.trim())
          }
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-outline/25 bg-surface-container-lowest px-3 py-2 text-xs font-medium text-on-surface hover:bg-primary/5 hover:border-primary/30 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? (
            <>
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
              Saving answers…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>save</span>
              Save answers
            </>
          )}
        </button>
        <button
          type="button"
          onClick={() => void handleDraftSection()}
          disabled={submitting || drafting || !hasApprovedOutline}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {drafting ? (
            <>
              <span className="material-symbols-outlined animate-spin" style={{ fontSize: "14px" }}>
                progress_activity
              </span>
              Drafting section…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined" style={{ fontSize: "14px" }}>auto_fix_high</span>
              Draft section
            </>
          )}
        </button>
      </div>
    </div>
  );
}
