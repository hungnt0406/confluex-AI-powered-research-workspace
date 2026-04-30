"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  AuthResponse,
  AuthUser,
  api,
  clearSession,
  loadToken,
  loadUser,
  saveSession,
} from "@/lib/api";

type AuthContextValue = {
  token: string | null;
  user: AuthUser | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (credential: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setToken(loadToken());
    setUser(loadUser());
    setReady(true);
  }, []);

  const handleAuth = useCallback(async (path: string, email: string, password: string) => {
    const response = await api<AuthResponse>(path, {
      method: "POST",
      json: { email, password },
    });
    saveSession(response.access_token, response.user);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const login = useCallback(
    (email: string, password: string) => handleAuth("/auth/login", email, password),
    [handleAuth],
  );
  const register = useCallback(
    (email: string, password: string) => handleAuth("/auth/register", email, password),
    [handleAuth],
  );

  const loginWithGoogle = useCallback(async (credential: string) => {
    const response = await api<AuthResponse>("/auth/google", {
      method: "POST",
      json: { credential },
    });
    saveSession(response.access_token, response.user);
    setToken(response.access_token);
    setUser(response.user);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setToken(null);
    setUser(null);
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ token, user, ready, login, register, loginWithGoogle, logout }),
    [token, user, ready, login, register, loginWithGoogle, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export { ApiError };
