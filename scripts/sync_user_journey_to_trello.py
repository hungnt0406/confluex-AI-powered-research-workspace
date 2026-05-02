"""Render docs/user-journey.md as a user-journey map on a Trello board.

Layout:
    * Each *list* (column) on the board is one stage of the journey.
    * Each *card* in that list is one "lane" of the journey map:
          Goal / Actions / System / Feeling / Pain / Opportunity.
    * Lane colour-coded labels make the rows readable across stages.
    * Extra lists at the start and end hold persona/overview, critical
      moments of truth, and shipped-vs-gap summary.

Reading the board left-to-right walks the user through every stage.
Reading top-to-bottom inside a list tells you what happens in that stage.

Usage:
    python scripts/sync_user_journey_to_trello.py \
        --board-id QEQiRDT2 \
        --journey docs/user-journey.md

Required env vars (same as sync_backlog_to_trello.py):
    TRELLO_KEY
    TRELLO_TOKEN

See the docstring in scripts/sync_backlog_to_trello.py for how to get them.
Re-running this script will create duplicate cards, so run it once on a
board and manage cards in Trello after that.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


TRELLO_API = "https://api.trello.com/1"


# ----- Trello client ---------------------------------------------------------


class TrelloClient:
    def __init__(self, key: str, token: str) -> None:
        self.key = key
        self.token = token

    def _request(self, method: str, path: str,
                 params: dict | None = None, body: dict | None = None) -> dict:
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


# ----- Journey schema --------------------------------------------------------


# order defines the top-to-bottom ("lane") order of cards within a stage list.
LANES: list[tuple[str, str, str]] = [
    # (lane_key, card_icon + label, trello_label_color)
    ("goal",        "🎯 Goal",        "sky"),
    ("actions",     "🎬 Actions",     "green"),
    ("system",      "⚙️ System",      "blue"),
    ("feeling",     "💗 Feeling",     "pink"),
    ("pain",        "⚠️ Pain points", "red"),
    ("opportunity", "💡 Opportunity", "yellow"),
]

# status labels for the stage header cards
STATUS_LABELS: list[tuple[str, str]] = [
    ("✅ Shipped", "lime"),
    ("🟡 Partial", "orange"),
    ("⬜ Planned", "black"),
]


# mapping of markdown bullet prefixes -> lane key. Intentionally forgiving.
BULLET_TO_LANE: dict[str, str] = {
    "user goal":       "goal",
    "goal":            "goal",
    "user actions":    "actions",
    "actions":         "actions",
    "system":          "system",
    "touchpoint":      "system",
    "touchpoints":     "system",
    "feeling":         "feeling",
    "feelings":        "feeling",
    "pain points":     "pain",
    "pain point":      "pain",
    "pain":            "pain",
    "opportunity":     "opportunity",
    "opportunities":   "opportunity",
}


# per-stage delivery status for the stage header card.
# Derived from the "Gap Check Versus Current Code" section of user-journey.md.
STAGE_STATUS: dict[int, str] = {
    1: "⬜ Planned",   # Discover & decide to try (landing page)
    2: "🟡 Partial",   # Sign up / log in (login shipped, onboarding planned)
    3: "🟡 Partial",   # Create project (via chat workspace, dedicated UI planned)
    4: "⬜ Planned",   # Upload seed PDFs (backend partial, UI planned)
    5: "🟡 Partial",   # Discovery pipeline (backend shipped, SSE planned)
    6: "🟡 Partial",   # Ranked paper list (ranked view shipped, richer UI planned)
    7: "🟡 Partial",   # Paper grounded Q&A (backend shipped, per-paper UI planned)
    8: "🟡 Partial",   # Writer generation (backend shipped, workspace UI planned)
    9: "🟡 Partial",   # Review output + QA flags (backend shipped, review UI planned)
    10: "⬜ Planned",  # Iterate / regenerate
    11: "🟡 Partial",  # Copy / export (formatter shipped, downloads planned)
    12: "🟡 Partial",  # Return & manage library (list/delete shipped, tagging planned)
}


@dataclass
class Stage:
    number: int
    title: str
    lanes: dict[str, str] = field(default_factory=dict)


@dataclass
class JourneyDoc:
    persona: str
    goal: str
    flow_mermaid: str
    stages: list[Stage]
    critical_moments: list[str]
    shipped: list[str]
    gaps: list[str]


# ----- Parser ----------------------------------------------------------------


STAGE_HEADER_RE = re.compile(r"^### Stage (\d+) — (.+)$", re.MULTILINE)
H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
BULLET_RE = re.compile(r"^- \*\*([^*]+?):\*\*\s*(.*)$")
SUBBULLET_RE = re.compile(r"^\s+-\s+(.*)$")


def _extract_section(text: str, heading: str) -> str:
    """Return the slice of `text` under `## heading` up to the next `## ` header."""
    pattern = re.compile(rf"^## {re.escape(heading)}\s*$", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        return ""
    start = m.end()
    next_m = H2_RE.search(text, pos=start)
    end = next_m.start() if next_m else len(text)
    return text[start:end].strip()


def _parse_stage_bullets(body: str) -> dict[str, str]:
    """Parse a stage's markdown body into lane_key -> combined text."""
    lanes: dict[str, list[str]] = {}
    current_lane: str | None = None
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            current_lane = None
            continue
        m = BULLET_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            lane = BULLET_TO_LANE.get(key)
            if lane is None:
                current_lane = None
                continue
            rest = m.group(2).strip()
            lanes.setdefault(lane, [])
            if rest:
                lanes[lane].append(rest)
            current_lane = lane
            continue
        sub = SUBBULLET_RE.match(line)
        if sub and current_lane is not None:
            lanes[current_lane].append(f"- {sub.group(1).strip()}")
            continue
        # free-form continuation lines stay in the active lane
        if current_lane is not None and line.strip():
            lanes[current_lane].append(line.strip())
    return {k: "\n".join(v).strip() for k, v in lanes.items()}


def parse_journey(path: Path) -> JourneyDoc:
    text = path.read_text(encoding="utf-8")

    persona = _extract_section(text, "Primary Persona")
    # The Primary Persona section also contains the product goal paragraph.
    goal_match = re.search(r"\*\*Goal:\*\*\s*(.+?)(?:\n\n|\Z)", persona, re.DOTALL)
    goal = goal_match.group(1).strip() if goal_match else ""

    flow_section = _extract_section(text, "High-Level Flow")
    flow_mermaid = ""
    m = re.search(r"```mermaid(.+?)```", flow_section, re.DOTALL)
    if m:
        flow_mermaid = m.group(1).strip()

    # Parse every stage block.
    headers = list(STAGE_HEADER_RE.finditer(text))
    stages: list[Stage] = []
    for i, hm in enumerate(headers):
        number = int(hm.group(1))
        title = hm.group(2).strip()
        start = hm.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]
        # Cap at the next top-level "## " so we don't bleed into following sections.
        next_h2 = H2_RE.search(body)
        if next_h2:
            body = body[:next_h2.start()]
        stages.append(Stage(number=number, title=title, lanes=_parse_stage_bullets(body)))

    # Critical moments of truth — bullet list under that section.
    critical_section = _extract_section(text, "Critical Moments Of Truth")
    critical_moments = [
        m.group(1).strip()
        for m in re.finditer(r"^- (.+)$", critical_section, re.MULTILINE)
    ]

    # Gap check — Shipped vs Still missing.
    gap_section = _extract_section(text, "Gap Check Versus Current Code")
    shipped: list[str] = []
    gaps: list[str] = []
    bucket: list[str] | None = None
    for raw in gap_section.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("shipped"):
            bucket = shipped
            continue
        if lower.startswith("still missing") or lower.startswith("gaps"):
            bucket = gaps
            continue
        m = re.match(r"^- (.+)$", line)
        if m and bucket is not None:
            bucket.append(m.group(1).strip())

    return JourneyDoc(
        persona=persona,
        goal=goal,
        flow_mermaid=flow_mermaid,
        stages=stages,
        critical_moments=critical_moments,
        shipped=shipped,
        gaps=gaps,
    )


# ----- Board rendering -------------------------------------------------------


def ensure_labels(client: TrelloClient, board_id: str) -> dict[str, str]:
    existing = {
        lbl["name"]: lbl["id"]
        for lbl in client.list_board_labels(board_id)
        if lbl.get("name")
    }
    result: dict[str, str] = {}
    wanted: list[tuple[str, str]] = (
        [(display, color) for _key, display, color in LANES]
        + STATUS_LABELS
        + [
            ("📖 Overview", "purple"),
            ("🎯 Critical Moments", "red"),
            ("Gap check", "black"),
        ]
    )
    for name, color in wanted:
        if name in existing:
            result[name] = existing[name]
        else:
            print(f"  + creating label: {name} ({color})")
            result[name] = client.create_label(board_id, name, color)["id"]
    return result


def ensure_list(client: TrelloClient, board_id: str,
                existing: dict[str, str], name: str) -> str:
    if name in existing:
        return existing[name]
    print(f"  + creating list: {name}")
    new = client.create_list(board_id, name)
    existing[name] = new["id"]
    return new["id"]


def _stage_list_name(stage: Stage) -> str:
    return f"Stage {stage.number} — {stage.title}"


def render_overview(client: TrelloClient, list_id: str,
                    doc: JourneyDoc, labels: dict[str, str]) -> None:
    # Persona card
    desc = (
        "**Product goal**\n\n"
        f"{doc.goal or '—'}\n\n"
        "---\n\n"
        f"{doc.persona}"
    )
    client.create_card(list_id, "👤 Personas & product goal", desc, [labels["📖 Overview"]])

    # High-level flow card (mermaid preserved in description for teammates who can render it)
    flow_desc = (
        "High-level journey flow, copied from `docs/user-journey.md`.\n\n"
        "```mermaid\n"
        f"{doc.flow_mermaid or ''}\n"
        "```\n\n"
        "_Open `docs/user-journey.md` for the latest version._"
    )
    client.create_card(list_id, "🗺️ High-level flow", flow_desc, [labels["📖 Overview"]])

    # How to read the board
    how_desc = (
        "This board renders the user journey of **Automated Literature Review**.\n\n"
        "**How to read it**\n"
        "- Lists (columns) left-to-right = the 12 journey stages.\n"
        "- Cards inside a list top-to-bottom = the lanes:\n"
        "    1. 🎯 Goal — what the user is trying to achieve\n"
        "    2. 🎬 Actions — what they actually do\n"
        "    3. ⚙️ System — touchpoints, APIs, what the product does\n"
        "    4. 💗 Feeling — emotional state at that moment\n"
        "    5. ⚠️ Pain points — where trust or flow breaks\n"
        "    6. 💡 Opportunity — what we could improve next\n\n"
        "Status labels on each stage header:\n"
        "- `✅ Shipped` — end-to-end coverage in the current build\n"
        "- `🟡 Partial` — backend or part of UX done, gaps remain\n"
        "- `⬜ Planned` — not yet built\n\n"
        "The last two lists summarize the **Critical Moments of Truth** and the "
        "**Shipped vs Gap** check against current code.\n\n"
        "Source of truth: `docs/user-journey.md`. Regenerate via `scripts/sync_user_journey_to_trello.py`."
    )
    client.create_card(list_id, "📘 How to read this board", how_desc, [labels["📖 Overview"]])


def render_stage(client: TrelloClient, list_id: str, stage: Stage,
                 labels: dict[str, str]) -> None:
    status_label_name = STAGE_STATUS.get(stage.number, "⬜ Planned")
    header_desc_parts = [
        f"**Stage {stage.number}** of 12 — {stage.title}",
        "",
        f"Status: **{status_label_name}**",
        "",
        "Cards below walk through the six lanes for this stage:",
        "🎯 Goal · 🎬 Actions · ⚙️ System · 💗 Feeling · ⚠️ Pain points · 💡 Opportunity",
    ]
    client.create_card(
        list_id,
        f"▸ Stage {stage.number} overview",
        "\n".join(header_desc_parts),
        [labels[status_label_name]],
    )

    for key, display, _color in LANES:
        text = stage.lanes.get(key, "").strip()
        if not text:
            text = "_(not specified in `docs/user-journey.md` for this stage)_"
        card_title = display
        card_desc = (
            f"**{display}** · Stage {stage.number} — {stage.title}\n\n"
            f"{text}"
        )
        client.create_card(list_id, card_title, card_desc, [labels[display]])


def render_critical(client: TrelloClient, list_id: str,
                    moments: list[str], labels: dict[str, str]) -> None:
    intro = (
        "Moments where the product wins or loses the user. Defend these first; "
        "everything else is polish.\n\nSource: `docs/user-journey.md` → Critical Moments of Truth."
    )
    client.create_card(list_id, "🎯 About this list", intro, [labels["🎯 Critical Moments"]])
    for moment in moments:
        # Pull out the bolded lead if present to use as title.
        m = re.match(r"\*\*(.+?)\*\*\s*(.*)", moment)
        if m:
            title = m.group(1).strip()
            body = m.group(2).strip(" —-")
        else:
            title = moment[:60].rstrip(" —-")
            body = moment
        client.create_card(list_id, title, body or moment, [labels["🎯 Critical Moments"]])


def render_gap_check(client: TrelloClient, list_id: str, shipped: list[str],
                     gaps: list[str], labels: dict[str, str]) -> None:
    intro = (
        "Shipped vs still-missing checklist against current code. Mirror of "
        "`docs/user-journey.md` → Gap Check Versus Current Code."
    )
    client.create_card(list_id, "🧭 About this list", intro, [labels["Gap check"]])
    if shipped:
        body = "\n".join(f"- {s}" for s in shipped)
        client.create_card(list_id, "✅ Shipped", body, [labels["✅ Shipped"]])
    if gaps:
        body = "\n".join(f"- {s}" for s in gaps)
        client.create_card(list_id, "⬜ Still missing or partial", body, [labels["⬜ Planned"]])


# ----- Main ------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Render docs/user-journey.md onto a Trello board.")
    parser.add_argument("--board-id", required=True,
                        help="Trello board shortLink (e.g. QEQiRDT2) or full board id.")
    parser.add_argument("--journey", default="docs/user-journey.md",
                        help="Path to the user journey markdown.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse the journey and print what would be created.")
    args = parser.parse_args()

    journey_path = Path(args.journey)
    if not journey_path.exists():
        print(f"error: {journey_path} not found", file=sys.stderr)
        return 2

    doc = parse_journey(journey_path)
    print(f"Parsed {len(doc.stages)} stages, {len(doc.critical_moments)} "
          f"critical moments, {len(doc.shipped)} shipped items, {len(doc.gaps)} gaps.")

    if args.dry_run:
        print("\n=== Overview ===")
        print(f"Goal: {doc.goal[:120]}{'…' if len(doc.goal) > 120 else ''}")
        print(f"Persona block: {len(doc.persona)} chars")
        print(f"Flow diagram: {'present' if doc.flow_mermaid else 'missing'}")
        print("\n=== Stages ===")
        for s in doc.stages:
            print(f"  Stage {s.number} — {s.title}  [{STAGE_STATUS.get(s.number, '⬜ Planned')}]")
            for key, display, _ in LANES:
                v = s.lanes.get(key, "")
                preview = v.replace("\n", " ")[:100]
                marker = "•" if v else "∅"
                print(f"      {marker} {display}: {preview}{'…' if len(v) > 100 else ''}")
        print("\n=== Critical moments ===")
        for c in doc.critical_moments:
            print(f"  • {c[:120]}{'…' if len(c) > 120 else ''}")
        print("\n=== Gaps ===")
        for g in doc.gaps:
            print(f"  • {g[:120]}{'…' if len(g) > 120 else ''}")
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

    print("Ensuring labels...")
    labels = ensure_labels(client, board_id)

    print("Ensuring lists...")
    existing_lists = {lst["name"]: lst["id"] for lst in client.list_board_lists(board_id)}

    overview_id = ensure_list(client, board_id, existing_lists, "📖 Overview")
    stage_list_ids: dict[int, str] = {}
    for stage in doc.stages:
        stage_list_ids[stage.number] = ensure_list(
            client, board_id, existing_lists, _stage_list_name(stage),
        )
    critical_id = ensure_list(client, board_id, existing_lists, "🎯 Critical Moments of Truth")
    gap_id = ensure_list(client, board_id, existing_lists, "✅ Shipped vs ⬜ Gaps")

    print("Rendering overview...")
    render_overview(client, overview_id, doc, labels)

    print("Rendering stages...")
    for stage in doc.stages:
        print(f"  ▸ Stage {stage.number} — {stage.title}")
        render_stage(client, stage_list_ids[stage.number], stage, labels)

    print("Rendering critical moments...")
    render_critical(client, critical_id, doc.critical_moments, labels)

    print("Rendering gap check...")
    render_gap_check(client, gap_id, doc.shipped, doc.gaps, labels)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
