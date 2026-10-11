"""WSGI entry point for PythonAnywhere and gunicorn.

PythonAnywhere:
  - Point the WSGI file at this module, or paste the loader below into
    /var/www/<yourusername>_pythonanywhere_com_wsgi.py
  - Ensure the virtualenv and project path are on sys.path.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402

application = create_app()
