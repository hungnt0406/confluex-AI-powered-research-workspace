"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { WriterWorkspace } from "@/components/WriterWorkspace";
import { ChatProvider } from "@/components/ChatProvider";
import { WriterDocumentRead, getWriterDocument } from "@/lib/api";
import OnboardingTour from "@/components/OnboardingTour";

function WriterDocumentLoader({ documentId, token }: { documentId: string; token: string }) {
  const [document, setDocument] = useState<WriterDocumentRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getWriterDocument(documentId, token)
      .then((doc) => {
        if (!cancelled) setDocument(doc);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load document.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [documentId, token]);

  if (loading) {
    return (
      <div className="flex h-screen flex-col">
        {/* Skeleton top bar */}
        <div className="flex h-12 shrink-0 items-center gap-3 border-b border-outline/20 bg-surface-container px-4">
          <div className="h-4 w-64 rounded skeleton-shimmer" />
        </div>
        {/* Skeleton 3-col */}
        <div className="flex flex-1 overflow-hidden">
          <div className="w-[220px] shrink-0 border-r border-outline/20 bg-surface-container p-3 space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-10 rounded-lg skeleton-shimmer" />
            ))}
          </div>
          <div className="flex-1 bg-stone-950" />
          <div className="w-[40vw] min-w-[360px] max-w-[640px] shrink-0 border-l border-outline/20 p-3 space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-xl skeleton-shimmer" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 px-4 text-center">
        <span
          className="material-symbols-outlined text-hint"
          style={{ fontSize: "40px", fontVariationSettings: "'FILL' 0, 'wght' 200, 'GRAD' 0, 'opsz' 40" }}
          aria-hidden="true"
        >
          error
        </span>
        <div>
          <p className="text-sm font-semibold text-on-surface">Failed to load document</p>
          <p className="mt-1 text-xs text-on-surface-variant">{error ?? "Unknown error"}</p>
        </div>
        <Link
          href="/writer"
          className="inline-flex h-9 items-center gap-2 rounded-full bg-primary px-4 text-sm font-semibold text-white no-underline hover:opacity-90"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>arrow_back</span>
          Back to Writer
        </Link>
      </div>
    );
  }

  return (
    <>
      <WriterWorkspace initialDocument={document} token={token} />
      <OnboardingTour variant="writer" />
    </>
  );
}

export default function WriterDocumentPage() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const params = useParams<{ documentId: string }>();
  const documentId = params.documentId;

  useEffect(() => {
    if (ready && !token) router.replace(`/login?next=%2Fwriter%2F${documentId}`);
  }, [ready, token, router, documentId]);

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-hint text-sm uppercase tracking-[0.2em]">
        Loading…
      </main>
    );
  }

  return (
    <ChatProvider>
      <WriterDocumentLoader documentId={documentId} token={token} />
    </ChatProvider>
  );
}
