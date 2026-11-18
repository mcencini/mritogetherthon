"""Run the protocol-optimisation notebook the image carries, inside the image.

Usage: ``docker exec mritogetherthon python /tests/notebook.py``. The notebook
is the copy the entry point put in ~/notebooks, executed there, so that the
check covers what an attendee opens: ED_MRI and TADRED installed, their results
folder writable by the attendee's user, and every cell running through to the
end. Exits 1 when the notebook is missing or a cell fails.
"""

import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient

path = Path.home() / "notebooks" / "placenta_b_optimisation.ipynb"
if not path.is_file():
    sys.exit(f"{path} is not there: the entry point should have copied it")

notebook = nbformat.read(path, as_version=4)
started = time.time()
NotebookClient(notebook, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(path.parent)}}).execute()
print(f"{path.name}: {len(notebook.cells)} cells in {time.time() - started:.0f} s")
