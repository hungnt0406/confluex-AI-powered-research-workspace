"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AdminTokenUsage, ApiError, api } from "@/lib/api";
import {
  ADMIN_USAGE_USERS_PATH,
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
  UsagePageHeader,
  UserSelect,
  buildAdminTokenUsagePath,
  formatUsageDateRange,
  getRangeLabel,
  sortUsersByUsage,
  useAdminAccess,
} from "../components";

export default function AdminUsageUsersPage() {
  const { ready, token, accessLoading, isAdmin, accessError, setIsAdmin } = useAdminAccess();
  const [range, setRange] = useState<RangeKey>("7");
  const [queryReady, setQueryReady] = useState(false);
  const [users, setUsers] = useState<AdminTokenUsage["by_user"]>([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const selectedUserRef = useRef("");
  const requestIdRef = useRef(0);
  const [userUsage, setUserUsage] = useState<AdminTokenUsage | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingUsage, setLoadingUsage] = useState(false);
  const [usageError, setUsageError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const userId = new URLSearchParams(window.location.search).get("user_id") ?? "";
    selectedUserRef.current = userId;
    setSelectedUserId(userId);
    setQueryReady(true);
  }, []);

  const loadSelectedUserUsage = useCallback(
    async (userId: string) => {
      const requestId = ++requestIdRef.current;
      if (!token || !userId) {
        setUserUsage(null);
        setLoadingUsage(false);
        return;
      }

      setLoadingUsage(true);
      setUsageError(null);
      try {
        const nextUsage = await api<AdminTokenUsage>(
          buildAdminTokenUsagePath(range, { userId }),
          { token },
        );
        if (requestId !== requestIdRef.current) return;
        setUserUsage(nextUsage);
      } catch (err: unknown) {
        if (requestId !== requestIdRef.current) return;
        if (err instanceof ApiError && err.status === 403) {
          setIsAdmin(false);
          return;
        }
        setUsageError(err instanceof Error ? err.message : "Failed to load selected user usage.");
      } finally {
        if (requestId === requestIdRef.current) setLoadingUsage(false);
      }
    },
    [range, setIsAdmin, token],
  );

  const loadUsersAndSelectedUsage = useCallback(async () => {
    if (!token || !queryReady) return;

    const requestId = ++requestIdRef.current;
    setLoadingUsers(true);
    setLoadingUsage(true);
    setUsageError(null);
    setUserUsage(null);
    try {
      const summary = await api<AdminTokenUsage>(buildAdminTokenUsagePath(range), { token });
      if (requestId !== requestIdRef.current) return;

      const nextUsers = sortUsersByUsage(summary.by_user);
      const requestedUserId = selectedUserRef.current;
      const nextSelectedUserId = nextUsers.some((user) => user.user_id === requestedUserId)
        ? requestedUserId
        : nextUsers[0]?.user_id ?? "";

      setUsers(nextUsers);
      selectedUserRef.current = nextSelectedUserId;
      setSelectedUserId(nextSelectedUserId);
      replaceSelectedUserQuery(nextSelectedUserId);

      if (!nextSelectedUserId) {
        setUserUsage(null);
        return;
      }

      const nextUsage = await api<AdminTokenUsage>(
        buildAdminTokenUsagePath(range, { userId: nextSelectedUserId }),
        { token },
      );
      if (requestId !== requestIdRef.current) return;
      setUserUsage(nextUsage);
    } catch (err: unknown) {
      if (requestId !== requestIdRef.current) return;
      if (err instanceof ApiError && err.status === 403) {
        setIsAdmin(false);
        return;
      }
      setUsers([]);
      setUserUsage(null);
      setUsageError(err instanceof Error ? err.message : "Failed to load user list.");
    } finally {
      if (requestId === requestIdRef.current) {
        setLoadingUsers(false);
        setLoadingUsage(false);
      }
    }
  }, [queryReady, range, setIsAdmin, token]);

  useEffect(() => {
    if (!token || accessLoading || !isAdmin || !queryReady) return;
    void loadUsersAndSelectedUsage();
  }, [accessLoading, isAdmin, loadUsersAndSelectedUsage, queryReady, token]);

  const handleUserChange = useCallback(
    (userId: string) => {
      selectedUserRef.current = userId;
      setSelectedUserId(userId);
      replaceSelectedUserQuery(userId);
      void loadSelectedUserUsage(userId);
    },
    [loadSelectedUserUsage],
  );

  const selectedUser = useMemo(
    () => users.find((user) => user.user_id === selectedUserId) ?? userUsage?.by_user[0] ?? null,
    [selectedUserId, userUsage, users],
  );
  const rangeLabel = useMemo(
    () => formatUsageDateRange(userUsage, getRangeLabel(range)),
    [range, userUsage],
  );
  const error = usageError ?? accessError;
  const loading = loadingUsers || loadingUsage;

  if (!ready || !token || accessLoading || !queryReady) {
    return <PageState label="Loading admin console" icon="hourglass_top" />;
  }

  if (!isAdmin) {
    return <ForbiddenAdminState />;
  }

  return (
    <AdminUsageLayout activeHref={ADMIN_USAGE_USERS_PATH}>
      <UsagePageHeader title="Selected User Analysis" rangeLabel={rangeLabel}>
        <RefreshButton loading={loading} onRefresh={() => void loadUsersAndSelectedUsage()} />
      </UsagePageHeader>

      <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
          <UserSelect
            users={users}
            value={selectedUserId}
            disabled={loadingUsers || users.length === 0}
            onChange={handleUserChange}
          />
          <DateRangeSelect range={range} onChange={setRange} />
        </div>
      </section>

      {selectedUser ? (
        <section className="rounded-xl border border-outline/20 bg-surface-container-lowest p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-hint">
            Selected user
          </p>
          <p className="mt-1 truncate text-sm font-medium text-on-surface">{selectedUser.user_email}</p>
        </section>
      ) : null}

      {error ? <ErrorBanner message={error} /> : null}

      {loading && !userUsage ? (
        <LoadingUsageState label="Loading selected user usage..." />
      ) : users.length === 0 ? (
        <EmptyUsageState description="No users have provider-reported token events in the selected range." />
      ) : userUsage && userUsage.request_count === 0 ? (
        <EmptyUsageState description="No usage data was found for the selected user in this range." />
      ) : userUsage ? (
        <>
          <KpiGrid usage={userUsage} />
          <section className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <DailyTrend rows={userUsage.by_day} title="Daily activity" mode="rows" />
            <BreakdownPanel title="Feature breakdown" rows={userUsage.by_feature} />
            <BreakdownPanel title="Model breakdown" rows={userUsage.by_model} />
          </section>
          <ProjectTable rows={userUsage.by_project} title="Projects used" />
          <RecentEventsTable rows={userUsage.recent_events} title="Recent activity" />
        </>
      ) : null}
    </AdminUsageLayout>
  );
}

function replaceSelectedUserQuery(userId: string) {
  if (typeof window === "undefined") return;

  const params = new URLSearchParams(window.location.search);
  if (userId) params.set("user_id", userId);
  else params.delete("user_id");

  const query = params.toString();
  const nextUrl = `${ADMIN_USAGE_USERS_PATH}${query ? `?${query}` : ""}`;
  window.history.replaceState(window.history.state, "", nextUrl);
}
