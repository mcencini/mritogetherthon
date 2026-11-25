"""Run day 1's protocol-optimisation notebook, as completed, as an attendee would.

Usage: ``docker exec mritogetherthon python /tests/notebook.py [notebook]``.
The notebook, by default the completed one of tests/fixtures (attendees get the
exercise, in handson/day1, whose gaps they fill in), is copied to the attendee's folder and executed there, as an attendee's copy is, so
that the check covers ED_MRI and TADRED being installed, their results folder
being writable by the attendee's user, and every cell running through to the
end. Exits 1 when the notebook is missing or a cell fails.
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
path = Path.home() / "smoke" / source.name
path.parent.mkdir(exist_ok=True)
shutil.copy(source, path)

notebook = nbformat.read(path, as_version=4)
started = time.time()
NotebookClient(notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
print(f"{path.name}: {len(notebook.cells)} cells in {time.time() - started:.0f} s")
