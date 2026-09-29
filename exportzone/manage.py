#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    """Run administrative commands."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - Django supplies this error path.
        raise ImportError(
            "Couldn't import Django. Ensure dependencies are installed and the "
            "virtual environment is active."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
