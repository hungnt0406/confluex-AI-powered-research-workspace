"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";
import {
  ApiError,
  PaymentOrder,
  createPaymentOrder,
  fetchCreditBalance,
  fetchPaymentOrder,
  notifyCreditBalanceChanged,
  paymentOrderId,
} from "@/lib/api";

function formatVnd(amount: number) {
  return new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatCountdown(expiresAt: string) {
  const remainingMs = Math.max(0, Date.parse(expiresAt) - Date.now());
  const totalSeconds = Math.floor(remainingMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function orderBankAccount(order: PaymentOrder) {
  return order.sepay_va_account ?? order.account_number ?? order.bank_account ?? "Provided by Sepay";
}

function orderBankName(order: PaymentOrder) {
  return order.sepay_va_bank_bin ?? order.bank_bin ?? "Receiving bank";
}

export default function BillingCheckoutPage() {
  return (
    <Suspense
      fallback={
        <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
          Loading...
        </main>
      }
    >
      <BillingCheckoutClient />
    </Suspense>
  );
}

function BillingCheckoutClient() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const packId = searchParams.get("pack") ?? "";
  const requestedPackRef = useRef<string | null>(null);
  const [order, setOrder] = useState<PaymentOrder | null>(null);
  const [loading, setLoading] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [tick, setTick] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const qrUrl = order?.qr_url ?? order?.qr_payload ?? null;
  const orderId = order ? paymentOrderId(order) : "";
  const expired = Boolean(order && (order.status === "expired" || Date.now() >= Date.parse(order.expires_at)));
  const countdown = useMemo(() => (order ? formatCountdown(order.expires_at) : "0:00"), [order, tick]);

  useEffect(() => {
    if (ready && !token) {
      const next = `/billing/checkout${packId ? `?pack=${encodeURIComponent(packId)}` : ""}`;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [ready, token, router, packId]);

  useEffect(() => {
    const timer = window.setInterval(() => setTick((current) => current + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const generateOrder = useCallback(async () => {
    if (!token || !packId) return;
    setLoading(true);
    setError(null);
    setCopyState("idle");
    try {
      const nextOrder = await createPaymentOrder(packId, token);
      requestedPackRef.current = packId;
      setOrder(nextOrder);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to create a payment order.");
    } finally {
      setLoading(false);
    }
  }, [packId, token]);

  useEffect(() => {
    if (!token || !packId || requestedPackRef.current === packId) return;
    void generateOrder();
  }, [generateOrder, packId, token]);

  useEffect(() => {
    if (!token || !orderId || !order || order.status !== "pending" || expired) return;

    const poll = async () => {
      try {
        const nextOrder = await fetchPaymentOrder(orderId, token);
        setOrder(nextOrder);
        if (nextOrder.status === "paid") {
          notifyCreditBalanceChanged();
          const balance = await fetchCreditBalance(token).catch(() => null);
          const params = new URLSearchParams({ order: paymentOrderId(nextOrder) });
          if (balance) params.set("balance", String(balance.credit_balance));
          router.replace(`/billing/success?${params.toString()}`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to refresh payment status.");
      }
    };

    const intervalId = window.setInterval(() => void poll(), 3000);
    return () => window.clearInterval(intervalId);
  }, [expired, order, orderId, router, token]);

  const copyReference = async () => {
    if (!order?.reference_code) return;
    try {
      await navigator.clipboard.writeText(order.reference_code);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1600);
    } catch {
      setCopyState("failed");
    }
  };

  if (!ready || !token) {
    return (
      <main className="flex h-screen items-center justify-center text-sm uppercase tracking-[0.2em] text-hint">
        Loading...
      </main>
    );
  }

  if (!packId) {
    return (
      <main className="flex h-screen items-center justify-center bg-background px-5 text-on-surface">
        <div className="max-w-md rounded-2xl border border-outline/20 bg-surface-container-lowest p-6 text-center shadow-sm">
          <p className="font-headline text-2xl font-semibold">Choose a credit pack</p>
          <p className="mt-2 text-sm text-on-surface-variant">
            Checkout needs a pack so the backend can lock the VND amount.
          </p>
          <Link
            href="/billing"
            className="mt-5 inline-flex h-10 items-center rounded-full bg-primary px-5 text-xs font-semibold text-white no-underline"
          >
            Go to billing
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="h-screen overflow-y-auto bg-background px-5 py-6 font-ui text-on-surface">
      <div className="mx-auto max-w-5xl">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-hint">
              Sepay checkout
            </p>
            <h1 className="mt-1 font-headline text-3xl font-semibold">Top up credits</h1>
          </div>
          <Link
            href="/billing"
            className="inline-flex h-10 items-center rounded-full border border-outline/30 px-4 text-xs font-semibold text-primary no-underline hover:bg-primary/5"
          >
            Billing overview
          </Link>
        </header>

        {error && (
          <div className="mb-4 rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <section className="grid gap-4 lg:grid-cols-[390px_minmax(0,1fr)]">
          <div className="rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 shadow-sm">
            <div className="aspect-square rounded-2xl border border-outline/20 bg-white p-4">
              {loading && !order ? (
                <div className="flex h-full items-center justify-center text-xs uppercase tracking-[0.18em] text-hint">
                  Creating QR...
                </div>
              ) : qrUrl ? (
                <img
                  src={qrUrl}
                  alt={`Sepay QR code for order ${order?.reference_code ?? ""}`}
                  className="h-full w-full object-contain"
                />
              ) : (
                <div className="flex h-full items-center justify-center text-center text-sm text-on-surface-variant">
                  QR image will appear after the order is created.
                </div>
              )}
            </div>
            <div className="mt-4 flex items-center justify-between rounded-xl bg-secondary-container/50 px-4 py-3">
              <span className="text-xs text-secondary">Status</span>
              <span className="text-xs font-semibold capitalize text-primary">
                {order?.status ?? (loading ? "creating" : "not started")}
              </span>
            </div>
          </div>

          <div className="rounded-2xl border border-outline/20 bg-surface-container-lowest p-5 shadow-sm">
            {order ? (
              <div className="space-y-4">
                <div className="rounded-2xl bg-primary p-5 text-white">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-on-primary-container">
                    Transfer exactly
                  </p>
                  <p className="mt-2 font-headline text-5xl font-semibold leading-none">
                    {formatVnd(order.vnd_amount)}
                  </p>
                  <p className="mt-3 text-sm text-white/60">
                    The USD pack price is converted to VND when this order is created.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <InfoTile label="Bank" value={orderBankName(order)} />
                  <InfoTile label="Account" value={orderBankAccount(order)} />
                </div>

                <div className="rounded-2xl border border-outline/20 bg-surface-container-low p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-hint">
                        Transfer description
                      </p>
                      <p className="mt-2 font-mono text-2xl font-semibold tracking-[0.08em] text-primary">
                        {order.reference_code}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void copyReference()}
                      className="inline-flex h-10 items-center gap-2 rounded-full bg-primary px-4 text-xs font-semibold text-white hover:opacity-90"
                    >
                      <span className="material-symbols-outlined text-sm">content_copy</span>
                      {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
                    </button>
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-on-surface-variant">
                    Include this reference code in the bank transfer description so the webhook can match your payment.
                  </p>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-outline/20 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-primary">schedule</span>
                    <span className="text-sm font-semibold">
                      {expired ? "Order expired" : `Expires in ${countdown}`}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => void generateOrder()}
                    disabled={loading || (!expired && order.status === "pending")}
                    className="inline-flex h-9 items-center rounded-full border border-primary/30 px-4 text-xs font-semibold text-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {expired ? "Generate new order" : "Waiting for payment"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex min-h-[480px] flex-col items-center justify-center text-center">
                <p className="font-headline text-2xl font-semibold">Preparing checkout</p>
                <p className="mt-2 max-w-sm text-sm text-on-surface-variant">
                  We are creating a Sepay order and locking the VND amount for this pack.
                </p>
                <button
                  type="button"
                  onClick={() => void generateOrder()}
                  disabled={loading}
                  className="mt-5 inline-flex h-10 items-center rounded-full bg-primary px-5 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
                >
                  {loading ? "Creating..." : "Create order"}
                </button>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-outline/20 bg-surface-container-low px-4 py-3">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-hint">{label}</p>
      <p className="mt-2 break-words text-sm font-semibold text-on-surface">{value}</p>
    </div>
  );
}
