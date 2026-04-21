"""Push BACKLOG.md into a Trello board.

One-shot importer that reads the structured sections of BACKLOG.md and
creates matching lists, labels, and cards on a Trello board via the REST API.

Usage:
    python scripts/sync_backlog_to_trello.py \
        --board-id cy5N7gyG \
        --backlog BACKLOG.md

Environment variables (required):
    TRELLO_KEY     Your personal Trello API key
    TRELLO_TOKEN   A token you authorized for that key

How to get the credentials:
    1. Key:    https://trello.com/app-key   -> copy the "Key" field.
    2. Token:  on the same page, click the "Token" link and approve.
               Copy the returned token string.

Design notes:
    * Idempotent enough for a one-shot import: if a list/label with the same
      name already exists on the board it is reused instead of duplicated.
      Cards are NOT deduplicated by title; re-running will create duplicates,
      so run this once, then manage cards in Trello going forward.
    * Story cards are created with acceptance criteria as a Trello checklist
      and tasks as a second checklist, matching the structure in BACKLOG.md.
    * Status -> list routing:
          Done / shipped       -> "Done"
          In Progress / Review -> "In Progress"
          Ready / Current focus-> "Ready"
          Blocked              -> "Blocked"
          Todo / Backlog       -> "Backlog"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

# On Windows cp1252 consoles the backlog's emojis would crash print(); force utf-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass
from dataclasses import dataclass, field
from pathlib import Path

import urllib.parse
import urllib.request
import urllib.error
import json


TRELLO_API = "https://api.trello.com/1"


# ----- Trello client (stdlib only, no extra deps) ----------------------------


class TrelloClient:
    def __init__(self, key: str, token: str) -> None:
        self.key = key
        self.token = token

    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None) -> dict:
        params = dict(params or {})
        params["key"] = self.key
        params["token"] = self.token
        url = f"{TRELLO_API}{path}?{urllib.parse.urlencode(params)}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8") or "{}"
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                msg = e.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Trello {method} {path} -> {e.code}: {msg}") from e
            except urllib.error.URLError as e:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Trello {method} {path} network error: {e}") from e
        raise RuntimeError("Trello request retries exhausted")

    def get_board(self, board_id: str) -> dict:
        return self._request("GET", f"/boards/{board_id}")

    def list_board_lists(self, board_id: str) -> list[dict]:
        return self._request("GET", f"/boards/{board_id}/lists")

    def create_list(self, board_id: str, name: str, pos: str | float = "bottom") -> dict:
        return self._request(
            "POST", "/lists",
            params={"name": name, "idBoard": board_id, "pos": pos},
        )

    def list_board_labels(self, board_id: str) -> list[dict]:
        return self._request("GET", f"/boards/{board_id}/labels", params={"limit": 1000})

    def create_label(self, board_id: str, name: str, color: str | None) -> dict:
        params = {"name": name, "idBoard": board_id}
        if color:
            params["color"] = color
        return self._request("POST", "/labels", params=params)

    def create_card(self, list_id: str, name: str, desc: str,
                    label_ids: list[str]) -> dict:
        return self._request(
            "POST", "/cards",
            params={
                "idList": list_id,
                "name": name,
                "desc": desc,
                "idLabels": ",".join(label_ids),
                "pos": "bottom",
            },
        )

    def add_checklist(self, card_id: str, name: str, items: list[tuple[str, bool]]) -> None:
        checklist = self._request(
            "POST", "/checklists",
            params={"idCard": card_id, "name": name, "pos": "bottom"},
        )
        checklist_id = checklist["id"]
        for text, checked in items:
            self._request(
                "POST", f"/checklists/{checklist_id}/checkItems",
                params={
                    "name": text[:16384],
                    "checked": "true" if checked else "false",
                    "pos": "bottom",
                },
            )


# ----- Markdown parsing -------------------------------------------------------


PRIORITY_COLOR = {
    "P0": "red",
    "P1": "orange",
    "P2": "yellow",
    "Nice": "lime",
}

PHASE_COLOR = {
    "Phase 1": "sky",
    "Phase 2": "sky",
    "Phase 3": "sky",
    "Phase 3W": "sky",
    "Phase 4": "sky",
    "Phase 5": "sky",
    "Post-MVP": "purple",
}

AREA_COLOR = {
    "backend": "blue",
    "frontend": "pink",
    "infra": "black",
    "docs": "lime",
}


@dataclass
class Story:
    story_id: str
    title: str
    epic_id: str
    epic_title: str
    priority: str
    phase: str
    status: str
    body: str
    acceptance: list[tuple[str, bool]] = field(default_factory=list)
    tasks: list[tuple[str, bool, str]] = field(default_factory=list)  # (text, checked, priority)


@dataclass
class Epic:
    epic_id: str
    title: str
    priority: str
    phase: str
    status: str
    body: str


def _status_to_list(status: str) -> str:
    s = status.lower()
    if "done" in s or "shipped" in s or "✅" in status:
        return "Done"
    if "in progress" in s or "in review" in s or "🔄" in status or "👀" in status:
        return "In Progress"
    if "ready" in s or "🟡" in status:
        return "Ready"
    if "blocked" in s or "⛔" in status:
        return "Blocked"
    if "deferred" in s or "🗄" in status:
        return "Later"
    return "Backlog"


def parse_backlog(path: Path) -> tuple[list[Epic], list[Story]]:
    text = path.read_text(encoding="utf-8")

    # Split on "## Epic E## — ..." headers.
    epic_header = re.compile(r"^## Epic (E\d+) — (.+?) \((P0|P1|P2|Nice), (.+?)\)", re.MULTILINE)
    epics: list[Epic] = []
    stories: list[Story] = []

    headers = list(epic_header.finditer(text))
    for idx, m in enumerate(headers):
        epic_id = m.group(1)
        epic_title = m.group(2).strip()
        priority = m.group(3).strip()
        phase = m.group(4).strip()
        status_tail = text[m.end():text.find("\n", m.end())]
        status = status_tail.replace("—", "").strip() or "In Progress"
        section_start = m.end()
        section_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        section = text[section_start:section_end]

        # Extract the paragraph directly after the header as the epic body.
        goal_match = re.search(r"\*\*Goal:\*\*(.+?)(?:\n\n|\n###|\n##)", section, re.DOTALL)
        epic_body_md = (goal_match.group(1).strip() if goal_match else "").strip()
        epics.append(Epic(epic_id, epic_title, priority, phase, status, epic_body_md))

        # Stories look like "### S-07 — Title"
        story_header = re.compile(r"^### (S-\d+) — (.+)$", re.MULTILINE)
        story_matches = list(story_header.finditer(section))
        for s_idx, sm in enumerate(story_matches):
            sid = sm.group(1)
            stitle = sm.group(2).strip()
            s_start = sm.end()
            s_end = story_matches[s_idx + 1].start() if s_idx + 1 < len(story_matches) else len(section)
            block = section[s_start:s_end]

            # Story body = lines until "**Acceptance**" or "| ID |" table
            body_end = len(block)
            for marker in ("**Acceptance**", "| ID | Task"):
                idx_marker = block.find(marker)
                if 0 <= idx_marker < body_end:
                    body_end = idx_marker
            body = block[:body_end].strip()

            # Acceptance criteria lines: "- [ ] ..." or "- [x] ..."
            acceptance: list[tuple[str, bool]] = []
            acc_block = ""
            acc_match = re.search(r"\*\*Acceptance\*\*(.+?)(?:\n\n|\n\| ID |\Z)", block, re.DOTALL)
            if acc_match:
                acc_block = acc_match.group(1)
                for ln in acc_block.splitlines():
                    ln = ln.strip()
                    m2 = re.match(r"-\s*\[( |x|X)\]\s*(.+)$", ln)
                    if m2:
                        acceptance.append((m2.group(2).strip(), m2.group(1).lower() == "x"))

            # Task table rows: | T-xxx | Task | Priority | Status | Source |
            tasks: list[tuple[str, bool, str]] = []
            task_table = re.search(
                r"\| ID \| Task \| Priority \| Status \|.*?\n((?:\|.*\n?)+)",
                block,
            )
            if task_table:
                for row in task_table.group(1).splitlines():
                    cells = [c.strip() for c in row.strip().strip("|").split("|")]
                    if len(cells) < 4 or cells[0].startswith("---"):
                        continue
                    tid, ttitle, tprio, tstatus = cells[0], cells[1], cells[2], cells[3]
                    if not tid.startswith("T-"):
                        continue
                    checked = "✅" in tstatus or "done" in tstatus.lower()
                    tasks.append((f"{tid} — {ttitle} ({tprio})", checked, tprio))

            stories.append(Story(
                story_id=sid,
                title=stitle,
                epic_id=epic_id,
                epic_title=epic_title,
                priority=priority,
                phase=phase if phase.startswith("Phase") or phase == "Post-MVP" else f"Phase {phase}",
                status=status,
                body=body,
                acceptance=acceptance,
                tasks=tasks,
            ))

    return epics, stories


# ----- Sync orchestration -----------------------------------------------------


WANTED_LISTS = ["Inbox", "Backlog", "Ready", "In Progress", "Blocked", "Done", "Later"]

WANTED_LABELS: list[tuple[str, str | None]] = [
    ("P0", "red"),
    ("P1", "orange"),
    ("P2", "yellow"),
    ("Nice", "lime"),
    ("epic", "green"),
    ("story", "green"),
    ("Phase 1", "sky"),
    ("Phase 2", "sky"),
    ("Phase 3", "sky"),
    ("Phase 3W", "sky"),
    ("Phase 4", "sky"),
    ("Phase 5", "sky"),
    ("Post-MVP", "purple"),
    ("backend", "blue"),
    ("frontend", "pink"),
    ("infra", "black"),
]


def ensure_lists(client: TrelloClient, board_id: str) -> dict[str, str]:
    existing = {lst["name"]: lst["id"] for lst in client.list_board_lists(board_id)}
    result: dict[str, str] = {}
    for name in WANTED_LISTS:
        if name in existing:
            result[name] = existing[name]
        else:
            print(f"  + creating list: {name}")
            result[name] = client.create_list(board_id, name)["id"]
    return result


def ensure_labels(client: TrelloClient, board_id: str) -> dict[str, str]:
    existing = {lbl["name"]: lbl["id"] for lbl in client.list_board_labels(board_id) if lbl.get("name")}
    result: dict[str, str] = {}
    for name, color in WANTED_LABELS:
        if name in existing:
            result[name] = existing[name]
        else:
            print(f"  + creating label: {name} ({color})")
            result[name] = client.create_label(board_id, name, color)["id"]
    return result


def _infer_area(story: Story) -> str | None:
    blob = (story.title + " " + story.body).lower()
    if "frontend" in blob or "page" in blob or "screen" in blob or "ui" in blob:
        return "frontend"
    if "deploy" in blob or "cors" in blob or "dockerfile" in blob or "railway" in blob:
        return "infra"
    return "backend"


def build_card(story: Story) -> tuple[str, str, list[str]]:
    title = f"[{story.story_id}] {story.title}"
    desc_lines = [
        f"**Epic:** {story.epic_id} — {story.epic_title}",
        f"**Priority:** {story.priority}",
        f"**Phase:** {story.phase}",
        f"**Status:** {story.status}",
        "",
        story.body,
        "",
        "---",
        f"Linked from `BACKLOG.md` — story `{story.story_id}` under epic `{story.epic_id}`.",
    ]
    desc = "\n".join(desc_lines).strip()
    labels: list[str] = [story.priority]
    if story.phase in {"Phase 1", "Phase 2", "Phase 3", "Phase 3W", "Phase 4", "Phase 5", "Post-MVP"}:
        labels.append(story.phase)
    labels.append("story")
    area = _infer_area(story)
    if area:
        labels.append(area)
    return title, desc, labels


def build_epic_card(epic: Epic) -> tuple[str, str, list[str]]:
    title = f"[{epic.epic_id}] EPIC — {epic.title}"
    desc = (
        f"**Priority:** {epic.priority}\n"
        f"**Phase:** {epic.phase}\n"
        f"**Status:** {epic.status}\n\n"
        f"{epic.body}\n\n"
        f"Stories for this epic live as separate cards tagged `{epic.epic_id}` in the description."
    )
    labels = [epic.priority, "epic"]
    if epic.phase in {"Phase 1", "Phase 2", "Phase 3", "Phase 3W", "Phase 4", "Phase 5", "Post-MVP"}:
        labels.append(epic.phase)
    return title, desc, labels


def main() -> int:
    parser = argparse.ArgumentParser(description="Push BACKLOG.md into a Trello board.")
    parser.add_argument("--board-id", required=True,
                        help="Trello board shortLink (e.g. cy5N7gyG) or full board id.")
    parser.add_argument("--backlog", default="BACKLOG.md", help="Path to BACKLOG.md")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse the backlog and print what would be created.")
    args = parser.parse_args()

    backlog_path = Path(args.backlog)
    if not backlog_path.exists():
        print(f"error: {backlog_path} not found", file=sys.stderr)
        return 2

    epics, stories = parse_backlog(backlog_path)
    print(f"Parsed {len(epics)} epics and {len(stories)} stories from {backlog_path}.")

    if args.dry_run:
        for epic in epics:
            print(f"  EPIC {epic.epic_id} ({epic.priority}, {epic.status}) — {epic.title}")
        for s in stories:
            print(f"    {s.story_id} [{s.priority}] {s.status} -> {_status_to_list(s.status)} — {s.title}")
            for a_text, a_checked in s.acceptance:
                print(f"        AC[{'x' if a_checked else ' '}] {a_text}")
            for t_text, t_checked, _ in s.tasks:
                print(f"        T [{'x' if t_checked else ' '}] {t_text}")
        return 0

    key = os.environ.get("TRELLO_KEY")
    token = os.environ.get("TRELLO_TOKEN")
    if not key or not token:
        print("error: set TRELLO_KEY and TRELLO_TOKEN env vars", file=sys.stderr)
        return 2

    client = TrelloClient(key, token)
    board = client.get_board(args.board_id)
    board_id = board["id"]
    print(f"Board: {board['name']} (id={board_id})")

    print("Ensuring lists...")
    lists = ensure_lists(client, board_id)
    print("Ensuring labels...")
    labels = ensure_labels(client, board_id)

    print("Creating epic cards...")
    for epic in epics:
        title, desc, lbls = build_epic_card(epic)
        list_id = lists[_status_to_list(epic.status)]
        label_ids = [labels[name] for name in lbls if name in labels]
        card = client.create_card(list_id, title, desc, label_ids)
        print(f"  + {title}  ->  {_status_to_list(epic.status)}")
        _ = card

    print("Creating story cards...")
    for s in stories:
        title, desc, lbls = build_card(s)
        list_id = lists[_status_to_list(s.status)]
        label_ids = [labels[name] for name in lbls if name in labels]
        card = client.create_card(list_id, title, desc, label_ids)
        card_id = card["id"]
        print(f"  + {title}  ->  {_status_to_list(s.status)}")
        if s.acceptance:
            client.add_checklist(card_id, "Acceptance criteria", s.acceptance)
        if s.tasks:
            client.add_checklist(
                card_id, "Tasks",
                [(text, checked) for text, checked, _ in s.tasks],
            )

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
