"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { useChat } from "@/components/ChatProvider";
import Sidebar from "@/components/Sidebar";
import {
  WriterDocumentSummaryRead,
  createWriterDocument,
  deleteWriterDocument,
  listWriterDocuments,
} from "@/lib/api";
import { ChatProvider } from "@/components/ChatProvider";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  draft: { label: "Draft", className: "bg-stone-100 text-stone-500 border border-stone-200" },
  planned: { label: "Planned", className: "bg-stone-100 text-stone-500 border border-stone-200" },
  in_progress: { label: "In progress", className: "bg-sky-50 text-sky-700 border border-sky-200" },
  complete: { label: "Complete", className: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
};

function statusConfig(status: string) {
  return STATUS_LABELS[status] ?? { label: status, className: "bg-stone-100 text-stone-500 border border-stone-200" };
}

interface NewDocumentModalProps {
  projectId: string | null;
  token: string;
  onCreated: (doc: WriterDocumentSummaryRead) => void;
  onClose: () => void;
}

function NewDocumentModal({ projectId, token, onCreated, onClose }: NewDocumentModalProps) {
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [thesis, setThesis] = useState("");
  const [paperType, setPaperType] = useState("research");
  const [citationStyle, setCitationStyle] = useState("ieee");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !topic.trim()) {
      setError("Title and topic are required.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const doc = await createWriterDocument(
        projectId,
        {
          title: title.trim(),
          topic: topic.trim(),
          thesis: thesis.trim() || undefined,
          paper_type: paperType,
          citation_style: citationStyle,
        },
        token,
      );
      onCreated(doc as unknown as WriterDocumentSummaryRead);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create document.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="New paper"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="w-full max-w-lg rounded-2xl border border-outline/20 bg-background p-6 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="font-headline text-xl font-semibold text-on-surface">New Paper</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-on-surface-variant hover:bg-primary/5 transition-colors"
            aria-label="Close"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>close</span>
          </button>
        </div>

        {!projectId && (
          <div className="mb-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-700">
            This paper will start as an independent writer document. You can import project sources later.
          </div>
        )}

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div>
            <label htmlFor="doc-title" className="mb-1.5 block text-xs font-semibold text-on-surface">
              Title <span className="text-error">*</span>
            </label>
            <input
              id="doc-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. A Survey of Transformer Architectures"
              required
              className="h-10 w-full rounded-xl border border-outline/30 bg-surface-container-low px-3.5 text-sm text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors"
            />
          </div>

          <div>
            <label htmlFor="doc-topic" className="mb-1.5 block text-xs font-semibold text-on-surface">
              Research Topic <span className="text-error">*</span>
            </label>
            <textarea
              id="doc-topic"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Describe the research topic or question this paper addresses…"
              required
              rows={3}
              className="w-full rounded-xl border border-outline/30 bg-surface-container-low px-3.5 py-2.5 text-sm text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors resize-none"
            />
          </div>

          <div>
            <label htmlFor="doc-thesis" className="mb-1.5 block text-xs font-semibold text-on-surface">
              Thesis Statement <span className="text-hint font-normal">(optional)</span>
            </label>
            <textarea
              id="doc-thesis"
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
              placeholder="Optional: what central claim does this paper argue?"
              rows={2}
              className="w-full rounded-xl border border-outline/30 bg-surface-container-low px-3.5 py-2.5 text-sm text-on-surface placeholder:text-hint outline-none focus:border-primary/50 transition-colors resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="doc-paper-type" className="mb-1.5 block text-xs font-semibold text-on-surface">
                Paper type
              </label>
              <select
                id="doc-paper-type"
                value={paperType}
                onChange={(e) => setPaperType(e.target.value)}
                className="h-10 w-full rounded-xl border border-outline/30 bg-surface-container-low px-3 text-sm text-on-surface outline-none focus:border-primary/50 transition-colors"
              >
                <option value="survey">Survey</option>
                <option value="research">Research</option>
                <option value="review">Review</option>
                <option value="thesis">Thesis</option>
                <option value="report">Report</option>
              </select>
            </div>

            <div>
              <label htmlFor="doc-citation-style" className="mb-1.5 block text-xs font-semibold text-on-surface">
                Citation style
              </label>
              <select
                id="doc-citation-style"
                value={citationStyle}
                onChange={(e) => setCitationStyle(e.target.value)}
                className="h-10 w-full rounded-xl border border-outline/30 bg-surface-container-low px-3 text-sm text-on-surface outline-none focus:border-primary/50 transition-colors"
              >
                <option value="ieee">IEEE</option>
                <option value="apa">APA</option>
                <option value="chicago">Chicago</option>
                <option value="mla">MLA</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-rose-500/20 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-full border border-outline/30 px-5 text-sm font-semibold text-on-surface-variant hover:bg-primary/5 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              aria-busy={submitting}
              aria-live="polite"
              className="flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <span
                className="material-symbols-outlined animate-spin"
                style={{ fontSize: "16px" }}
                aria-hidden="true"
                hidden={!submitting}
              >
                progress_activity
              </span>
              <span hidden={submitting}>Create Paper</span>
              <span hidden={!submitting}>Creating…</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DocumentCard({
  doc,
  onDelete,
}: {
  doc: WriterDocumentSummaryRead;
  onDelete: (id: string) => void;
}) {
  const { label, className } = statusConfig(doc.status);

  return (
    <div className="group relative rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 transition-all hover:border-primary/30 hover:shadow-sm">
      <Link href={`/writer/${doc.id}`} className="absolute inset-0 rounded-2xl" aria-label={`Open ${doc.title}`} />

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold ${className}`}>
              {label}
            </span>
            <span className="rounded-full border border-outline/20 bg-surface-container-low px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-hint">
              {doc.paper_type}
            </span>
          </div>
          <h3 className="text-sm font-semibold text-on-surface leading-snug truncate">{doc.title}</h3>
          <p className="mt-1 text-xs text-on-surface-variant line-clamp-2">{doc.topic}</p>
        </div>

        <button
          type="button"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDelete(doc.id);
          }}
          className="relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-hint opacity-0 group-hover:opacity-100 hover:bg-error/10 hover:text-error transition-all"
          aria-label={`Delete ${doc.title}`}
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>delete</span>
        </button>
      </div>

      <div className="mt-4 flex items-center justify-between text-[11px] text-hint">
        <span>Created {formatDate(doc.created_at)}</span>
        <span className="flex items-center gap-1 text-primary font-semibold">
          Open
          <span className="material-symbols-outlined" style={{ fontSize: "12px" }}>arrow_forward</span>
        </span>
      </div>
    </div>
  );
}

function WriterListInner() {
  const { token } = useAuth();
  const { activeProject, busy } = useChat();
  const router = useRouter();

  const [documents, setDocuments] = useState<WriterDocumentSummaryRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const refresh = useCallback(async () => {
    if (!token) {
      setDocuments([]);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const docs = await listWriterDocuments(token);
      setDocuments(docs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleDelete = useCallback(async (docId: string) => {
    if (!token) return;
    if (!window.confirm("Delete this paper document? This cannot be undone.")) return;
    try {
      await deleteWriterDocument(docId, token);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    }
  }, [token]);

  const handleCreated = useCallback((doc: WriterDocumentSummaryRead) => {
    setShowModal(false);
    router.push(`/writer/${doc.id}`);
  }, [router]);

  const showLoadingState = busy || loading;
  const chatHref = activeProject ? `/chat?project=${activeProject.id}` : "/chat";

  return (
    <div className="flex h-screen overflow-hidden w-full bg-background">
      <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen((v) => !v)} />

      <main className="flex-1 overflow-y-auto px-6 py-6 font-ui text-on-surface">
        <div className="mx-auto max-w-5xl">
          {/* Header */}
          <header className="flex flex-wrap items-center justify-between gap-4 mb-8">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-hint">Writer</p>
              <h1 className="mt-1 font-headline text-3xl font-semibold text-on-surface">
                Paper Drafts
              </h1>
              {activeProject && (
                <p className="mt-1 text-sm text-on-surface-variant">
                  Project: <span className="font-medium text-on-surface">{activeProject.title}</span>
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Link
                href={chatHref}
                className="flex h-10 items-center gap-2 rounded-full border border-outline/30 bg-surface-container-lowest px-4 text-sm font-semibold text-on-surface-variant hover:bg-primary/5 hover:text-on-surface transition-colors"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>arrow_back</span>
                Back to Chat
              </Link>
              <button
                type="button"
                onClick={() => setShowModal(true)}
                className="flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>add</span>
                New Paper
              </button>
            </div>
          </header>

          {error && (
            <div className="mb-6 rounded-xl border border-rose-500/20 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          {/* Document grid */}
          {showLoadingState ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-40 rounded-2xl skeleton-shimmer" />
              ))}
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-outline/30 py-20 text-center">
              <span
                className="material-symbols-outlined text-hint"
                style={{ fontSize: "48px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 48" }}
                aria-hidden="true"
              >
                description
              </span>
              <p className="mt-4 text-sm font-semibold text-on-surface">No papers yet</p>
              <p className="mt-1 text-xs text-on-surface-variant max-w-xs">
                Create your first AI-assisted paper draft, then attach sources from uploads, search, or a project.
              </p>
              <button
                type="button"
                onClick={() => setShowModal(true)}
                className="mt-6 flex h-10 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>add</span>
                New Paper
              </button>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {documents.map((doc) => (
                <DocumentCard key={doc.id} doc={doc} onDelete={(id) => void handleDelete(id)} />
              ))}
            </div>
          )}
        </div>
      </main>

      {showModal && token && (
        <NewDocumentModal
          projectId={activeProject?.id ?? null}
          token={token}
          onCreated={handleCreated}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}

export default function WriterPage() {
  const { ready, token } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !token) router.replace("/login?next=%2Fwriter");
  }, [ready, token, router]);

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-hint text-sm uppercase tracking-[0.2em]">
        Loading…
      </main>
    );
  }

  return (
    <ChatProvider>
      <WriterListInner />
    </ChatProvider>
  );
}
