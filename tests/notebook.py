"""Run a hands-on notebook, as an attendee would.

Usage: ``docker exec mritogetherthon python /tests/notebook.py [notebook]``.
The notebook, by default day 1's completed one of tests/fixtures (attendees get
the exercise, in handson/day1, whose gaps they fill in), is copied with the
folder it is in (its helper modules and data) to the attendee's folder, and
executed there, as an attendee's copy is. For day 1 the check covers ED_MRI and
TADRED being installed and their results folder being writable by the
attendee's user; for every notebook, each cell running through to the end.
Exits 1 when the notebook is missing or a cell fails.
"""

import shutil
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

source = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "fixtures/day1_placenta_b_optimisation_complete.ipynb")
if not source.is_file():
    sys.exit(f"{source} is not there")
folder = Path.home() / "smoke" / source.parent.name
shutil.copytree(source.parent, folder, dirs_exist_ok=True)
path = folder / source.name
# The material is read-only in the environment (sync-material); the copy is the attendee's.
for item in [folder, *folder.rglob("*")]:
    item.chmod(item.stat().st_mode | 0o200)

notebook = nbformat.read(path, as_version=4)
started = time.time()
NotebookClient(notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
print(f"{path.name}: {len(notebook.cells)} cells in {time.time() - started:.0f} s")
