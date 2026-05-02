"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type DeepSearchDisplaySource, useChat } from "@/components/ChatProvider";
import { ProjectPaper } from "@/lib/api";

export default function ContextPanel() {
  const {
    papers,
    deepSearchSources,
    runSummary,
    selectedPaperIds,
    togglePaperSelection,
    lastUploadedPaperId = null,
  } = useChat();
  const open = papers.length > 0 || deepSearchSources.length > 0;
  const splitPanel = papers.length > 0 && deepSearchSources.length > 0;

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
        overflow: "hidden",
        pointerEvents: open ? "auto" : "none",
        position: "relative",
      }}
      className="h-full min-h-0 flex-shrink-0 flex flex-col bg-background border-l border-outline/30 font-ui"
    >
      {open && (
        <div
          onMouseDown={onHandleMouseDown}
          className="absolute left-0 top-0 h-full w-1 cursor-col-resize hover:bg-primary/30 z-10"
          style={{ width: "4px" }}
        />
      )}
      <div className="flex-1 min-h-0 p-5" style={{ minWidth: "200px" }}>
        <div className="flex h-full min-h-0 flex-col gap-5">
          {papers.length > 0 && (
            <section className={`flex min-h-0 flex-col space-y-2 ${splitPanel ? "flex-[2_1_0%]" : "flex-1"}`}>
              <div className="flex flex-none items-center justify-between">
                <h3 className="font-bold text-xs text-on-surface uppercase tracking-widest">
                  Related Papers
                </h3>
                {runSummary && (
                  <span className="text-[10px] text-hint">
                    {runSummary.ranked_count} ranked
                  </span>
                )}
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto pr-1 custom-scrollbar">
                <ul className="space-y-2">
                  {papers.map((paper) => (
                    <PaperCard
                      key={paper.id}
                      paper={paper}
                      isSelected={selectedPaperIds.includes(paper.id)}
                      isFreshlyUploaded={lastUploadedPaperId === paper.id}
                      onToggle={() => togglePaperSelection(paper.id)}
                    />
                  ))}
                </ul>
              </div>
            </section>
          )}

          {splitPanel && <div aria-hidden="true" className="h-px flex-none bg-outline/20" />}

          {deepSearchSources.length > 0 && (
            <section className={`flex min-h-0 flex-col space-y-2 ${splitPanel ? "flex-[1_1_0%]" : "flex-1"}`}>
              <div className="flex flex-none items-center justify-between">
                <h3 className="font-bold text-xs text-on-surface uppercase tracking-widest">
                  Deep Search Sources
                </h3>
                <span className="text-[10px] text-hint">
                  {deepSearchSources.length} cited
                </span>
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto pr-1 custom-scrollbar">
                <ul className="space-y-2">
                  {deepSearchSources.map((source) => (
                    <DeepSearchSourceCard key={`${source.id}-${source.title}`} source={source} />
                  ))}
                </ul>
              </div>
            </section>
          )}
        </div>
      </div>

    </aside>
  );
}

function DeepSearchSourceCard({ source }: { source: DeepSearchDisplaySource }) {
  const typeLabel = formatDeepSearchSourceType(source.sourceType);
  const body = (
    <>
      <div className="flex items-start gap-2">
        <SourceFavicon source={source} />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium text-on-surface leading-snug line-clamp-2">
            {source.title}
          </p>
          <p className="mt-1 text-[10px] text-hint">
            {source.id} · {typeLabel}
          </p>
        </div>
      </div>
    </>
  );

  const className =
    "block p-3 rounded-xl border border-outline/20 bg-surface-container-low transition-[background-color,border-color] hover:border-primary/30";

  if (source.url) {
    return (
      <li>
        <a href={source.url} target="_blank" rel="noreferrer" className={className}>
          {body}
        </a>
      </li>
    );
  }

  return (
    <li className={className}>
      {body}
    </li>
  );
}

function SourceFavicon({ source }: { source: DeepSearchDisplaySource }) {
  const [failed, setFailed] = useState(false);
  const faviconUrl = source.url ? getFaviconUrl(source.url) : null;

  if (!faviconUrl || failed) {
    return (
      <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-container-high text-hint ring-1 ring-outline/20">
        <span
          className="material-symbols-outlined"
          aria-hidden="true"
          style={{
            fontSize: "13px",
            fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
          }}
        >
          article
        </span>
      </div>
    );
  }

  return (
    <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-surface-container-high ring-1 ring-outline/20">
      <img
        src={faviconUrl}
        alt=""
        aria-hidden="true"
        className="h-3.5 w-3.5 object-contain"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

function getFaviconUrl(url: string) {
  try {
    const hostname = new URL(url).hostname;
    if (!hostname) return null;
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(hostname)}&sz=32`;
  } catch {
    return null;
  }
}

function PaperCard({
  paper,
  isSelected,
  isFreshlyUploaded,
  onToggle,
}: {
  paper: ProjectPaper;
  isSelected: boolean;
  isFreshlyUploaded: boolean;
  onToggle: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showUploadHighlight, setShowUploadHighlight] = useState(isFreshlyUploaded);
  const summaryId = `paper-summary-${paper.id}`;
  const showSummaryToggle = paper.summary != null;
  const isUploadedPaper = isUploadedReferencePaper(paper);

  useEffect(() => {
    if (!isFreshlyUploaded) {
      setShowUploadHighlight(false);
      return;
    }

    setShowUploadHighlight(true);
    const timeoutId = window.setTimeout(() => {
      setShowUploadHighlight(false);
    }, 2200);

    return () => window.clearTimeout(timeoutId);
  }, [isFreshlyUploaded]);

  return (
    <li
      className={`p-3 rounded-xl border transition-[background-color,border-color,box-shadow] ${
        isSelected
          ? "bg-primary/10 border-primary/30"
          : "bg-surface-container-low border-outline/20 hover:border-outline/40"
      } ${
        showUploadHighlight
          ? "shadow-[0_0_0_1px_rgba(53,130,75,0.22),0_0_0_10px_rgba(53,130,75,0.08)]"
          : ""
      }`}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={isSelected}
          aria-label={isSelected ? "Deselect paper" : "Select paper"}
          className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md border transition-colors ${
            isSelected
              ? "border-primary bg-primary text-white"
              : "border-outline/40 text-hint hover:border-primary/50"
          }`}
        >
          <span
            className="material-symbols-outlined"
            style={{
              fontSize: "14px",
              fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
            }}
          >
            {isSelected ? "check" : "add"}
          </span>
        </button>
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
          {isUploadedPaper && (
            <div className="mt-1">
              <span className="inline-flex items-center rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-primary">
                Uploaded PDF
              </span>
            </div>
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

function formatDeepSearchSourceType(sourceType: DeepSearchDisplaySource["sourceType"]) {
  return sourceType
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function isUploadedReferencePaper(paper: ProjectPaper) {
  const paperWithReference = paper as ProjectPaper & {
    reference_file_id?: string | null;
  };

  if (paperWithReference.reference_file_id) {
    return true;
  }

  const normalizedSource = paper.source.trim().toLowerCase();
  return normalizedSource === "user_upload"
    || normalizedSource.includes("uploaded")
    || normalizedSource.includes("reference");
}
