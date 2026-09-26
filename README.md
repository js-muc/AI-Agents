# 🤖 AI Research Agent

> A multi-agent AI system that autonomously researches any topic and produces a structured report — with live status streaming to a web UI.

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.15-orange)](https://crewai.com/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 What It Does

Submit a research topic and a recipient email address. Three specialized AI agents collaborate in sequence:

| Agent | Role | Responsibility |
|-------|------|----------------|
| 👔 **Supervisor** | Planning | Breaks the topic into structured research areas |
| 🔍 **Researcher** | Discovery | Executes web searches and extracts key findings |
| 📊 **Analyst** | Writing | Synthesizes findings into a professional Markdown report and delivers it via email |

The user watches the run happen in real time through a browser-based interface with per-agent status badges and a live activity log streamed over Server-Sent Events.

---

## 📊 Project Status

**Core pipeline: complete and operational.**

**Full end-to-end reliability: in active development.**

The three-agent pipeline runs correctly, the UI streams live status, and the report is produced when the run completes within the LLM provider's rate limits. On the free tier of the current LLM provider (Groq), a thorough research pass can issue more parallel tool calls than the rate limit permits, in which case the pipeline is terminated mid-run and no report is delivered.

**Two paths to production-ready reliability:**

1. **Use a paid LLM tier** — removes the rate limit entirely. Cost is approximately $0.10–0.50 per full research run.
2. **Apply the bounded-research rewrite** — pre-fetch a fixed number of search results in the backend and pass them to the agents as static context. This eliminates unbounded tool calls by construction.

Both options are documented in [`docs/ENGINEERING_LOG.md`](docs/ENGINEERING_LOG.md).

---

## ✨ What Works Today

**Verified through testing:**

- **Multi-agent orchestration** — 3 CrewAI agents with sequential task dependencies (`crew.jsonc`)
- **Real-time UI updates** — Server-Sent Events push agent status and log lines to the browser
- **Per-agent status tracking** — UI shows each agent's real state (idle / working / complete / error)
- **Web search integration** — Serper API for live results
- **Environment variable substitution** — `${VAR}` placeholders in agent JSONC files are expanded at runtime, keeping the source configs secret-free
- **Process isolation** — `start_new_session=True` plus `os.killpg` guarantees no orphan subprocesses
- **Task state machine guards** — prevents illegal transitions (COMPLETE → IN_PROGRESS)
- **Hard timeouts** — 10-minute wall clock limit; auto-terminates and reports cleanly
- **Report persistence** — successful runs write to `output/report_final.md`
- **Email delivery** — via Gmail SMTP (App Password)
- **Calendar scheduling** — follow-up meeting is created via Google Calendar

**In development:**

- Automatic recovery from LLM rate limits (currently terminates cleanly without retry)
- Bounded tool-call semantics at the framework layer
- Multi-tenant session isolation

---

## 🏗️ Architecture
┌────────────────┐ POST /api/generate ┌────────────────┐
│ Web Browser │ ─────────────────────────────────► │ Flask API │
│ (HTML/CSS/JS) │ │ (backend/) │
└────────────────┘ ◄──── Server-Sent Events (SSE) ─── └────────┬───────┘
│
spawns agent_runner
in a separate thread
│
▼
┌────────────────┐
│ CrewAI │
│ (sequential) │
└────────┬───────┘
│
┌───────────────────────────┼───────────────────────────┐
▼ ▼ ▼
┌────────────┐ ┌────────────┐ ┌────────────┐
│ Supervisor │ ─── plan ──► │ Researcher │ ── findings ►│ Analyst │
│ │ │ │ │ │
└────────────┘ └────────────┘ └────────────┘
│ Serper │ Gmail SMTP
│ Web search │ Google Calendar
│ CSV persistence │ Markdown report

text

### Request lifecycle

1. The user submits a topic and recipient email
2. The Flask backend spawns `agent_runner.py` in a background thread
3. `agent_runner.py` creates an isolated working directory under `temp/`, copies configuration files, and expands `${VAR}` placeholders into the agent configs
4. A `crewai run` subprocess is spawned in a new process session
5. As CrewAI emits stdout, `agent_runner.py` parses task transition markers and pushes structured log + status events to a queue
6. The Flask SSE endpoint streams those events to the browser
7. On successful completion, the report file is copied to `output/report_final.md` and a `complete` event is delivered to the frontend

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.10 – 3.14 |
| Agent framework | [CrewAI](https://crewai.com/) | ≥ 1.15.18, < 2.0.0 |
| Backend | Flask | 3.1.3 |
| CORS | flask-cors | 6.0.5 |
| Production server | gunicorn | 26.2.0 |
| Env loading | python-dotenv | 1.2.3 |
| HTTP client | requests | 2.34.2 |
| Frontend | Vanilla HTML / CSS / JavaScript | — |
| LLM | Groq (OpenAI-compatible API) | — |
| Web search | Serper API | — |
| Email | Gmail SMTP (App Password) | — |
| Calendar | Google Calendar | — |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10 or newer
- A [Groq API key](https://console.groq.com/keys) (free tier works for individual runs)
- A [Serper API key](https://serper.dev) (free tier provides 2,500 searches)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords)

### Installation

```bash
git clone https://github.com/js-muc/AI-Agents.git
cd AI-Agents

# Backend virtual environment (Flask + server)
python3 -m venv .venv-backend
source .venv-backend/bin/activate
pip install -r backend/requirements.txt

# Agent virtual environment (CrewAI)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
Configuration
bash
cp .env.example .env
Then edit .env and fill in:

Variable	Where to get it
GROQ_API_KEY	https://console.groq.com/keys
SERPER_API_KEY	https://serper.dev/dashboard
EMAIL_ADDRESS	Your Gmail address
EMAIL_PASSWORD	A Gmail App Password (16 characters, not your account password)
Running
bash
source .venv-backend/bin/activate
cd backend
python app.py
Open http://127.0.0.1:5000 in your browser.

Enter a research topic and a recipient email. The three agents will run in sequence. When the run completes successfully, the report is written to output/report_final.md and shown in the UI.

📁 Project Structure
text
.
├── backend/                       # Flask server + agent orchestration
│   ├── agent_runner.py            # Spawns CrewAI, parses output, streams status
│   ├── app.py                     # Flask routes + SSE endpoint
│   ├── config.py                  # Paths, host, port
│   ├── log_manager.py             # In-memory per-session log queues
│   ├── pdf_generator.py           # Optional PDF export of the report
│   └── requirements.txt
│
├── frontend/                      # Vanilla HTML/CSS/JS interface
│   ├── index.html
│   ├── script.js
│   └── style.css
│
├── agents/                        # CrewAI agent definitions (JSONC)
│   ├── supervisor.jsonc
│   ├── senior_research_specialist_for.jsonc
│   └── expert_data_analyst_and_report_writer_for.jsonc
│
├── tools/                         # Custom tools available to the agents
│   ├── calendar_tool.py
│   ├── email_tool.py
│   ├── human_approval_tool.py
│   ├── sheets_tool.py
│   └── bounded_serper_tool.py     # Experimental bounded-search wrapper
│
├── docs/                          # Deep documentation
│   ├── ARCHITECTURE.md            # Component-by-component walkthrough
│   └── ENGINEERING_LOG.md         # Real problems and how they were solved
│
├── crew.jsonc                     # Crew configuration
├── pyproject.toml                 # Python project metadata
├── start-backend.sh               # Convenience launcher
├── .env.example                   # Template for required secrets
└── .gitignore
🔐 Security
No API keys are committed. All secrets are read from environment variables loaded via python-dotenv.

Agent configs use ${VAR_NAME} placeholders. These are expanded at runtime in an isolated temporary directory by agent_runner.py; the source files stay clean and secret-free.

.env is gitignored. Committed by exception only as .env.example, which contains placeholders only.

Rotation procedure. Regenerate the key at the provider's dashboard, update .env locally, restart the backend.

🎓 Engineering Highlights
Five non-obvious problems solved while building this system. Each is documented in more depth in docs/ENGINEERING_LOG.md.

1. Process group isolation.
CrewAI's uv run spawns child processes that survive when the parent exits normally. agent_runner.py uses subprocess.Popen(..., start_new_session=True) and os.killpg(os.getpgid(pid), SIGKILL) to guarantee the entire process tree terminates — even on error paths.

2. Task state machine integrity.
CrewAI's terminal output redraws the current task marker dozens of times per minute. Without guards, a late redraw could be misread as a task transition and restart a completed task. Guarded transitions (and not task_completed['research']) prevent illegal state changes.

3. Environment variable expansion for JSONC.
CrewAI does not expand ${VAR} placeholders in agent JSONC files. agent_runner.py performs the expansion into a temporary copy of the configs, keeping the source files clean and secret-free.

4. Virtual environment separation.
CrewAI's uv sync reconciles the environment to match pyproject.toml and removes packages it doesn't recognize. This would remove Flask on every run. The solution: two virtual environments — .venv for CrewAI, .venv-backend for the Flask server.

5. Multi-agent context accumulation.
Each downstream agent receives the accumulated output of upstream agents through CrewAI's context field. For iterative research tasks, this can exceed the LLM's context window. This is the primary open issue and is documented in the engineering log along with the proposed bounded-research rewrite.

🗺️ Roadmap
Completed:

☑ Three-agent sequential workflow
☑ Real-time UI status via Server-Sent Events
☑ Automatic email delivery
☑ Google Calendar scheduling
☑ Process isolation and cleanup
☑ Environment-variable configuration for agent files
☑ Professional documentation set
In progress:

□ Bounded-search semantics at the framework layer
□ Automatic retry with exponential backoff on rate-limit responses
□ Public deployment (Railway)
Future:

□ Multi-tenant session isolation
□ Structured PDF export
□ Custom agent templates
□ Report diffing between runs
📄 License
MIT — see LICENSE.

👤 Author
Jesee Muchoki

Email: jeseemuchoki5@gmail.com

GitHub: @js-muc

Built in Nairobi, 2026.
