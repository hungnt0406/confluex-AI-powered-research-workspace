"use client";

import { useAuth } from "@/components/AuthProvider";
import { useChat } from "@/components/ChatProvider";
import Logo from "@/components/Logo";

interface SidebarProps {
  open: boolean;
  onToggle: () => void;
}

export default function Sidebar({ open, onToggle }: SidebarProps) {
  const { user, logout } = useAuth();
  const { projects, activeProject, selectProject, startNewResearch } = useChat();

  return (
    <aside
      className="flex flex-col h-screen bg-surface-container border-r border-outline/30 z-50 overflow-hidden shrink-0"
      style={{
        width: open ? "260px" : "48px",
        transition: "width 300ms ease",
      }}
    >
      {/* Toggle button at the top */}
      <div
        className={`flex items-center p-2 ${open ? "justify-between" : "justify-center"}`}
        style={{ minHeight: "44px" }}
      >
        {open && <Logo size="sm" />}
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
            className="flex items-center gap-2.5 w-full px-2.5 py-2 mb-4 rounded-lg hover:bg-primary/5 transition-colors text-xs font-medium text-on-surface"
          >
            <span
              className="material-symbols-outlined text-primary"
              style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
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
                const isActive = activeProject?.id === project.id;
                return (
                  <button
                    key={project.id}
                    onClick={() => selectProject(project.id)}
                    className={`flex items-center gap-2.5 px-2.5 py-1.5 w-full text-left text-xs rounded-lg transition-colors ${
                      isActive
                        ? "bg-primary/10 font-medium text-on-surface"
                        : "hover:bg-primary/5 text-on-surface-variant"
                    }`}
                  >
                    <span
                      className={`material-symbols-outlined ${
                        isActive ? "text-primary" : "opacity-60"
                      }`}
                      style={{ fontSize: "16px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
                    >
                      chat_bubble
                    </span>
                    <span className="truncate">{project.title}</span>
                  </button>
                );
              })
            )}
          </nav>

          {/* Footer */}
          <div className="mt-auto pt-4 border-t border-outline/30">
            <button
              onClick={logout}
              className="flex items-center gap-2.5 w-full px-2.5 py-1.5 rounded-lg hover:bg-primary/5 transition-colors text-xs text-on-surface-variant"
            >
              <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                logout
              </span>
              <span>Sign out</span>
            </button>
            <div className="flex items-center gap-2.5 w-full px-2.5 py-2 mt-1">
              <span
                className="material-symbols-outlined w-6 h-6 rounded-full border border-outline/50 flex items-center justify-center text-on-surface-variant"
                style={{ fontSize: "16px", fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
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
            className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-primary/5 transition-colors"
            aria-label="New Research"
            title="New Research"
          >
            <span
              className="material-symbols-outlined text-primary"
              style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
            >
              edit_square
            </span>
          </button>

          {/* Active project indicator or generic chat icon */}
          {projects.length > 0 && (
            <div className="flex flex-col items-center gap-1 flex-1 overflow-hidden mt-1">
              {projects.slice(0, 8).map((project) => {
                const isActive = activeProject?.id === project.id;
                return (
                  <button
                    key={project.id}
                    onClick={() => selectProject(project.id)}
                    className={`flex items-center justify-center w-8 h-8 rounded-lg transition-colors ${
                      isActive
                        ? "bg-primary/10"
                        : "hover:bg-primary/5"
                    }`}
                    aria-label={project.title}
                    title={project.title}
                  >
                    <span
                      className={`material-symbols-outlined ${isActive ? "text-primary" : "text-on-surface-variant opacity-60"}`}
                      style={{ fontSize: "16px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
                    >
                      chat_bubble
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Footer icons */}
          <div className="mt-auto flex flex-col items-center gap-1 pt-2 border-t border-outline/30 w-full">
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
                className="material-symbols-outlined w-6 h-6 rounded-full border border-outline/50 flex items-center justify-center text-on-surface-variant"
                style={{ fontSize: "16px", fontVariationSettings: "'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 20" }}
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
