# Architecture

This document describes how the AI Research Agent is put together — what each component does, how they communicate, and the decisions behind the structure.

---

## 1. System Overview

The system has three moving parts:

| Layer | Runs where | Language | Responsibility |
|-------|-----------|----------|----------------|
| **Frontend** | Browser | HTML / CSS / JavaScript | Form, status indicators, live logs, report display |
| **Backend** | Python process | Python / Flask | HTTP API, SSE streaming, spawning the agent runner |
| **Agent runtime** | Subprocess | Python / CrewAI | Orchestrates the three agents and their tasks |

Data flows left-to-right for requests, right-to-left for status updates.

---

## 2. The Backend

### `backend/app.py`

Flask application serving:

| Route | Method | Purpose |
|-------|--------|---------|
| `/` | GET | Serves `frontend/index.html` |
| `/static/<path>` | GET | Serves CSS, JS, and static assets |
| `/api/generate` | POST | Accepts `{topic, recipient, session_id}`; spawns `run_agent` in a background thread; returns `{success, session_id}` |
| `/api/logs/<session_id>` | GET | Server-Sent Events stream of agent logs and status updates |
| `/api/status` | GET | Health check endpoint |
| `/api/download/<session_id>` | GET | (Optional) PDF export of a completed report |

The SSE endpoint is the mechanism that drives the live UI. It holds a long-lived HTTP response open and pushes events as they arrive in the session's log queue.

### `backend/agent_runner.py`

This is the core of the system. Its job is to:

1. Create an isolated working directory under `temp/crew_run_<session_id>_<random>/`
2. Symlink the CrewAI virtual environment into the temp directory
3. Copy `pyproject.toml`, `crew.jsonc`, `agents/`, `tools/`, and `knowledge/` into it
4. Inject the current `topic` and `recipient` into `crew.jsonc`
5. Expand `${VAR}` placeholders in every `agents/*.jsonc` file using values from the environment
6. Spawn `crewai run` as a subprocess with `start_new_session=True`
7. Read the subprocess's PTY output line by line
8. Parse markers such as `Task 1/3: planning_task` and infer current agent state
9. Push structured log messages and status updates to the session queue
10. On completion, copy the generated report to `output/report_final.md`
11. Ensure the entire process group is terminated — even on error

### `backend/log_manager.py`

Provides per-session `queue.Queue` instances. Keeps all log delivery in-memory and session-scoped. No persistent storage is required for the log stream.

### `backend/config.py`

Centralises paths and constants:

- `PROJECT_ROOT` — path to the repository root
- `CREWAI_EXE` — path to the `crewai` executable inside `.venv`
- `FRONTEND_FOLDER` — path to `frontend/`
- `SERVER_HOST`, `SERVER_PORT`, `DEBUG_MODE`

---

## 3. The Agent Runtime

The agents are defined as JSONC files that CrewAI reads at runtime.

### Agents

| File | Role | Tools |
|------|------|-------|
| `agents/supervisor.jsonc` | Project planning | — |
| `agents/senior_research_specialist_for.jsonc` | Web research | `SerperDevTool`, `ScrapeWebsiteTool`, `FileReadTool`, `sheets_tool` |
| `agents/expert_data_analyst_and_report_writer_for.jsonc` | Report writing & delivery | `email_tool`, `calendar_tool`, `FileWriterTool` |

Each agent's `llm` block uses an environment-variable placeholder for the API key:

```jsonc
"llm": {
    "provider": "openai",
    "model": "llama-3.3-70b-versatile",
    "base_url": "https://api.groq.com/openai/v1",
    "api_key": "${GROQ_API_KEY}"
}
Tasks (crew.jsonc)
Three sequential tasks with explicit context dependencies:

text
planning_task  →  research_task  →  write_task
                       ↑                ↑
                  context:         context:
                ["planning_task"]  ["research_task"]
The context field tells CrewAI to feed the output of the referenced task into the dependent task. This creates the pipeline that produces a report from a topic.

Sequential process
"process": "sequential" instructs CrewAI to run tasks one after another, respecting the context chain.

4. The Frontend
Plain HTML, CSS, and JavaScript — no build step, no framework.

frontend/index.html
Form with two inputs (topic, recipient email)

Three agent status indicators (status-supervisor, status-researcher, status-analyst)

Activity log container

Report panel (hidden until completion)

frontend/script.js
Key responsibilities:

Submits the form to /api/generate

Opens an EventSource against /api/logs/<session_id>

Parses three event types from the SSE stream:

agent_status — sets one agent to working, complete, or error

log — appends a message to the activity log

complete — finalizes the UI and displays the report

Uses a sessionComplete flag to ignore any late status updates after completion (protects against message-ordering races)

frontend/style.css
Dark, low-contrast UI designed for readability of long log streams.

5. Communication Contracts
Frontend → Backend
http
POST /api/generate
Content-Type: application/json

{
  "topic": "Benefits of drinking water",
  "recipient": "user@example.com",
  "session_id": "session_1790252060226_p7ua3d_r"
}
Response:

json
{ "success": true, "session_id": "session_1790252060226_p7ua3d_r" }
Backend → Frontend (SSE)
Three message types are emitted on /api/logs/<session_id>:

jsonc
// 1. Agent status update
{ "type": "agent_status", "agent": "researcher", "status": "working" }

// 2. Log message
{
  "type": "log",
  "message": "🔍 Researcher: Gathering information...",
  "level": "info",
  "timestamp": "15:32:34"
}

// 3. Completion (sent exactly once, at the end)
{ "type": "complete", "result": "# Report on Benefits of Drinking Water\n\n..." }
6. Failure Handling
Failure	Detection	Response
Missing crew.jsonc	File check before spawn	Raise and log; abort
CrewAI subprocess exits non-zero	process.returncode != 0	Emit error event; do not attempt to display a report
Agent task hangs indefinitely	Per-task soft warning at 15 min	Log a warning; keep waiting until total timeout
Total run exceeds time budget	MAX_TOTAL_DURATION (45 min)	Kill process group; emit error
Report file missing	Post-run file check	Emit complete with result: null
Queue full when emitting complete	Retry loop (10 attempts, 0.5 s apart)	Retry; log if all attempts fail
Orphan CrewAI subprocesses	start_new_session=True + os.killpg	Kill entire process group in finally
7. Design Decisions
Why two virtual environments? CrewAI's uv sync reconciles pyproject.toml and will remove packages it doesn't recognise. The backend needs Flask, which CrewAI has no reason to keep. Separate venvs eliminate the conflict.

Why expand ${VAR} manually? CrewAI's JSONC parser is intentionally minimal. It does not perform shell-style environment variable substitution. agent_runner.py performs the expansion into a temporary copy so the source files stay clean and secret-free.

Why start_new_session=True? Without it, killing the parent crewai process leaves uv run children running as orphans. Placing the subprocess in a new session makes it the leader of a new process group; os.killpg then terminates the whole tree reliably.

Why SSE instead of WebSockets? The traffic is one-directional (server → client) after the initial POST. SSE is simpler, works over plain HTTP/1.1, and has first-class browser support.

Why no framework on the frontend? The UI has one form, three status badges, one log panel, and one report panel. A framework would add a build step, a dependency tree, and nothing else.

8. Configuration Surface
Every tunable lives in one of three places:

Where	What
.env	Secrets (GROQ_API_KEY, SERPER_API_KEY, EMAIL_ADDRESS, EMAIL_PASSWORD)
crew.jsonc	Task definitions, agent order, process type, max_rpm
agents/*.jsonc	Per-agent role, goal, backstory, tools, LLM settings
backend/agent_runner.py	Timeouts, retry limits, temp directory policy
Last updated: September 2026
