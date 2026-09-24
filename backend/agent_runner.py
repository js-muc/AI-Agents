import os
import subprocess
import json
import time
import re
import pty
import select
import sys
import tempfile
import shutil
import threading
import queue
import signal
from datetime import datetime, timedelta
from enum import Enum
from config import PROJECT_ROOT, CREWAI_EXE
from log_manager import get_log_queue, create_log_message

# ===== Load .env so CrewAI subprocess sees SERPER_API_KEY =====
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

_key = os.environ.get('SERPER_API_KEY', 'NOT_SET')
print(f"🔑 SERPER_API_KEY: {'LOADED (' + _key[:10] + '...)' if _key != 'NOT_SET' else 'MISSING'}")

# ===== Use project directory for temp files =====
TEMP_DIR = os.path.join(PROJECT_ROOT, 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)
tempfile.tempdir = TEMP_DIR

# ===== Configuration =====
# NOTE: MAX_TASK_DURATION is now a SOFT WARNING only — never fakes completion.
#       Only MAX_TOTAL_DURATION truly stops the process.
MAX_TASK_DURATION = 900      # 15 min soft warning per task
MAX_TOTAL_DURATION = 2700    # 45 min hard stop
MAX_SAME_TASK_REPEATS = 500  # Anti-loop only triggers on truly pathological loops

print(f"📂 Using temp directory: {TEMP_DIR}")

# ===== LOCK =====
crew_run_lock = threading.Lock()

# ===== CLEANING =====
TERMINAL_CONTROL_RE = re.compile(
    r'\x1b\[[0-9;?]*[a-zA-Z]|'
    r'\x1b\][^\x07]*\x07|'
    r'\x1b[()][A-Z0-9]|'
    r'\x1b\[[0-9;]*m|'
    r'\r|'
    r'\x1b[PX^_].*?\x1b\\|'
    r'\x1b\[[0-9;]*[a-zA-Z]'
)

def clean_log_text(text):
    """Strip terminal codes and clean up text"""
    text = TERMINAL_CONTROL_RE.sub('', str(text))
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    text = re.sub(r'\d+;\d+;\d+m', '', text)
    text = re.sub(r'\d+;\d+m', '', text)
    text = re.sub(r'\d+;\d+;\d+;\d+m', '', text)
    text = re.sub(r';\d+;\d+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    noise_patterns = [
        'No activity yet', 'expand/collapse', 'palette',
        'navigate enter', 'collection methods', 'Generating response',
        'Thinking', 'TOKENS', 'AGENTS', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'
    ]
    if any(p in text for p in noise_patterns) or len(text) < 3:
        return ''
    
    if 'Task' in text and '/' in text:
        match = re.search(r'Task\s+(\d+)/3.*?(planning|research|write)_task', text, re.IGNORECASE)
        if match:
            task_num = match.group(1)
            task_name = match.group(2)
            return f"Task {task_num}/3: {task_name}_task"
    
    return text

def run_agent(session_id, topic, recipient):
    """Run CrewAI — CrewAI drives task transitions, we only observe."""
    log_q = get_log_queue(session_id)
    
    # ===== TRACK TASKS =====
    task_completed = {
        'planning': False,
        'research': False,
        'write': False
    }
    
    task_repeat_count = {'planning': 0, 'research': 0, 'write': 0}
    last_task_seen = None
    last_task_change_time = time.time()
    task_start_times = {}
    crew_completed = False
    last_task_status_sent = {}
    
    # ===== Last warning timestamps per task (prevents spam) =====
    last_warning_time = {}
    
    def send_log(message, level='info'):
        clean_msg = clean_log_text(message)
        if clean_msg and len(clean_msg) > 3:
            try:
                log_q.put(create_log_message(clean_msg, level), timeout=1)
            except queue.Full:
                pass

    def update_agent_status(agent, status):
        try:
            log_q.put({
                'type': 'agent_status',
                'agent': agent,
                'status': status
            }, timeout=1)
        except queue.Full:
            pass
        
        emoji_map = {'working': '🔄', 'complete': '✅', 'error': '❌', 'idle': '⏸️'}
        emoji = emoji_map.get(status, '')
        send_log(f"{emoji} {agent.title()} is {status}", 'status')

    def complete_task(task_name):
        if task_name in task_completed and not task_completed[task_name]:
            task_completed[task_name] = True
            agent_map = {'planning': 'supervisor', 'research': 'researcher', 'write': 'analyst'}
            agent = agent_map.get(task_name)
            if agent:
                update_agent_status(agent, 'complete')
                send_log(f"✅ {agent.title()} task complete", 'success')

    def start_task(task_name):
        agent_map = {'planning': 'supervisor', 'research': 'researcher', 'write': 'analyst'}
        agent = agent_map.get(task_name)
        if agent:
            update_agent_status(agent, 'working')
            messages = {
                'planning': f"👔 Supervisor: Creating research plan...",
                'research': f"🔍 Researcher: Gathering information...",
                'write': f"📊 Analyst: Writing report..."
            }
            send_log(messages.get(task_name, f"Starting {task_name}"), 'thinking')

    def kill_process_group(proc):
        if not proc:
            return
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
            send_log(f"🛑 Killed process group {pgid}", 'info')
        except ProcessLookupError:
            pass
        except Exception as e:
            send_log(f"⚠️ Process group kill failed: {e}", 'warning')
            try:
                proc.kill()
            except:
                pass

    # ===== MAIN EXECUTION =====
    temp_dir = None
    report_content = None
    current_task = None
    process = None
    master = None
    start_time = time.time()
    
    try:
        send_log(f"🚀 Starting: {topic}")
        send_log(f"📧 Recipient: {recipient}")

        with crew_run_lock:
            temp_dir = tempfile.mkdtemp(prefix=f"crew_run_{session_id}_", dir=TEMP_DIR)
            send_log(f"📁 Created: {os.path.basename(temp_dir)}")

            # Symlink existing venv
            venv_src = os.path.join(PROJECT_ROOT, '.venv')
            venv_dst = os.path.join(temp_dir, '.venv')
            
            if os.path.exists(venv_src) and not os.path.exists(venv_dst):
                try:
                    os.symlink(venv_src, venv_dst)
                    send_log("⚡ Linked existing venv (no reinstall)")
                except Exception as e:
                    send_log(f"⚠️ Symlink failed: {e}")

            # Copy files
            copy_items = ['pyproject.toml', 'crew.jsonc', 'agents', 'tools', 'knowledge']
            for item in copy_items:
                src = os.path.join(PROJECT_ROOT, item)
                dst = os.path.join(temp_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                elif os.path.isfile(src):
                    shutil.copy2(src, dst)
                else:
                    send_log(f"⚠️ Missing: {item}")

            # ===== FIX: Expand ${VAR} placeholders in agent files =====
            # CrewAI does NOT expand env vars from JSONC — we do it manually.
            agents_dir = os.path.join(temp_dir, 'agents')
            if os.path.exists(agents_dir):
                for fname in os.listdir(agents_dir):
                    if fname.endswith('.jsonc'):
                        fpath = os.path.join(agents_dir, fname)
                        with open(fpath, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        def replace_env(match):
                            var_name = match.group(1)
                            value = os.environ.get(var_name, '')
                            if not value:
                                send_log(f"⚠️ Env var '{var_name}' not set!", 'warning')
                            return value
                        
                        expanded = re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', replace_env, content)
                        
                        if expanded != content:
                            with open(fpath, 'w', encoding='utf-8') as f:
                                f.write(expanded)
                
                send_log("🔑 Expanded env variables in agent files")
            # ===== END FIX =====

            os.makedirs(os.path.join(temp_dir, 'output'), exist_ok=True)

            # Update crew.jsonc
            crew_path = os.path.join(temp_dir, 'crew.jsonc')
            if os.path.exists(crew_path):
                with open(crew_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                inputs_json = json.dumps({"topic": topic, "recipient": recipient})
                if '"inputs":' in content:
                    content = re.sub(
                        r'"inputs":\s*\{[^}]*\}',
                        f'"inputs": {inputs_json}',
                        content
                    )
                else:
                    content = content.rstrip() + f',\n  "inputs": {inputs_json}\n'

                with open(crew_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                send_log("📝 Updated crew.jsonc with inputs")
            else:
                send_log("❌ crew.jsonc not found!", 'error')
                raise Exception("crew.jsonc missing")

            # Start Supervisor
            start_task('planning')
            current_task = 'planning'
            task_start_times['planning'] = time.time()

            # ===== Run CrewAI =====
            cmd = [CREWAI_EXE, 'run']
            env = os.environ.copy()
            env['NO_COLOR'] = '1'
            env['TERM'] = 'dumb'
            env['PYTHONUNBUFFERED'] = '1'
            env['VIRTUAL_ENV'] = os.path.join(PROJECT_ROOT, '.venv')
            env['TMPDIR'] = TEMP_DIR
            env['UV_LINK_MODE'] = 'copy'
            env['UV_PROJECT_ENVIRONMENT'] = os.path.join(PROJECT_ROOT, '.venv')
            env['UV_NO_SYNC'] = '1'
            env['UV_OFFLINE'] = '1'

            master, slave = pty.openpty()
            
            try:
                import termios
                attrs = termios.tcgetattr(slave)
                attrs[3] = attrs[3] & ~termios.ICANON
                attrs[3] = attrs[3] & ~termios.ECHO
                attrs[6][termios.VMIN] = 1
                attrs[6][termios.VTIME] = 0
                termios.tcsetattr(slave, termios.TCSANOW, attrs)
            except Exception as e:
                send_log(f"⚠️ PTY config warning: {e}")
            
            process = subprocess.Popen(
                cmd,
                stdout=slave,
                stderr=slave,
                stdin=slave,
                cwd=temp_dir,
                env=env,
                close_fds=True,
                bufsize=0,
                start_new_session=True,
            )
            os.close(slave)

            send_log("⚙️ CrewAI processing...", 'info')

            # ===== PROCESS LOGS =====
            last_output_time = time.time()
            stuck_counter = 0
            
            while True:
                try:
                    # ===== HARD STOP: Total timeout =====
                    if time.time() - start_time > MAX_TOTAL_DURATION:
                        send_log(f"⏰ Total timeout ({MAX_TOTAL_DURATION}s) reached — killing process", 'warning')
                        break
                    
                    # ===== SOFT WARNING: Per-task duration (NO fake completion) =====
                    # We observe CrewAI's task; we do not fake it.
                    if current_task and current_task in task_start_times:
                        task_elapsed = time.time() - task_start_times[current_task]
                        if task_elapsed > MAX_TASK_DURATION:
                            # Only warn once per 60 seconds per task
                            last_warn = last_warning_time.get(current_task, 0)
                            if time.time() - last_warn > 60:
                                send_log(
                                    f"⚠️ Task '{current_task}' running for {int(task_elapsed)}s (soft limit)",
                                    'warning'
                                )
                                last_warning_time[current_task] = time.time()
                    
                    ready, _, _ = select.select([master], [], [], 0.5)
                    if ready:
                        try:
                            data = os.read(master, 4096)
                            if not data:
                                break

                            last_output_time = time.time()
                            raw_text = data.decode('utf-8', errors='ignore')
                            cleaned_line = clean_log_text(raw_text)
                            
                            if not cleaned_line or len(cleaned_line) < 3:
                                continue
                                
                            low_line = cleaned_line.lower()

                            # ===== Detect CrewAI full completion =====
                            if 'Completed 3 tasks' in cleaned_line or 'Completed 3/3' in cleaned_line:
                                send_log("✅ CrewAI reports all tasks complete — exiting loop", 'success')
                                for task in ['planning', 'research', 'write']:
                                    if not task_completed[task]:
                                        complete_task(task)
                                crew_completed = True
                                break

                            # ===== Detect task transitions =====
                            task_match = re.search(r'Task\s+(\d+)/3', cleaned_line, re.IGNORECASE)
                            if task_match:
                                task_num = int(task_match.group(1))
                                task_map = {1: 'planning', 2: 'research', 3: 'write'}
                                this_task = task_map.get(task_num)
                                
                                if this_task:
                                    task_repeat_count[this_task] += 1
                                    
                                    # Anti-loop: only fires on truly pathological loops
                                    if task_repeat_count[this_task] > MAX_SAME_TASK_REPEATS:
                                        send_log(
                                            f"🔁 Task '{this_task}' repeated {task_repeat_count[this_task]} times — forcing complete",
                                            'warning'
                                        )
                                        complete_task(this_task)
                                        task_repeat_count[this_task] = 0
                                    
                                    if last_task_seen != this_task:
                                        last_task_seen = this_task
                                        last_task_change_time = time.time()
                                        send_log(f"📌 Task change detected: {this_task}")
                                
                                # ===== Task transitions (guarded — never restart completed) =====
                                if task_num == 1 and not task_completed['planning']:
                                    if current_task != 'planning':
                                        start_task('planning')
                                        current_task = 'planning'
                                        task_start_times['planning'] = time.time()
                                
                                elif task_num == 2 and not task_completed['research']:
                                    if not task_completed['planning']:
                                        complete_task('planning')
                                    if current_task != 'research':
                                        start_task('research')
                                        current_task = 'research'
                                        task_start_times['research'] = time.time()
                                
                                elif task_num == 3 and not task_completed['write']:
                                    if not task_completed['research']:
                                        complete_task('research')
                                    if current_task != 'write':
                                        start_task('write')
                                        current_task = 'write'
                                        task_start_times['write'] = time.time()
                            
                            # Completion indicators
                            if any(mark in cleaned_line for mark in ['✔', '✓', '✅']):
                                if 'planning' in low_line and not task_completed['planning']:
                                    complete_task('planning')
                                elif 'research' in low_line and not task_completed['research']:
                                    complete_task('research')
                                elif 'write' in low_line and not task_completed['write']:
                                    complete_task('write')
                            
                            # ===== Deduplicate "Task X/3" log lines =====
                            if 'Task' in cleaned_line and '/' in cleaned_line:
                                task_status_key = cleaned_line[:40]
                                now = time.time()
                                last_time = last_task_status_sent.get(task_status_key, 0)
                                
                                if now - last_time > 30:
                                    last_task_status_sent[task_status_key] = now
                                    send_log(cleaned_line, 'info')
                                continue
                            
                            # Send meaningful logs
                            skip_patterns = [
                                'crewai', 'tool usage', 'using tool',
                                '---', '===', '***', 'AGENTS',
                                'TOKENS', 'thinking', 'collection methods',
                                'Generating response', 'The task of',
                                'Installing dependencies', 'Creating virtual environment',
                                'Resolved', 'Installed', 'warning', 'Using CPython'
                            ]
                            if any(p in low_line for p in skip_patterns):
                                continue
                            
                            if 'error' in low_line:
                                send_log(f"❌ {cleaned_line}", 'error')
                            elif 'success' in low_line:
                                send_log(f"✅ {cleaned_line}", 'success')
                            elif len(cleaned_line) > 15:
                                send_log(cleaned_line, 'info')

                        except OSError:
                            break
                    else:
                        exit_code = process.poll()
                        if exit_code is not None:
                            send_log(f"✅ CrewAI process exited (code: {exit_code})", 'info')
                            break
                        
                        # Stuck detection
                        if time.time() - last_output_time > 120:
                            stuck_counter += 1
                            if stuck_counter > 3:
                                send_log("⚠️ Process seems stuck (no output for 6 min)", 'warning')
                                break
                        else:
                            stuck_counter = 0
                            
                except Exception as e:
                    send_log(f"⚠️ Error: {str(e)}", 'error')
                    break

            # ===== CLEANUP PROCESS =====
            if process:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    send_log("⚠️ Killing stuck process GROUP", 'warning')
                    kill_process_group(process)
                    try:
                        process.wait(timeout=5)
                    except:
                        pass
            
            if master:
                try:
                    os.close(master)
                except:
                    pass

            # ===== Check if CrewAI actually ran =====
            if process and process.returncode != 0 and not crew_completed:
                send_log(f"❌ CrewAI crashed with exit code {process.returncode}", 'error')
                send_log("❌ No agents actually executed — check logs above", 'error')
                
                for agent in ['supervisor', 'researcher', 'analyst']:
                    update_agent_status(agent, 'error')
                
                try:
                    log_q.put({
                        'type': 'complete',
                        'result': None,
                        'error': f'CrewAI startup failed (exit code {process.returncode})'
                    }, timeout=2)
                except queue.Full:
                    pass
                return

            # ===== Force completion (only after we've exited the loop) =====
            for task in ['planning', 'research', 'write']:
                if not task_completed[task]:
                    complete_task(task)
            
            send_log("✅ All agents complete!", 'success')

            # ===== Find report =====
            report_paths = [
                os.path.join(temp_dir, 'output', 'report_final.md'),
                os.path.join(temp_dir, 'output', 'report.md'),
                os.path.join(temp_dir, 'output', 'final_report.md'),
            ]
            
            report_content = None
            for path in report_paths:
                if os.path.exists(path):
                    file_age = time.time() - os.path.getmtime(path)
                    if file_age > 3600:
                        send_log(f"⚠️ Ignoring stale report: {os.path.basename(path)}", 'warning')
                        continue
                    
                    with open(path, 'r', encoding='utf-8') as f:
                        report_content = f.read()
                    send_log(f"📄 Report found: {os.path.basename(path)}")
                    break

            if report_content:
                project_report_path = os.path.join(PROJECT_ROOT, 'output', 'report_final.md')
                os.makedirs(os.path.join(PROJECT_ROOT, 'output'), exist_ok=True)
                
                with open(project_report_path, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                
                send_log(f"📄 Report saved ({len(report_content)} chars)")
                
                complete_event = {
                    'type': 'complete',
                    'result': report_content
                }
                
                sent = False
                for attempt in range(10):
                    try:
                        log_q.put(complete_event, timeout=1)
                        sent = True
                        break
                    except queue.Full:
                        send_log(f"⚠️ Queue full, retry {attempt+1}/10", 'warning')
                        time.sleep(0.5)
                
                if sent:
                    send_log("📤 Complete event delivered to frontend", 'success')
                else:
                    print(f"❌ CRITICAL: Could not deliver complete event for session {session_id}")
            else:
                send_log("⚠️ No report generated", 'warning')
                try:
                    log_q.put({
                        'type': 'complete',
                        'result': None
                    }, timeout=2)
                except queue.Full:
                    pass

    except Exception as e:
        send_log(f"❌ Error: {str(e)}", 'error')
        import traceback
        send_log(traceback.format_exc(), 'error')
        
        for agent in ['supervisor', 'researcher', 'analyst']:
            update_agent_status(agent, 'error')
        
        try:
            log_q.put({
                'type': 'complete',
                'result': None
            }, timeout=2)
        except queue.Full:
            pass
    finally:
        if process:
            try:
                if process.poll() is None:
                    kill_process_group(process)
                else:
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except:
                        pass
            except Exception as e:
                print(f"⚠️ Cleanup warning: {e}")
        
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        
        send_log("🏁 Process completed")