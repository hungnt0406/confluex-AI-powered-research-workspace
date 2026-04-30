"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { ApiError } from "@/lib/api";
import Logo from "@/components/Logo";

export default function LoginPage() {
  const { login, register, loginWithGoogle } = useAuth();
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

  const handleGoogleLogin = useCallback(
    async (credential: string) => {
      setBusy(true);
      setError(null);
      try {
        await loginWithGoogle(credential);
        router.replace("/chat");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Google sign-in failed.");
      } finally {
        setBusy(false);
      }
    },
    [loginWithGoogle, router],
  );

  return (
    <main className="flex h-screen items-center justify-center bg-background px-6 font-ui text-on-surface">
      <form
        onSubmit={submit}
        className="w-full max-w-sm bg-surface-container-low border border-outline/30 rounded-2xl p-8 shadow-sm space-y-6"
      >
        <div className="text-center space-y-2">
          <div className="flex justify-center">
            <Logo size="lg" />
          </div>
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

        {/* Divider */}
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-outline/30" />
          </div>
          <div className="relative flex justify-center text-xs">
            <span className="bg-surface-container-low px-3 text-hint">or continue with</span>
          </div>
        </div>

        {/* Google Sign-In */}
        <GoogleSignInButton onSuccess={handleGoogleLogin} disabled={busy} />

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

function GoogleSignInButton({
  onSuccess,
  disabled,
}: {
  onSuccess: (credential: string) => Promise<void>;
  disabled?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const callbackRef = useRef(onSuccess);
  callbackRef.current = onSuccess;

  useEffect(() => {
    if (!containerRef.current) return;

    const el = containerRef.current;
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    if (!clientId) return;

    const tryRender = () => {
      if (!window.google?.accounts?.id) return false;

      window.google.accounts.id.initialize({
        client_id: clientId,
        callback: (response) => {
          void callbackRef.current(response.credential);
        },
      });

      window.google.accounts.id.renderButton(el, {
        theme: "outline",
        size: "large",
        width: 300,
        text: "signin_with",
        shape: "pill",
      });

      return true;
    };

    // GIS script may not have loaded yet — poll briefly.
    if (tryRender()) return;
    const timer = setInterval(() => {
      if (tryRender()) clearInterval(timer);
    }, 200);

    return () => clearInterval(timer);
  }, []);

  return (
    <div
      ref={containerRef}
      className={`flex justify-center ${disabled ? "pointer-events-none opacity-50" : ""}`}
    />
  );
}
