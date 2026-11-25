"""One-output adapter for the BART CLI on Linux, macOS and Windows/WSL."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np


def find_bart():
    candidates = []
    for name in ("BART_TOOLBOX_PATH", "TOOLBOX_PATH"):
        if os.environ.get(name):
            candidates.append(("native", str(Path(os.environ[name]) / "bart")))
    if shutil.which("bart"):
        candidates.append(("native", shutil.which("bart")))
    if os.name == "nt" and shutil.which("wsl.exe"):
        candidates.append(("WSL", shutil.which("wsl.exe")))
    for mode, executable in candidates:
        args = [executable, "version"] if mode == "native" else [executable, "-e", "bart", "version"]
        try:
            result = subprocess.run(args, capture_output=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired):
            continue
        version = result.stdout.decode(errors="replace").strip()
        if result.returncode == 0 and version:
            return mode, executable, version
    raise RuntimeError("Install Berkeley Advanced Reconstruction Toolbox (BART), then rerun this cell. "
                       "See https://mrirecon.codeberg.page/installation.html .")


def bart(args, *arrays):
    """Pass complex NumPy arrays to one BART command and return its output array."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        inputs = []
        for i, array in enumerate(arrays):
            array = np.asarray(array, dtype=np.complex64)
            name = f"in{i}"
            (root / f"{name}.hdr").write_text("# Dimensions\n" + " ".join(map(str, array.shape)) + "\n")
            array.ravel(order="F").tofile(root / f"{name}.cfl")
            inputs.append(f"{root.name}/{name}")
        command = [bart_executable]
        if bart_mode == "WSL":
            command += ["--cd", str(root.parent), "-e", "/usr/bin/env", "OMP_NUM_THREADS=1",
                        "OPENBLAS_NUM_THREADS=1", "bart"]
        threads = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        result = subprocess.run(command + list(args) + inputs + [f"{root.name}/out"], cwd=root.parent, env=threads,
                                capture_output=True)
        if result.returncode:
            message = (result.stderr + result.stdout).decode(errors="replace").strip()
            raise RuntimeError(f"BART {' '.join(args)} failed. {message}")
        dimensions = list(map(int, (root / "out.hdr").read_text().splitlines()[1].split()))
        rank = max((np.ndim(array) for array in arrays), default=1)
        while len(dimensions) > rank and dimensions[-1] == 1:
            dimensions.pop()
        dimensions += [1] * (rank - len(dimensions))
        return np.fromfile(root / "out.cfl", dtype=np.complex64).reshape(dimensions, order="F")


bart_mode, bart_executable, bart_version = find_bart()
