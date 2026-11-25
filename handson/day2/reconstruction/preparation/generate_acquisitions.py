"""Prepare the portable acquisitions used in the MRI Together reconstruction notebook.

Run `python preparation/generate_acquisitions.py` with NumPy, SciPy and scikit-image.
It uses the geometry of the bundled KomaMRI point acquisition and regenerates the
two Shepp–Logan EPI volumes and Cartesian multishot measurements. To regenerate
the point acquisition too, run `export_koma.jl` and pass `--point-exports DIR`.
Use `--twix path/to/epi.dat` with twixtools installed to regenerate the byte index.
For your own pair, use `--koma-pair B0_FOLDER DWI_FOLDER --pair-output my_epi.npz`.
The lesson reads the resulting files and can run independently of this script.
"""

import argparse
from hashlib import sha256
from pathlib import Path
import shutil

import numpy as np
from scipy.interpolate import make_interp_spline
from scipy.ndimage import binary_dilation, binary_erosion


GEOMETRY_FIELDS = ('matrix_xy', 'fov_m', 'ky_idx', 'pol', 'kx_first_cpm',
                   'adc_time_s', 'gx_time_s', 'gx_tm', 'gamma_hz_t')
PUBLIC_EPI_SHA = '5311aa6eb58e76ffea5ca5c314299f85a838c7ac35ad5b273cd48863356f3954'


def physical_kx(geometry, delay_s=0.0):
    """Evaluate each signed readout from the exported gradient and ADC sample centers."""
    gt, unique_knots = np.unique(geometry['gx_time_s'], return_index=True)
    grad = geometry['gx_tm'][unique_knots]
    t = geometry['adc_time_s']
    if (t - delay_s).min() < gt[0] or (t - delay_s).max() > gt[-1]:
        raise ValueError('Requested ADC time outside the Gx waveform')
    area = make_interp_spline(gt, grad, k=1).antiderivative()
    return (geometry['kx_first_cpm'][:, None] + geometry['gamma_hz_t'] *
            (area(t - delay_s) - area(t[:, :1])))


def read_koma_export(folder):
    """Read the three numeric files written by export_koma_epi in export_koma.jl."""
    nx, ny, fx, fy, gamma, b = np.loadtxt(folder / 'geometry.tsv')
    adc = np.loadtxt(folder / 'adc.tsv', ndmin=2)
    ids, counts = np.unique(adc[:, 0], return_counts=True)
    if not (len(ids) >= 2 and counts.min() >= 2 and np.ptp(counts) == 0 and
            np.array_equal(adc[:, 0], np.repeat(ids, counts))):
        raise ValueError('Select equal-length single-shot imaging profiles in acquisition order')
    _, times, kx, ky, kz, real, imag = adc.reshape(len(ids), counts[0], 7).transpose(2, 0, 1)
    lines = np.rint(np.median(ky, axis=1) * fy).astype(int) + int(ny) // 2
    if (np.any(np.diff(times.ravel()) <= 0) or not np.isfinite(times).all() or
            np.ptp(kz) * max(fx, fy) > 0.04 or np.any(np.diff(np.sort(lines)) != 1) or
            min(lines) < 0 or max(lines) >= int(ny) or
            np.max(abs(ky * fy - (lines[:, None] - int(ny) // 2))) > 0.04):
        raise ValueError('Expected one Cartesian, in-plane, single-shot readout train')
    polarity = np.sign(kx[:, -1] - kx[:, 0]).astype(np.int8)
    if np.any(polarity[:, None] * np.diff(kx, axis=1) <= 0) or np.any(polarity[1:] == polarity[:-1]):
        raise ValueError('Expected alternating monotonic readout polarity')
    tg, gx = np.loadtxt(folder / 'gx.tsv').T
    geometry = dict(matrix_xy=np.asarray([nx, ny], dtype=int), fov_m=np.array([fx, fy]),
                    ky_idx=lines, pol=polarity, kx_first_cpm=kx[:, 0],
                    adc_time_s=times, gx_time_s=tg, gx_tm=gx, gamma_hz_t=gamma)
    np.testing.assert_allclose(physical_kx(geometry), kx, atol=0.04 / fx, rtol=0,
                               err_msg='Gx, ADC timing and physical k-space disagree')
    return geometry, real + 1j * imag, b


def pack_koma_pair(b0_folder, dwi_folder, path, point_check=False):
    """Use a shared readout geometry for matched single-shot b0/DWI acquisitions."""
    b0g, b0, b0_value = read_koma_export(b0_folder)
    dwg, dw, dw_value = read_koma_export(dwi_folder)
    for key in ('matrix_xy', 'fov_m', 'ky_idx', 'pol'):
        np.testing.assert_allclose(b0g[key], dwg[key])
    for delay in (-3.5e-6, 0, 3.5e-6):
        np.testing.assert_allclose(physical_kx(b0g, delay), physical_kx(dwg, delay), atol=1e-4)
    np.testing.assert_allclose(np.diff(b0g['adc_time_s'], axis=1), np.diff(dwg['adc_time_s'], axis=1),
                               rtol=1e-4, atol=1e-9, err_msg='ADC dwell times differ')
    if b0_value != 0 or dw_value <= 0:
        raise ValueError('Expected a baseline volume followed by a positive b-value')
    extra = {}
    if point_check:
        if dw_value != 1000:
            raise ValueError('The bundled point demo uses b = 1000')
        extra = dict(expected_xy=[41, 27], expected_ratio=np.exp(-0.8))
    np.savez_compressed(path, **b0g, raw=np.stack([b0, dw]), b_values=[b0_value, dw_value], **extra)


def fft_centered(img, axes):
    return np.fft.fftshift(np.fft.fftn(np.fft.ifftshift(img, axes=axes), axes=axes,
                                        norm='ortho'), axes=axes)


def phantom_objects(matrix, b_values):
    from skimage.data import shepp_logan_phantom
    from skimage.transform import resize

    nx, ny = matrix
    if (nx, ny) != (64, 64):
        raise ValueError('The teaching phantom is defined on the 64 × 64 ramp-EPI geometry')
    x, y = np.meshgrid((np.arange(nx) - nx // 2) / nx,
                       (np.arange(ny) - ny // 2) / ny, indexing='ij')
    baseline = np.zeros((nx, ny))
    baseline[3:59, 9:55] = resize(np.flipud(shepp_logan_phantom()), (46, 56),
                                  anti_aliasing=True).T
    inside = baseline > 0.015
    diffusivity = np.select([baseline > .55, baseline > .23], [.00045, .00150], .00085) * inside
    phase0 = .45 * np.sin(2 * np.pi * x) + .55 * y
    phase_dw = phase0 + 1.8 * np.sin(2 * np.pi * y + .4) + 2.6 * y + .7 * x
    reference = np.stack([baseline * np.exp(-b * diffusivity + 1j * phase)
                          for b, phase in zip(b_values, (phase0, phase_dw))])
    return reference, diffusivity, inside


def bipolar_samples(obj, kx, geometry):
    """Direct spatial encoding for signed nonuniform kx. ky is Cartesian."""
    nx = obj.shape[0]
    x_m = (np.arange(nx) - nx // 2) * geometry['fov_m'][0] / nx
    ky_spectrum = fft_centered(obj, axes=(1,))
    raw = np.empty(kx.shape, dtype=complex)
    for line, j in enumerate(geometry['ky_idx']):
        encoding = np.exp(-2j * np.pi * kx[line, :, None] * x_m)
        raw[line] = np.sum(encoding * ky_spectrum[:, j], axis=1) / np.sqrt(nx)
    return raw


def multishot_data(reference):
    nx, ny = reference.shape[1:]
    x, y = np.meshgrid((np.arange(nx) - nx // 2) / nx,
                       (np.arange(ny) - ny // 2) / ny, indexing='ij')
    sens = []
    for theta in np.arange(8) * (2 * np.pi / 8):
        dx, dy = x - .58 * np.cos(theta), y - .58 * np.sin(theta)
        magnitude = np.exp(-(dx**2 + dy**2) / (2 * .37**2))
        phase = 1.8 * (x * np.sin(theta) - y * np.cos(theta))
        sens.append(magnitude * np.exp(1j * phase))
    sens = np.stack(sens, axis=-1)
    sens /= np.sqrt(np.sum(np.abs(sens)**2, axis=-1, keepdims=True))
    sens = sens[:, :, None, :]  # [x, y, slice, coil], as consumed by BART
    b0_calib = fft_centered(reference[0, :, :, None, None] * sens, axes=(0, 1))
    phase_pattern = .8 + 3 * x - 1.4 * y + .7 * np.cos(2 * np.pi * y)
    shots = []
    for shot in range(2):
        shot_object = reference[1] * np.exp(1j * (-1)**shot * phase_pattern)
        k = fft_centered(shot_object[:, :, None, None] * sens, axes=(0, 1))
        k[:, np.arange(ny) % 2 != shot] = 0
        shots.append(k)
    return b0_calib.astype(np.complex64), np.asarray(shots, dtype=np.complex64)


def generate_workshop(point_path, output_path):
    with np.load(point_path, allow_pickle=False) as point:
        geometry = {key: point[key] for key in GEOMETRY_FIELDS}
    b_values = np.array([0., 800.])
    reference, diffusivity, inside = phantom_objects(geometry['matrix_xy'], b_values)
    ideal_b0 = bipolar_samples(reference[0], physical_kx(geometry), geometry)
    phase_rad, delay_us = .72, 2.7
    kx = physical_kx(geometry, delay_us * 1e-6)
    rng = np.random.default_rng(1961)
    raw = []
    for obj in reference:
        measured = bipolar_samples(obj, kx, geometry)
        measured *= np.exp(.5j * geometry['pol'][:, None] * phase_rad)
        noise = rng.normal(size=kx.shape) + 1j * rng.normal(size=kx.shape)
        raw.append(measured + .0015 * noise)
    signal_mask = binary_erosion(inside, iterations=1)
    ghost_mask = np.roll(signal_mask, inside.shape[1] // 2, axis=1) & ~binary_dilation(inside, iterations=2)
    b0_calib, shots = multishot_data(reference)
    np.savez_compressed(output_path, **geometry, b_values=b_values, raw=np.stack(raw),
                        reference=reference, ideal_b0=ideal_b0, diffusivity_mm2_s=diffusivity,
                        object_mask=inside, signal_mask=signal_mask, ghost_mask=ghost_mask,
                        ms_b0_calib=b0_calib, ms_shots=shots, injected_phase_rad=phase_rad,
                        injected_delay_us=delay_us)


def prepare_twix_index(path, data_dir):
    """Locate the original channel ADC bytes in the public twixtools epi.dat example."""
    import twixtools

    buf = path.read_bytes()
    if sha256(buf).hexdigest() != PUBLIC_EPI_SHA:
        raise ValueError('The byte index is specific to the public twixtools example_data/epi.dat')
    scan = twixtools.read_twix(str(path), parse_geometry=False)[-1]
    imgs = sorted((b for b in scan['mdb'] if b.is_image_scan()), key=lambda b: b.cLin)
    navs = [b for b in scan['mdb'] if b.is_flag_set('PHASCOR')]
    blocks = navs + imgs
    echoes = np.stack([block.data for block in blocks])
    offsets = np.empty(echoes.shape[:2], dtype=np.int64)
    for idx in np.ndindex(offsets.shape):
        train = np.asarray(echoes[idx], dtype='<c8').tobytes()
        start = buf.find(train)
        if start < 0 or buf.find(train, start + 1) >= 0:
            raise ValueError(f'ADC data for echo and coil {idx} did not match a unique byte offset')
        offsets[idx] = start
    def readout_offset(block):
        if hasattr(block.mdh, 'ReadOutOffcentre'):
            return block.mdh.ReadOutOffcentre
        return block.mdh['fReadOutOffcentre']
    meas = scan['hdr']['Meas']
    yaps = scan['hdr']['MeasYaps']
    timing_names = ('alRegridRampupTime', 'alRegridFlattopTime', 'alRegridRampdownTime',
                    'alRegridDelaySamplesTime', 'aflRegridADCDuration')
    np.savez_compressed(data_dir / 'epi_dat_index.npz', byte_offsets=offsets,
                        reflected=[b.is_flag_set('REFLECT') for b in blocks],
                        offset_mm=np.asarray([readout_offset(b) for b in blocks], dtype=np.float32),
                        timing_us=np.asarray([meas[key][0] for key in timing_names], dtype=float),
                        fov_mm=yaps['sSliceArray']['asSlice'][0]['dReadoutFOV'],
                        base_matrix=yaps['sKSpace']['lBaseResolution'],
                        sha256=PUBLIC_EPI_SHA, n_adc=echoes.shape[-1])
    if path.resolve() != (data_dir / 'epi.dat').resolve():
        shutil.copyfile(path, data_dir / 'epi.dat')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    parser.add_argument('--point-exports', type=Path, help='Parent of julia_b0/ and julia_dw/ TSV folders')
    parser.add_argument('--twix', type=Path, help='Public twixtools example_data/epi.dat')
    parser.add_argument('--koma-pair', type=Path, nargs=2, metavar=('B0', 'DWI'),
                        help='Pack a pair of exported workshop acquisitions')
    parser.add_argument('--pair-output', type=Path, default=Path('koma_pair.npz'))
    args = parser.parse_args()
    if args.koma_pair:
        pack_koma_pair(*args.koma_pair, args.pair_output)
        return
    args.data_dir.mkdir(parents=True, exist_ok=True)
    point = args.data_dir / 'koma_point.npz'
    if args.point_exports:
        pack_koma_pair(args.point_exports / 'julia_b0', args.point_exports / 'julia_dw',
                       point, point_check=True)
    if not point.is_file():
        parser.error('Supply --point-exports or place the bundled koma_point.npz in --data-dir')
    generate_workshop(point, args.data_dir / 'epi_workshop.npz')
    if args.twix:
        prepare_twix_index(args.twix, args.data_dir)


if __name__ == '__main__':
    main()
