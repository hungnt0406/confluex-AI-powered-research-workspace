"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useChat } from "@/components/ChatProvider";
import { ProjectPaper } from "@/lib/api";

export default function ContextPanel() {
  const { papers, runSummary, groundingPaper } = useChat();
  const open = papers.length > 0;

  const [width, setWidth] = useState<number>(600);
  const dragging = useRef(false);
  const startX = useRef(0);
  const startWidth = useRef(0);

  useEffect(() => {
    setWidth(Math.round(window.innerWidth * 0.3));
  }, []);

  const onMouseMove = useCallback((e: MouseEvent) => {
    if (!dragging.current) return;
    const delta = startX.current - e.clientX;
    const next = Math.min(Math.max(startWidth.current + delta, 240), window.innerWidth * 0.8);
    setWidth(Math.round(next));
  }, []);

  const onMouseUp = useCallback(() => {
    if (!dragging.current) return;
    dragging.current = false;
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
  }, [onMouseMove]);

  useEffect(() => {
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      if (dragging.current) {
        document.body.style.userSelect = "";
        document.body.style.cursor = "";
      }
    };
  }, [onMouseMove, onMouseUp]);

  const onHandleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = true;
      startX.current = e.clientX;
      startWidth.current = width;
      document.body.style.userSelect = "none";
      document.body.style.cursor = "col-resize";
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    },
    [width, onMouseMove, onMouseUp]
  );

  return (
    <aside
      style={{
        width: open ? `${width}px` : "0",
        opacity: open ? 1 : 0,
        transition: dragging.current ? "opacity 500ms ease" : "width 500ms ease, opacity 500ms ease",
        overflowY: open ? "auto" : "hidden",
        pointerEvents: open ? "auto" : "none",
        position: "relative",
      }}
      className="flex-shrink-0 flex flex-col bg-background border-l border-outline/30 custom-scrollbar font-ui"
    >
      {open && (
        <div
          onMouseDown={onHandleMouseDown}
          className="absolute left-0 top-0 h-full w-1 cursor-col-resize hover:bg-primary/30 z-10"
          style={{ width: "4px" }}
        />
      )}
      <div className="p-5 space-y-5" style={{ minWidth: "200px" }}>
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-xs text-on-surface uppercase tracking-widest">
            Related Papers
          </h3>
          {runSummary && (
            <span className="text-[10px] text-hint">
              {runSummary.ranked_count} ranked
            </span>
          )}
        </div>

        <ul className="space-y-2">
          {papers.map((paper) => (
            <PaperCard
              key={paper.id}
              paper={paper}
              isGrounding={groundingPaper?.id === paper.id}
            />
          ))}
        </ul>
      </div>
    </aside>
  );
}

function PaperCard({
  paper,
  isGrounding,
}: {
  paper: ProjectPaper;
  isGrounding: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const summaryId = `paper-summary-${paper.id}`;
  const showSummaryToggle = paper.summary != null;

  return (
    <li
      className={`p-3 rounded-xl border transition-colors ${
        isGrounding
          ? "bg-primary/10 border-primary/30"
          : "bg-surface-container-low border-outline/20 hover:border-outline/40"
      }`}
    >
      <div className="flex items-start gap-2">
        <span
          className="material-symbols-outlined text-primary mt-0.5 flex-shrink-0"
          style={{
            fontSize: "14px",
            fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
          }}
        >
          {isGrounding ? "chat_bubble" : "article"}
        </span>
        <div className="min-w-0 flex-1">
          {paper.source_url ? (
            <a
              href={paper.source_url}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-medium text-on-surface leading-snug line-clamp-2 hover:text-primary"
            >
              {paper.title}
            </a>
          ) : (
            <p className="text-[11px] font-medium text-on-surface leading-snug line-clamp-2">
              {paper.title}
            </p>
          )}
          <p className="text-[10px] text-hint mt-1 truncate">
            {paper.authors.slice(0, 2).join(", ")}
            {paper.year ? ` · ${paper.year}` : ""}
          </p>
          <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-hint tabular-nums">
            <div className="ml-[6px] flex flex-wrap items-center gap-x-2 gap-y-1">
              <div className="flex items-center gap-0.5">
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{
                    fontSize: "16px",
                    marginLeft: "-7px",
                    marginRight: "-1px",
                    fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                  }}
                >
                  format_quote
                </span>
                <span>{paper.citation_count ?? "—"}</span>
                <span>cited</span>
              </div>
              <div className="flex items-center gap-0.5">
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{
                    fontSize: "16px",
                    marginLeft: "-7px",
                    marginRight: "-1px",
                    fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                  }}
                >
                  list_alt
                </span>
                <span>{paper.reference_count ?? "—"}</span>
                <span>refs</span>
              </div>
            </div>
            {showSummaryToggle && (
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls={summaryId}
                aria-label={expanded ? "Hide summary" : "Show summary"}
                onClick={() => setExpanded((current) => !current)}
                className="inline-flex h-10 min-w-10 flex-shrink-0 items-center justify-center rounded-md px-2 text-hint transition-colors hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
              >
                <span
                  className="material-symbols-outlined"
                  aria-hidden="true"
                  style={{
                    fontSize: "16px",
                    fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                  }}
                >
                  {expanded ? "expand_less" : "expand_more"}
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
      {expanded && paper.summary && (
        <div
          id={summaryId}
          className="mt-2 pt-2 border-t border-outline/20 space-y-1.5"
        >
          {paper.summary.has_error ? (
            <div className="flex items-center gap-1.5 text-[10px] text-hint leading-snug">
              <span
                className="material-symbols-outlined"
                aria-hidden="true"
                style={{
                  fontSize: "16px",
                  marginLeft: "-7px",
                  fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                }}
              >
                error
              </span>
              <span className="truncate">
                {paper.summary.error_message
                  ? `Summary unavailable: ${paper.summary.error_message}`
                  : "Summary unavailable"}
              </span>
            </div>
          ) : (
            <>
              <SummarySection label="Problem" value={paper.summary.problem} />
              <SummarySection label="Method" value={paper.summary.method} />
              <SummarySection label="Result" value={paper.summary.result} />
            </>
          )}
        </div>
      )}
    </li>
  );
}

function SummarySection({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  return (
    <div className="space-y-0.5">
      <p className="text-[9px] uppercase tracking-widest text-hint">{label}</p>
      <p className="text-[10px] text-on-surface leading-snug">{value ?? <span className="text-hint">—</span>}</p>
    </div>
  );
}
