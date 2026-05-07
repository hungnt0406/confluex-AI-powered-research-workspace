"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import { CreditBalance, fetchCreditBalance, notifyCreditBalanceChanged } from "@/lib/api";

export default function BillingSuccessPage() {
  return (
    <Suspense
      fallback={
        <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
          Loading...
        </main>
      }
    >
      <BillingSuccessClient />
    </Suspense>
  );
}

function BillingSuccessClient() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const balanceFromQuery = searchParams.get("balance");
  const orderId = searchParams.get("order");

  useEffect(() => {
    if (ready && !token) {
      router.replace("/login?next=%2Fbilling%2Fsuccess");
    }
  }, [ready, token, router]);

  useEffect(() => {
    if (!token) return;
    notifyCreditBalanceChanged();
    fetchCreditBalance(token)
      .then(setBalance)
      .catch(() => setBalance(null));
  }, [token]);

  const displayedBalance = balance?.credit_balance ?? (balanceFromQuery ? Number(balanceFromQuery) : null);

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
        Loading...
      </main>
    );
  }

  return (
    <main className="relative flex h-screen items-center justify-center overflow-hidden bg-background px-5 font-ui text-on-surface">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        {Array.from({ length: 24 }).map((_, index) => (
          <span
            key={index}
            className="absolute h-2 w-2 rounded-full bg-primary/40"
            style={{
              left: `${8 + ((index * 37) % 84)}%`,
              top: `${10 + ((index * 19) % 72)}%`,
              transform: `rotate(${index * 17}deg)`,
              opacity: index % 3 === 0 ? 0.55 : 0.28,
            }}
          />
        ))}
      </div>

      <section className="relative z-10 w-full max-w-lg rounded-3xl border border-outline/20 bg-surface-container-lowest p-8 text-center shadow-sm">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-secondary-container text-primary">
          <span className="material-symbols-outlined text-3xl">check_circle</span>
        </div>
        <p className="mt-5 text-[11px] font-bold uppercase tracking-[0.22em] text-hint">
          Payment confirmed
        </p>
        <h1 className="mt-2 font-headline text-4xl font-semibold">Credits added</h1>
        <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-on-surface-variant">
          Sepay confirmed the transfer and your workspace balance has been updated.
        </p>

        <div className="mt-6 rounded-2xl bg-primary px-5 py-5 text-white">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-on-primary-container">
            Current balance
          </p>
          <p className="mt-2 font-headline text-5xl font-semibold leading-none">
            {displayedBalance === null || Number.isNaN(displayedBalance)
              ? "Updated"
              : displayedBalance.toLocaleString("en-US")}
          </p>
          {displayedBalance !== null && !Number.isNaN(displayedBalance) && (
            <p className="mt-2 text-xs text-white/60">credits available</p>
          )}
        </div>

        {orderId && (
          <p className="mt-4 text-[11px] text-hint">
            Order {orderId}
          </p>
        )}

        <div className="mt-7 flex flex-col gap-2 sm:flex-row sm:justify-center">
          <Link
            href="/chat"
            className="inline-flex h-11 items-center justify-center rounded-full bg-primary px-5 text-sm font-semibold text-white no-underline hover:opacity-90"
          >
            Continue research
          </Link>
          <Link
            href="/billing"
            className="inline-flex h-11 items-center justify-center rounded-full border border-outline/30 px-5 text-sm font-semibold text-primary no-underline hover:bg-primary/5"
          >
            View ledger
          </Link>
        </div>
      </section>
    </main>
  );
}
