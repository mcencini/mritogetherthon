"""Basic recon for single-shot EPI with ramp sampling and navigator echoes, based on the .seq file.

Python port of external/pulseq/matlab/demoRecon/reconExample2DEPI.m:
k-space trajectory from pypulseq, per-line regridding onto a uniform kx grid, ky sorting
(partial Fourier lines are zero-filled), navigator-based odd/even phase correction, 2D FFT.

Labels used (pp.make_label in the sequence):
    SLC  slice index (spatial order)  -> one image per slice
    NAV  navigator lines at ky = 0 with alternating RO polarity
From the navigators the phase difference between the two RO polarities is estimated in hybrid
space (x, ky) as phi(x) = phi0 + phi1 * x and removed from all imaging lines of the "negative"
polarity (classic Nyquist-ghost correction).

Matrix size and FOV are taken from the [DEFINITIONS] (Nx, Ny, FOV) if present, else from the trajectory.

usage: python tools/simulation/recon_epi_rs.py <file.seq> [<file.raw>] [--delay <s>]
       --delay simulates a gradient/ADC timing error (s) in the trajectory used for the recon,
       to test the navigator correction on ghost-free simulated data
"""

import sys
from pathlib import Path

if __name__ == '__main__':      # started directly: run it in the workshop environment (.venv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import tools.workshop_env  # noqa: F401

import matplotlib.pyplot as plt
import numpy as np
import pypulseq as pp
from scipy.interpolate import CubicSpline

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))       # repository folder, for tools/
from tools.rf_profile import show_or_save  # noqa: E402


def load_raw(raw_path):
    shape = tuple(int(s) for s in Path(str(raw_path) + '.shape').read_text().split())
    data = np.fromfile(raw_path, dtype=np.complex64)
    # raw data: complex64 samples in acquisition order, <file.raw>.shape holds the array size
    return data.reshape(shape, order='F')


def get_def(seq, key, default=None):
    try:
        return seq.get_definition(key)
    except (KeyError, ValueError):
        return default


def recon_slice(data, kx, ky, is_nav, nx, ny, fov_x, fov_y, nav_corr=True):
    """Reconstruct one slice. data/kx/ky: (lines, samples) in acquisition order."""
    pol = np.sign(kx[:, -1] - kx[:, 0])      # RO polarity of each line
    img_lines = np.where(~is_nav)[0]
    nav_lines = np.where(is_nav)[0]
    delta_kx, delta_ky = 1 / fov_x, 1 / fov_y

    # uniform kx grid -N/2 ... N/2-1 (the sequence samples symmetrically, so -N/2 is just at the edge)
    kxx = np.arange(-nx // 2, nx // 2) * delta_kx

    # regrid every line (ramp sampling -> non-uniform kx)
    regridded = np.zeros((len(data), nx), dtype=complex)
    for i in range(len(data)):
        order = np.argsort(kx[i])
        x, d = kx[i][order], data[i][order]
        # allow a small extrapolation (half a k-space step) beyond the outermost samples
        inside = (kxx >= x[0] - delta_kx / 2) & (kxx <= x[-1] + delta_kx / 2)
        regridded[i, inside] = CubicSpline(x, d.real)(kxx[inside]) + 1j * CubicSpline(x, d.imag)(kxx[inside])

    # hybrid space (x, line)
    hybrid = np.fft.fftshift(np.fft.ifft(np.fft.ifftshift(regridded, axes=-1), axis=-1), axes=-1)

    # navigator phase correction: phi(x) between the two RO polarities
    phi0 = phi1 = 0.0
    if nav_corr and len(nav_lines) >= 2:
        nav_pos = hybrid[nav_lines[pol[nav_lines] > 0]].mean(axis=0)
        nav_neg = hybrid[nav_lines[pol[nav_lines] < 0]].mean(axis=0)
        cd = nav_neg * np.conj(nav_pos)
        # linear phase (slope per pixel) and constant phase, magnitude-weighted (robust, no unwrapping)
        phi1 = np.angle(np.sum(cd[1:] * np.conj(cd[:-1])))
        xi = np.arange(nx) - nx // 2
        phi0 = np.angle(np.sum(cd * np.exp(-1j * phi1 * xi)))
        hybrid[pol < 0] *= np.exp(-1j * (phi0 + phi1 * xi))

    # sort imaging lines by ky, zero-fill missing lines (partial Fourier)
    hyb_sorted = np.zeros((ny, nx), dtype=complex)
    for i in img_lines:
        row = int(round(ky[i, 0] / delta_ky)) + ny // 2
        hyb_sorted[row] = hybrid[i]

    img = np.fft.fftshift(np.fft.ifft(np.fft.ifftshift(hyb_sorted, axes=0), axis=0), axes=0)
    kspace = np.fft.fftshift(np.fft.fft(np.fft.ifftshift(hyb_sorted, axes=-1), axis=-1), axes=-1)
    return kspace, img, (phi0, phi1)


def recon_epi(seq_path, raw_path, traj_delay=0.0, nav_corr=True):
    """Returns a list with one dict per slice (spatial order): kspace, img, data, phi, slice index."""
    seq = pp.Sequence()
    seq.read(seq_path)
    ktraj_adc, ktraj, t_exc, t_ref, t_adc = seq.calculate_kspace(trajectory_delay=traj_delay)

    data = load_raw(raw_path).reshape(-1)    # all ADC samples in acquisition order (single coil)

    # samples per readout: first temporal gap between ADCs
    dt_adc = np.diff(t_adc)
    n_adc = int(np.argmax(dt_adc > dt_adc[0] * 1.5)) + 1
    n_lines = len(t_adc) // n_adc
    assert data.size == n_adc * n_lines, f'{data.size} samples, expected {n_adc} x {n_lines}'
    data = data.reshape(n_lines, n_adc)
    kx = ktraj_adc[0].reshape(n_lines, n_adc)
    ky = ktraj_adc[1].reshape(n_lines, n_adc)

    # labels (one value per ADC)
    labels = seq.evaluate_labels(evolution='adc')
    is_nav = np.asarray(labels['NAV'], dtype=bool) if 'NAV' in labels else np.zeros(n_lines, bool)
    slc = np.asarray(labels['SLC'], dtype=int) if 'SLC' in labels else np.zeros(n_lines, int)

    # geometry: definitions if present, else from the trajectory
    fov_def = get_def(seq, 'FOV')
    ky_img = ky[~is_nav, 0]
    delta_ky = abs(ky_img[-1] - ky_img[-2])
    fov_x = float(np.atleast_1d(fov_def)[0]) if fov_def is not None else 1 / delta_ky
    fov_y = float(np.atleast_1d(fov_def)[1]) if fov_def is not None else 1 / delta_ky
    ny = int(get_def(seq, 'Ny', 0)) or 2 * max(round(abs(ky_img[-1]) / delta_ky), round(abs(ky_img[0]) / delta_ky))
    nx = int(get_def(seq, 'Nx', 0)) or ny

    slices = sorted(set(slc.tolist()))
    print(f'{len(slices)} slice(s), {n_lines // len(slices)} lines per slice '
          f'({is_nav.sum() // len(slices)} navigators) x {n_adc} samples, '
          f'FOV {fov_x * 1e3:.0f} x {fov_y * 1e3:.0f} mm, matrix {nx} x {ny}')

    results = []
    for s in slices:
        sel = slc == s
        kspace, img, phi = recon_slice(data[sel], kx[sel], ky[sel], is_nav[sel], nx, ny, fov_x, fov_y, nav_corr)
        if nav_corr and is_nav[sel].sum() >= 2:
            print(f'  slice {s}: navigator correction phi0 = {phi[0]:.3f} rad, phi1 = {phi[1]:.4f} rad/pixel')
        elif nav_corr:
            print(f'  slice {s}: no navigators in this file -> no odd/even correction')
        results.append(dict(slice=s, kspace=kspace, img=img, data=data[sel], phi=phi, fov=(fov_x, fov_y)))
    return results


def show_recon(seq_path, raw_path, delay=0.0):
    """Reconstruct with and without navigator correction and plot raw data, k-space and images."""
    res = recon_epi(seq_path, raw_path, traj_delay=delay, nav_corr=True)
    res_nc = recon_epi(seq_path, raw_path, traj_delay=delay, nav_corr=False)

    # rows: slices; columns: raw data, k-space, image without / with navigator correction
    n = len(res)
    fig, axs = plt.subplots(n, 4, figsize=(20, 5 * n), squeeze=False)
    for r, (a, b) in enumerate(zip(res, res_nc)):
        fov_x, fov_y = a['fov']
        ext = [-fov_x / 2 * 1e3, fov_x / 2 * 1e3, fov_y / 2 * 1e3, -fov_y / 2 * 1e3]   # correct aspect ratio
        vmax = np.abs(a['img']).max() or 1
        axs[r, 0].imshow(np.abs(a['data']), aspect='auto', cmap='gray')
        axs[r, 0].set(title=f'slice {a["slice"]}: raw data (navigators on top)', xlabel='ADC sample', ylabel='line')
        axs[r, 1].imshow(np.log1p(np.abs(a['kspace']) / (np.abs(a['kspace']).max() or 1) * 1e3), cmap='gray', aspect='auto')
        axs[r, 1].set(title='regridded k-space (log)', xlabel='kx', ylabel='ky')
        axs[r, 2].imshow(np.abs(b['img']), cmap='gray', vmax=vmax, extent=ext)
        axs[r, 2].set(title='without navigator correction', xlabel='x [mm]', ylabel='y [mm]')
        axs[r, 3].imshow(np.abs(a['img']), cmap='gray', vmax=vmax, extent=ext)
        axs[r, 3].set(title='with navigator correction', xlabel='x [mm]', ylabel='y [mm]')
    if delay:
        fig.suptitle(f'simulated timing error {delay * 1e6:.1f} us')
    fig.tight_layout()
    show_or_save('EPI recon')


if __name__ == '__main__':
    args = sys.argv[1:]
    delay = 0.0
    if '--delay' in args:
        i = args.index('--delay')
        delay = float(args[i + 1])
        del args[i:i + 2]
    seq_path = args[0]
    raw_path = args[1] if len(args) > 1 else str(Path(seq_path).with_suffix('.raw'))

    show_recon(seq_path, raw_path, delay)
