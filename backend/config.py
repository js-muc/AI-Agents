import os

# ================================================================
# CONFIGURATION
# ================================================================
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_FOLDER = os.path.join(PROJECT_ROOT, 'frontend')
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, 'output')

# Virtual environment paths
VENV_FOLDER = os.path.join(PROJECT_ROOT, '.venv')

CREWAI_EXE = os.path.join(VENV_FOLDER, 'bin', 'crewai')
if not os.path.exists(CREWAI_EXE):
    CREWAI_EXE = os.path.join(VENV_FOLDER, 'Scripts', 'crewai.exe')
if not os.path.exists(CREWAI_EXE):
    CREWAI_EXE = 'crewai'

# Server configuration
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000
DEBUG_MODE = True