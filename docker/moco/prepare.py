"""Make the ISMRM MoCo workshop's notebooks run in the TogetherThon image.

Usage: ``python prepare.py WORKSHOP_DIR OUT_DIR``. The workshop's notebooks were
written for Google Colab and begin with cells that install everything (apt,
pip, git clone, cmake). The image has all of it already, so this

* drops those cells, and the Colab-only ``/content`` copies of the repository,
* points the data to the folder next to the notebook,
* selects the image's "Python 3.10 (MoCo)" kernel,
* adds a note on top saying so,

and copies the notebooks, with the workshop's ``utils`` and ``data``, to OUT_DIR.
Nothing else is changed, so that the notebooks stay the workshop's own.
"""

import re
import shutil
import sys
from pathlib import Path

import nbformat

NOTEBOOKS = ["HandsOn_ISMRM_MoCo_Workshop.ipynb", "HandsOn_ISMRM_MoCo_Workshop_solution.ipynb"]

#: A shell command that installs, builds or fetches the workshop's own code.
INSTALL = re.compile(
    r"apt(-get)? |pip (install|uninstall)|git clone|cmake|^\s*make\b|nvidia-smi"
    r"|update-alternatives|cp /content|\[ -d bart|ln -sf"
)
NOTE = (
    "> **In the TogetherThon environment** everything this notebook installs on Colab (apt, pip, "
    "BART, ESPIRiT, MERLIN, pysap, voxelmorph) is already in the image, so its installation cells "
    "were removed. Use the **Python 3.10 (MoCo)** kernel, and start with the *Imports*."
)


def is_install(source):
    if source.lstrip().startswith("%%bash"):
        return bool(INSTALL.search(source))
    return any(line.lstrip().startswith("!") and INSTALL.search(line) for line in source.splitlines())


def prepare(path, out):
    notebook = nbformat.read(path, as_version=4)
    cells = []
    for cell in notebook.cells:
        if cell.cell_type == "code":
            if is_install(cell.source):
                continue
            cell.source = cell.source.replace("/content/ismrm-moco-workshop/", "")
        cells.append(cell)
    cells.insert(0, nbformat.v4.new_markdown_cell(NOTE))
    notebook.cells = cells
    notebook.metadata["kernelspec"] = {
        "display_name": "Python 3.10 (MoCo)", "language": "python", "name": "moco"}
    nbformat.write(notebook, out / path.name)


def main(workshop, out):
    workshop, out = Path(workshop), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name in NOTEBOOKS:
        prepare(workshop / name, out)
    for folder in ("utils", "data"):
        shutil.copytree(workshop / folder, out / folder, dirs_exist_ok=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
