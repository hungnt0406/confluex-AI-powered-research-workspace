# Confluex Frontend

Next.js 14 App Router chat UI for the Automated Literature Review FastAPI backend.

This frontend currently ships a login screen, a chat-style workspace, and admin-only token usage monitor pages. The workspace creates projects, runs the Searcher -> Reader discovery flow, shows ranked papers in context with citation/reference counts and expandable structured summaries, lets the user select up to 5 papers, uploads reference PDFs from the composer, asks general questions with no selected papers, asks grounded questions across the current selected paper set, and can switch the composer into Deep Search mode for streamed research reports with cited sources in the right context panel.

## Setup

```bash
cp .env.local.example .env.local   # points at http://localhost:8000 by default
npm install
npm run dev
```

Backend must be running on `NEXT_PUBLIC_API_BASE_URL` with `CORS_ALLOWED_ORIGINS` including the frontend origin. Local defaults allow `http://localhost:3000`; production should set the backend env var to the Vercel production URL.

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
- First user message without an active project:
  1. `POST /projects` (title = first 120 chars, topic = full message, citation_format = APA).
  2. `POST /projects/{id}/run` — Searcher → Reader pipeline; queries + counts shown in the right context panel.
  3. `GET /projects/{id}/papers` — ranked papers populate the right panel with no paper selected by default.
  4. `POST /projects/{id}/conversations/stream` — starts a project-scoped chat with `paper_ids: []` for a streamed general answer until papers are selected.
- Admin usage monitor: `/admin/usage` checks `GET /admin/access`, then reads `GET /admin/token-usage` as a global dashboard for allowlisted admins with preset or custom date ranges and a full-range recent activity table. `/admin/usage/users` reuses the same endpoint for selected-user analysis with a searchable user picker, a `user_id` query string deep link, and a user log that shows project chat prompts when available.
- Follow-up messages: `POST /projects/{id}/conversations/{conversation_id}/messages/stream` appends streamed assistant tokens to the same thread, carrying the current selected `paper_ids`.
- Assistant answers render grounded-source Markdown directly in the chat transcript: named inline links such as `[Databricks Lakehouse](https://example.com)` appear as compact citation pills with hover/focus previews, and final `## Sources` bullets remain clean Markdown links with publisher and relevance notes.
- Composer mode toggle:
  1. `Standard` keeps the existing project conversation behavior.
  2. `Deep Search` first shows a pending research plan card with `Edit plan` and `Start research` actions instead of starting the stream immediately.
  3. `Start research` sends the approved prompt and selected `paper_ids` to `POST /projects/{id}/deep-search/stream`.
  4. With no active project, approved Deep Search first creates a project from the prompt, runs `POST /projects/{id}/run` to populate the related-paper panel, then streams the Deep Search run.
  5. With an active project that has no discovered related papers yet, approved Deep Search runs the same discovery refresh before streaming; projects that already have discovered papers keep the existing paper list.
  6. The stream renders an expandable `Show thinking` panel with the full research path visible immediately, advances the active phase from `status` events, keeps a live elapsed timer/progress shimmer while waiting for the next backend event, creates the final answer bubble only when report text is available, and shows `source` / `done` event citations in the right context panel below `Related Papers`. Deep Search backend frames include SSE padding comments so small status updates are less likely to be buffered until the end of the run.
- Selecting a project in the sidebar re-hydrates ranked papers, restores the latest saved grounded project conversation, restores the last selected paper set from localStorage when possible, preserves intentionally empty selections, and restores the last-open project after refresh.
- Each recent project row now exposes a hover/focus overflow menu for rename and delete actions.

## Files

- `app/layout.tsx`, `app/globals.css`, `tailwind.config.ts` — app shell and styling tokens.
- `app/login/page.tsx` — sign in / register.
- `app/chat/page.tsx` — auth-gated workspace.
- `app/admin/usage/page.tsx`, `app/admin/usage/users/page.tsx`, `app/admin/usage/components.tsx` — admin-only token usage dashboard, selected-user analysis, and shared monitor UI.
- `components/AuthProvider.tsx` — token/user state.
- `components/ChatProvider.tsx` — orchestrates project creation, composer PDF uploads, selected-paper persistence, grounded project conversations, and Deep Search streaming/source metadata.
- `components/Sidebar.tsx`, `components/ChatWorkspace.tsx`, `components/ContextPanel.tsx` — workspace panels, composer upload UI, admin monitor navigation, uploaded-paper markers, sentence-level Deep Search source buttons, and the Papers / Graph tab switcher in the right context panel.
- `components/CitationGraph.tsx` — Connected-Papers-style force-directed citation neighborhood for one selected seed paper, dynamically imported (`ssr: false`) and backed by `GET /projects/{id}/papers/{paper_id}/citation-graph`; node clicks open in-app previews, existing project papers are marked, missing related papers can be imported, graph payloads are cached in workspace state, and a List view exposes the same data as semantic HTML.
- `lib/api.ts` — typed `fetch` wrapper, SSE stream parsers, and backend DTO types.

## Current limitations

- No frontend tests are present yet.
- The frontend still does not expose full reference-file management or writer generation.
- The UI is a shipped shell, not the full multi-stage product flow described in `docs/user-journey.md`.
