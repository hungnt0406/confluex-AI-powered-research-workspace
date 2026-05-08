"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import {
  CreditBalance,
  CreditPack,
  fetchCreditBalance,
  fetchCreditPacks,
} from "@/lib/api";

const FALLBACK_PACKS: CreditPack[] = [
  { id: "student", name: "Student", credits: 800, usd_cents: 800 },
  { id: "pro", name: "Researcher Pro", credits: 2400, usd_cents: 2400, badge: "Most chosen" },
  { id: "lab_starter", name: "Lab Starter", credits: 6600, usd_cents: 6600 },
  { id: "topup_deep", name: "Deep Search top-up", credits: 800, usd_cents: 600 },
  { id: "topup_storage", name: "PDF upload credit bump", credits: 600, usd_cents: 400 },
];

function formatUsd(cents: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 === 0 ? 0 : 2,
  }).format(cents / 100);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function transactionLabel(kind: string, feature: string | null) {
  if (feature) return feature.replace(/_/g, " ");
  if (kind === "topup") return "credit top-up";
  if (kind === "grant") return "credit grant";
  if (kind === "consume") return "feature usage";
  return kind.replace(/_/g, " ");
}

export default function BillingPage() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [packs, setPacks] = useState<CreditPack[]>(FALLBACK_PACKS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && !token) {
      router.replace("/login?next=%2Fbilling");
    }
  }, [ready, token, router]);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [nextBalance, nextPacks] = await Promise.all([
        fetchCreditBalance(token),
        fetchCreditPacks(token).catch(() => FALLBACK_PACKS),
      ]);
      setBalance(nextBalance);
      setPacks(nextPacks.length > 0 ? nextPacks : FALLBACK_PACKS);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load billing.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
        Loading...
      </main>
    );
  }

  return (
    <main className="h-screen overflow-y-auto bg-background px-5 py-6 font-ui text-on-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-hint">
              Billing
            </p>
            <h1 className="mt-1 font-headline text-3xl font-semibold">Credits</h1>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/pricing"
              className="inline-flex h-10 items-center rounded-full border border-outline/30 px-4 text-xs font-semibold text-primary no-underline hover:bg-primary/5"
            >
              View pricing
            </Link>
            <Link
              href="/chat"
              className="inline-flex h-10 items-center rounded-full bg-primary px-4 text-xs font-semibold text-white no-underline hover:opacity-90"
            >
              Back to workspace
            </Link>
          </div>
        </header>

        {error && (
          <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 shadow-sm">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-secondary">
                  Available balance
                </p>
                <p className="mt-3 font-headline text-6xl font-semibold leading-none text-primary">
                  {loading
                    ? "..."
                    : balance?.is_unlimited
                      ? "Unlimited"
                      : (balance?.credit_balance ?? 0).toLocaleString("en-US")}
                </p>
                <p className="mt-2 text-sm text-on-surface-variant">
                  {balance?.is_unlimited
                    ? "Admin bypass is active; gated research work is not debited."
                    : "Credits are debited only when gated research work starts."}
                </p>
              </div>
              <Link
                href="/billing/checkout?pack=topup_deep"
                className="inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-white no-underline hover:opacity-90"
              >
                <span className="material-symbols-outlined text-base">add_card</span>
                Top up
              </Link>
            </div>
          </div>

          <div className="rounded-2xl border border-outline/20 bg-primary p-5 text-white shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-primary-container">
              Spend guide
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              {[
                ["Deep Search", "80"],
                ["Writer output", "40"],
                ["Paper chat", "2"],
                ["PDF upload", "5"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl bg-white/10 px-3 py-2">
                  <p className="text-white/55">{label}</p>
                  <p className="mt-1 font-semibold">{value} credits</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Top-up packs</h2>
              <span className="text-[11px] uppercase tracking-[0.16em] text-hint">USD shown, VND charged</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {packs.map((pack) => (
                <Link
                  key={pack.id}
                  href={`/billing/checkout?pack=${encodeURIComponent(pack.id)}`}
                  className="group rounded-xl border border-outline/20 bg-surface-container-low p-4 no-underline transition-colors hover:border-primary/35 hover:bg-secondary-container/40"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-on-surface">{pack.name}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">
                        {pack.credits.toLocaleString("en-US")} credits
                      </p>
                    </div>
                    {pack.badge && (
                      <span className="rounded-full bg-primary px-2 py-1 text-[10px] font-semibold text-white">
                        {pack.badge}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 flex items-end justify-between">
                    <span className="font-headline text-2xl font-semibold text-primary">
                      {formatUsd(pack.usd_cents)}
                    </span>
                    <span className="material-symbols-outlined text-primary transition-transform group-hover:translate-x-0.5">
                      arrow_forward
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>

          <div className="rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Recent transactions</h2>
              <button
                type="button"
                onClick={() => void refresh()}
                className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-xs font-semibold text-primary hover:bg-primary/5"
              >
                <span className="material-symbols-outlined text-sm">refresh</span>
                Refresh
              </button>
            </div>
            {loading ? (
              <p className="py-8 text-center text-xs uppercase tracking-[0.18em] text-hint">
                Loading ledger...
              </p>
            ) : balance?.recent_transactions.length ? (
              <div className="divide-y divide-outline/15">
                {balance.recent_transactions.map((transaction) => (
                  <div key={transaction.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-semibold capitalize text-on-surface">
                        {transactionLabel(transaction.kind, transaction.feature)}
                      </p>
                      <p className="mt-1 text-[11px] text-hint">{formatDate(transaction.created_at)}</p>
                    </div>
                    <div className="text-right">
                      <p
                        className={`text-sm font-semibold tabular-nums ${
                          transaction.delta >= 0 ? "text-emerald-700" : "text-on-surface"
                        }`}
                      >
                        {transaction.delta >= 0 ? "+" : ""}
                        {transaction.delta.toLocaleString("en-US")}
                      </p>
                      <p className="mt-1 text-[11px] text-hint">
                        {transaction.balance_after.toLocaleString("en-US")} left
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-outline/30 px-4 py-8 text-center">
                <p className="text-sm font-semibold">No ledger activity yet</p>
                <p className="mt-1 text-xs text-on-surface-variant">
                  Your signup grant and top-ups will appear here.
                </p>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
