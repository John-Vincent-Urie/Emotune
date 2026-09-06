#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""
import importlib.util
import os
import sys
from pathlib import Path

# Marker so a re-exec can never loop, however the venv is broken.
_REEXEC_FLAG = 'EMOTUNE_MANAGE_REEXEC'


def _local_venv_python():
    """The interpreter inside backend/venv, if there is one."""
    venv_dir = Path(__file__).resolve().parent / 'venv'
    candidate = (
        venv_dir / 'Scripts' / 'python.exe'
        if os.name == 'nt'
        else venv_dir / 'bin' / 'python'
    )
    return candidate if candidate.is_file() else None


def _reexec_under_local_venv():
    """Restart under backend/venv when the current interpreter lacks Django.

    `python3 manage.py runserver` outside an activated venv used to fail with
    "Couldn't import Django", which reads like a broken install rather than a
    forgotten `source venv/bin/activate`. The dependencies are right there next
    to this file, so use them.

    Resolved from this file's own location, never a hardcoded path, so it works
    for anyone who cloned the repo. Anything unexpected -- no venv, an
    already-correct interpreter, a venv that still has no Django -- falls
    through to Django's own import error, which says what to do.
    """
    if os.environ.get(_REEXEC_FLAG) or importlib.util.find_spec('django'):
        return

    interpreter = _local_venv_python()
    if interpreter is None:
        return
    # Compared unresolved on purpose. A venv's bin/python is a symlink to the
    # system interpreter, so resolve() makes the two look identical and the
    # re-exec never happens -- a venv is the path you invoke, not the binary
    # behind it. The env marker above is what actually prevents a loop.
    if Path(sys.executable) == interpreter:
        return

    os.environ[_REEXEC_FLAG] = '1'
    try:
        os.execv(str(interpreter), [str(interpreter), *sys.argv])
    except OSError:
        # Let the normal import error below explain the problem instead.
        os.environ.pop(_REEXEC_FLAG, None)


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'emotune_project.settings')
    _reexec_under_local_venv()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
