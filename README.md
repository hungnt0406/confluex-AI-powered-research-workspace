# Starter Code App

A template for building AI Agents in Python.

## Project Overview: AI20K-026
### Automated Literature Review — Multi-Agent Research Survey

**Category:** University | **Topic:** Multi-Agent | **Complexity Score:** 3

> [!IMPORTANT]
> **Requirement Status:** The requirements outlined below are not fixed and may change in the future based on project evolution and feedback.

#### The Problem 🎯
PhD candidates often spend 2–4 months conducting literature reviews, reading 100–200 papers, many of which turn out to be irrelevant. Approximately 60% of research time is consumed by searching, reading, and synthesizing papers. Furthermore, advisor feedback frequently requires adding more papers on specific sub-topics, leading to repetitive and time-consuming search cycles.

#### Proposed Solution 🔨
A multi-agent system designed to automate the research workflow:
- **Searcher Agent**: Sources papers from Semantic Scholar, arXiv, and PubMed using advanced query strategies.
- **Reader Agent**: Summarizes each paper based on a template (methodology, findings, and relevance).
- **Writer Agent**: Synthesizes the summaries into a literature review draft with a natural narrative flow.
- **Quality Agent**: Ensures the coherence and quality of the generated output.

#### Technical Stack
- **Frameworks**: LangGraph / CrewAI
- **LLMs**: OpenAI / Claude API
- **Data Sources**: Semantic Scholar / arXiv API
- **Output**: docx / LaTeX generation
- **Platform**: Streamlit (UI), Railway (Deployment)

#### Minimum Requirements 📜
- **Complete Web Application**: Must be deployed online with a valid URL.
- **Access Control**: Basic login and permission management.
- **User Interface**: Polished UI/UX.
- **User Management**: Basic CRUD for users.

#### Prohibitions 🚫
- NO demo notebooks.
- NO CLI scripts.
- Prototypes running only on localhost are NOT accepted.


## Structure

```
├── src/
│   ├── agent.py        # Main agent loop
│   ├── tools.py        # Tool definitions
│   └── config.py       # Configuration
├── scripts/
│   ├── setup_hooks.sh  # One-time hook installer
│   ├── log_hook.py     # AI tool hook handler
│   └── submit_log.py   # Submits logs on git push
├── requirements.txt
├── .env.example
├── AGENTS.md           # Rules for using AI coding agents
├── JOURNAL.md          # Weekly journal — product journey & learnings
└── WORKLOG.md          # Technical decisions, task assignments, brainstorming
```

## Getting Started

### 1. Clone and setup

```bash
git clone https://github.com/a20-ai-thuc-chien/A20-App-143.git
cd A20-App-143

# Install git pre-push hook (required, run once)
bash scripts/setup_hooks.sh
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in your `ANTHROPIC_API_KEY`. The `AI_LOG_*` variables are pre-filled.

### 3. Run

```bash
python -m venv venv
source venv/bin/activate       # Linux/Mac
# or: venv\Scripts\activate    # Windows

pip install -r requirements.txt
python -m src.agent
```

## Weekly Journal

Update **[JOURNAL.md](./JOURNAL.md)** at the end of every week to document your product-building journey:

- Features shipped
- AI tools used and how they helped
- Hardest problem of the week and how you solved it
- What you'd do differently
- Plan for next week

> JOURNAL.md **must be updated** before each PR. It is your learning record for the course.

## Worklog

Update **[WORKLOG.md](./WORKLOG.md)** whenever your team makes a technical decision or changes direction:

- **Technical decisions** — why did you choose this approach over alternatives?
- **Task assignments** — who does what, by when
- **Brainstorming** — options considered, pros/cons, conclusion
- **Important bugs** — root cause and fix

See each file for the format and examples.

## AI Logging

Prompts and tool calls are **automatically logged** when you use any supported AI tool (Claude Code, Cursor, Codex, Gemini, Copilot). No manual steps needed after running `setup_hooks.sh`.

See [AGENTS.md](./AGENTS.md) for details.
