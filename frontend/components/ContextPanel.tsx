"use client";

import { useChat } from "@/components/ChatProvider";
import { ProjectPaper } from "@/lib/api";

export default function ContextPanel() {
  const { papers, runSummary, groundingPaper } = useChat();
  const open = papers.length > 0;

  return (
    <aside
      style={{
        width: open ? "18rem" : "0",
        opacity: open ? 1 : 0,
        transition: "width 500ms ease, opacity 500ms ease",
        overflowY: open ? "auto" : "hidden",
        pointerEvents: open ? "auto" : "none",
      }}
      className="flex-shrink-0 flex flex-col bg-background border-l border-outline/30 custom-scrollbar font-ui"
    >
      <div className="w-72 p-5 space-y-5">
        {/* Header */}
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

        {/* Papers list */}
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
          {paper.relevance_score != null && (
            <div className="mt-1.5 flex items-center gap-1.5">
              <div className="flex-1 h-1 bg-outline/20 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary/60 rounded-full"
                  style={{ width: `${Math.min(paper.relevance_score, 100)}%` }}
                />
              </div>
              <span className="text-[9px] text-hint tabular-nums">
                {paper.relevance_score.toFixed(0)}
              </span>
            </div>
          )}
        </div>
      </div>
    </li>
  );
}
