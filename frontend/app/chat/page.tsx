"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import Sidebar from "@/components/Sidebar";
import ContextPanel from "@/components/ContextPanel";
import ChatWorkspace from "@/components/ChatWorkspace";
import { ChatProvider, useChat } from "@/components/ChatProvider";
import OnboardingTour from "@/components/OnboardingTour";

export default function ChatPage() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    if (ready && !token) router.replace("/login");
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
      <div className="relative flex h-screen overflow-hidden w-full">
        <Sidebar open={sidebarOpen} onToggle={() => setSidebarOpen((v) => !v)} />
        <ChatWorkspace />
        <ContextPanel />
        <InsufficientCreditsCta />
        <OnboardingTour variant="chat" />
      </div>
    </ChatProvider>
  );
}

function InsufficientCreditsCta() {
  const { insufficientCredits, clearInsufficientCredits } = useChat();

  if (!insufficientCredits) return null;

  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-24 z-50 flex justify-center px-4">
      <div className="pointer-events-auto flex max-w-xl items-center gap-3 rounded-2xl border border-primary/20 bg-surface-container-lowest px-4 py-3 text-sm shadow-lg">
        <span className="material-symbols-outlined shrink-0 text-primary">bolt</span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-on-surface">{insufficientCredits.message}</p>
          <p className="mt-0.5 text-xs text-on-surface-variant">
            Add credits and retry the research step.
          </p>
        </div>
        <Link
          href={insufficientCredits.href}
          className="inline-flex h-9 shrink-0 items-center rounded-full bg-primary px-4 text-xs font-semibold text-white no-underline hover:opacity-90"
        >
          {insufficientCredits.ctaLabel}
        </Link>
        <button
          type="button"
          onClick={clearInsufficientCredits}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-on-surface-variant hover:bg-primary/5"
          aria-label="Dismiss insufficient credits notice"
        >
          <span className="material-symbols-outlined text-base">close</span>
        </button>
      </div>
    </div>
  );
}
