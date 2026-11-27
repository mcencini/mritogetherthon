"""Sets up everything for the workshop. Runs automatically the first time you start a level file.

You can also run it by hand (from the repository folder):
    python tools/install.py             set up, or repair a broken installation
    python tools/install.py --no-sim    without the simulation packages (MRzero + PyTorch, ~1 GB less)
    python tools/install.py --fresh     delete the environment and set it up again from scratch

What it does (every step is skipped if it is already done):
    1. git submodules (tools/external), if the repository was cloned without --recursive
    2. uv (https://github.com/astral-sh/uv): a small tool that downloads Python 3.13 -> tools/.uv
    3. the virtual environment .venv with Python 3.13 (independent of the Python on your computer)
    4. the packages: tools/requirements.txt (+ tools/requirements-sim.txt, CPU only, no CUDA)
    5. interactive plot windows (installs PyQt6 if no GUI toolkit is available)
    6. the installation check (tools/check_setup.py)

Only the Python standard library is used here, so this runs with any Python >= 3.8.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
VENV = ROOT / '.venv'
UV_DIR = TOOLS / '.uv'
UV_VERSION = '0.13.10'
PYTHON_VERSION = '3.13'
SUPPORTED = [(3, 10), (3, 11), (3, 12), (3, 13)]      # MRzero is not available for 3.14 on Linux / macOS yet
PYPULSEQ_SUBMODULE = '-e ./external/pypulseq[sigpy]'
PYPULSEQ_PYPI = 'pypulseq[sigpy]==1.5.0.post1'
MARKER = VENV / '.workshop-installed'
NON_INTERACTIVE = ('agg', 'pdf', 'svg', 'ps', 'cairo', 'template')


def venv_python():
    return VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def fingerprint():
    """changes when the requirements change -> the level files run the installation again"""
    h = hashlib.sha256()
    for f in ('requirements.txt', 'requirements-sim.txt'):
        h.update((TOOLS / f).read_bytes())
    h.update(PYTHON_VERSION.encode())
    return h.hexdigest()[:16]


def is_installed():
    return venv_python().exists() and MARKER.exists() and MARKER.read_text().split()[:1] == [fingerprint()]


def run(cmd, quiet=False, **kw):
    """run a command; quiet: show its output only if it fails (pip prints many harmless warnings)"""
    print('    $ ' + ' '.join(str(c) for c in cmd), flush=True)
    if not quiet:
        subprocess.run([str(c) for c in cmd], check=True, **kw)
        return
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout[-5000:] + r.stderr[-5000:])
        raise subprocess.CalledProcessError(r.returncode, cmd)


def output(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ''


def step(n, text):
    print(f'\n[{n}/6] {text}', flush=True)


# ------------------------------------------------------------------ 1. submodules
def submodules():
    step(1, 'libraries in tools/external (git submodules)')
    marker = TOOLS / 'external' / 'pypulseq' / 'pyproject.toml'
    if not marker.exists() and (ROOT / '.git').exists() and shutil.which('git'):
        try:
            run(['git', 'submodule', 'update', '--init', '--depth', '1'], cwd=ROOT)
        except subprocess.CalledProcessError:
            pass
    if marker.exists():
        print('    ok')
        return True
    print('    not available (repository downloaded as ZIP, or no git) -> pypulseq is installed from PyPI instead')
    return False


# ------------------------------------------------------------------ 2. uv
def uv_target():
    arch = {'x86_64': 'x86_64', 'amd64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}.get(platform.machine().lower())
    system = {'win32': 'pc-windows-msvc', 'darwin': 'apple-darwin'}.get(sys.platform)
    if sys.platform.startswith('linux'):
        system = 'unknown-linux-gnu'
    return f'{arch}-{system}' if arch and system else None


def get_uv():
    step(2, f'uv {UV_VERSION} (downloads Python {PYTHON_VERSION} for the workshop)')
    exe = UV_DIR / ('uv.exe' if os.name == 'nt' else 'uv')
    if exe.exists():
        print('    ok')
        return exe
    target = uv_target()
    if target is None:
        print(f'    no uv for this computer ({sys.platform}, {platform.machine()})')
        return None
    ext = 'zip' if sys.platform == 'win32' else 'tar.gz'
    url = f'https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/uv-{target}.{ext}'
    print(f'    downloading {url}', flush=True)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / f'uv.{ext}'
            urllib.request.urlretrieve(url, archive)
            UV_DIR.mkdir(exist_ok=True)
            if ext == 'zip':
                with zipfile.ZipFile(archive) as z:
                    name = next(n for n in z.namelist() if n.endswith('uv.exe'))
                    exe.write_bytes(z.read(name))
            else:
                with tarfile.open(archive) as t:
                    member = next(m for m in t.getmembers() if m.name.rsplit('/', 1)[-1] == 'uv')
                    exe.write_bytes(t.extractfile(member).read())
        exe.chmod(0o755)
        return exe
    except Exception as e:                      # no internet, proxy, ...
        print(f'    download failed: {e}')
        return None


# ------------------------------------------------------------------ 3. virtual environment
def venv_version():
    return output([venv_python(), '-c', 'import sys; print("%d.%d" % sys.version_info[:2])'])


def make_venv(uv, fresh):
    step(3, 'virtual environment .venv')
    if fresh and VENV.exists():
        print('    --fresh: deleting the old .venv')
        shutil.rmtree(VENV)
    if venv_python().exists():
        v = venv_version()
        if v and tuple(int(x) for x in v.split('.')) in SUPPORTED and output([venv_python(), '-m', 'pip', '--version']):
            print(f'    ok (Python {v})')
            return
        print(f'    the existing .venv is not usable (Python {v or "?"}) -> creating it again')
        shutil.rmtree(VENV)
    if uv:
        env = dict(os.environ, UV_PYTHON_INSTALL_DIR=str(UV_DIR / 'python'), UV_CACHE_DIR=str(UV_DIR / 'cache'),
                   UV_PYTHON_PREFERENCE='only-managed')
        run([uv, 'venv', '--seed', '--python', PYTHON_VERSION, VENV], env=env)
    elif sys.version_info[:2] in SUPPORTED:
        print(f'    without uv: using this Python ({sys.version.split()[0]})')
        run([sys.executable, '-m', 'venv', VENV])
    else:
        raise SystemExit(f'Could not get Python {PYTHON_VERSION} (no uv) and this Python ({sys.version.split()[0]}) '
                         'is not supported.\nInstall Python 3.13 from https://www.python.org/downloads/ and start '
                         'the level file with it, e.g.:  py -3.13 level1_beginner.py  (Windows)')


# ------------------------------------------------------------------ 4. packages
def install_packages(have_submodule, sim):
    step(4, 'Python packages' + (' (incl. the simulation: MRzero + PyTorch CPU, ~200 MB download)' if sim else ''))
    py = venv_python()
    run([py, '-m', 'pip', 'install', '--quiet', '--upgrade', 'pip'], quiet=True)
    req = (TOOLS / 'requirements.txt').read_text()
    if not have_submodule:
        req = req.replace(PYPULSEQ_SUBMODULE, PYPULSEQ_PYPI)
    with tempfile.NamedTemporaryFile('w', prefix='requirements-', suffix='.tmp', delete=False, dir=TOOLS) as f:
        f.write(req)
    try:
        run([py, '-m', 'pip', 'install', '--quiet', '-r', f.name], quiet=True, cwd=TOOLS)
    finally:
        os.unlink(f.name)
    if sim:
        run([py, '-m', 'pip', 'install', '--quiet', '-r', 'requirements-sim.txt'], quiet=True, cwd=TOOLS)


# ------------------------------------------------------------------ 5. plot windows
def plot_windows():
    step(5, 'interactive plot windows')
    py = venv_python()
    get = [py, '-c', 'import matplotlib; print(matplotlib.get_backend())']
    backend = output(get).lower()
    headless = sys.platform.startswith('linux') and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    if backend in NON_INTERACTIVE and not headless:
        print('    no GUI toolkit found -> installing PyQt6')
        run([py, '-m', 'pip', 'install', '--quiet', 'PyQt6'], quiet=True)
        backend = output(get).lower()
    if backend in NON_INTERACTIVE:
        print('    no display (e.g. SSH / container): the plots are saved as PNG files to tools/export/')
    else:
        print(f'    ok ({backend})')


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if '-h' in args or '--help' in args:
        print(__doc__)
        return 0
    sim = '--no-sim' not in args
    print(f'Setting up the workshop in {ROOT}')
    try:
        have_submodule = submodules()
        uv = get_uv()
        make_venv(uv, fresh='--fresh' in args)
        install_packages(have_submodule, sim)
        plot_windows()
        step(6, 'installation check')
        ok = subprocess.run([str(venv_python()), str(TOOLS / 'check_setup.py')]).returncode == 0
    except (subprocess.CalledProcessError, OSError) as e:
        print(f'\nThe installation failed: {e}')
        print('Check your internet connection and run it again:   python tools/install.py')
        print('Still failing? See "Troubleshooting" in the README, or ask a tutor.')
        return 1
    if not ok:
        return 1
    MARKER.write_text(f'{fingerprint()} sim={sim}\n')
    print('\nSetup complete.' if argv is not None else '\nDone. Start with:   python level1_beginner.py', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
