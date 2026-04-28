"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  AdminAccess,
  AdminTokenUsage,
  AdminUsageProjectRow,
  AdminUsageUserRow,
  ApiError,
  TokenUsageBreakdownRow,
  TokenUsageDailyRow,
  api,
} from "@/lib/api";

type RangeKey = "7" | "30" | "all";

const RANGE_OPTIONS: { key: RangeKey; label: string }[] = [
  { key: "7", label: "7 days" },
  { key: "30", label: "30 days" },
  { key: "all", label: "All time" },
];

export default function AdminUsagePage() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const [accessLoading, setAccessLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [usage, setUsage] = useState<AdminTokenUsage | null>(null);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<RangeKey>("30");
  const [userFilter, setUserFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [knownUsers, setKnownUsers] = useState<AdminUsageUserRow[]>([]);
  const [knownProjects, setKnownProjects] = useState<AdminUsageProjectRow[]>([]);

  useEffect(() => {
    if (ready && !token) router.replace("/login");
  }, [ready, token, router]);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    setAccessLoading(true);
    api<AdminAccess>("/admin/access", { token })
      .then((response) => {
        if (cancelled) return;
        setIsAdmin(response.is_admin);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setIsAdmin(false);
        setError(err instanceof Error ? err.message : "Failed to verify admin access.");
      })
      .finally(() => {
        if (!cancelled) setAccessLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const loadUsage = useCallback(async () => {
    if (!token) return;

    const dates = getRangeDates(range);
    const params = new URLSearchParams();
    if (dates.dateFrom) params.set("date_from", dates.dateFrom);
    if (dates.dateTo) params.set("date_to", dates.dateTo);
    if (userFilter) params.set("user_id", userFilter);
    if (projectFilter) params.set("project_id", projectFilter);

    setLoadingUsage(true);
    setError(null);
    try {
      const nextUsage = await api<AdminTokenUsage>(
        `/admin/token-usage${params.size ? `?${params.toString()}` : ""}`,
        { token },
      );
      setUsage(nextUsage);
      setKnownUsers((current) => mergeUsers(current, nextUsage.by_user));
      setKnownProjects((current) => mergeProjects(current, nextUsage.by_project));
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setIsAdmin(false);
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load token usage.");
    } finally {
      setLoadingUsage(false);
    }
  }, [projectFilter, range, token, userFilter]);

  useEffect(() => {
    if (!token || accessLoading || !isAdmin) return;
    void loadUsage();
  }, [accessLoading, isAdmin, loadUsage, token]);

  const rangeLabel = useMemo(() => {
    if (!usage?.date_from && !usage?.date_to) return "All time";
    if (usage.date_from && usage.date_to) return `${formatDate(usage.date_from)} - ${formatDate(usage.date_to)}`;
    return usage.date_from ? `From ${formatDate(usage.date_from)}` : `Until ${formatDate(usage.date_to ?? "")}`;
  }, [usage]);

  if (!ready || !token || accessLoading) {
    return <PageState label="Loading admin console" icon="hourglass_top" />;
  }

  if (!isAdmin) {
    return (
      <main className="flex h-screen items-center justify-center bg-background p-6 font-ui">
        <section className="w-full max-w-md rounded-xl border border-outline/20 bg-surface-container-lowest p-6">
          <div className="flex items-center gap-2 text-error">
            <span className="material-symbols-outlined" style={{ fontSize: "20px" }}>
              lock
            </span>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em]">403</p>
          </div>
          <h1 className="mt-3 font-headline text-2xl text-on-surface">Admin access required</h1>
          <p className="mt-2 text-sm leading-6 text-secondary">
            Your account is not allowlisted for usage monitoring.
          </p>
          <Link
            href="/chat"
            className="mt-5 inline-flex h-9 items-center gap-2 rounded-lg border border-outline/25 bg-background px-3 text-xs font-medium text-on-surface transition-colors hover:border-primary/35 hover:bg-primary/5"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              arrow_back
            </span>
            Back to chat
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="h-screen overflow-y-auto bg-background font-ui text-on-surface custom-scrollbar">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6">
        <header className="flex flex-col gap-4 border-b border-outline/20 pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <ConfluexMark />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-headline text-3xl leading-tight text-primary">
                  Token Usage Monitor
                </h1>
                <span className="rounded-full border border-accent/20 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
                  Admin
                </span>
              </div>
              <p className="mt-1 text-xs text-hint">{rangeLabel}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void loadUsage()}
              disabled={loadingUsage}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-outline/25 bg-surface-container-lowest text-on-surface-variant transition-colors hover:border-primary/35 hover:bg-primary/5 disabled:opacity-50"
              aria-label="Refresh usage"
              title="Refresh usage"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
                refresh
              </span>
            </button>
            <Link
              href="/chat"
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-outline/25 bg-surface-container-lowest px-3 text-xs font-medium text-on-surface transition-colors hover:border-primary/35 hover:bg-primary/5"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                arrow_back
              </span>
              Back to chat
            </Link>
          </div>
        </header>

        <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
          <div className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]">
            <div className="flex rounded-lg border border-outline/20 bg-surface-container-low p-1">
              {RANGE_OPTIONS.map((option) => (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setRange(option.key)}
                  className={`h-8 rounded-md px-3 text-[11px] font-semibold uppercase tracking-[0.12em] transition-colors ${
                    range === option.key
                      ? "bg-primary text-on-primary"
                      : "text-secondary hover:bg-primary/10 hover:text-primary"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <label className="min-w-0">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-hint">
                User filter
              </span>
              <select
                value={userFilter}
                onChange={(event) => setUserFilter(event.target.value)}
                className="h-9 w-full rounded-lg border border-outline/25 bg-background px-3 text-xs text-on-surface outline-none transition-colors focus:border-primary/50"
              >
                <option value="">All users</option>
                {knownUsers.map((user) => (
                  <option key={user.user_id} value={user.user_id}>
                    {user.user_email}
                  </option>
                ))}
              </select>
            </label>
            <label className="min-w-0">
              <span className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-hint">
                Project filter
              </span>
              <select
                value={projectFilter}
                onChange={(event) => setProjectFilter(event.target.value)}
                className="h-9 w-full rounded-lg border border-outline/25 bg-background px-3 text-xs text-on-surface outline-none transition-colors focus:border-primary/50"
              >
                <option value="">All projects</option>
                {knownProjects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.project_title} - {project.user_email}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </section>

        {error && (
          <div className="rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        {loadingUsage && !usage ? (
          <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-8 text-center text-sm text-hint">
            Loading usage data...
          </section>
        ) : usage && usage.request_count === 0 ? (
          <EmptyUsageState />
        ) : usage ? (
          <>
            <KpiGrid usage={usage} />
            <section className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
              <DailyTrend rows={usage.by_day} />
              <BreakdownPanel title="Usage by feature" rows={usage.by_feature} />
              <BreakdownPanel title="Usage by model" rows={usage.by_model} />
            </section>
            <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
              <ProjectTable rows={usage.by_project} />
              <RecentEventsTable rows={usage.recent_events} />
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}

function PageState({ label, icon }: { label: string; icon: string }) {
  return (
    <main className="flex h-screen items-center justify-center bg-background text-hint">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em]">
        <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
          {icon}
        </span>
        {label}
      </div>
    </main>
  );
}

function ConfluexMark() {
  return (
    <div className="flex items-center gap-2">
      <svg
        viewBox="0 0 62 60"
        width={28}
        height={28}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {[
          "M 4,50 C 8,35 18,15 32,6",
          "M 9,52 C 13,36 24,16 39,7",
          "M 14,53 C 19,37 30,17 45,8",
          "M 19,54 C 25,38 36,18 51,9",
          "M 24,55 C 30,39 42,19 56,10",
          "M 29,55 C 36,40 47,21 58,14",
          "M 33,54 C 40,41 51,24 58,20",
          "M 37,53 C 43,42 53,27 57,26",
          "M 40,52 C 45,43 53,31 56,32",
        ].map((d, i) => (
          <path key={i} d={d} stroke="#7BAD8A" strokeWidth="1.6" strokeLinecap="round" />
        ))}
      </svg>
      <span className="text-sm font-semibold text-accent">confluex</span>
    </div>
  );
}

function KpiGrid({ usage }: { usage: AdminTokenUsage }) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <KpiCard label="Total tokens" value={formatInteger(usage.total_tokens)} />
      <KpiCard label="Credits used" value={formatCredits(usage.cost_credits)} />
      <KpiCard label="Requests" value={formatInteger(usage.request_count)} />
      <KpiCard label="Prompt tokens" value={formatInteger(usage.prompt_tokens)} />
      <KpiCard label="Completion tokens" value={formatInteger(usage.completion_tokens)} />
      <KpiCard label="Cached tokens" value={formatInteger(usage.cached_tokens)} />
    </section>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-hint">{label}</p>
      <p className="mt-2 text-xl font-semibold tabular-nums text-primary">{value}</p>
    </div>
  );
}

function DailyTrend({ rows }: { rows: TokenUsageDailyRow[] }) {
  const maxTokens = Math.max(...rows.map((row) => row.total_tokens), 1);
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title="Daily usage trend" />
      <div className="mt-4 flex h-44 items-end gap-1 border-b border-outline/20 pb-2">
        {rows.length === 0 ? (
          <p className="m-auto text-xs text-hint">No daily usage in this range.</p>
        ) : (
          rows.map((row) => (
            <div key={row.day} className="flex min-w-4 flex-1 flex-col items-center gap-1">
              <div
                className="w-full rounded-t bg-primary/80"
                style={{ height: `${Math.max((row.total_tokens / maxTokens) * 100, 5)}%` }}
                title={`${formatDate(row.day)}: ${formatInteger(row.total_tokens)} tokens`}
              />
            </div>
          ))
        )}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-hint">
        <span>{rows[0] ? formatDate(rows[0].day) : "-"}</span>
        <span>{rows[rows.length - 1] ? formatDate(rows[rows.length - 1].day) : "-"}</span>
      </div>
    </section>
  );
}

function BreakdownPanel({ title, rows }: { title: string; rows: TokenUsageBreakdownRow[] }) {
  const maxTokens = Math.max(...rows.map((row) => row.total_tokens), 1);
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title={title} />
      <div className="mt-4 space-y-3">
        {rows.length === 0 ? (
          <p className="text-xs text-hint">No usage yet.</p>
        ) : (
          rows.slice(0, 8).map((row) => (
            <div key={row.key}>
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="truncate font-medium text-on-surface">{formatLabel(row.key)}</span>
                <span className="tabular-nums text-hint">{formatInteger(row.total_tokens)}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-surface-container">
                <div
                  className="h-1.5 rounded-full bg-accent"
                  style={{ width: `${Math.max((row.total_tokens / maxTokens) * 100, 4)}%` }}
                />
              </div>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function ProjectTable({ rows }: { rows: AdminUsageProjectRow[] }) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title="Project drilldown" />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[620px] text-left text-xs">
          <thead className="border-b border-outline/20 text-[10px] uppercase tracking-[0.14em] text-hint">
            <tr>
              <th className="py-2 pr-3 font-semibold">Project</th>
              <th className="py-2 pr-3 font-semibold">User</th>
              <th className="py-2 pr-3 text-right font-semibold">Requests</th>
              <th className="py-2 pr-3 text-right font-semibold">Tokens</th>
              <th className="py-2 text-right font-semibold">Credits</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline/10">
            {rows.slice(0, 12).map((row) => (
              <tr key={row.project_id}>
                <td className="py-2 pr-3">
                  <p className="max-w-52 truncate font-medium text-on-surface">{row.project_title}</p>
                </td>
                <td className="py-2 pr-3 text-secondary">{row.user_email}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatInteger(row.request_count)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatInteger(row.total_tokens)}</td>
                <td className="py-2 text-right tabular-nums">{formatCredits(row.cost_credits)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecentEventsTable({ rows }: { rows: AdminTokenUsage["recent_events"] }) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title="Recent events" />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-xs">
          <thead className="border-b border-outline/20 text-[10px] uppercase tracking-[0.14em] text-hint">
            <tr>
              <th className="py-2 pr-3 font-semibold">Time</th>
              <th className="py-2 pr-3 font-semibold">User</th>
              <th className="py-2 pr-3 font-semibold">Project</th>
              <th className="py-2 pr-3 font-semibold">Feature</th>
              <th className="py-2 pr-3 font-semibold">Model</th>
              <th className="py-2 pr-3 text-right font-semibold">Tokens</th>
              <th className="py-2 text-right font-semibold">Credits</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline/10">
            {rows.map((row) => (
              <tr key={row.id}>
                <td className="py-2 pr-3 whitespace-nowrap text-hint">{formatDateTime(row.created_at)}</td>
                <td className="py-2 pr-3 text-secondary">{row.user_email}</td>
                <td className="py-2 pr-3">
                  <p className="max-w-40 truncate">{row.project_title}</p>
                </td>
                <td className="py-2 pr-3">{formatLabel(row.feature)}</td>
                <td className="py-2 pr-3 text-hint">
                  <p className="max-w-36 truncate">{row.model ?? "unknown"}</p>
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{formatInteger(row.total_tokens)}</td>
                <td className="py-2 text-right tabular-nums">{formatCredits(row.cost_credits)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EmptyUsageState() {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-8 text-center">
      <span className="material-symbols-outlined text-hint" style={{ fontSize: "28px" }}>
        monitoring
      </span>
      <h2 className="mt-3 text-sm font-semibold text-on-surface">No usage data</h2>
      <p className="mt-1 text-xs text-hint">No provider-reported token events match the current filters.</p>
    </section>
  );
}

function PanelTitle({ title }: { title: string }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">
      {title}
    </h2>
  );
}

function getRangeDates(range: RangeKey) {
  if (range === "all") return { dateFrom: null, dateTo: null };
  const dateTo = new Date();
  const dateFrom = new Date(dateTo);
  dateFrom.setDate(dateTo.getDate() - Number(range) + 1);
  return {
    dateFrom: toIsoDate(dateFrom),
    dateTo: toIsoDate(dateTo),
  };
}

function mergeUsers(current: AdminUsageUserRow[], incoming: AdminUsageUserRow[]) {
  const byId = new Map(current.map((user) => [user.user_id, user]));
  for (const user of incoming) byId.set(user.user_id, user);
  return Array.from(byId.values()).sort((left, right) =>
    left.user_email.localeCompare(right.user_email),
  );
}

function mergeProjects(current: AdminUsageProjectRow[], incoming: AdminUsageProjectRow[]) {
  const byId = new Map(current.map((project) => [project.project_id, project]));
  for (const project of incoming) byId.set(project.project_id, project);
  return Array.from(byId.values()).sort((left, right) =>
    left.project_title.localeCompare(right.project_title),
  );
}

function toIsoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatCredits(value: number | null) {
  if (value === null) return "-";
  return value.toLocaleString("en-US", { maximumFractionDigits: 5 });
}

function formatDate(value: string) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
