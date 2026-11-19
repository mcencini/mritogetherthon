"""Run the protocol-optimisation notebook's solution inside the image.

Usage: ``docker exec mritogetherthon python /tests/notebook.py``. Attendees get
``~/notebooks/placenta_b_optimisation.ipynb``, whose exercises are left to
write, so the check runs ``tests/placenta_b_optimisation_solved.ipynb``, the
same notebook with the exercises solved. It checks that

* the entry point put the attendees' notebook in their folder,
* both notebooks have the same cells outside the exercises, so that the solved
  one stays a faithful stand-in when the notebook is edited,
* the solved one runs to the end: ED_MRI and TADRED are installed, and their
  results folder is writable by the attendee's user.

Exits 1 when one of these fails.
"""

import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

given = Path.home() / "notebooks" / "placenta_b_optimisation.ipynb"
solved = Path(__file__).resolve().parent / "placenta_b_optimisation_solved.ipynb"
if not given.is_file():
    sys.exit(f"{given} is not there: the entry point should have copied it")

a = nbformat.read(given, as_version=4).cells
b = nbformat.read(solved, as_version=4).cells
if [c.cell_type for c in a] != [c.cell_type for c in b]:
    sys.exit("the notebook and its solved copy have different cells: update tests/ with it")
for x, y in zip(a, b):
    if x.cell_type == "markdown" and x.source != y.source:
        sys.exit(f"the notebook and its solved copy differ in a text cell:\n{x.source[:80]}")

notebook = nbformat.read(solved, as_version=4)
started = time.time()
NotebookClient(notebook, timeout=900, kernel_name="python3",
               resources={"metadata": {"path": str(Path.home())}}).execute()
print(f"{solved.name}: {len(notebook.cells)} cells in {time.time() - started:.0f} s")
