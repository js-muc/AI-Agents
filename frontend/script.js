// ===== DOM REFERENCES =====
const form = document.getElementById('agentForm');
const submitBtn = document.getElementById('submitBtn');
const topicInput = document.getElementById('topic');
const recipientInput = document.getElementById('recipient');
const logContainer = document.getElementById('logContainer');
const logCount = document.getElementById('logCount');
const reportPanel = document.getElementById('reportPanel');
const reportContent = document.getElementById('reportContent');
const downloadBtn = document.getElementById('downloadBtn');
const statusBadge = document.getElementById('statusBadge');
const overallStatus = document.getElementById('overallStatus');
const navStatusText = document.getElementById('navStatusText');
const navStatusDot = document.getElementById('navStatusDot');

let sessionId = 'session_' + Date.now();
let reportContentText = '';
let eventSource = null;
let logCountValue = 0;
let isProcessing = false;
let sessionComplete = false;   // ← FIX: Prevents late messages overwriting complete status

// ===== AGENT STATUS ELEMENTS (ONLY 3 AGENTS) =====
const agentStatusMap = {
    supervisor: document.getElementById('status-supervisor'),
    researcher: document.getElementById('status-researcher'),
    analyst: document.getElementById('status-analyst')
};

// ===== ADD LOG =====
function addLog(message, level = 'info') {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    
    let displayMessage = message;
    entry.innerHTML = `<span class="log-time">[${time}]</span><span class="log-message level-${level}">${displayMessage}</span>`;
    logContainer.appendChild(entry);
    logContainer.scrollTop = logContainer.scrollHeight;
    logCountValue++;
    logCount.textContent = logCountValue;
}

// ===== UPDATE STATUS =====
function setStatus(status, type = 'idle') {
    const map = {
        idle: { text: '● Idle', class: 'idle', navText: 'System Ready' },
        working: { text: '● Processing...', class: 'working', navText: 'Processing...' },
        complete: { text: '● Complete', class: 'complete', navText: 'Complete' },
        error: { text: '● Error', class: 'error', navText: 'Error' }
    };
    const s = map[type] || map.idle;
    statusBadge.textContent = s.text;
    statusBadge.className = 'card-badge ' + s.class;
    overallStatus.textContent = s.text;
    navStatusText.textContent = s.navText;
    navStatusDot.style.background = type === 'working' ? '#f59e0b' : type === 'complete' ? '#10b981' : type === 'error' ? '#ef4444' : '#10b981';
}

// ===== UPDATE AGENT STATUS =====
function updateAgentStatus(agent, status) {
    // ===== FIX: Guard against late status updates after session is complete =====
    if (sessionComplete && status !== 'complete') {
        console.log(`Ignoring late status: ${agent} → ${status}`);
        return;
    }
    
    const el = agentStatusMap[agent];
    if (!el) return;
    
    const statusMap = {
        idle: { text: '⏸️ Idle', class: 'idle' },
        working: { text: '🔄 Working', class: 'working' },
        complete: { text: '✅ Complete', class: 'complete' },
        error: { text: '❌ Error', class: 'error' }
    };
    const s = statusMap[status] || statusMap.idle;
    el.textContent = s.text;
    el.className = 'agent-status-badge ' + s.class;
    
    // ===== SAFETY NET: If all 3 agents complete, stop spinner =====
    const allComplete = ['supervisor', 'researcher', 'analyst'].every(name => {
        const agentEl = agentStatusMap[name];
        return agentEl && agentEl.className.includes('complete');
    });
    
    if (allComplete && isProcessing) {
        setTimeout(() => {
            if (isProcessing) {
                isProcessing = false;
                sessionComplete = true;
                setStatus('Complete', 'complete');
                submitBtn.disabled = false;
                submitBtn.classList.remove('loading');
                submitBtn.querySelector('.btn-text').textContent = '🚀 Generate Research Report';
                
                if (eventSource) {
                    eventSource.onerror = null;
                    eventSource.close();
                    eventSource = null;
                }
            }
        }, 2000);
    }
}

// ===== RESET AGENT STATUSES =====
function resetAgentStatuses() {
    for (const key in agentStatusMap) {
        updateAgentStatus(key, 'idle');
    }
}

// ===== DETECT AGENT FROM LOG (ONLY 3 AGENTS) =====
function detectAgent(message) {
    const lower = message.toLowerCase();
    if (lower.includes('supervisor') || lower.includes('planning')) return 'supervisor';
    if (lower.includes('researcher') || lower.includes('search') || lower.includes('serper')) return 'researcher';
    if (lower.includes('analyst') || lower.includes('analyzing') || lower.includes('report')) return 'analyst';
    return null;
}

// ===== CHECK IF MESSAGE IS AGENT STATUS =====
function isAgentStatusMessage(message) {
    const statusPatterns = ['supervisor is', 'researcher is', 'analyst is'];
    return statusPatterns.some(pattern => message.toLowerCase().includes(pattern));
}

// ===== CONNECT TO LOGS =====
function connectLogs(sessionId) {
    if (eventSource) { 
        eventSource.close(); 
        eventSource = null;
    }
    
    eventSource = new EventSource(`/api/logs/${sessionId}`);
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // ===== HANDLE AGENT STATUS MESSAGES =====
            if (data.type === 'agent_status') {
                const agent = data.agent;
                const status = data.status;
                
                if (agent && status) {
                    updateAgentStatus(agent, status);
                    
                    const statusEmoji = status === 'working' ? '🔄' : status === 'complete' ? '✅' : '❌';
                    addLog(`${statusEmoji} ${agent.charAt(0).toUpperCase() + agent.slice(1)} is ${status}`, 'status');
                }
                return;
            }
            
            // ===== HANDLE PING =====
            if (data.type === 'ping') return;
            
            // ===== HANDLE COMPLETE =====
            if (data.type === 'complete') {
                isProcessing = false;
                sessionComplete = true;   // ← FIX: Lock session
                
                // 1. Mark ALL agents as complete (always, regardless of result)
                for (const key in agentStatusMap) {
                    updateAgentStatus(key, 'complete');
                }
                
                // 2. If we have a report, display it
                if (data.result && data.result.trim().length > 0) {
                    reportContentText = data.result;
                    reportContent.textContent = data.result;
                    reportPanel.classList.add('show');
                    addLog('✅ Report generated successfully!', 'success');
                } else {
                    addLog('⚠️ Process finished but no report was generated', 'warning');
                }
                
                // 3. ALWAYS set overall status to Complete
                setStatus('Complete', 'complete');
                
                // 4. ALWAYS stop spinner
                submitBtn.disabled = false;
                submitBtn.classList.remove('loading');
                submitBtn.querySelector('.btn-text').textContent = '🚀 Generate Research Report';
                
                // 5. Cleanly close EventSource WITHOUT triggering reconnect
                if (eventSource) {
                    eventSource.onerror = null;
                    eventSource.close();
                    eventSource = null;
                }
                return;
            }
            
            // ===== HANDLE REGULAR LOGS =====
            if (data.message) {
                addLog(data.message, data.level || 'info');
                
                // Backup detection method (only if session not complete)
                if (!sessionComplete) {
                    const agent = detectAgent(data.message);
                    if (agent) {
                        const isComplete = data.message.includes('complete') || 
                                           data.message.includes('success') || 
                                           data.message.includes('done') ||
                                           data.message.includes('finished') ||
                                           data.message.includes('generated') ||
                                           data.message.includes('✅');
                        
                        if (isComplete) {
                            updateAgentStatus(agent, 'complete');
                        } else if (!isAgentStatusMessage(data.message)) {
                            const currentStatus = agentStatusMap[agent]?.className || '';
                            if (!currentStatus.includes('complete')) {
                                updateAgentStatus(agent, 'working');
                            }
                        }
                    }
                }
            }
            
        } catch (error) {
            console.error('Error processing event:', error);
        }
    };
    
    eventSource.onerror = function() {
        // Only reconnect if we're still processing AND stream isn't closed
        if (!isProcessing || sessionComplete) {
            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }
            return;
        }
        
        setTimeout(() => {
            if (isProcessing && !sessionComplete && eventSource && eventSource.readyState !== EventSource.CLOSED) {
                eventSource.close();
                connectLogs(sessionId);
            }
        }, 3000);
    };
}

// ===== FORM SUBMIT =====
form.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    if (isProcessing) {
        addLog('⚠️ A request is already in progress. Please wait.', 'warning');
        return;
    }
    
    const topic = topicInput.value.trim();
    const recipient = recipientInput.value.trim();

    if (!topic || !recipient) {
        addLog('⚠️ Please fill in both fields', 'error');
        if (!topic) topicInput.style.borderColor = '#ef4444';
        if (!recipient) recipientInput.style.borderColor = '#ef4444';
        setTimeout(() => {
            topicInput.style.borderColor = '';
            recipientInput.style.borderColor = '';
        }, 3000);
        return;
    }

    // Reset everything
    resetAgentStatuses();
    isProcessing = true;
    sessionComplete = false;   // ← FIX: Reset for new run
    submitBtn.disabled = true;
    submitBtn.classList.add('loading');
    submitBtn.querySelector('.btn-text').textContent = '⏳ Generating...';
    setStatus('Processing...', 'working');
    reportPanel.classList.remove('show');
    reportContent.textContent = '';
    reportContentText = '';
    logContainer.innerHTML = '';
    logCountValue = 0;
    logCount.textContent = '0';
    
    sessionId = 'session_' + Date.now();

    addLog('🚀 Starting: ' + topic, 'info');
    addLog('📧 Recipient: ' + recipient, 'info');

    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic, recipient, session_id: sessionId })
        });
        
        const data = await response.json();
        
        if (data.success) {
            connectLogs(sessionId);
        } else {
            addLog('❌ Error: ' + data.error, 'error');
            setStatus('Error', 'error');
            isProcessing = false;
            sessionComplete = true;
            submitBtn.disabled = false;
            submitBtn.classList.remove('loading');
            submitBtn.querySelector('.btn-text').textContent = '🔄 Retry Generation';
        }
    } catch (error) {
        addLog('❌ Network error: ' + error.message, 'error');
        setStatus('Error', 'error');
        isProcessing = false;
        sessionComplete = true;
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
        submitBtn.querySelector('.btn-text').textContent = '🔄 Retry Generation';
    }
});

// ===== DOWNLOAD =====
downloadBtn.addEventListener('click', function() {
    if (reportContentText) {
        try {
            const blob = new Blob([reportContentText], { type: 'text/markdown;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
            a.download = `research_report_${timestamp}.md`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            addLog('📥 Report downloaded', 'info');
        } catch (error) {
            addLog('❌ Error downloading report: ' + error.message, 'error');
        }
    } else {
        addLog('⚠️ No report available to download', 'warning');
    }
});

// ===== KEYBOARD SHORTCUTS =====
document.addEventListener('keydown', function(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        form.dispatchEvent(new Event('submit'));
    }
});

// ===== CLEANUP ON UNLOAD =====
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.onerror = null;
        eventSource.close();
        eventSource = null;
    }
});

// ===== INITIAL =====
setStatus('Idle', 'idle');
addLog('💡 Enter a topic and email to get started', 'info');
addLog('🤖 3-Agent System: Supervisor → Researcher → Analyst', 'info');
addLog('⌨️ Press Ctrl+Enter to submit', 'info');