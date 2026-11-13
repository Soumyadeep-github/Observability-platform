#!/usr/bin/env python3
"""Serve the built UI and Python API together on localhost."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
if not python.exists():
    raise SystemExit('Create .venv and install backend/requirements-dev.txt first; see README.md.')
if not (ROOT / 'frontend/dist/index.html').exists():
    raise SystemExit('Build the UI first: python3 scripts/frontend.py build')
try:
    sys.exit(subprocess.call([str(python), '-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT / 'backend'))
except KeyboardInterrupt:
    pass
