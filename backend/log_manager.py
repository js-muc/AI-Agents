import queue
from datetime import datetime
import json

log_queues = {}
reports = {}

def get_log_queue(session_id):
    """Get or create a log queue for a session"""
    if session_id not in log_queues:
        # Increase maxsize to prevent blocking
        log_queues[session_id] = queue.Queue(maxsize=1000)
    return log_queues[session_id]

def clear_log_queue(session_id):
    """Clear all messages from a session's queue"""
    if session_id in log_queues:
        q = log_queues[session_id]
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
            except Exception:
                pass

def delete_log_queue(session_id):
    """Delete a session's queue"""
    if session_id in log_queues:
        # Clear first
        clear_log_queue(session_id)
        del log_queues[session_id]

def create_log_message(message, level='info'):
    """Create a standard log message"""
    return {
        'timestamp': datetime.now().strftime('%H:%M:%S'),
        'message': str(message),
        'level': level
    }

def create_agent_status_message(agent, status):
    """Create an agent status message for the UI"""
    return {
        'type': 'agent_status',
        'agent': agent,      # 'supervisor', 'researcher', 'analyst'
        'status': status     # 'working', 'complete', 'error', 'idle'
    }

def store_report(session_id, report):
    """Store a report for a session"""
    reports[session_id] = report

def get_report(session_id):
    """Get a stored report"""
    return reports.get(session_id)

def delete_report(session_id):
    """Delete a stored report"""
    if session_id in reports:
        del reports[session_id]

def cleanup_session(session_id):
    """Clean up all resources for a session"""
    delete_log_queue(session_id)
    delete_report(session_id)

def get_queue_size(session_id):
    """Get the size of a session's queue (for monitoring)"""
    if session_id in log_queues:
        return log_queues[session_id].qsize()
    return 0

def is_queue_empty(session_id):
    """Check if a session's queue is empty"""
    if session_id in log_queues:
        return log_queues[session_id].empty()
    return True

def get_all_active_sessions():
    """Get list of all active session IDs"""
    return list(log_queues.keys())

def get_session_count():
    """Get the number of active sessions"""
    return len(log_queues)