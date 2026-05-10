"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { useChat } from "@/components/ChatProvider";
import {
  AdminAccess,
  CREDIT_BALANCE_REFRESH_EVENT,
  CreditBalance,
  Project,
  api,
  fetchCreditBalance,
} from "@/lib/api";

interface SidebarProps {
  open: boolean;
  onToggle: () => void;
}

export default function Sidebar({ open, onToggle }: SidebarProps) {
  const { token, user, logout } = useAuth();
  const { projects, activeProject, busy, selectProject, renameProject, deleteProject, startNewResearch } = useChat();
  const [isAdmin, setIsAdmin] = useState(false);
  const [creditBalance, setCreditBalance] = useState<CreditBalance | null>(null);

  useEffect(() => {
    if (!token) {
      setIsAdmin(false);
      return;
    }

    let cancelled = false;
    api<AdminAccess>("/admin/access", { token })
      .then((response) => {
        if (!cancelled) setIsAdmin(response.is_admin);
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const refreshCreditBalance = useCallback(async () => {
    if (!token) {
      setCreditBalance(null);
      return;
    }

    try {
      const response = await fetchCreditBalance(token);
      setCreditBalance(response);
    } catch {
      setCreditBalance(null);
    }
  }, [token]);

  const creditBalanceLabel = creditBalance?.is_unlimited
    ? "Unlimited"
    : creditBalance === null
      ? "..."
      : creditBalance.credit_balance.toLocaleString("en-US");
  const creditBalanceTitle = creditBalance?.is_unlimited
    ? "Unlimited credits"
    : creditBalance === null
      ? "Credit balance"
      : `${creditBalance.credit_balance.toLocaleString("en-US")} credits`;

  useEffect(() => {
    void refreshCreditBalance();
    if (!token) return;

    const intervalId = window.setInterval(() => void refreshCreditBalance(), 60_000);
    const handleRefresh = () => void refreshCreditBalance();
    window.addEventListener(CREDIT_BALANCE_REFRESH_EVENT, handleRefresh);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener(CREDIT_BALANCE_REFRESH_EVENT, handleRefresh);
    };
  }, [refreshCreditBalance, token]);

  const handleDeleteProject = async (projectId: string, projectTitle: string) => {
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(`Delete "${projectTitle}"? This cannot be undone.`);
      if (!confirmed) return;
    }

    await deleteProject(projectId);
  };

  return (
    <aside
      className="flex flex-col h-screen bg-surface-container border-r border-outline/30 z-50 overflow-hidden shrink-0"
      style={{
        width: open ? "260px" : "48px",
        transition: "width 300ms ease",
      }}
    >
      {/* Header: logo + toggle on same row */}
      <div
        className={`flex items-center p-2 ${open ? "justify-between" : "justify-center"}`}
        style={{ minHeight: "52px" }}
      >
        {open && (
          <div className="flex items-center gap-2 pl-1">
            <svg
              viewBox="0 0 62 60"
              width={26}
              height={26}
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              style={{ flexShrink: 0 }}
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
                <path key={i} d={d} stroke="#7BAD8A" strokeWidth="1.6" strokeLinecap="round" fill="none" />
              ))}
            </svg>
            <span
              style={{
                fontFamily: "'Inter', sans-serif",
                fontWeight: 600,
                color: "#2C1010",
                letterSpacing: "-0.01em",
                fontSize: "1rem",
                lineHeight: 1,
              }}
            >
              confluex
            </span>
          </div>
        )}
        <button
          onClick={onToggle}
          className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors text-on-surface-variant"
          aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
        >
          <span
            className="material-symbols-outlined"
            style={{ fontSize: "20px" }}
          >
            view_sidebar
          </span>
        </button>
      </div>

      {open ? (
        /* ── Expanded state ── */
        <div className="flex flex-col h-full overflow-hidden px-3 pb-3">
          {/* New Research button */}
          <button
            onClick={startNewResearch}
            className="flex items-center gap-2.5 w-full px-2.5 py-2 mb-4 rounded-lg hover:bg-primary/20 transition-colors duration-200 text-xs font-medium text-on-surface group"
          >
            <span
              className="material-symbols-outlined text-primary group-hover:text-primary"
              style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20", marginLeft: "-7px" }}
            >
              edit_square
            </span>
            <span>New Research</span>
          </button>

          {/* Project list */}
          <nav className="flex-1 overflow-y-auto custom-scrollbar space-y-1">
            <div className="px-3 mb-2">
              <p className="text-[11px] font-bold text-on-surface-variant/70 uppercase tracking-wider">
                Recents
              </p>
            </div>
            {projects.length === 0 ? (
              <p className="px-3 text-xs text-hint">No projects yet.</p>
            ) : (
              projects.map((project) => {
                return (
                  <ProjectListItem
                    key={project.id}
                    project={project}
                    isActive={activeProject?.id === project.id}
                    busy={busy}
                    onSelect={selectProject}
                    onRename={renameProject}
                    onDelete={handleDeleteProject}
                  />
                );
              })
            )}
          </nav>

          {/* Footer */}
          <div className="mt-auto pt-4 border-t border-outline/30">
            <Link
              href="/billing"
              className="mb-1 flex items-center justify-between gap-2.5 w-full rounded-lg border border-primary/15 bg-primary/5 px-2.5 py-1.5 text-xs text-primary transition-colors hover:bg-primary/10"
            >
              <span className="flex min-w-0 items-center gap-2.5">
                <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-7px" }}>
                  bolt
                </span>
                <span className="truncate">Credits</span>
              </span>
              <span className="font-semibold tabular-nums">
                {creditBalanceLabel}
              </span>
            </Link>
            <Link
              href={activeProject ? `/writer?project=${activeProject.id}` : "/writer"}
              className="mb-1 flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg hover:bg-primary/5 transition-colors text-xs text-on-surface-variant"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-7px" }}>
                description
              </span>
              <span>Writer</span>
              <span className="ml-auto rounded-full border border-primary/15 bg-primary/5 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-primary">
                Beta
              </span>
            </Link>
            <Link
              href="/pricing"
              className="mb-1 flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg hover:bg-primary/5 transition-colors text-xs text-on-surface-variant"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-7px" }}>
                workspace_premium
              </span>
              <span>Plans</span>
            </Link>
            {isAdmin && (
              <Link
                href="/admin/usage"
                className="mb-1 flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg hover:bg-primary/5 transition-colors text-xs text-on-surface-variant"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-7px" }}>
                  monitoring
                </span>
                <span>Usage Monitor</span>
              </Link>
            )}
            <button
              onClick={logout}
              className="flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg hover:bg-primary/5 transition-colors text-xs text-on-surface-variant"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px", marginLeft: "-7px" }}>
                logout
              </span>
              <span>Sign out</span>
            </button>
            <div className="flex items-center gap-2.5 w-full px-2.5 py-2 mt-1">
              <span
                className="material-symbols-outlined text-on-surface-variant"
                style={{ fontSize: "20px", fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20", marginLeft: "-7px" }}
              >
                account_circle
              </span>
              <div className="flex-1 truncate">
                <p className="text-xs font-semibold truncate leading-none text-on-surface">
                  {user?.email ?? "Scholar User"}
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* ── Collapsed icon-rail state ── */
        <div className="flex flex-col items-center h-full overflow-hidden py-2 gap-1">
          {/* New Research */}
          <button
            onClick={startNewResearch}
            className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/20 transition-colors duration-200 group"
            aria-label="New Research"
            title="New Research"
          >
            <span
              className="material-symbols-outlined text-primary group-hover:text-primary"
              style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
            >
              edit_square
            </span>
          </button>

          {/* Footer icons */}
          <div className="mt-auto flex flex-col items-center gap-1 pt-2 border-t border-outline/30 w-full">
            <Link
              href="/billing"
              className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/5 hover:bg-primary/10 transition-colors text-primary"
              aria-label={creditBalanceTitle}
              title={creditBalanceTitle}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                bolt
              </span>
            </Link>
            <Link
              href={activeProject ? `/writer?project=${activeProject.id}` : "/writer"}
              className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors text-on-surface-variant"
              aria-label="Writer beta"
              title="Writer beta"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                description
              </span>
            </Link>
            <Link
              href="/pricing"
              className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors text-on-surface-variant"
              aria-label="Plans"
              title="Plans"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                workspace_premium
              </span>
            </Link>
            {isAdmin && (
              <Link
                href="/admin/usage"
                className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors text-on-surface-variant"
                aria-label="Usage Monitor"
                title="Usage Monitor"
              >
                <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                  monitoring
                </span>
              </Link>
            )}
            <button
              onClick={logout}
              className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors text-on-surface-variant"
              aria-label="Sign out"
              title="Sign out"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                logout
              </span>
            </button>
            <div
              className="flex items-center justify-center w-8 h-8"
              title={user?.email ?? "Scholar User"}
            >
              <span
                className="material-symbols-outlined text-on-surface-variant"
                style={{ fontSize: "20px", fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
              >
                account_circle
              </span>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function ProjectListItem({
  project,
  isActive,
  busy,
  onSelect,
  onRename,
  onDelete,
}: {
  project: Project;
  isActive: boolean;
  busy: boolean;
  onSelect: (projectId: string) => Promise<void>;
  onRename: (projectId: string, title: string) => Promise<void>;
  onDelete: (projectId: string, projectTitle: string) => Promise<void>;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [isRenaming, setIsRenaming] = useState(false);
  const [draftTitle, setDraftTitle] = useState(project.title);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!isRenaming) {
      setDraftTitle(project.title);
    }
  }, [isRenaming, project.title]);

  useEffect(() => {
    if (!menuOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [menuOpen]);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      if (isRenaming) {
        setIsRenaming(false);
        setDraftTitle(project.title);
      }
    };

    if (!menuOpen && !isRenaming) return;

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isRenaming, menuOpen, project.title]);

  useEffect(() => {
    if (!isRenaming) return;
    inputRef.current?.focus();
    inputRef.current?.select();
  }, [isRenaming]);

  const handleRenameSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextTitle = draftTitle.trim();
    if (!nextTitle || nextTitle === project.title) {
      setIsRenaming(false);
      setDraftTitle(project.title);
      return;
    }

    try {
      await onRename(project.id, nextTitle);
      setIsRenaming(false);
      setDraftTitle(nextTitle);
    } catch {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  };

  const startRename = () => {
    setMenuOpen(false);
    setIsRenaming(true);
    setDraftTitle(project.title);
  };

  const cancelRename = () => {
    setIsRenaming(false);
    setDraftTitle(project.title);
  };

  return (
    <div
      className={`group relative flex items-center gap-1 rounded-lg ${
        isActive ? "bg-primary/10" : "hover:bg-primary/5"
      }`}
    >
      {isRenaming ? (
        <form onSubmit={handleRenameSubmit} className="flex min-w-0 flex-1 items-center gap-1 px-2 py-1">
          <span
            className={`material-symbols-outlined ${isActive ? "text-primary" : "opacity-60"}`}
            style={{
              fontSize: "16px",
              fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
              marginLeft: "-7px",
            }}
          >
            chat_bubble
          </span>
          <input
            ref={inputRef}
            value={draftTitle}
            onChange={(event) => setDraftTitle(event.target.value)}
            disabled={busy}
            maxLength={255}
            aria-label={`Rename ${project.title}`}
            className="h-8 min-w-0 flex-1 rounded-md border border-outline/30 bg-background px-2 text-xs text-on-surface outline-none transition-colors focus:border-primary/50"
          />
          <button
            type="submit"
            disabled={busy}
            className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-primary/10 hover:text-on-surface disabled:opacity-40"
            aria-label={`Save ${project.title}`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              check
            </span>
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={cancelRename}
            className="flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant transition-colors hover:bg-primary/10 hover:text-on-surface disabled:opacity-40"
            aria-label={`Cancel renaming ${project.title}`}
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              close
            </span>
          </button>
        </form>
      ) : (
        <>
          <button
            onClick={() => void onSelect(project.id)}
            className={`flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-1.5 text-left text-xs transition-colors ${
              isActive ? "font-medium text-on-surface" : "text-on-surface-variant"
            }`}
          >
            <span
              className={`material-symbols-outlined ${isActive ? "text-primary" : "opacity-60"}`}
              style={{
                fontSize: "16px",
                fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
                marginLeft: "-7px",
              }}
            >
              chat_bubble
            </span>
            <span className="truncate">{project.title}</span>
          </button>
          <div ref={menuRef} className="relative mr-1">
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen((current) => !current);
              }}
              aria-label={`Open actions for ${project.title}`}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className={`flex h-8 w-8 items-center justify-center rounded-md text-on-surface-variant/70 transition-all hover:bg-primary/10 hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
                menuOpen
                  ? "opacity-100"
                  : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-visible:opacity-100"
              }`}
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                more_horiz
              </span>
            </button>
            {menuOpen && (
              <div
                role="menu"
                aria-label={`Actions for ${project.title}`}
                className="absolute right-0 top-full z-20 mt-1 w-32 rounded-xl border border-outline/20 bg-background p-1 shadow-lg"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={startRename}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-on-surface transition-colors hover:bg-primary/10"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                    edit
                  </span>
                  <span>Rename</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setMenuOpen(false);
                    void onDelete(project.id, project.title);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-xs text-error transition-colors hover:bg-error/10"
                >
                  <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                    delete
                  </span>
                  <span>Delete</span>
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
