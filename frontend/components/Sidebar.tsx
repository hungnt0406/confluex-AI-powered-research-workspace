"use client";

import { useAuth } from "@/components/AuthProvider";
import { useChat } from "@/components/ChatProvider";

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { projects, activeProject, selectProject, startNewResearch } = useChat();

  return (
    <aside className="hidden md:flex flex-col h-screen w-[260px] bg-surface-container border-r border-outline/30 z-50">
      <div className="p-3 flex flex-col h-full">
        <button
          onClick={startNewResearch}
          className="flex items-center gap-2.5 w-full px-2.5 py-2 rounded-lg hover:bg-primary/5 transition-colors text-xs font-medium mb-4 text-on-surface"
        >
          <span
            className="material-symbols-outlined text-primary"
            style={{ fontSize: "18px", fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20" }}
          >
            edit_square
          </span>
          <span>New Research</span>
        </button>

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
    </aside>
  );
}
