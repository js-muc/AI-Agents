from flask import Flask, send_from_directory, jsonify, request, Response, stream_with_context
import threading
import json
import queue
from datetime import datetime

from config import PROJECT_ROOT, FRONTEND_FOLDER, SERVER_HOST, SERVER_PORT, DEBUG_MODE
from log_manager import get_log_queue, clear_log_queue, delete_log_queue, get_report, delete_report
from agent_runner import run_agent
from pdf_generator import generate_pdf

app = Flask(__name__)

@app.route('/')
def index():
    return send_from_directory(FRONTEND_FOLDER, 'index.html')

@app.route('/static/style.css')
def serve_css():
    return send_from_directory(FRONTEND_FOLDER, 'style.css', mimetype='text/css')

@app.route('/static/script.js')
def serve_js():
    return send_from_directory(FRONTEND_FOLDER, 'script.js', mimetype='application/javascript')

@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND_FOLDER, path)

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json
    topic = data.get('topic')
    recipient = data.get('recipient')
    session_id = data.get('session_id', 'default')

    if not topic or not recipient:
        return jsonify({'success': False, 'error': 'Missing topic or recipient'})

    clear_log_queue(session_id)

    thread = threading.Thread(target=run_agent, args=(session_id, topic, recipient))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'session_id': session_id
    })

@app.route('/api/logs/<session_id>', methods=['GET'])
def get_logs(session_id):
    def generate():
        log_q = get_log_queue(session_id)
        while True:
            try:
                item = log_q.get(timeout=5)
                if item.get('type') == 'complete':
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"

        delete_log_queue(session_id)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/download/<session_id>', methods=['GET'])
def download_report(session_id):
    report = get_report(session_id)
    if not report:
        return jsonify({'success': False, 'error': 'Report not found'}), 404

    try:
        pdf_bytes = generate_pdf(report)
        return Response(pdf_bytes, mimetype='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename=report_{session_id}.pdf'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'PDF generation failed: {str(e)}'}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 AI Research Agent Server")
    print("=" * 60)
    print(f"✅ Server: http://{SERVER_HOST}:{SERVER_PORT}")
    print("=" * 60)
    app.run(debug=DEBUG_MODE, port=SERVER_PORT, host=SERVER_HOST)