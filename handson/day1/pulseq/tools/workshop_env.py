"""Imported at the very top of the level files: makes sure they run in the workshop environment (.venv).

- First start: runs tools/install.py (only once, a few minutes).
- Started with another Python (e.g. the one on your computer, or the wrong one selected in VS Code):
  restarts the level file with the Python of .venv. You do not have to activate anything.

Set the environment variable WORKSHOP_NO_VENV=1 to switch this off (if you manage your environment yourself).
In a notebook (Google Colab, Jupyter) it does nothing: the notebook installs its packages itself.
"""

import os
import subprocess
import sys
from pathlib import Path

from tools import install


def _in_workshop_venv():
    try:
        return Path(sys.prefix).resolve() == install.VENV.resolve()
    except OSError:
        return False


IN_NOTEBOOK = 'ipykernel' in sys.modules or 'google.colab' in sys.modules

if not os.environ.get('WORKSHOP_NO_VENV') and not IN_NOTEBOOK:
    if not install.is_installed():
        print('First start (or the requirements changed): setting up the workshop environment.')
        print('This happens only once and takes a few minutes.\n', flush=True)
        if install.main([]) != 0:
            sys.exit(1)
        print()
    if not _in_workshop_venv():
        # restart this script with the workshop Python (same arguments, same working directory)
        sys.stdout.flush()
        sys.exit(subprocess.call([str(install.venv_python()), *sys.argv]))
