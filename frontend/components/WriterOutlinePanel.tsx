"use client";

import { WriterDocumentRead, WriterSectionRead } from "@/lib/api";

interface WriterOutlinePanelProps {
  document: WriterDocumentRead;
  activeSectionId: string | null;
  onSectionClick: (sectionId: string) => void;
}

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  planned: { label: "Planned", className: "bg-stone-100 text-stone-500 border border-stone-200" },
  awaiting_input: { label: "Needs input", className: "bg-amber-50 text-amber-700 border border-amber-200" },
  drafted: { label: "Drafted", className: "bg-sky-50 text-sky-700 border border-sky-200" },
  user_edited: { label: "Edited", className: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
};

function statusConfig(status: string) {
  return STATUS_CONFIG[status] ?? { label: status, className: "bg-stone-100 text-stone-500 border border-stone-200" };
}

function SectionStatusPill({ status }: { status: string }) {
  const { label, className } = statusConfig(status);
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${className}`}>
      {label}
    </span>
  );
}

function SectionItem({
  section,
  isActive,
  onClick,
}: {
  section: WriterSectionRead;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left rounded-lg px-2.5 py-2 transition-colors group ${
        isActive
          ? "bg-primary/10 text-on-surface"
          : "text-on-surface-variant hover:bg-primary/5 hover:text-on-surface"
      }`}
    >
      <div className="flex items-start gap-2">
        <span
          className={`material-symbols-outlined mt-0.5 shrink-0 transition-colors ${
            isActive ? "text-primary" : "text-on-surface-variant/50 group-hover:text-primary/60"
          }`}
          style={{ fontSize: "14px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
          aria-hidden="true"
        >
          article
        </span>
        <div className="min-w-0 flex-1">
          <p className={`truncate text-xs font-medium leading-snug ${isActive ? "text-on-surface" : ""}`}>
            {section.title}
          </p>
          <div className="mt-1">
            <SectionStatusPill status={section.status} />
          </div>
        </div>
      </div>
    </button>
  );
}

export function WriterOutlinePanel({
  document,
  activeSectionId,
  onSectionClick,
}: WriterOutlinePanelProps) {
  const sections = [...(document.sections ?? [])].sort((a, b) => a.order_index - b.order_index);

  const draftedCount = sections.filter((s) => s.status === "drafted" || s.status === "user_edited").length;
  const progress = sections.length > 0 ? Math.round((draftedCount / sections.length) * 100) : 0;

  return (
    <aside className="flex h-full flex-col overflow-hidden bg-surface-container border-r border-outline/20">
      {/* Header */}
      <div className="shrink-0 border-b border-outline/20 px-3 py-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-hint">Outline</p>
        <p className="mt-0.5 truncate text-xs font-semibold text-on-surface">{document.title}</p>

        {/* Progress bar */}
        <div className="mt-3">
          <div className="flex items-center justify-between text-[10px] text-hint">
            <span>{draftedCount} / {sections.length} drafted</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-outline/20">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${progress}%` }}
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
        </div>
      </div>

      {/* Section list */}
      <nav className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-0.5" aria-label="Document sections">
        {sections.length === 0 ? (
          <div className="px-2 py-6 text-center">
            <span
              className="material-symbols-outlined text-hint"
              style={{ fontSize: "28px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 28" }}
              aria-hidden="true"
            >
              list_alt
            </span>
            <p className="mt-2 text-xs text-hint">No sections yet.</p>
            <p className="mt-0.5 text-[10px] text-hint">Create a document section to get started.</p>
          </div>
        ) : (
          sections.map((section) => (
            <SectionItem
              key={section.id}
              section={section}
              isActive={activeSectionId === section.id}
              onClick={() => onSectionClick(section.id)}
            />
          ))
        )}
      </nav>
    </aside>
  );
}
