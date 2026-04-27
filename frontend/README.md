# Confluex Frontend

Next.js 14 App Router chat UI for the Automated Literature Review FastAPI backend.

This frontend currently ships a login screen plus a chat-style workspace that creates projects, runs the Searcher -> Reader discovery flow, shows ranked papers in context with citation/reference counts and expandable structured summaries, shows compact project token usage, lets the user select up to 5 papers, uploads reference PDFs from the composer, asks general questions with no selected papers, and asks grounded questions across the current selected paper set.

## Setup

```bash
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm install
npm run dev
```

Backend must be running on `NEXT_PUBLIC_API_BASE_URL` with CORS allowing `http://localhost:3000` (already configured in `backend/main.py`).

On Linux machines with user systemd available, prefer the bounded dev server when testing Turbopack compiles:

```bash
npm run dev:bounded
```

This runs `next dev` inside the `a20-next-dev` user scope with `MemoryMax=10G` and `MemorySwapMax=0`, so a bad dev compile is killed without consuming the whole machine. If Turbopack behaves oddly after config changes, reset only the dev cache first:

```bash
npm run dev:reset
```

## What it wires up

- `POST /auth/register` / `POST /auth/login` — session stored in `localStorage` via `AuthProvider`.
- `GET /projects` — sidebar "Recents" list.
- `PATCH /projects/{id}` — sidebar overflow menu can rename a saved chat/project in place.
- Composer upload button:
  1. With an active project: `POST /projects/{id}/reference-files` uploads a PDF reference into the current project.
  2. With no active project: the workspace first creates a project from the provided topic, then uploads the PDF without running discovery or creating a conversation.
  3. After upload: `GET /projects/{id}/papers` refreshes the right panel; uploaded papers are marked with an `Uploaded PDF` badge and are not auto-selected.
  4. `GET /projects/{id}/token-usage` refreshes the right-panel usage card after provider-backed parsing.
- First user message without an active project:
  1. `POST /projects` (title = first 120 chars, topic = full message, citation_format = APA).
  2. `POST /projects/{id}/run` — Searcher → Reader pipeline; queries + counts shown in the right context panel.
  3. `GET /projects/{id}/papers` — ranked papers populate the right panel with no paper selected by default.
  4. `POST /projects/{id}/conversations/stream` — starts a project-scoped chat with `paper_ids: []` for a streamed general answer until papers are selected.
- Usage summary: `GET /projects/{id}/token-usage` refreshes when selecting a project and after pipeline/conversation actions that may call OpenRouter.
- Follow-up messages: `POST /projects/{id}/conversations/{conversation_id}/messages/stream` appends streamed assistant tokens to the same thread, carrying the current selected `paper_ids`.
- Selecting a project in the sidebar re-hydrates ranked papers, restores the latest saved grounded project conversation, restores the last selected paper set from localStorage when possible, preserves intentionally empty selections, and restores the last-open project after refresh.
- Each recent project row now exposes a hover/focus overflow menu for rename and delete actions.

## Files

- `app/layout.tsx`, `app/globals.css`, `tailwind.config.ts` — app shell and styling tokens.
- `app/login/page.tsx` — sign in / register.
- `app/chat/page.tsx` — auth-gated workspace.
- `components/AuthProvider.tsx` — token/user state.
- `components/ChatProvider.tsx` — orchestrates project creation, composer PDF uploads, selected-paper persistence, and grounded project conversations.
- `components/Sidebar.tsx`, `components/ChatWorkspace.tsx`, `components/ContextPanel.tsx` — workspace panels, composer upload UI, and uploaded-paper markers.
- `lib/api.ts` — typed `fetch` wrapper, SSE stream parser, and backend DTO types.

## Current limitations

- No frontend tests are present yet.
- The frontend still does not expose full reference-file management or writer generation.
- The UI is a shipped shell, not the full multi-stage product flow described in `docs/user-journey.md`.
