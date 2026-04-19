"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import Sidebar from "@/components/Sidebar";
import ContextPanel from "@/components/ContextPanel";
import ChatWorkspace from "@/components/ChatWorkspace";
import { ChatProvider } from "@/components/ChatProvider";

export default function ChatPage() {
  const { ready, token } = useAuth();
  const router = useRouter();

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
      <div className="flex h-screen overflow-hidden w-full">
        <Sidebar />
        <ChatWorkspace />
        <ContextPanel />
      </div>
    </ChatProvider>
  );
}
