# Admin Token Usage Monitoring Page

## Summary

- Move token usage out of `/chat` and create an admin-only `/admin/usage` monitoring page.
- The page must visually match the existing Confluex web app: same warm background, green/brown palette, compact layout, `Inter` UI text, and `Noto Serif` only where the app already uses headline typography.
- Protect access with an `ADMIN_EMAILS` allowlist for v1.

## Key Changes

### Backend

- Add `ADMIN_EMAILS` config and an admin dependency.
- Add `GET /admin/access` and `GET /admin/token-usage`.
- Aggregate existing `ai_usage_events` across all users/projects; no DB migration is needed.

### Frontend

- Add `/admin/usage` route.
- Remove the token usage card from `ContextPanel.tsx`.
- Keep chat focused on research: related papers only in the right panel.
- Add an admin "Usage Monitor" entry in the existing sidebar/footer area, visible only to allowlisted admins.

### Visual Design

- Reuse existing Tailwind tokens from `tailwind.config.ts`: `background`, `surface-container`, `surface-container-low`, `outline`, `primary`, `secondary`, `hint`, and `accent`.
- Use `font-ui` / `Inter` for dashboard labels, tables, filters, and numbers.
- Use `font-headline` / `Noto Serif` sparingly for the page title only.
- Match current app density: compact panels, thin borders, small uppercase labels, muted dividers, and tabular numbers.
- Do not introduce a marketing hero, gradients, decorative blobs, or an unrelated theme.

## Dashboard Content

- Header: "Token Usage Monitor", admin badge, refresh action, and back-to-chat action.
- Filters: date range segmented control, user filter, and project filter.
- KPI row: total tokens, credits, requests, prompt tokens, completion tokens, and cached tokens.
- Main sections: daily usage trend, usage by feature, usage by model, project/user drilldown table, and recent usage events.
- States: loading, empty usage data, and non-admin `403` state.

## Public API and Types

- `GET /admin/access -> { is_admin: boolean }`
- `GET /admin/token-usage?date_from=&date_to=&user_id=&project_id=`
- Usage response includes totals, prompt/completion/reasoning/cached tokens, credits, request count, `by_day`, `by_feature`, `by_model`, `by_user`, `by_project`, and `recent_events`.
- Keep existing `GET /projects/{id}/token-usage` for compatibility, but no longer render it in chat.

## Test Plan

- Backend tests for admin allowlist access, non-admin `403`, cross-user aggregation, filters, and the existing project usage endpoint.
- Frontend build with `npm run build`.
- Manual UI checks: chat page no longer shows token usage, admin page matches existing colors/fonts, and non-admin users are blocked.
- Repo checks: `uv run ruff check .`, `uv run mypy backend/`, and focused pytest for usage/admin routes.

## Assumptions

- `ADMIN_EMAILS` is comma-separated.
- Default dashboard range is last 30 days.
- v1 is monitoring only: no budgets, alerts, export, or billing controls.
- Usage is based only on provider-reported OpenRouter events already persisted in `ai_usage_events`.

## Stitch Prompt

```text
Design a Confluex admin page for token usage monitoring that matches the existing web app visual system.

Existing design system:
- Background: warm off-white #faf9f7.
- Surfaces: #ffffff, #f4f3f1, #efeeec.
- Primary: deep research green #1d2d18.
- Secondary/muted text: #596154, #8C8375.
- Accent: muted brown #5D4037.
- Borders: soft gray-green outline #747870 at low opacity.
- Fonts: Inter for UI/body, Noto Serif only for headline/page title.
- Style: compact academic operations dashboard, subtle borders, small uppercase labels, tabular numbers, restrained spacing.

Screen:
- Admin route/page, not chat.
- Title: "Token Usage Monitor" using Noto Serif.
- Header includes Confluex identity, small "Admin" badge, refresh icon button, and "Back to chat" action.
- Filter bar with segmented date range: 7 days, 30 days selected, All time; user filter; project filter.
- KPI row: Total tokens, Credits used, Requests, Prompt tokens, Completion tokens, Cached tokens.
- Main area:
  1. Daily usage trend.
  2. Usage by feature.
  3. Usage by model.
  4. Project drilldown table: project, user email, requests, tokens, credits.
  5. Recent events table: time, user, project, feature, model, tokens, credits.
- Include empty state and non-admin 403 state.
- Keep it dense, calm, and scannable. No hero section, no marketing copy, no new color theme, no decorative gradients or blobs.
```
