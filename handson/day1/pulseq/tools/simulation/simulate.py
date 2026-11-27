"""Simulate a .seq file with MRzero and reconstruct the image.

The easy way: set SIMULATE = True (and GRADIENT_DELAY) at the bottom of a level file.

By hand (from the repository folder):
    python tools/simulation/simulate.py                                     the reference solution
    python tools/simulation/simulate.py tools/export/my_dwepi_M4.seq        any .seq file
    python tools/simulation/simulate.py tools/export/my_dwepi_M4.seq 3e-6   + a 3 us gradient delay
    python tools/simulation/simulate.py tools/export/my_dwepi_M4.seq 0 5    off-resonance x 5 (EPI distortions)

result: plot window (or tools/export/EPI_recon_fig1.png without a display)

Only ONE k-space is simulated: the slice at the isocenter (z = 0), first repetition.
The other slices / repetitions are cut out of the sequence before the simulation, because every
k-space costs simulation time and memory, and the phantom is 2D anyway (it only exists at z = 0).

Needs the simulation packages (installed by tools/install.py, unless --no-sim was used).
MRzero: https://github.com/MRsources/MRzero-Core  (phantom: numerical_brain_cropped.mat from there)
"""

import contextlib
import os
import sys
import time
import warnings
from pathlib import Path
from urllib.request import urlretrieve

if __name__ == '__main__':      # started directly: run it in the workshop environment (.venv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import tools.workshop_env  # noqa: F401

import numpy as np
import pypulseq as pp

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))      # repository folder, for tools/

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
EXPORT = TOOLS / 'export'
PHANTOM_URL = 'https://github.com/MRsources/MRzero-Core/raw/main/documentation/playground_mr0/numerical_brain_cropped.mat'
PHANTOM_FILE = HERE / 'data' / 'numerical_brain_cropped.mat'
CHUNK_VOXELS = 2000              # voxels simulated at once: the memory stays at ~1 GB for any phantom size
D_CSF, D_TISSUE = 3.0, 0.8       # diffusion coefficients [10^-3 mm^2/s]; CSF = voxels with T1 > 3 s


def isocenter_kspace(seq_file, out_file):
    """Write a copy of the sequence that contains only the isocenter slice of the first repetition."""
    seq = pp.Sequence()
    seq.read(str(seq_file))
    blocks = list(seq.block_events)
    exc = [i for i in blocks if seq.get_block(i).rf is not None and seq.get_block(i).rf.use == 'excitation']
    if not exc:
        sys.exit(f'{seq_file}: no excitation pulse found (use="excitation" in make_..._pulse)')
    # the slices of the first repetition: one excitation per slice
    n_slices = int(seq.get_definition('NSlices')) if 'NSlices' in seq.definitions else 1
    first_rep = exc[:max(1, n_slices)]
    iso = min(first_rep, key=lambda i: abs(seq.get_block(i).rf.freq_offset))
    start = blocks.index(iso)
    nxt = [i for i in exc if i > iso]
    stop = blocks.index(nxt[0]) if nxt else len(blocks)

    new = pp.Sequence(system=seq.system)
    for i in blocks[start:stop]:
        b = seq.get_block(i)
        events = [e for e in (b.rf, b.gx, b.gy, b.gz, b.adc) if e is not None]
        labels = getattr(b, 'label', None)
        if isinstance(labels, dict):
            events += list(labels.values())
        elif labels:
            events += list(labels)
        new.add_block(*events, pp.make_delay(b.block_duration))
    for key, value in seq.definitions.items():
        if key not in ('GradientRasterTime', 'RadiofrequencyRasterTime', 'AdcRasterTime', 'BlockDurationRaster'):
            new.set_definition(key, value)
    new.set_definition('NSlices', 1)
    new.write(str(out_file))

    n_exc_total = len(exc)
    print(f'NOTE: only ONE k-space is simulated: the isocenter slice (f = {seq.get_block(iso).rf.freq_offset:.0f} Hz) '
          f'of the first repetition, {stop - start} of {len(blocks)} blocks.')
    if n_exc_total > 1:
        print(f'      The other {n_exc_total - 1} excitation(s) (slices / repetitions) are skipped: each one would '
              'cost the same simulation time again, and the 2D phantom only exists at z = 0.')


@contextlib.contextmanager
def quiet():
    """Hide the internal debug output of MRzero (also the one printed by its Rust code)."""
    sys.stdout.flush()
    saved = os.dup(1)
    with open(os.devnull, 'w') as devnull:
        os.dup2(devnull.fileno(), 1)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                yield
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)


def load_phantom(b0_scale=1.0):
    import MRzeroCore as mr0
    if not PHANTOM_FILE.exists():
        PHANTOM_FILE.parent.mkdir(exist_ok=True)
        print(f'downloading the phantom -> {PHANTOM_FILE.relative_to(TOOLS.parent)}')
        urlretrieve(PHANTOM_URL, PHANTOM_FILE)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        ph = mr0.VoxelGridPhantom.load_mat(str(PHANTOM_FILE))      # full resolution (141 x 161 voxels)
    # the original phantom has the same D everywhere: give CSF a higher one -> visible diffusion contrast
    ph.D[:] = D_TISSUE
    ph.D[ph.T1 > 3.0] = D_CSF
    # off-resonance: the phantom has a B0 map (about -46 ... +43 Hz); b0_scale = 0 switches it off,
    # larger values exaggerate it -> stronger EPI distortions in phase-encoding direction
    ph.B0 = ph.B0 * b0_scale
    return ph


def simulate(seq_file, raw_file, b0_scale=1.0):
    """MRzero simulation of the whole phantom, in parts of CHUNK_VOXELS voxels.

    The MR signal is the sum of the signals of all voxels, so the phantom can be simulated in parts and the
    signals added up: same result, but much less memory (all voxels at once would need ~4 GB).
    """
    import copy

    import MRzeroCore as mr0
    import torch
    ph = load_phantom(b0_scale)
    t = time.time()
    voxels = torch.nonzero(ph.PD.flatten() > 0).flatten()
    n_parts = -(-len(voxels) // CHUNK_VOXELS)
    b0 = ph.B0[ph.PD > 0]
    print(f'phantom: {tuple(ph.PD.shape[:2])} voxels, {len(voxels)} with signal, simulated in {n_parts} parts, '
          f'off-resonance {float(b0.min()):.0f} ... {float(b0.max()):.0f} Hz (B0_SCALE = {b0_scale:g})')
    with quiet():
        seq = mr0.Sequence.import_file(str(seq_file))
        graph = mr0.compute_graph(seq, ph.build(), 200, 1e-3)
        signal = 0
        for k in range(0, len(voxels), CHUNK_VOXELS):
            part = copy.deepcopy(ph)
            keep = torch.zeros(ph.PD.numel(), dtype=torch.bool)
            keep[voxels[k:k + CHUNK_VOXELS]] = True
            part.PD = ph.PD * keep.reshape(ph.PD.shape)
            signal = signal + mr0.execute_graph(graph, seq, part.build(), print_progress=False)
    print(f'simulation: {time.time() - t:.1f} s')
    s = signal.detach().cpu().numpy().astype(np.complex64).reshape(-1)
    s.tofile(raw_file)                                      # same format as recon_epi_rs.py expects
    Path(str(raw_file) + '.shape').write_text(f'{s.size} 1 1\n')


def run(seq_file=None, delay=0.0, b0_scale=1.0):
    """Simulate the isocenter k-space of seq_file (None: the reference solution) and reconstruct it.

    delay: gradient hardware delay in SECONDS, e.g. 3e-6 = 3 us (0: none)
    b0_scale: scales the off-resonance (B0 map) of the phantom: 0 = none, 1 = as measured, 5 = strong
    """
    if abs(delay) > 100e-6:
        print(f'>>> GRADIENT_DELAY = {delay:g} s is far too large: it is given in SECONDS.\n'
              f'    Realistic gradient delays are a few microseconds, e.g. GRADIENT_DELAY = 3e-6 (= 3 us).')
        return 1
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)    # print immediately (also when piped)
    EXPORT.mkdir(exist_ok=True)
    try:
        import MRzeroCore  # noqa: F401
    except ImportError:
        print('The simulation packages are not installed:   python tools/install.py')
        return 1

    # 1) the sequence: your file or the reference solution
    if seq_file:
        seq_file = Path(seq_file).resolve()
        print(f'=== 1/3 {seq_file}')
    else:
        seq_file = EXPORT / 'solution.seq'
        print(f'=== 1/3 export the reference solution -> {seq_file}')
        sys.path.insert(0, str(TOOLS / 'solution'))
        import matplotlib
        matplotlib.use('Agg')
        import tut_dw_se_epi_rs
        tut_dw_se_epi_rs.main(plot=False, test_report=False, seq_filename=str(seq_file))
    iso_file = EXPORT / f'{seq_file.stem}_iso.seq'
    isocenter_kspace(seq_file, iso_file)

    # optional: hardware delay -> simulate a shifted copy, reconstruct with the original
    sim_file, raw_file = iso_file, iso_file.with_suffix('.raw')
    if delay:
        sim_file = EXPORT / f'{seq_file.stem}_iso_hwdelay.seq'
        raw_file = sim_file.with_suffix('.raw')
        print(f'    simulate a gradient delay of {delay * 1e6:g} us (the recon still uses the original timing)')
        from tools.simulation.make_hw_delay_seq import shift_adcs
        try:
            shift_adcs(iso_file, sim_file, delay)
        except ValueError as e:
            print(f'\n>>> {e}')
            return 1

    # 2) simulation
    print('=== 2/3 MRzero simulation')
    simulate(sim_file, raw_file, b0_scale)

    # 3) reconstruction (plot window / notebook, or PNG in tools/export without a display)
    print('=== 3/3 reconstruction')
    from tools.simulation.recon_epi_rs import show_recon
    show_recon(str(iso_file), str(raw_file))
    return 0


if __name__ == '__main__':
    args = sys.argv[1:]
    sys.exit(run(args[0] if args else None, float(args[1]) if len(args) > 1 else 0.0,
                 float(args[2]) if len(args) > 2 else 1.0))
