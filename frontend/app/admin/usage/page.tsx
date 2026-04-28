"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminTokenUsage, ApiError, api } from "@/lib/api";
import {
  ADMIN_USAGE_DASHBOARD_PATH,
  AdminUsageLayout,
  BreakdownPanel,
  DailyTrend,
  DateRangeSelect,
  EmptyUsageState,
  ErrorBanner,
  ForbiddenAdminState,
  KpiGrid,
  LoadingUsageState,
  PageState,
  ProjectTable,
  RangeKey,
  RecentEventsTable,
  RefreshButton,
  TopUsersTable,
  UsagePageHeader,
  buildAdminTokenUsagePath,
  formatUsageDateRange,
  getRangeLabel,
  useAdminAccess,
} from "./components";

export default function AdminUsagePage() {
  const { ready, token, accessLoading, isAdmin, accessError, setIsAdmin } = useAdminAccess();
  const [usage, setUsage] = useState<AdminTokenUsage | null>(null);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [range, setRange] = useState<RangeKey>("7");

  const loadUsage = useCallback(async () => {
    if (!token) return;

    setLoadingUsage(true);
    setUsageError(null);
    try {
      const nextUsage = await api<AdminTokenUsage>(buildAdminTokenUsagePath(range), { token });
      setUsage(nextUsage);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setIsAdmin(false);
        return;
      }
      setUsageError(err instanceof Error ? err.message : "Failed to load token usage.");
    } finally {
      setLoadingUsage(false);
    }
  }, [range, setIsAdmin, token]);

  useEffect(() => {
    if (!token || accessLoading || !isAdmin) return;
    void loadUsage();
  }, [accessLoading, isAdmin, loadUsage, token]);

  const rangeLabel = useMemo(
    () => formatUsageDateRange(usage, getRangeLabel(range)),
    [range, usage],
  );
  const error = usageError ?? accessError;

  if (!ready || !token || accessLoading) {
    return <PageState label="Loading admin console" icon="hourglass_top" />;
  }

  if (!isAdmin) {
    return <ForbiddenAdminState />;
  }

  return (
    <AdminUsageLayout activeHref={ADMIN_USAGE_DASHBOARD_PATH}>
      <UsagePageHeader title="Token Usage Monitor" rangeLabel={rangeLabel}>
        <RefreshButton loading={loadingUsage} onRefresh={() => void loadUsage()} />
      </UsagePageHeader>

      <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,18rem)]">
          <DateRangeSelect range={range} onChange={setRange} />
        </div>
      </section>

      {error ? <ErrorBanner message={error} /> : null}

      {loadingUsage && !usage ? (
        <LoadingUsageState />
      ) : usage && usage.request_count === 0 ? (
        <EmptyUsageState />
      ) : usage ? (
        <>
          <KpiGrid usage={usage} />
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <DailyTrend rows={usage.by_day} mode="rows" />
            <BreakdownPanel title="Usage by feature" rows={usage.by_feature} />
            <BreakdownPanel title="Usage by model" rows={usage.by_model} />
          </section>
          <TopUsersTable
            rows={usage.by_user}
            totalTokens={usage.total_tokens}
            totalRequests={usage.request_count}
          />
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <ProjectTable rows={usage.by_project} />
            <RecentEventsTable rows={usage.recent_events} />
          </section>
        </>
      ) : null}
    </AdminUsageLayout>
  );
}
