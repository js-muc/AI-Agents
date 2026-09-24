# 🤖 AI Research Agent

> A production-grade multi-agent AI system that researches any topic and delivers a professional report to a specified recipient — automatically.

[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.15-orange)](https://crewai.com/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🎯 What It Does

Submit a research topic and a recipient email. Three autonomous AI agents work in sequence:

| Agent | Role | Responsibility |
|-------|------|----------------|
| 👔 **Supervisor** | Planning | Breaks the topic into structured research areas |
| 🔍 **Researcher** | Discovery | Executes targeted web searches and extracts findings |
| 📊 **Analyst** | Writing | Synthesizes findings into a professional Markdown report, emails it to the recipient, and schedules a follow-up |

The user watches this happen live through a web interface with per-agent status indicators and a streaming activity log.

---

## ✨ Features

- **Multi-agent orchestration** — 3 specialized CrewAI agents with sequential task dependencies
- **Real web search** — Serper API for live, sourced information
- **Real-time streaming** — Server-Sent Events (SSE) push agent status and logs to the UI
- **Live agent status** — the UI reflects each agent's real state (idle, working, complete, error)
- **Automatic email delivery** — report is sent via Gmail SMTP to the specified recipient
- **Calendar scheduling** — a follow-up meeting is created via Google Calendar
- **Downloadable report** — final output is available as a Markdown file
- **Graceful failure handling** — errors are logged and surfaced, not hidden
- **Process isolation** — subprocess groups are cleaned up on exit, no orphan processes
- **Environment-variable config** — no API keys committed to the repository

---

## 🏗️ Architecture
┌────────────────┐ POST /api/generate ┌────────────────┐
│ Web Browser │ ─────────────────────────────────► │ Flask API │
│ (HTML/CSS/JS) │ │ (backend/) │
└────────────────┘ ◄──── Server-Sent Events (SSE) ─── └────────┬───────┘
│
spawns agent_runner
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
│ Sheets tool │ Output file

text

### Request lifecycle

1. User submits a topic + recipient email
2. Backend starts `agent_runner.py` in a background thread
3. `agent_runner.py` creates an isolated temp directory, copies configuration files, and expands environment variables into the agent configs
4. A `crewai run` subprocess is spawned inside a new session (so the entire process group can be terminated cleanly)
5. As CrewAI emits stdout, `agent_runner.py` parses task transitions and pushes status updates to a queue
6. The Flask SSE endpoint streams those updates to the browser
7. When CrewAI finishes, the report is copied to `output/report_final.md` and the completion event is sent to the UI

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
| LLM (routed) | Groq (`llama-3.3-70b-versatile` and others) | — |
| Search | Serper API | — |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- A [Groq API key](https://console.groq.com/keys) (free tier)
- A [Serper API key](https://serper.dev) (free tier)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords)

### Installation

```bash
git clone https://github.com/js-muc/AI-Agents.git
cd AI-Agents

# Create the backend virtual environment
python3 -m venv .venv-backend
source .venv-backend/bin/activate
pip install -r backend/requirements.txt

# Create the agents virtual environment (isolated from the backend)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
Configuration
bash
cp .env.example .env
# Edit .env and fill in:
#   GROQ_API_KEY       — from https://console.groq.com/keys
#   SERPER_API_KEY     — from https://serper.dev/dashboard
#   EMAIL_ADDRESS      — your Gmail address
#   EMAIL_PASSWORD     — a Gmail App Password (not your account password)
Run
bash
# Activate the backend venv
source .venv-backend/bin/activate

# Start the server
cd backend
python app.py
Open http://127.0.0.1:5000 in your browser.

Submit a topic (e.g., "Benefits of drinking water") and a recipient email. The three agents will run in sequence and deliver a report to the recipient.

📁 Project Structure
text
.
├── backend/                       # Flask server + agent orchestration
│   ├── __init__.py
│   ├── agent_runner.py            # Spawns CrewAI, parses output, drives UI updates
│   ├── app.py                     # Flask routes + SSE endpoint
│   ├── config.py                  # Paths, host, port
│   ├── log_manager.py             # In-memory per-session log queues
│   ├── pdf_generator.py           # Optional PDF export of the report
│   └── requirements.txt
├── frontend/                      # Vanilla HTML/CSS/JS interface
│   ├── index.html
│   ├── script.js
│   └── style.css
├── agents/                        # CrewAI agent definitions (JSONC)
│   ├── supervisor.jsonc
│   ├── senior_research_specialist_for.jsonc
│   └── expert_data_analyst_and_report_writer_for.jsonc
├── tools/                         # Custom tools available to the agents
│   ├── calendar_tool.py
│   ├── email_tool.py
│   ├── human_approval_tool.py
│   └── sheets_tool.py
├── crew.jsonc                     # Crew configuration (agents, tasks, process)
├── pyproject.toml                 # Python project metadata
├── start-backend.sh               # One-shot backend launcher
├── .env.example                   # Template for required secrets
└── .gitignore
🔐 Security
No API keys are committed. All secrets are read from environment variables loaded via python-dotenv.

Agent config files use ${VAR_NAME} placeholders. These are expanded at runtime in an isolated temp directory by agent_runner.py — the originals stay clean.

.env is gitignored.

Rotated credentials are never stored in Git history.

To rotate a key:

Regenerate the key at the provider's dashboard

Update .env locally

Restart the backend

📈 Engineering Highlights
A few non-obvious problems that were solved while building this:

1. Process group isolation. CrewAI's uv run spawns child processes that are not automatically killed when the parent exits. agent_runner.py uses subprocess.Popen(..., start_new_session=True) and os.killpg(os.getpgid(pid), SIGKILL) to guarantee the entire tree is terminated.

2. Task state machine integrity. CrewAI's TUI redraws "Task X/3" markers frequently. Without guards, those redraws can be misread as task transitions and cause a completed task to restart. Guard checks (not task_completed['research']) prevent illegal state transitions.

3. Environment variable expansion for JSONC. CrewAI does not expand ${VAR} placeholders in agent JSONC files. agent_runner.py performs the expansion manually into a temporary copy, keeping the source configs secret-free.

4. Venv separation. The backend (Flask) and the agent runtime (CrewAI) use separate virtual environments. This prevents uv sync (invoked by CrewAI) from uninstalling Flask when it reconciles pyproject.toml.

5. Environment loading across process boundaries. .env is loaded once in agent_runner.py via load_dotenv(). The subprocess inherits the resulting os.environ through subprocess.Popen(..., env=env), so the agent runtime sees the same secrets as the parent.

🗺️ Roadmap
☑ Three-agent sequential workflow
☑ Real-time UI status via SSE
☑ Report generation, email delivery, calendar scheduling
☑ Process isolation and cleanup
☑ Environment-variable configuration for agent files
□ Public deployment (Railway)
□ Multi-tenant session management
□ Structured PDF export
📄 License
MIT — see LICENSE.

👤 Author
Jesee Muchoki

Email: jeseemuchoki5@gmail.com

GitHub: @js-muc

Built in Nairobi, 2026.
