"""Run this first: checks that everything is installed, and tells you how to fix what is missing.

usage (from the repository folder):   python tools/check_setup.py
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
VENV = ROOT / '.venv'
VENV_PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
ok = True

# check the workshop environment, not the Python this was started with
if Path(sys.prefix).resolve() != VENV.resolve() and not os.environ.get('WORKSHOP_NO_VENV'):
    if VENV_PYTHON.exists():
        sys.exit(subprocess.call([str(VENV_PYTHON), __file__]))
    print('The workshop environment (.venv) does not exist yet.')
    print('Set it up with:   python tools/install.py     (or simply start:  python level1_beginner.py)')
    sys.exit(1)


def need(cond, msg, fix=''):
    global ok
    print(f'  [{"OK" if cond else "MISSING"}] {msg}' + ('' if cond else f'\n            -> {fix}'))
    ok &= bool(cond)


def info(msg):
    print(f'  [INFO] {msg}')


print('Python')
need(sys.version_info >= (3, 10), f'Python {sys.version.split()[0]} (>= 3.10 needed)',
     'install a newer Python from https://www.python.org/downloads/')

print('\nRepository (git submodules)')
for sub in ('pypulseq', 'pulseq'):
    d = TOOLS / 'external' / sub
    if d.exists() and any(d.iterdir()):
        need(True, f'tools/external/{sub}')
    elif sub == 'pypulseq':
        info('tools/external/pypulseq is empty (ZIP download?) -> fine, pypulseq comes from PyPI instead')
    else:
        info('tools/external/pulseq is empty (ZIP download?) -> fine, it only holds the MATLAB demos for reference')

print('\nPython packages')
for mod in ('numpy', 'scipy', 'matplotlib', 'sigpy', 'pypulseq'):
    try:
        m = importlib.import_module(mod)
        need(True, f'{mod} {getattr(m, "__version__", "")}')
    except ImportError:
        need(False, mod, 'python tools/install.py')
try:
    import pypulseq
    src = Path(pypulseq.__file__).resolve()
    submodule = TOOLS / 'external' / 'pypulseq'
    if (submodule / 'pyproject.toml').exists() and submodule not in src.parents:
        info(f'pypulseq is loaded from {src.parent},')
        info('not from tools/external/pypulseq. Fine if it is version 1.5.0.post1, otherwise: python tools/install.py')
except ImportError:
    pass

if ok:
    import numpy as np
    import pypulseq as pp
    from pypulseq.make_sigpy_pulse import sigpy_n_seq  # noqa: F401  (needed for the SLR pulse)

    seq = pp.Sequence()
    seq.add_block(pp.make_block_pulse(np.pi / 2, duration=1e-3))
    seq.add_block(pp.make_adc(64, duration=3.2e-3))
    out = TOOLS / 'export' / 'setup_test.seq'
    out.parent.mkdir(exist_ok=True)
    seq.write(str(out))
    need(True, f'pypulseq can write a sequence ({out.relative_to(ROOT)})')

print('\nPlots')
try:
    import matplotlib
    backend = matplotlib.get_backend()
except ImportError:
    backend = 'agg'
if backend.lower() in ('agg', 'pdf', 'svg', 'ps', 'cairo', 'template'):
    info(f'matplotlib backend {backend}: no plot windows, the plots are saved as PNG files to tools/export/')
    info('(normal over SSH or in a container without a display; on a desktop: python tools/install.py)')
else:
    need(True, f'matplotlib backend {backend}: interactive plot windows (mouse wheel = zoom)')

print('\nSimulation (optional, only for the simulation at the end)')
try:
    import MRzeroCore  # noqa: F401
    import torch
    need(True, f'MRzero {getattr(MRzeroCore, "__version__", "")}, torch {torch.__version__}'
               + ('' if torch.version.cuda is None else '  (CUDA version: large, the CPU version is enough)'))
except ImportError:
    if sys.version_info >= (3, 14) and sys.platform != 'win32':
        info('MRzero is not available for Python 3.14 on Linux / macOS yet.')
        info('Use the workshop environment:   python tools/install.py --fresh')
    else:
        info('MRzero not installed. Only needed for the simulation:   python tools/install.py')

print('\nAll good, have fun!  Start with:  python level1_beginner.py' if ok
      else '\nPlease fix the MISSING items above (or ask a tutor).')
sys.exit(0 if ok else 1)
