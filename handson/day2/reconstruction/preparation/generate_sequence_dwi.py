"""Prepare the workshop's single-shot, single-channel DWI series.

Run from the project directory with NumPy, SciPy, scikit-image and
PyPulseq 1.5.0.post2: python preparation/generate_sequence_dwi.py

The Pulseq files supply the RF-aware trajectory, gradient waveform, ADC events,
nominal b-value, direction and echo time. A 2D complex Shepp–Logan phantom
supplies spin density, directional monoexponential attenuation, T2 weighting
and smooth image phase. The readout delay, even–odd phase error and noise are
controlled additions to the imaging echoes. This is a Fourier signal model.
"""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
import pypulseq as pp
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt, label
from skimage.data import shepp_logan_phantom
from skimage.transform import resize

from generate_acquisitions import bipolar_samples, multishot_data, physical_kx


ROOT = Path(__file__).resolve().parent.parent
DELAY_US = 2.7
PHASE_RAD = 0.72


def read_acquisition(path):
    seq = pp.Sequence()
    seq.read(str(path))
    definitions = seq.definitions
    matrix = np.array([definitions['Nx'], definitions['Ny']], dtype=int)
    fov = np.asarray(definitions['FOV'])[:2]
    labels = seq.evaluate_labels(evolution='adc')
    is_nav = labels['NAV'].astype(bool)
    counts = [block.adc.num_samples for index in seq.block_events
              if (block := seq.get_block(index)).adc is not None]
    assert len(counts) == len(is_nav) and len(set(counts)) == 1
    shape = (len(is_nav), counts[0])
    trajectory = seq.calculate_kspace(output_as_dict=True)
    times = trajectory['t_adc'].reshape(shape)
    # Pulseq k is in cycles/m; with a 180-degree pulse, the RF-aware trajectory
    # includes the reversal of the accumulated pre-refocusing gradient moment.
    kx, ky, kz = trajectory['k_traj_adc'].reshape(3, *shape)
    imaging = ~is_nav
    np.testing.assert_allclose(np.ptp(ky, axis=1), 0, atol=1e-6)
    np.testing.assert_allclose(np.ptp(kz[imaging]), 0, atol=1e-6)
    lines = np.rint(ky[imaging, 0] * fov[1]).astype(int) + matrix[1] // 2
    np.testing.assert_allclose(ky[imaging, 0] * fov[1], lines - matrix[1] // 2, atol=1e-3)
    pol = np.sign(kx[:, -1] - kx[:, 0]).astype(np.int8)
    assert np.all(np.diff(kx, axis=1) * pol[:, None] > 0)
    np.testing.assert_array_equal(np.flatnonzero(is_nav), np.arange(int(definitions['NavigatorLines'])))
    np.testing.assert_array_equal(lines, np.arange(int(definitions['NyMeasured']) - 1, -1, -1))
    np.testing.assert_array_equal(pol[is_nav], [1, -1, 1])
    np.testing.assert_array_equal(pol[imaging], (-1) ** np.arange(len(lines)))

    tg, gx_hz_m = seq.waveforms()[0]
    geometry = dict(matrix_xy=matrix, fov_m=fov, ky_idx=lines, pol=pol[imaging],
                    kx_first_cpm=kx[imaging, 0], adc_time_s=times[imaging],
                    gx_time_s=tg, gx_tm=gx_hz_m / seq.system.gamma, gamma_hz_t=seq.system.gamma)
    # Independently integrate the exported nominal Gx between ADC samples.
    np.testing.assert_allclose(physical_kx(geometry), kx[imaging], atol=2e-5, rtol=0)
    events = dict(event_is_nav=is_nav, event_polarity=pol, event_ky_cpm=ky[:, 0],
                  event_kx_cpm=kx, event_adc_times_s=times,
                  excitation_time_s=trajectory['t_excitation'][0],
                  refocusing_time_s=trajectory['t_refocusing'][0])
    b = float(definitions['BValue'])
    direction = 'baseline' if b == 0 else ('x', 'y')[np.argmax(definitions['DiffusionDirection'])]
    return geometry, events, (float(definitions['TE']) * 1000, b, direction)


def tissue_maps(matrix, fov_m):
    """Place the upright phantom in physical x,y coordinates at its native aspect ratio."""
    nx, ny = matrix
    source = shepp_logan_phantom()
    occupied = np.where(source > 0)
    source = source[occupied[0].min():occupied[0].max() + 1,
                    occupied[1].min():occupied[1].max() + 1]
    # Source rows run from superior to inferior; our Fourier arrays use [x,y]
    # with y increasing upwards. Convert orientations once, in the object.
    dx_m, dy_m = fov_m / matrix
    height = round(.90 * ny)
    width = round(height * (source.shape[1] / source.shape[0]) * dy_m / dx_m)
    start_x, start_y = (matrix - [width, height]) // 2
    density = np.zeros((nx, ny))
    upright_xy = resize(source, (height, width), anti_aliasing=True)[::-1].T
    density[start_x:start_x + width, start_y:start_y + height] = upright_xy
    inside = density > .015
    shell = density > .55
    inclusion = (density > .23) & ~shell
    dx = np.select([shell, inclusion], [.00045, .00150], .00075) * inside
    dy = np.select([shell, inclusion], [.00045, .00150], .00115) * inside
    t2_ms = np.select([shell, inclusion], [115., 95.], 80.)
    # Interior voxels from the uniform body provide a high-SNR directional ADC ROI.
    roi = binary_erosion((density > .18) & (density < .22), iterations=3)
    assert roi.sum() > 70
    np.testing.assert_allclose(dx[roi], .00075)
    np.testing.assert_allclose(dy[roi], .00115)
    x, y = np.meshgrid((np.arange(nx) - nx // 2) / nx,
                       (np.arange(ny) - ny // 2) / ny, indexing='ij')
    phase0 = .45 * np.sin(2 * np.pi * x) + .55 * y
    phase_dw = phase0 + 1.8 * np.sin(2 * np.pi * y + .4) + 2.6 * y + .7 * x
    return density, dx, dy, t2_ms, inside, roi, phase0, phase_dw


def build(archive_path, output):
    rng = np.random.default_rng(1961)
    raw_series, parameters, sources, digests = [], [], [], []
    references = []
    shared = events = maps = ideal_b0 = None
    with ZipFile(archive_path) as archive, TemporaryDirectory() as temp_dir:
        for name in sorted(n for n in archive.namelist() if '/dwi_' in n and n.endswith('.seq')):
            content = archive.read(name)
            seq_path = Path(temp_dir) / 'acquisition.seq'
            seq_path.write_bytes(content)
            geometry, echo_events, settings = read_acquisition(seq_path)
            te_ms, b, direction = settings
            if shared is None:
                assert b == 0
                shared, events = geometry, echo_events
                maps = tissue_maps(shared['matrix_xy'], shared['fov_m'])
            np.testing.assert_array_equal(geometry['ky_idx'], shared['ky_idx'])
            np.testing.assert_array_equal(geometry['pol'], shared['pol'])
            np.testing.assert_allclose(geometry['fov_m'], shared['fov_m'])
            np.testing.assert_array_equal(geometry['matrix_xy'], shared['matrix_xy'])
            np.testing.assert_allclose(echo_events['event_kx_cpm'], events['event_kx_cpm'], atol=.01)
            np.testing.assert_allclose(echo_events['event_ky_cpm'], events['event_ky_cpm'], atol=.01)
            actual_kx = physical_kx(geometry, DELAY_US * 1e-6)
            np.testing.assert_allclose(actual_kx, physical_kx(shared, DELAY_US * 1e-6), atol=.01)
            density, dx, dy, t2_ms, inside, roi, phase0, phase_dw = maps
            diffusivity = dy if direction == 'y' else dx
            image = density * np.exp(-te_ms / t2_ms - b * diffusivity + 1j * (phase_dw if b else phase0))
            if np.isclose(te_ms, 46.7) and (b == 0 or (b == 500 and direction == 'x')):
                references.append(image)
            if ideal_b0 is None:
                ideal_b0 = bipolar_samples(image, physical_kx(geometry), geometry)
            raw = bipolar_samples(image, actual_kx, geometry)
            raw *= np.exp(.5j * PHASE_RAD * geometry['pol'][:, None])
            noise = rng.normal(size=raw.shape) + 1j * rng.normal(size=raw.shape)
            raw_series.append((raw + .0003 * noise).astype(np.complex64))
            parameters.append(settings)
            sources.append(name)
            digests.append(sha256(content).hexdigest())

    assert len(raw_series) == 26 and len(references) == 2
    series_te, series_b, directions = map(np.asarray, zip(*parameters))
    pair = np.flatnonzero(np.isclose(series_te, 46.7) &
                          ((series_b == 0) | ((series_b == 500) & (directions == 'x'))))
    series_raw = np.stack(raw_series)
    reference = np.asarray(references)
    signal = binary_erosion(inside, iterations=1)
    ghost = np.roll(signal, inside.shape[1] // 2, axis=1) & ~binary_dilation(inside, iterations=2)
    # Central samples of the broadest high-diffusivity inclusion; remove three
    # edge pixels to limit partial-volume effects in both diffusion directions.
    isotropic_inclusions = (dx == .00150) & (dy == .00150)
    components, _ = label(isotropic_inclusions)
    distances = distance_transform_edt(isotropic_inclusions)
    central_pixel = np.unravel_index(distances.argmax(), distances.shape)
    iso_roi = (components == components[central_pixel]) & (distances > 3)
    assert np.count_nonzero(iso_roi) > 50
    ms_calib, ms_shots = multishot_data(reference)
    np.savez_compressed(output, **shared, **events,
                        raw=series_raw[pair], b_values=series_b[pair], reference=reference,
                        object_mask=inside, signal_mask=signal, ghost_mask=ghost, ideal_b0=ideal_b0,
                        series_te_ms=series_te, series_b=series_b, series_direction=directions,
                        series_raw=series_raw, series_source=sources, series_sha256=digests,
                        adc_roi=roi, adc_truth_xy=np.array([dx[roi][0], dy[roi][0]]),
                        adc_iso_roi=iso_roi, adc_iso_truth=dx[iso_roi][0],
                        diffusivity_mm2_s=dx, diffusivity_y_mm2_s=dy,
                        ms_b0_calib=ms_calib, ms_shots=ms_shots, pair_indices=pair,
                        injected_phase_rad=PHASE_RAD, injected_delay_us=DELAY_US)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'preparation' / 'seq_diffusion.zip')
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'sequence_dwi.npz')
    args = parser.parse_args()
    build(args.archive, args.output)
