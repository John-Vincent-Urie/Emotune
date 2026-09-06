"""Run ml_model scripts without activating the virtualenv.

Every entry point here needs packages that live only in `backend/venv`, so
`python3 ml_model/train_baseline.py` used to die on an import error that reads
like a broken install rather than a forgotten `source venv/bin/activate`. The
dependencies are sitting right there in the repo, so use them.

Call `ensure_local_venv()` at the very top of a script, before importing
anything that is not in the standard library.

`backend/manage.py` carries its own copy of this logic on purpose: it cannot
import from here, and bootstrap code has to run before the project is
importable at all.
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / 'backend'

# Marker so a re-exec can never loop, however the venv is broken.
_REEXEC_FLAG = 'EMOTUNE_ML_REEXEC'


def local_venv_python():
    """The interpreter inside backend/venv, if there is one."""
    venv_dir = BACKEND_DIR / 'venv'
    candidate = (
        venv_dir / 'Scripts' / 'python.exe'
        if os.name == 'nt'
        else venv_dir / 'bin' / 'python'
    )
    return candidate if candidate.is_file() else None


def ensure_local_venv(probe_module='django'):
    """Restart under backend/venv if `probe_module` is missing here.

    `probe_module` should be something the calling script actually imports, so
    a script that only needs pandas is not judged on whether Django happens to
    be installed.

    Anything unexpected -- no venv, an already-correct interpreter, a venv that
    still lacks the package -- falls through and lets the script raise its own
    import error, which names the missing package.
    """
    if os.environ.get(_REEXEC_FLAG) or importlib.util.find_spec(probe_module):
        return

    interpreter = local_venv_python()
    if interpreter is None:
        return
    # Compared unresolved on purpose: a venv's bin/python is a symlink to the
    # system interpreter, so resolve() makes the two look identical and the
    # re-exec never happens. A venv is the path you invoke, not the binary
    # behind it. The env marker above is what actually prevents a loop.
    if Path(sys.executable) == interpreter:
        return

    os.environ[_REEXEC_FLAG] = '1'
    try:
        os.execv(str(interpreter), [str(interpreter), *sys.argv])
    except OSError:
        os.environ.pop(_REEXEC_FLAG, None)


def add_backend_to_path():
    """Put backend/ on sys.path so `ml.*` and the Django apps are importable."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
