# Engineering Log

A working record of the non-obvious problems encountered while building this system, how they were diagnosed, and what was changed.

This document is intentionally specific. It records what actually happened during development — including the bugs that took the longest to find.

---

## 1. Isolating the CrewAI Subprocess

**Symptom.** After a run completed, the `crewai run` process was still alive. CPU usage stayed at 70%+. The system appeared idle in the UI but the machine kept working.

**Diagnosis.** CrewAI is invoked through `uv run`. `subprocess.Popen.kill()` sends SIGKILL to the immediate child only. `uv` had spawned its own children, which were re-parented to init and kept running.

**Fix.** Spawn the process with `start_new_session=True` so it becomes the leader of a new process group:

```python
process = subprocess.Popen(
    cmd,
    stdout=slave, stderr=slave, stdin=slave,
    cwd=temp_dir, env=env,
    start_new_session=True,
)
And terminate the group on cleanup:

python
import signal
os.killpg(os.getpgid(process.pid), signal.SIGKILL)
Lesson. Killing a subprocess is not the same as killing a process tree.

2. Task State Machine Integrity
Symptom. After the Researcher was force-completed due to a timeout, the UI showed the Analyst as active — but the Researcher kept producing output and eventually the log showed Task 2/3: research_task again. The state had regressed from Task 3/3 back to Task 2/3.

Diagnosis. CrewAI's TUI redraws the current task marker on every render. During the Researcher phase, the string Task 2/3: research_task was emitted dozens of times per minute. When a late redraw arrived after the task had been force-completed, the parser read it as a new task transition and restarted the Researcher.

Fix. Guard each task transition against the completion state:

python
if task_num == 1 and not task_completed['planning']:
    ...
elif task_num == 2 and not task_completed['research']:
    ...
elif task_num == 3 and not task_completed['write']:
    ...
Lesson. A state machine that allows COMPLETE → IN_PROGRESS transitions is broken. Every transition into a state should have a precondition.

3. Environment Variable Expansion in Agent Configs
Symptom. After moving API keys out of agent JSONC files and replacing them with ${GROQ_API_KEY}, all runs failed with 401 Invalid API key. Inspecting the temp file CrewAI actually read showed the literal string "api_key": "${GROQ_API_KEY}".

Diagnosis. CrewAI's JSONC parser does not expand ${VAR} placeholders from the process environment. The literal placeholder was being passed to the LLM provider.

Fix. Expand placeholders manually in agent_runner.py before invoking CrewAI:

python
agents_dir = os.path.join(temp_dir, 'agents')
if os.path.exists(agents_dir):
    for fname in os.listdir(agents_dir):
        if fname.endswith('.jsonc'):
            fpath = os.path.join(agents_dir, fname)
            with open(fpath) as f:
                content = f.read()

            def replace_env(match):
                return os.environ.get(match.group(1), '')

            expanded = re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', replace_env, content)

            with open(fpath, 'w') as f:
                f.write(expanded)
Lesson. Never assume a third-party tool does what a feature name suggests. Verify by inspecting the artifact the tool actually consumes.

4. Virtual Environment Separation
Symptom. Every few runs, python app.py failed with ModuleNotFoundError: No module named 'flask' — even though Flask had been installed. Reinstalling fixed it temporarily; the failure returned after the next CrewAI run.

Diagnosis. CrewAI runs uv sync --no-install-project on startup. That command reads pyproject.toml, reconciles the environment to match it, and removes packages that are not listed. Flask was not declared in pyproject.toml, so it was uninstalled on each run.

Fix. Use two virtual environments:

.venv — used by CrewAI, contains only what pyproject.toml declares

.venv-backend — used by the Flask server, contains Flask, flask-cors, gunicorn, python-dotenv

The two environments do not interfere.

Lesson. A package manager that reconciles an environment will remove anything it wasn't told to install. Declare the full set of dependencies or isolate the runtimes.

5. LLM Provider Choice
Symptom. Runs were slow — 15 to 30 minutes for a single research task. Some runs were terminated by the per-task timeout before they completed.

Diagnosis. The initial provider was a free LLM router that dispatches requests across multiple upstream free tiers. Observed per-call latency ranged from 5 to 60 seconds, with frequent 429 Too Many Requests responses when the shared upstream quota was exhausted.

Fix. Switch to a provider with a generous free tier and consistent low latency. The final configuration uses Groq's inference API, which processes calls in 1–3 seconds.

Lesson. "Free" is a description of cost, not of performance. Rate-limited shared tiers are unsuitable for workloads that make dozens of sequential LLM calls per request.

6. Report Content vs. Report Summary
Symptom. The generated report_final.md was 229 bytes — a single confirmation sentence saying the report had been emailed. The actual research content was visible in the log but never reached the file.

Diagnosis. CrewAI's output_file field writes the agent's final answer to disk. The Analyst agent was structured to write the report, send it via email, and then return a short confirmation as its final answer. CrewAI saved the confirmation.

Fix. Restructure the Analyst's task so its final answer is the report:

text
Your FINAL ANSWER must contain the COMPLETE report text in Markdown format.
Do NOT summarize. Do NOT say 'I have sent the report.'
Output the ENTIRE report as your final answer.
Your final answer must start with: '# Report on {topic}'
Lesson. output_file writes the last thing the agent says. If the agent's last thing is a status message, that's what gets saved.

7. Agent Output Overflow (Context Size)
Symptom. After moving to Groq, runs began failing with 413 Request too large for model. The task chain itself was fine — the request to the LLM exceeded the model's context window.

Diagnosis. Each agent receives the accumulated output of all prior agents through the context field. With unrestricted research, the Researcher's output could reach tens of thousands of tokens. By the time the Analyst ran, the total context exceeded 128K tokens.

Fix. Bound the size of intermediate outputs:

Researcher: exactly 5 web searches, 3 findings per search, 30 words maximum per finding

Analyst: 800–1200 word report maximum

crew.jsonc gained "max_rpm": 25 to smooth request pacing

Lesson. Multi-agent systems accumulate context multiplicatively. Bound each stage or the last stage will not fit.

8. Secret Rotation Discipline
Symptom. A .env-excluded secret was accidentally committed because it was hardcoded in an agent JSONC file rather than read from the environment.

Diagnosis. The .gitignore protected .env, but the agent files contained the key directly.

Fix.

The leaked key was rotated at the provider

Agent files were edited to read from ${VAR} placeholders

agent_runner.py gained the runtime expansion described in §3

Local Git history was rewritten and force-pushed to remove the old commit

Lesson. .gitignore is not a substitute for secret hygiene. Secrets belong in exactly one place: the environment.

9. Pre-Push Verification
Procedure now used before every push:

bash
# 1. Scan tracked files for the patterns of every secret in .env
git ls-files | xargs grep -l "gsk_\|sk-or-v1-\|serper" 2>/dev/null

# 2. Confirm .env is ignored
git check-ignore -v .env

# 3. Confirm the working tree is exactly what you intend to push
git status --short
Lesson. A pre-push scan takes 10 seconds. A leaked credential takes hours to remediate.

This log is updated as the system evolves.
