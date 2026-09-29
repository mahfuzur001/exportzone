"""Passenger entry point (cPanel / shared hosting).

Passenger loads this module by file path from the application root, so the
project directory must be on ``sys.path`` before ``config.settings`` can be
imported. The settings module is then resolved exactly as it is for
``python manage.py runserver``, which keeps a single source of truth.
"""

import os
import sys

from django.core.wsgi import get_wsgi_application # type: ignore

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()