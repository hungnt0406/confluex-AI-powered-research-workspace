"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "@/components/AuthProvider";
import {
  AdminAccess,
  AdminTokenUsage,
  AdminUsageProjectRow,
  AdminUsageUserRow,
  TokenUsageBreakdownRow,
  TokenUsageDailyRow,
  api,
} from "@/lib/api";

export type PresetRangeKey = "7" | "30" | "all";
export type RangeKey = PresetRangeKey | `custom:${string}:${string}`;

export const ADMIN_USAGE_DASHBOARD_PATH = "/admin/usage";
export const ADMIN_USAGE_USERS_PATH = "/admin/usage/users";

export const RANGE_OPTIONS: { key: PresetRangeKey; label: string }[] = [
  { key: "7", label: "7 days" },
  { key: "30", label: "30 days" },
  { key: "all", label: "All time" },
];

const CALENDAR_WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

const ADMIN_SECTIONS = [
  {
    href: ADMIN_USAGE_DASHBOARD_PATH,
    label: "Usage Dashboard",
    icon: "dashboard",
  },
  {
    href: ADMIN_USAGE_USERS_PATH,
    label: "User Analysis",
    icon: "group",
  },
];

export function useAdminAccess() {
  const { ready, token } = useAuth();
  const router = useRouter();
  const [accessLoading, setAccessLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);
  const [accessError, setAccessError] = useState<string | null>(null);

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
        setAccessError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setIsAdmin(false);
        setAccessError(err instanceof Error ? err.message : "Failed to verify admin access.");
      })
      .finally(() => {
        if (!cancelled) setAccessLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return {
    ready,
    token,
    accessLoading,
    isAdmin,
    accessError,
    setIsAdmin,
  };
}

export function AdminUsageLayout({
  activeHref,
  children,
}: {
  activeHref: string;
  children: ReactNode;
}) {
  return (
    <main className="flex h-screen bg-background font-ui text-on-surface">
      <AdminSidebar activeHref={activeHref} />
      <div className="min-w-0 flex-1 overflow-y-auto custom-scrollbar">
        <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6">
          <MobileAdminNav activeHref={activeHref} />
          {children}
        </div>
      </div>
    </main>
  );
}

export function UsagePageHeader({
  title,
  rangeLabel,
  children,
}: {
  title: string;
  rangeLabel: string;
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-outline/20 pb-4 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <h1 className="font-headline text-3xl leading-tight text-primary">{title}</h1>
        <p className="mt-1 text-xs text-hint">{rangeLabel}</p>
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2">{children}</div> : null}
    </header>
  );
}

export function PageState({ label, icon }: { label: string; icon: string }) {
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

export function ForbiddenAdminState() {
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

export function DateRangeSelect({
  range,
  onChange,
}: {
  range: RangeKey;
  onChange: (range: RangeKey) => void;
}) {
  const labelId = useId();
  const selectedDates = useMemo(() => getRangeDates(range), [range]);
  const [open, setOpen] = useState(false);
  const [pendingStart, setPendingStart] = useState<string | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() =>
    startOfMonth(getCalendarAnchorDate(selectedDates)),
  );
  const calendarDays = useMemo(() => buildCalendarDays(calendarMonth), [calendarMonth]);

  useEffect(() => {
    if (open) return;
    setPendingStart(null);
    setCalendarMonth(startOfMonth(getCalendarAnchorDate(selectedDates)));
  }, [open, selectedDates.dateFrom, selectedDates.dateTo]);

  const applyPreset = useCallback(
    (preset: PresetRangeKey) => {
      setPendingStart(null);
      setOpen(false);
      onChange(preset);
    },
    [onChange],
  );

  const applySingleDay = useCallback(
    (day: string) => {
      setPendingStart(null);
      setOpen(false);
      onChange(buildCustomRange(day, day));
    },
    [onChange],
  );

  const handleDayClick = useCallback(
    (day: string) => {
      if (!pendingStart) {
        setPendingStart(day);
        return;
      }

      setPendingStart(null);
      setOpen(false);
      onChange(buildCustomRange(pendingStart, day));
    },
    [onChange, pendingStart],
  );

  return (
    <div
      className="relative min-w-0"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
      }}
    >
      <span
        id={labelId}
        className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-hint"
      >
        Date range
      </span>
      <button
        type="button"
        aria-labelledby={labelId}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-outline/25 bg-background px-3 text-left text-xs text-on-surface outline-none transition-colors hover:border-primary/35 focus:border-primary/50"
      >
        <span className="truncate">{getRangeLabel(range)}</span>
        <span className="material-symbols-outlined flex-shrink-0" style={{ fontSize: "18px" }}>
          expand_more
        </span>
      </button>

      {open ? (
        <div
          role="dialog"
          aria-labelledby={labelId}
          className="absolute right-0 z-30 mt-1 w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-outline/25 bg-surface-container-lowest p-3 shadow-lg"
        >
          <div className="grid grid-cols-3 gap-2">
            {RANGE_OPTIONS.map((option) => {
              const active = range === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => applyPreset(option.key)}
                  className={`h-8 rounded-lg border px-2 text-xs font-medium transition-colors ${
                    active
                      ? "border-primary/35 bg-primary/10 text-primary"
                      : "border-outline/20 text-on-surface-variant hover:border-primary/35 hover:bg-primary/5"
                  }`}
                >
                  {option.label}
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setCalendarMonth((month) => addMonths(month, -1))}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-primary/5 hover:text-primary"
              aria-label="Previous month"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
                chevron_left
              </span>
            </button>
            <p className="text-xs font-semibold text-on-surface">
              {formatCalendarMonth(calendarMonth)}
            </p>
            <button
              type="button"
              onClick={() => setCalendarMonth((month) => addMonths(month, 1))}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-on-surface-variant transition-colors hover:bg-primary/5 hover:text-primary"
              aria-label="Next month"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
                chevron_right
              </span>
            </button>
          </div>

          <div className="mt-2 grid grid-cols-7 gap-1 text-center text-[10px] font-semibold uppercase text-hint">
            {CALENDAR_WEEKDAYS.map((weekday, index) => (
              <span key={`${weekday}-${index}`} className="py-1">
                {weekday}
              </span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day) => {
              const dayKey = toIsoDate(day);
              const inMonth = isSameMonth(day, calendarMonth);
              const selected = isDateInRange(dayKey, selectedDates.dateFrom, selectedDates.dateTo);
              const pending = pendingStart === dayKey;
              return (
                <button
                  key={dayKey}
                  type="button"
                  onClick={() => handleDayClick(dayKey)}
                  onDoubleClick={() => applySingleDay(dayKey)}
                  aria-label={formatDate(dayKey)}
                  className={`aspect-square rounded-lg text-xs tabular-nums transition-colors ${
                    pending
                      ? "bg-accent text-on-primary"
                      : selected
                        ? "bg-primary/10 font-semibold text-primary"
                      : inMonth
                        ? "text-on-surface hover:bg-primary/5"
                        : "text-hint/55 hover:bg-primary/5"
                  }`}
                  aria-pressed={selected || pending}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function UserSelect({
  users,
  value,
  disabled,
  onChange,
}: {
  users: AdminUsageUserRow[];
  value: string;
  disabled?: boolean;
  onChange: (userId: string) => void;
}) {
  const inputId = useId();
  const listboxId = `${inputId}-listbox`;
  const selectedUser = useMemo(
    () => users.find((user) => user.user_id === value) ?? null,
    [users, value],
  );
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const filteredUsers = useMemo(() => filterUsersBySearch(users, query), [query, users]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const activeUser = activeIndex >= 0 ? filteredUsers[activeIndex] ?? null : null;
  const activeOptionId =
    open && activeUser ? getUserOptionId(inputId, activeIndex) : undefined;

  useEffect(() => {
    setQuery(selectedUser?.user_email ?? "");
  }, [selectedUser?.user_email]);

  useEffect(() => {
    if (!open) {
      setActiveIndex(-1);
      return;
    }

    setActiveIndex((currentIndex) => {
      if (filteredUsers.length === 0) return -1;
      if (currentIndex >= 0 && currentIndex < filteredUsers.length) return currentIndex;
      return getInitialActiveUserIndex(filteredUsers, value);
    });
  }, [filteredUsers, open, value]);

  const selectUser = useCallback(
    (user: AdminUsageUserRow) => {
      setQuery(user.user_email);
      setOpen(false);
      setActiveIndex(-1);
      if (user.user_id !== value) onChange(user.user_id);
    },
    [onChange, value],
  );

  const restoreSelectedQuery = useCallback(() => {
    setQuery(selectedUser?.user_email ?? "");
    setOpen(false);
    setActiveIndex(-1);
  }, [selectedUser?.user_email]);

  const closeListbox = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
  }, []);

  const commitQuery = useCallback(() => {
    if (open && activeUser) {
      selectUser(activeUser);
      return;
    }

    const exactMatch = users.find(
      (user) =>
        user.user_email.toLowerCase() === query.trim().toLowerCase() ||
        user.user_id.toLowerCase() === query.trim().toLowerCase(),
    );
    const nextUser = exactMatch ?? (filteredUsers.length === 1 ? filteredUsers[0] : null);
    if (nextUser) {
      selectUser(nextUser);
      return;
    }
    closeListbox();
  }, [activeUser, closeListbox, filteredUsers, open, query, selectUser, users]);

  return (
    <div
      className="relative min-w-0"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) closeListbox();
      }}
    >
      <label
        htmlFor={inputId}
        className="mb-1 block text-[10px] font-semibold uppercase tracking-[0.16em] text-hint"
      >
        User
      </label>
      <div className="relative">
        <span
          className="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-hint"
          style={{ fontSize: "16px" }}
        >
          search
        </span>
        <input
          id={inputId}
          type="search"
          value={query}
          role="combobox"
          aria-controls={listboxId}
          aria-expanded={open && !disabled}
          aria-autocomplete="list"
          aria-activedescendant={activeOptionId}
          aria-haspopup="listbox"
          aria-label="Search users"
          autoComplete="off"
          disabled={disabled}
          placeholder={users.length === 0 ? "No users" : "Search by email or user ID"}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            setActiveIndex(0);
          }}
          onFocus={() => {
            setOpen(true);
            setActiveIndex((currentIndex) =>
              currentIndex >= 0 ? currentIndex : getInitialActiveUserIndex(filteredUsers, value),
            );
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpen(true);
              setActiveIndex((currentIndex) => getNextUserIndex(filteredUsers, currentIndex));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setOpen(true);
              setActiveIndex((currentIndex) => getPreviousUserIndex(filteredUsers, currentIndex));
            }
            if (event.key === "Enter") {
              event.preventDefault();
              commitQuery();
            }
            if (event.key === "Escape") {
              event.preventDefault();
              restoreSelectedQuery();
            }
          }}
          className="h-9 w-full rounded-lg border border-outline/25 bg-background pl-9 pr-3 text-xs text-on-surface outline-none transition-colors focus:border-primary/50 disabled:opacity-50"
        />
      </div>
      {open && !disabled ? (
        <div
          id={listboxId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-outline/25 bg-surface-container-lowest p-1 shadow-lg"
        >
          {filteredUsers.length === 0 ? (
            <p className="px-3 py-2 text-xs text-hint">No matching users</p>
          ) : (
            filteredUsers.map((user, index) => {
              const selected = user.user_id === value;
              const active = index === activeIndex;
              return (
                <div
                  key={user.user_id}
                  id={getUserOptionId(inputId, index)}
                  role="option"
                  aria-selected={selected}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    selectUser(user);
                  }}
                  onMouseEnter={() => setActiveIndex(index)}
                  className={`flex w-full min-w-0 items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-xs transition-colors ${
                    selected
                      ? "bg-primary/10 text-primary"
                      : active
                        ? "bg-primary/5 text-on-surface"
                      : "text-on-surface hover:bg-primary/5"
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{user.user_email}</span>
                    <span className="block truncate text-[10px] text-hint">{user.user_id}</span>
                  </span>
                  <span className="flex-shrink-0 tabular-nums text-hint">
                    {formatCompactInteger(user.total_tokens)}
                  </span>
                </div>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

function filterUsersBySearch(users: AdminUsageUserRow[], query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return users.slice(0, 20);

  return users
    .filter((user) => {
      const email = user.user_email.toLowerCase();
      const id = user.user_id.toLowerCase();
      return email.includes(normalizedQuery) || id.includes(normalizedQuery);
    })
    .slice(0, 20);
}

function getInitialActiveUserIndex(users: AdminUsageUserRow[], selectedUserId: string) {
  if (users.length === 0) return -1;
  const selectedIndex = users.findIndex((user) => user.user_id === selectedUserId);
  return selectedIndex >= 0 ? selectedIndex : 0;
}

function getNextUserIndex(users: AdminUsageUserRow[], currentIndex: number) {
  if (users.length === 0) return -1;
  if (currentIndex < 0) return 0;
  return currentIndex >= users.length - 1 ? 0 : currentIndex + 1;
}

function getPreviousUserIndex(users: AdminUsageUserRow[], currentIndex: number) {
  if (users.length === 0) return -1;
  if (currentIndex <= 0) return users.length - 1;
  return currentIndex - 1;
}

function getUserOptionId(inputId: string, index: number) {
  return `${inputId}-option-${index}`;
}

export function RefreshButton({
  loading,
  onRefresh,
}: {
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRefresh}
      disabled={loading}
      className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-outline/25 bg-surface-container-lowest text-on-surface-variant transition-colors hover:border-primary/35 hover:bg-primary/5 disabled:opacity-50"
      aria-label="Refresh usage"
      title="Refresh usage"
    >
      <span className="material-symbols-outlined" style={{ fontSize: "18px" }}>
        refresh
      </span>
    </button>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
      {message}
    </div>
  );
}

export function LoadingUsageState({ label = "Loading usage data..." }: { label?: string }) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-8 text-center text-sm text-hint">
      {label}
    </section>
  );
}

export function EmptyUsageState({
  description = "No provider-reported token events match the current range.",
}: {
  description?: string;
}) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-8 text-center">
      <span className="material-symbols-outlined text-hint" style={{ fontSize: "28px" }}>
        monitoring
      </span>
      <h2 className="mt-3 text-sm font-semibold text-on-surface">No usage data</h2>
      <p className="mt-1 text-xs text-hint">{description}</p>
    </section>
  );
}

export function KpiGrid({ usage }: { usage: AdminTokenUsage }) {
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

export function DailyTrend({
  rows,
  title = "Daily usage trend",
  mode = "rows",
}: {
  rows: TokenUsageDailyRow[];
  title?: string;
  mode?: "last7" | "rows";
}) {
  const displayRows = useMemo(
    () => (mode === "last7" ? buildLastSevenDailyRows(rows) : rows),
    [mode, rows],
  );
  const maxTokens = Math.max(...displayRows.map((row) => row.total_tokens), 1);
  const hasUsage = displayRows.some((row) => row.total_tokens > 0);
  const chartWidth = 640;
  const chartHeight = 180;
  const chartTop = 22;
  const chartBottom = 142;
  const chartLeft = 18;
  const chartRight = chartWidth - 18;
  const xStep = displayRows.length > 1 ? (chartRight - chartLeft) / (displayRows.length - 1) : 0;
  const points = displayRows.map((row, index) => {
    const x = chartLeft + index * xStep;
    const y = chartBottom - (row.total_tokens / maxTokens) * (chartBottom - chartTop);
    return { ...row, x, y };
  });
  const linePoints = points.map((point) => `${point.x},${point.y}`).join(" ");
  const firstPoint = points[0];
  const lastPoint = points[points.length - 1];
  const areaPoints = firstPoint && lastPoint
    ? `${firstPoint.x},${chartBottom} ${linePoints} ${lastPoint.x},${chartBottom}`
    : "";

  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title={title} />
      <div className="mt-4 h-52 border-b border-outline/20 pb-2">
        {!hasUsage ? (
          <div className="flex h-full items-center justify-center text-xs text-hint">
            No token usage recorded for this view.
          </div>
        ) : (
          <svg
            className="h-full w-full overflow-visible"
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            role="img"
            aria-label={`Line chart for ${title.toLowerCase()}`}
          >
            {[0, 1, 2].map((index) => {
              const y = chartTop + index * ((chartBottom - chartTop) / 2);
              return (
                <line
                  key={index}
                  x1={chartLeft}
                  x2={chartRight}
                  y1={y}
                  y2={y}
                  stroke="#747870"
                  strokeOpacity="0.14"
                  strokeWidth="1"
                />
              );
            })}
            <polyline points={areaPoints} fill="#1d2d18" fillOpacity="0.08" stroke="none" />
            <polyline
              points={linePoints}
              fill="none"
              stroke="#1d2d18"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {points.map((point) => (
              <g key={point.day}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r="4.5"
                  fill="#faf9f7"
                  stroke="#1d2d18"
                  strokeWidth="2.5"
                >
                  <title>
                    {formatDate(point.day)}: {formatInteger(point.total_tokens)} tokens
                  </title>
                </circle>
                {point.total_tokens > 0 && (
                  <text
                    x={point.x}
                    y={Math.max(point.y - 10, 10)}
                    textAnchor="middle"
                    className="fill-hint text-[10px] font-medium tabular-nums"
                  >
                    {formatCompactInteger(point.total_tokens)}
                  </text>
                )}
              </g>
            ))}
          </svg>
        )}
      </div>
      <div
        className="mt-2 grid gap-1 text-center text-[10px] text-hint"
        style={{ gridTemplateColumns: `repeat(${Math.max(displayRows.length, 1)}, minmax(0, 1fr))` }}
      >
        {displayRows.map((row) => (
          <span key={row.day}>{formatShortDate(row.day)}</span>
        ))}
      </div>
    </section>
  );
}

export function BreakdownPanel({ title, rows }: { title: string; rows: TokenUsageBreakdownRow[] }) {
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

export function TopUsersTable({
  rows,
  totalTokens,
  totalRequests,
}: {
  rows: AdminUsageUserRow[];
  totalTokens: number;
  totalRequests: number;
}) {
  const maxTokens = Math.max(...rows.map((row) => row.total_tokens), 1);
  const topUser = rows[0] ?? null;

  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <div className="flex flex-col gap-3 border-b border-outline/20 pb-3 lg:flex-row lg:items-center lg:justify-between">
        <PanelTitle title="Top users" />
        <div className="grid grid-cols-3 gap-2 text-right text-xs">
          <MiniStat label="Users" value={formatInteger(rows.length)} />
          <MiniStat label="Requests" value={formatInteger(totalRequests)} />
          <MiniStat label="Top user" value={topUser ? formatInteger(topUser.total_tokens) : "-"} />
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="py-6 text-center text-xs text-hint">No user usage in this range.</p>
      ) : (
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)]">
          <div className="space-y-3">
            {rows.slice(0, 6).map((row) => {
              const tokenShare = totalTokens > 0 ? (row.total_tokens / totalTokens) * 100 : 0;
              return (
                <div key={row.user_id} className="rounded-lg border border-outline/15 bg-surface-container-low p-3">
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="truncate font-medium text-on-surface">{row.user_email}</span>
                    <span className="tabular-nums text-hint">{tokenShare.toFixed(1)}%</span>
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-background">
                    <div
                      className="h-1.5 rounded-full bg-primary"
                      style={{ width: `${Math.max((row.total_tokens / maxTokens) * 100, 4)}%` }}
                    />
                  </div>
                  <div className="mt-2 flex justify-between text-[10px] text-hint">
                    <span>{formatInteger(row.request_count)} requests</span>
                    <span>{formatInteger(row.total_tokens)} tokens</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-xs">
              <thead className="border-b border-outline/20 text-[10px] uppercase tracking-[0.14em] text-hint">
                <tr>
                  <th className="py-2 pr-3 font-semibold">User</th>
                  <th className="py-2 pr-3 text-right font-semibold">Requests</th>
                  <th className="py-2 pr-3 text-right font-semibold">Tokens</th>
                  <th className="py-2 pr-3 text-right font-semibold">Token share</th>
                  <th className="py-2 text-right font-semibold">Credits</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline/10">
                {rows.map((row) => (
                  <tr key={row.user_id}>
                    <td className="py-2 pr-3 text-secondary">{row.user_email}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatInteger(row.request_count)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{formatInteger(row.total_tokens)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {totalTokens > 0 ? `${((row.total_tokens / totalTokens) * 100).toFixed(1)}%` : "-"}
                    </td>
                    <td className="py-2 text-right tabular-nums">{formatCredits(row.cost_credits)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

export function ProjectTable({
  rows,
  title = "Top projects",
}: {
  rows: AdminUsageProjectRow[];
  title?: string;
}) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title={title} />
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

export function RecentEventsTable({
  rows,
  title = "User log",
}: {
  rows: AdminTokenUsage["recent_events"];
  title?: string;
}) {
  return (
    <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-4">
      <PanelTitle title={title} />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-xs">
          <thead className="border-b border-outline/20 text-[10px] uppercase tracking-[0.14em] text-hint">
            <tr>
              <th className="py-2 pr-3 font-semibold">Time</th>
              <th className="py-2 pr-3 font-semibold">User</th>
              <th className="py-2 pr-3 font-semibold">Project</th>
              <th className="py-2 pr-3 font-semibold">Prompt</th>
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
                <td className="py-2 pr-3">
                  <p className="max-w-72 truncate text-on-surface" title={row.user_prompt ?? undefined}>
                    {row.user_prompt ?? "-"}
                  </p>
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

export function buildAdminTokenUsagePath(
  range: RangeKey,
  filters: { userId?: string; projectId?: string } = {},
) {
  const dates = getRangeDates(range);
  const params = new URLSearchParams();
  if (dates.dateFrom) params.set("date_from", dates.dateFrom);
  if (dates.dateTo) params.set("date_to", dates.dateTo);
  if (filters.userId) params.set("user_id", filters.userId);
  if (filters.projectId) params.set("project_id", filters.projectId);
  return `/admin/token-usage${params.size ? `?${params.toString()}` : ""}`;
}

export function getRangeLabel(range: RangeKey) {
  if (isPresetRange(range)) {
    return RANGE_OPTIONS.find((option) => option.key === range)?.label ?? "Usage range";
  }

  const dates = getRangeDates(range);
  if (dates.dateFrom && dates.dateTo) {
    return dates.dateFrom === dates.dateTo
      ? formatDate(dates.dateFrom)
      : `${formatDate(dates.dateFrom)} - ${formatDate(dates.dateTo)}`;
  }

  return "Custom range";
}

export function formatUsageDateRange(usage: AdminTokenUsage | null, fallback = "Usage range") {
  if (!usage) return fallback;
  if (!usage.date_from && !usage.date_to) return "All time";
  if (usage.date_from && usage.date_to) return `${formatDate(usage.date_from)} - ${formatDate(usage.date_to)}`;
  return usage.date_from ? `From ${formatDate(usage.date_from)}` : `Until ${formatDate(usage.date_to ?? "")}`;
}

export function sortUsersByUsage(users: AdminUsageUserRow[]) {
  return [...users].sort((left, right) => {
    const tokenDelta = right.total_tokens - left.total_tokens;
    return tokenDelta === 0 ? left.user_email.localeCompare(right.user_email) : tokenDelta;
  });
}

function AdminSidebar({ activeHref }: { activeHref: string }) {
  return (
    <aside className="hidden h-screen w-60 flex-shrink-0 flex-col border-r border-outline/30 bg-surface-container p-3 md:flex">
      <div className="px-1 py-2">
        <ConfluexMark />
        <p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-hint">
          Admin Console
        </p>
      </div>

      <nav className="mt-4 space-y-1" aria-label="Admin pages">
        {ADMIN_SECTIONS.map((section) => {
          const active = section.href === activeHref;
          return (
            <Link
              key={section.href}
              href={section.href}
              className={`flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                active
                  ? "bg-primary/10 text-primary"
                  : "text-on-surface-variant hover:bg-primary/10 hover:text-primary"
              }`}
            >
              <span
                className="material-symbols-outlined text-primary"
                style={{ fontSize: "17px", marginLeft: "-6px" }}
              >
                {section.icon}
              </span>
              <span>{section.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto border-t border-outline/30 pt-3">
        <Link
          href="/chat"
          className="flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-xs font-medium text-on-surface-variant transition-colors hover:bg-primary/5 hover:text-on-surface"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-6px" }}>
            arrow_back
          </span>
          <span>Back to chat</span>
        </Link>
      </div>
    </aside>
  );
}

function MobileAdminNav({ activeHref }: { activeHref: string }) {
  return (
    <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-2 md:hidden">
      <div className="flex flex-wrap items-center gap-2">
        {ADMIN_SECTIONS.map((section) => {
          const active = section.href === activeHref;
          return (
            <Link
              key={section.href}
              href={section.href}
              className={`inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                active
                  ? "bg-primary/10 text-primary"
                  : "text-on-surface-variant hover:bg-primary/10 hover:text-primary"
              }`}
            >
              <span className="material-symbols-outlined text-primary" style={{ fontSize: "17px" }}>
                {section.icon}
              </span>
              {section.label}
            </Link>
          );
        })}
        <Link
          href="/chat"
          className="ml-auto inline-flex h-9 items-center gap-2 rounded-lg px-2.5 text-xs font-medium text-on-surface-variant transition-colors hover:bg-primary/5 hover:text-on-surface"
        >
          <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
            arrow_back
          </span>
          Chat
        </Link>
      </div>
    </div>
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

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-hint">{label}</p>
      <p className="mt-2 text-xl font-semibold tabular-nums text-primary">{value}</p>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-outline/15 bg-surface-container-low px-3 py-2">
      <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-hint">{label}</p>
      <p className="mt-1 font-semibold tabular-nums text-primary">{value}</p>
    </div>
  );
}

function PanelTitle({ title }: { title: string }) {
  return <h2 className="text-[11px] font-semibold uppercase tracking-[0.16em] text-secondary">{title}</h2>;
}

function getRangeDates(range: RangeKey) {
  if (!isPresetRange(range)) {
    const [, dateFrom, dateTo] = range.split(":");
    if (isIsoDate(dateFrom) && isIsoDate(dateTo)) {
      return normalizeDateRange(dateFrom, dateTo);
    }
  }

  if (range === "all") return { dateFrom: null, dateTo: null };
  const dateTo = new Date();
  const dateFrom = new Date(dateTo);
  dateFrom.setDate(dateTo.getDate() - Number(range) + 1);
  return {
    dateFrom: toIsoDate(dateFrom),
    dateTo: toIsoDate(dateTo),
  };
}

function isPresetRange(range: RangeKey): range is PresetRangeKey {
  return range === "7" || range === "30" || range === "all";
}

function buildCustomRange(dateFrom: string, dateTo: string): RangeKey {
  const dates = normalizeDateRange(dateFrom, dateTo);
  return `custom:${dates.dateFrom}:${dates.dateTo}`;
}

function normalizeDateRange(dateFrom: string, dateTo: string) {
  return dateFrom <= dateTo
    ? { dateFrom, dateTo }
    : { dateFrom: dateTo, dateTo: dateFrom };
}

function isIsoDate(value: string | undefined) {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

function getCalendarAnchorDate(dates: { dateFrom: string | null; dateTo: string | null }) {
  return dates.dateTo ? parseIsoDate(dates.dateTo) : new Date();
}

function buildCalendarDays(month: Date) {
  const firstDay = startOfMonth(month);
  const gridStart = addDays(firstDay, -firstDay.getDay());
  return Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, months: number) {
  return new Date(value.getFullYear(), value.getMonth() + months, 1);
}

function isSameMonth(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth();
}

function isDateInRange(day: string, dateFrom: string | null, dateTo: string | null) {
  if (!dateFrom || !dateTo) return false;
  return day >= dateFrom && day <= dateTo;
}

function parseIsoDate(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function buildLastSevenDailyRows(rows: TokenUsageDailyRow[]) {
  const rowByDay = new Map(rows.map((row) => [row.day, row]));
  const today = startOfLocalDay(new Date());
  return Array.from({ length: 7 }, (_, index) => {
    const day = addDays(today, index - 6);
    const dayKey = toIsoDate(day);
    const row = rowByDay.get(dayKey);
    return {
      day: dayKey,
      total_tokens: row?.total_tokens ?? 0,
      prompt_tokens: row?.prompt_tokens ?? 0,
      completion_tokens: row?.completion_tokens ?? 0,
      cost_credits: row?.cost_credits ?? null,
      request_count: row?.request_count ?? 0,
    };
  });
}

function startOfLocalDay(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function addDays(value: Date, days: number) {
  const next = new Date(value);
  next.setDate(value.getDate() + days);
  return next;
}

function toIsoDate(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatCompactInteger(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
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

function formatCalendarMonth(value: Date) {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
  }).format(value);
}

function formatShortDate(value: string) {
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
