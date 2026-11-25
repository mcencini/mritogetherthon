"""Reconstruction routines used by the MRI Together Day 2 notebook."""
from pathlib import Path
import hashlib

import numpy as np
from scipy.optimize import minimize, minimize_scalar


def load_arrays(path):
    with np.load(path, allow_pickle=False) as file:
        return {name: file[name] for name in file.files}


def fft2c(image):
    axes = (0, 1)
    return np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image, axes=axes),
                                      axes=axes, norm='ortho'), axes=axes)


def ifft2c(kspace):
    axes = (0, 1)
    return np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace, axes=axes),
                                        axes=axes, norm='ortho'), axes=axes)


def gradient_integral(times, gradient, query):
    """Exact integral of a piecewise-linear waveform from its first knot."""
    dt = np.diff(times)
    if np.any(dt < 0) or query.min() < times[0] or query.max() > times[-1]:
        raise ValueError('The gradient waveform must cover all ADC sample times.')
    areas = np.r_[0., np.cumsum(dt * (gradient[:-1] + gradient[1:]) / 2)]
    slopes = np.divide(np.diff(gradient), dt, out=np.zeros_like(dt), where=dt > 0)
    i = np.searchsorted(times, query, side='right').clip(1, len(times) - 1) - 1
    u = query - times[i]
    return areas[i] + u * (gradient[i] + u * slopes[i] / 2)


def adc_trajectory(data, delay_us=0):
    """kx in cycles/m, in echo and ADC order. The per-echo anchor is nominal."""
    t = data['adc_time_s']
    times, gx = data['gx_time_s'], data['gx_tm']
    anchor_area = gradient_integral(times, gx, t[:, :1])
    sample_area = gradient_integral(times, gx, t - delay_us * 1e-6)
    return data['kx_first_cpm'][:, None] + data['gamma_hz_t'] * (sample_area - anchor_area)


def cartesian_kx(data):
    nx = int(data['matrix_xy'][0])
    return (np.arange(nx) - nx//2) / data['fov_m'][0]


def correct_native(raw, polarity, phase_rad):
    """Remove the fitted even–odd phase error from complex native samples."""
    return raw * np.exp(-.5j * polarity[:, None] * phase_rad)


def regrid(raw, kx, grid, ky_idx, ny):
    """Interpolate complex EPI echoes and put them on their physical ky rows."""
    result = np.zeros((len(grid), ny), dtype=complex)
    for echo, row in enumerate(ky_idx):
        coords, values = kx[echo], raw[echo]
        if coords[-1] < coords[0]:
            coords, values = coords[::-1], values[::-1]
        if np.any(np.diff(coords) <= 0):
            raise ValueError('Expected monotonic readout coordinates.')
        result[:, row] = np.interp(grid, coords, values, left=0, right=0)
    return result


def fit_b0(raw_b0, data):
    """Minimize zero-filled b=0 image entropy over delay and even–odd phase error."""
    grid = cartesian_kx(data)
    ny = int(data['matrix_xy'][1])
    # Use the same physical kx support for every trial.
    keep = np.ones(len(grid), dtype=bool)
    for delay in (-3.5, 0., 3.5):
        k = adc_trajectory(data, delay)
        keep &= (grid >= k.min(axis=1).max()) & (grid <= k.max(axis=1).min())
    if not keep.any():
        raise ValueError('The readouts have no common Cartesian support.')

    def entropy(params):
        delay, phase = params
        corrected = correct_native(raw_b0, data['pol'], phase)
        k = regrid(corrected, adc_trajectory(data, delay), grid, data['ky_idx'], ny)
        k[~keep] = 0
        power = np.abs(ifft2c(k))**2
        p = power[power > 0] / power.sum()
        return -np.sum(p*np.log(p))

    delays = np.linspace(-3.5, 3.5, 13)
    phases = np.linspace(-1.5, 1.5, 9)
    _, d, f = min((entropy((d, f)), d, f) for d in delays for f in phases)
    bounds = [(max(delays[0], d - np.diff(delays)[0]), min(delays[-1], d + np.diff(delays)[0])),
              (max(phases[0], f - np.diff(phases)[0]), min(phases[-1], f + np.diff(phases)[0]))]
    solution = minimize(entropy, (d, f), method='Powell', bounds=bounds,
                        options={'xtol': 1e-4, 'ftol': 1e-9})
    if not solution.success:
        raise RuntimeError(solution.message)
    return tuple(solution.x)


def pf_phase(kspace, acquired):
    """Central measured PE band used for the volume's phase estimate."""
    ny = kspace.shape[1]
    width = int(np.count_nonzero(acquired)) - ny//2
    if width <= 0:
        raise ValueError('Phase estimation needs central data on both sides of DC.')
    start = (ny-width)//2
    center = np.zeros(ny, bool)
    center[start:start+width] = True
    if not np.all(acquired[center]):
        raise ValueError('The prescribed central phase band contains missing lines.')
    low = np.zeros_like(kspace)
    low[:, center] = kspace[:, center]
    return np.exp(1j * np.angle(ifft2c(low)))


def pocs(kspace, acquired, iterations=24):
    q = pf_phase(kspace, acquired)
    image = ifft2c(kspace)
    for _ in range(iterations):
        phase_projected = q * (q.conj() * image).real
        updated = fft2c(phase_projected)
        updated[:, acquired] = kspace[:, acquired]
        image = ifft2c(updated)
    return image


def load_epi_dat(path):
    """Read the distributed Siemens example using its MDH-derived byte index."""
    path = Path(path)
    scan = load_arrays(path.with_name('epi_dat_index.npz'))
    binary = path.read_bytes()
    if hashlib.sha256(binary).hexdigest() != str(scan['sha256'].item()):
        raise ValueError('The companion MDH byte index belongs to the supplied epi.dat.')
    offsets = scan['byte_offsets']
    n = int(scan['n_adc'])
    scan['echoes'] = np.stack([np.frombuffer(binary, dtype='<c8', count=n, offset=int(offset))
                               for offset in offsets.flat]).reshape(*offsets.shape, n)
    return scan


def siemens_geometry(scan):
    """Signed ADC coordinates and header receiver-offset adjustment."""
    echoes = scan['echoes']
    n = echoes.shape[-1]
    up, flat, down, begin, duration = scan['timing_us']
    dwell = duration/n
    t = begin + (np.arange(n) + .5)*dwell
    knots = np.array([0., up, up+flat, up+flat+down])
    amplitudes = np.array([0., 1., 1., 0.])
    base, fov = int(scan['base_matrix']), float(scan['fov_mm'])/1000
    scale = (base/fov) / (dwell * np.interp(t, knots, amplitudes).sum())
    area = lambda t: gradient_integral(knots, amplitudes, t) * scale
    midpoint = area(t)[n//2-1:n//2+1].mean()
    k_nom = area(t) - midpoint
    p = np.where(scan['reflected'], -1, 1)
    grid = np.linspace(k_nom[0], k_nom[-1], n)
    flat_step = np.diff(k_nom)[n//2]
    off = scan['offset_mm'][:, None, None] / 1000
    echoes = echoes * np.exp(2j*np.pi * off * (flat_step*np.arange(n)-k_nom))
    def coordinates(delay_us):
        return p[:, None] * (area(t-delay_us)-midpoint)
    return echoes, p, grid, coordinates


def siemens_profiles(echoes, p, grid, kx, phase_rad):
    """Correct the native even–odd phase error, then interpolate each coil."""
    raw = echoes * np.exp(-.5j*phase_rad*p[:, None, None])
    output = np.empty((len(echoes), raw.shape[1], len(grid)), complex)
    for i in range(len(echoes)):
        coords, samples = kx[i], raw[i]
        if p[i] < 0:
            coords, samples = coords[::-1], samples[:, ::-1]
        for c, channel in enumerate(samples):
            output[i, c] = np.interp(grid, coords, channel, left=0, right=0)
    return output


def fit_navigators(scan):
    """Use the three unencoded echoes to estimate delay and even–odd phase error."""
    echoes, p, grid, coords = siemens_geometry(scan)
    if not np.array_equal(p[:3], [-1, 1, -1]):
        raise ValueError('Expected reverse/forward/reverse navigator order.')
    # Common interior band for trial shifts keeps the compared signal support fixed.
    def measure(delay):
        nav = siemens_profiles(echoes[:3], p[:3], grid[2:-2], coords(delay)[:3], 0)
        reverse = (nav[0] + nav[2])/2
        forward = nav[1]
        cross = np.vdot(reverse, forward)
        coherence = abs(cross) / (np.linalg.norm(reverse)*np.linalg.norm(forward))
        return 1 - coherence, np.angle(cross)
    opt = minimize_scalar(lambda d: measure(d)[0], bounds=(-5, 5), method='bounded')
    return opt.x, measure(opt.x)[1]


def siemens_image(scan, delay_us, phase_rad):
    from bart_io import bart
    echoes, p, grid, coords = siemens_geometry(scan)
    lines = siemens_profiles(echoes[3:], p[3:], grid, coords(delay_us)[3:], phase_rad)
    lines[:, :, [0, -1]] = 0  # identical supported band for both displayed images
    kspace = np.transpose(lines, (2, 0, 1))
    coils = bart(['fft', '-iu', '3'], kspace)
    rss = np.sqrt(np.sum(np.abs(coils)**2, axis=2))
    n = int(scan['base_matrix'])
    start = (len(rss)-n)//2
    return rss[start:start+n]
