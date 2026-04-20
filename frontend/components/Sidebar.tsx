"use client";

import { useAuth } from "@/components/AuthProvider";
import { useChat } from "@/components/ChatProvider";

interface SidebarProps {
  open: boolean;
  onToggle: () => void;
}

export default function Sidebar({ open, onToggle }: SidebarProps) {
  const { user, logout } = useAuth();
  const { projects, activeProject, selectProject, deleteProject, startNewResearch } = useChat();

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
                const isActive = activeProject?.id === project.id;
                return (
                  <div
                    key={project.id}
                    className={`group flex items-center gap-1 rounded-lg ${
                      isActive ? "bg-primary/10" : "hover:bg-primary/5"
                    }`}
                  >
                    <button
                      onClick={() => selectProject(project.id)}
                      className={`flex min-w-0 flex-1 items-center gap-2.5 px-2.5 py-1.5 text-left text-xs transition-colors ${
                        isActive
                          ? "font-medium text-on-surface"
                          : "text-on-surface-variant"
                      }`}
                    >
                      <span
                        className={`material-symbols-outlined ${
                          isActive ? "text-primary" : "opacity-60"
                        }`}
                        style={{ fontSize: "16px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20", marginLeft: "-7px" }}
                      >
                        chat_bubble
                      </span>
                      <span className="truncate">{project.title}</span>
                    </button>
                    <button
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleDeleteProject(project.id, project.title);
                      }}
                      className="mr-1 flex h-7 w-7 items-center justify-center rounded-md text-on-surface-variant/70 transition-colors hover:bg-error/10 hover:text-error"
                      aria-label={`Delete ${project.title}`}
                      title={`Delete ${project.title}`}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
                        delete
                      </span>
                    </button>
                  </div>
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
