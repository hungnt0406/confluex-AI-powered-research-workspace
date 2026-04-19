"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, register } = useAuth();
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await register(email, password);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex h-screen items-center justify-center bg-background px-6">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-surface-container-low border border-outline/30 rounded-2xl p-8 shadow-sm space-y-6"
      >
        <div className="text-center space-y-2">
          <h1 className="font-headline text-3xl font-medium">Confluex</h1>
          <p className="text-sm text-secondary">
            {mode === "login" ? "Sign in to your research workspace." : "Create a new research account."}
          </p>
        </div>

        <div className="space-y-3">
          <label className="block">
            <span className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">
              Email
            </span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-outline/40 bg-surface-container-lowest px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </label>
          <label className="block">
            <span className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">
              Password
            </span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-outline/40 bg-surface-container-lowest px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </label>
        </div>

        {error && <p className="text-xs text-error">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-primary text-white rounded-lg py-2.5 text-sm font-medium disabled:opacity-40"
        >
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="w-full text-xs text-secondary hover:text-primary"
        >
          {mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
