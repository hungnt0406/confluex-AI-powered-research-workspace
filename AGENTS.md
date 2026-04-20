# Agent Guidelines

## Mandatory Rules When Using AI Coding Agents

### 1. AI Prompt Logging (Automatic)

Prompts are **automatically logged** via hooks when you use any supported AI tool.
You do **not** need to manually update `PROMPT_LOG.md`.

Supported tools and their hook configs:
| Tool | Config file |
|---|---|
| Claude Code | `.claude/settings.json` |
| Cursor | `.cursor/hooks.json` |
| OpenAI Codex | `.codex/hooks.json` |
| Gemini CLI | `.gemini/settings.json` |
| GitHub Copilot | `.github/hooks/hooks.json` |

Logs are saved to `.ai-log/session.jsonl` and submitted automatically on `git push`.

### 2. Setup (One-time)

```bash
# Install git pre-push hook
bash scripts/setup_hooks.sh
```

`AI_LOG_SERVER` and `AI_LOG_API_KEY` are already set in `.env.example`.

### 3. Pull Request Requirements

- **Title**: Short description of the change
- **Description**: Must include:
  - Summary of changes
  - List of changed files

PR description format:

```
## Summary
<description of changes>

## Changes
- <list of changed files>
```

### 4. Rules for AI Agents

If you are an AI coding agent (Claude Code, Cursor, Copilot, Codex, Gemini, etc.):

- **MUST NOT** create a PR without first ensuring `bash scripts/setup_hooks.sh` has been run
- **MUST** include a clear PR description with summary and changed files
- **MUST** update `JOURNAL.md` whenever you make repository changes, using a timestamped entry that summarizes the request, files changed, and current status. Use `AI_WORKLOG.md` as the detail reference.
- **DO NOT** commit `.ai-log/*.jsonl` files (they are gitignored)
- Logging happens automatically — do not ask users to log prompts manually

## Recommended Entry Workflow For Agents

When entering this repository to implement or modify a feature, follow this order before editing code:

1. Read `AGENTS.md` for repository rules.
2. Read `README.md` for current scope, setup, and API surface.
3. Read `docs/feature-map.md` to locate the relevant code, tests, docs, and config.
4. Open the exact implementation files for the feature you are changing.
5. Read the related tests before making behavior changes.
6. Check whether public docs must change because of the implementation.
7. Make the smallest correct change that satisfies the request.
8. Verify the change with the most relevant tests or checks you can run.
9. Update `JOURNAL.md` if you changed repository files.

Minimum expectation before implementing:

- Do not rely on filename guesses alone.
- Do not edit based only on `README.md` or plans.
- Read enough local code to understand the request path end-to-end: entrypoint, main logic, data model or schema, and relevant tests.

## Working Principles For Agents

These principles are intended to improve reliability, not to force unnecessary ceremony.

| Principle | Addresses |
|---|---|
| **Think Before Coding** | Wrong assumptions, hidden confusion, missed tradeoffs |
| **Simplicity First** | Overcomplication, speculative abstractions |
| **Surgical Changes** | Unnecessary churn, touching unrelated code |
| **Goal-Driven Execution** | Vague progress, weak verification |

### 1. Think Before Coding

**Do not assume silently. Surface uncertainty early.**

- State important assumptions when they affect the implementation.
- If the request is materially ambiguous, clarify it instead of guessing.
- If there are multiple reasonable approaches, choose one deliberately and say why.
- Push back when a simpler or safer approach better fits the stated goal.
- Do not hide confusion behind confident code.

### 2. Simplicity First

**Implement the smallest solution that fully solves the requested problem.**

- Do not add features that were not requested.
- Do not introduce abstractions until they are justified by actual reuse or complexity.
- Do not add configurability, extension points, or defensive structure without a concrete need.
- Prefer straightforward code over clever code.
- If the solution feels larger than the problem, simplify it.

### 3. Surgical Changes

**Change only what the request requires.**

- Touch the minimum set of files and lines needed for the task.
- Do not refactor unrelated code while implementing the request.
- Match local patterns unless there is a clear reason not to.
- If you notice unrelated problems, mention them separately instead of silently fixing them.
- Clean up only the unused imports, variables, helpers, or docs made obsolete by your own change.

### 4. Goal-Driven Execution

**Define success, implement, then verify.**

- Translate the request into observable success criteria before changing code.
- Prefer verification that proves the requested behavior, especially tests when practical.
- For bug fixes, reproduce the failure first when practical, then verify the fix.
- For behavior changes, update or add the narrowest tests that prove the new behavior.
- For refactors, preserve behavior and verify before and after where possible.

For non-trivial tasks, use a brief plan like:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```
