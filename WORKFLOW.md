# Agent Workflow For Code-Changing Prompts

Use this workflow whenever a user prompt asks an AI coding agent to change repository files. This file complements `AGENTS.md`; if there is a conflict, follow `AGENTS.md`.

## 1. Classify The Prompt

Before editing, decide what kind of change is being requested:

- **Bug fix:** reproduce or inspect the failing path, then verify the fixed behavior.
- **Feature change:** identify entrypoints, data flow, UI/API contract, tests, and docs.
- **Refactor:** preserve behavior and run checks before and after when practical.
- **Docs/config only:** still verify references, commands, and affected workflow rules.
- **Review only:** do not edit unless the user explicitly asks for changes.

If the request is materially ambiguous, ask a concise clarification question. If a reasonable assumption is safe, state it and continue.

## 2. Required Context Before Editing

Read enough local context to understand the path end to end:

1. Read `AGENTS.md`.
2. Read `README.md` for current scope and setup.
3. Read `docs/feature-map.md` to locate relevant code, tests, docs, and config.
4. Open the exact implementation files being changed.
5. Open related tests before behavior changes.
6. Check whether public docs, examples, or config files must change.
7. Check `git status --short` and avoid overwriting unrelated user changes.

Do not rely on filename guesses alone.

## 3. Define Success Criteria

Translate the prompt into observable outcomes before changing code:

- What user-visible behavior should change?
- What API/schema/type contract must be preserved or updated?
- What files are expected to change?
- What tests or checks will prove the change?
- What docs or logs must be updated?

For non-trivial work, use a short plan:

```text
1. Inspect [path] -> verify: understand current behavior
2. Change [path] -> verify: focused test/check
3. Update docs/logs -> verify: lint or diff check
```

## 4. Implement Surgically

Make the smallest correct change:

- Match existing patterns and naming.
- Do not refactor unrelated code.
- Do not add configuration or abstractions without a concrete need.
- Do not invent data, counts, IDs, source titles, or behavior not backed by runtime state.
- Keep public compatibility fields when existing clients may depend on them.
- Clean up only unused code created or made obsolete by your change.

## 5. Testing Expectations

Prefer tests that prove behavior, not just shape:

- For bug fixes, add a regression test that would fail before the fix.
- For streaming/async behavior, prove event order or state timing where practical.
- For frontend contracts, update TypeScript types and static/behavior tests when available.
- For API/schema changes, test required fields, backward compatibility, and error cases.

Run the narrowest useful checks first, then broader checks if risk warrants it.

## 6. Verification Checklist

Pick commands appropriate to the changed files. Common checks:

```bash
python -m pytest <relevant tests> -q
python -m ruff check <changed python files>
python -m mypy <changed typed python files>
cd frontend && ./node_modules/.bin/tsc --noEmit
git diff --check
```

If a required check cannot run, record why in the final response and in the log entry.

## 7. Documentation And Logs

When repository files change:

- Update `JOURNAL.md` with a timestamped entry.
- Use `AI_WORKLOG.md` as the detail reference when it exists or is part of the current work.
- Update user-facing docs when behavior, setup, API surface, feature ownership, or config changes.
- Do not manually edit `.ai-log/*.jsonl`; prompt logging is automatic.

Journal entries should include:

- Request summary.
- Files changed.
- Current status.
- Verification run or blockers.

## 8. Pull Request Rules

Before creating a PR:

1. Ensure `bash scripts/setup_hooks.sh` has been run.
2. Use a short descriptive PR title.
3. Include this PR body format:

```markdown
## Summary
<description of changes>

## Changes
- <list of changed files>
```

Never create a PR without satisfying the repository rules in `AGENTS.md`.

## 9. Final Response Template

Keep the final response concise and concrete:

- What changed.
- Why it solves the request.
- Which tests/checks passed.
- Any checks not run and why.
- Any remaining risk or follow-up that matters.

