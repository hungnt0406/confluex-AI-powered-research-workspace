"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function Home() {
  const { ready, token } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    router.replace(token ? "/chat" : "/login");
  }, [ready, token, router]);
  return (
    <main className="flex h-screen items-center justify-center text-hint text-sm uppercase tracking-[0.2em]">
      Loading…
    </main>
  );
}
