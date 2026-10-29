"""Run a notebook in each of the image's kernels, inside the image.

Usage: ``docker exec mritogetherthon python /tests/smoke.py``. The notebooks
are written to ~/smoke, the attendee's folder, and executed there: the Python
one designs a Pulseq sequence, the Julia one simulates a sequence on a phantom
with KomaMRI. Exits 1 when a cell fails.
"""

import os
import sys
import time

import nbformat
from nbclient import NotebookClient

PYTHON = [
    "import numpy as np\nimport pypulseq as pp",
    "system = pp.Opts(max_grad=32, grad_unit='mT/m', max_slew=130, slew_unit='T/m/s')\n"
    "seq = pp.Sequence(system)\n"
    "rf, gz, _ = pp.make_sinc_pulse(flip_angle=np.pi / 8, duration=2e-3, slice_thickness=5e-3,\n"
    "                               apodization=0.5, time_bw_product=4, system=system, return_gz=True)\n"
    "gx = pp.make_trapezoid(channel='x', flat_area=64 / 0.256, flat_time=3.2e-3, system=system)\n"
    "adc = pp.make_adc(num_samples=64, duration=gx.flat_time, delay=gx.rise_time, system=system)\n"
    "seq.add_block(rf, gz)\n"
    "seq.add_block(gx, adc)\n"
    "ok, errors = seq.check_timing()\n"
    "assert ok, errors\n"
    "seq.write('smoke.seq')",
]

JULIA = [
    "using KomaMRICore",
    "sys = Scanner()\n"
    "seq = PulseDesigner.EPI_example()\n"
    "obj = brain_phantom2D()[1:50:end]\n"
    "raw = simulate(obj, seq, sys)\n"
    "@assert length(raw.profiles) > 0\n"
    "println(length(raw.profiles), \" profiles\")",
]


def run(name, kernel, cells):
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [nbformat.v4.new_code_cell(source) for source in cells]
    notebook.metadata["kernelspec"] = {"name": kernel, "display_name": kernel}
    folder = os.path.join(os.environ["HOME"], "smoke")
    os.makedirs(folder, exist_ok=True)
    started = time.monotonic()
    NotebookClient(notebook, timeout=1200, kernel_name=kernel,
                   resources={"metadata": {"path": folder}}).execute()
    nbformat.write(notebook, os.path.join(folder, f"{name}.ipynb"))
    print(f"{name}: {len(cells)} cells in {time.monotonic() - started:.0f} s", flush=True)


def main():
    from jupyter_client.kernelspec import KernelSpecManager

    kernels = KernelSpecManager().find_kernel_specs()
    julia = next(name for name in kernels if name.startswith("julia"))
    run("python", "python3", PYTHON)
    run("julia", julia, JULIA)
    return 0


if __name__ == "__main__":
    sys.exit(main())
