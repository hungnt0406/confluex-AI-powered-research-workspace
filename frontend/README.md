# Confluex Frontend

Next.js 14 App Router chat UI for the Automated Literature Review FastAPI backend.

This frontend currently ships a login screen plus a chat-style workspace that creates projects, runs the Searcher -> Reader discovery flow, shows ranked papers in context with citation/reference counts and expandable structured summaries, and starts grounded paper conversations on the top paper.

## Setup

```bash
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm install
npm run dev
```

Backend must be running on `NEXT_PUBLIC_API_BASE_URL` with CORS allowing `http://localhost:3000` (already configured in `backend/main.py`).

## What it wires up

- `POST /auth/register` / `POST /auth/login` — session stored in `localStorage` via `AuthProvider`.
- `GET /projects` — sidebar "Recents" list.
- First user message without an active project:
  1. `POST /projects` (title = first 120 chars, topic = full message, citation_format = APA).
  2. `POST /projects/{id}/run` — Searcher → Reader pipeline; queries + counts shown in the right context panel.
  3. `GET /projects/{id}/papers` — top-ranked paper is picked as grounding target.
  4. `POST /projects/{id}/papers/{paper_id}/conversations` — starts a grounded Q&A.
- Follow-up messages: `POST .../conversations/{conversation_id}/messages` appended to the same grounded thread.
- Selecting a project in the sidebar re-hydrates ranked papers and re-grounds on the top one.

## Files

- `app/layout.tsx`, `app/globals.css`, `tailwind.config.ts` — app shell and styling tokens.
- `app/login/page.tsx` — sign in / register.
- `app/chat/page.tsx` — auth-gated workspace.
- `components/AuthProvider.tsx` — token/user state.
- `components/ChatProvider.tsx` — orchestrates project creation, pipeline run, and grounded conversations.
- `components/Sidebar.tsx`, `components/ChatWorkspace.tsx`, `components/ContextPanel.tsx` — workspace panels.
- `lib/api.ts` — typed `fetch` wrapper and backend DTO types.

## Current limitations

- No frontend tests are present yet.
- The frontend does not yet expose reference-file management or writer generation.
- The UI is a shipped shell, not the full multi-stage product flow described in `docs/user-journey.md`.
