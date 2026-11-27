"""Automatic check of a DW-SE-EPI .seq file -- tells you what works and what does not.

usage:  python tools/check_seq.py tools/export/my_dwepi_M1.seq [--milestone N]
        (the level scripts run this check automatically at the end)

    --milestone 1   spin-echo EPI: timing, hardware limits, k-space coverage, TE, labels
    --milestone 2   + diffusion: b-value measured from the gradient waveforms
    --milestone 3   + navigators
    --milestone 4   + multi-slice: frequency/phase offsets, interleaved order
Without --milestone every feature that is present in the file is checked.

The checks only use the .seq file (events, labels and [DEFINITIONS]), not your Python code,
so any implementation that produces a correct sequence passes.
"""

import argparse
import sys
from pathlib import Path

if __name__ == '__main__':      # started directly: run it in the workshop environment (.venv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import tools.workshop_env  # noqa: F401

import numpy as np
import pypulseq as pp

GAMMA = 42.576e6
results = []


def report(status, msg, hint=None):
    results.append(status)
    print(f'  [{status}] {msg}')
    if hint and status == 'FAIL':
        print(f'         hint: {hint}')


def check(cond, msg, hint=None):
    report('PASS' if cond else 'FAIL', msg, hint)
    return cond


def get_def(seq, key, default=None):
    try:
        return seq.get_definition(key)
    except (KeyError, ValueError):
        return default


def run_check(seq_file, milestone=0, max_grad=90, max_slew=130):
    """Check a .seq file, print PASS / FAIL with hints. Returns the number of failed checks."""
    results.clear()
    ms = milestone
    args = argparse.Namespace(seq=str(seq_file), milestone=milestone, max_grad=max_grad, max_slew=max_slew)
    seq = pp.Sequence()
    seq.read(args.seq)
    print(f'checking {args.seq}' + (f' for milestone {ms}' if ms else ''))

    # ------------------------------------------------------------------ definitions
    print('\n[1] definitions')
    need = ['FOV', 'Nx', 'Ny', 'TE', 'TR', 'BValue', 'NSlices']
    missing = [k for k in need if get_def(seq, k) is None]
    if not check(not missing, 'required definitions present' + (f' (missing: {missing})' if missing else ''),
                 'seq.set_definition(key=..., value=...) before seq.write()'):
        return finish()
    fov = np.atleast_1d(get_def(seq, 'FOV')).astype(float)
    fovX, fovY = fov[0], fov[1] if fov.size > 1 else fov[0]
    nx, ny = int(get_def(seq, 'Nx')), int(get_def(seq, 'Ny'))
    te, tr = float(get_def(seq, 'TE')), float(get_def(seq, 'TR'))
    bDef = float(get_def(seq, 'BValue'))
    nSlicesDef = int(get_def(seq, 'NSlices'))
    print(f'       FOV {fovX * 1e3:.0f} x {fovY * 1e3:.0f} mm, matrix {nx} x {ny}, TE {te * 1e3:.2f} ms, '
          f'TR {tr * 1e3:.0f} ms, b = {bDef:g}, {nSlicesDef} slice(s)')

    # ------------------------------------------------------------------ timing + hardware
    print('\n[2] timing and hardware limits')
    ok, errs = seq.check_timing()
    check(ok, 'seq.check_timing()', f'{len(errs)} errors, first: {errs[0] if errs else ""}')
    wave = seq.waveforms_and_times()[0]
    gMax, sMax = 0.0, 0.0
    for ax in range(3):
        t, g = wave[ax]
        if t.size < 2:
            continue
        gMax = max(gMax, np.max(np.abs(g)))
        dt = np.diff(t)
        good = dt > 1e-9
        if good.any():
            sMax = max(sMax, np.max(np.abs(np.diff(g)[good] / dt[good])))
    gMaxT, sMaxT = gMax / GAMMA * 1e3, sMax / GAMMA
    check(gMaxT <= args.max_grad * 1.001, f'max gradient {gMaxT:.1f} mT/m (limit {args.max_grad:g})',
          'an amplitude is too high; did you pass system=system to every make_* function?')
    check(sMaxT <= args.max_slew * 1.01, f'max slew rate per axis {sMaxT:.1f} T/m/s (limit {args.max_slew:g})',
          'a ramp is too short; did you add two gradients on the same axis in one block?')

    # ------------------------------------------------------------------ RF / structure
    print('\n[3] RF pulses and labels')
    rfs = []             # (block, use, freq_offset, phase_offset, gz amplitude, rf)
    t0 = 0.0
    for i in seq.block_events:
        b = seq.get_block(i)
        if b.rf is not None:
            gz = b.gz.amplitude if b.gz is not None and hasattr(b.gz, 'amplitude') else np.nan
            rfs.append(dict(block=i, t=t0, use=b.rf.use, f=b.rf.freq_offset, ph=b.rf.phase_offset, gz=gz, rf=b.rf))
        t0 += pp.calc_duration(b)
    exc = [r for r in rfs if r['use'] == 'excitation']
    ref = [r for r in rfs if r['use'] == 'refocusing']
    check(len(exc) > 0 and len(exc) == len(ref),
          f'{len(exc)} excitation and {len(ref)} refocusing pulses',
          "use='excitation' / use='refocusing' in the make_*_pulse calls, one 180° per 90°")
    if not exc:
        return finish()

    labels = seq.evaluate_labels(evolution='adc')
    ktrajAdc, _, tExc, tRef, tAdc = seq.calculate_kspace()
    nAdcTot = tAdc.size
    nAdcBlocks = len(np.asarray(labels['SLC'])) if 'SLC' in labels else None
    hasSlc = check('SLC' in labels, 'label SLC (slice index) present',
                   "pp.make_label(label='SLC', type='SET', value=iSlice) on the 1st ADC block of each slice")
    isNav = np.asarray(labels['NAV'], bool) if 'NAV' in labels else None
    slc = np.asarray(labels['SLC'], int) if hasSlc else None

    # split ADC samples into lines (one ADC event = one line)
    dtA = np.diff(tAdc)
    nPerLine = int(np.argmax(dtA > dtA[0] * 1.5)) + 1
    nLines = nAdcTot // nPerLine
    if not check(nLines * nPerLine == nAdcTot, f'{nLines} ADC events with {nPerLine} samples each',
                 'all ADC events must have the same number of samples'):
        return finish()
    kx = ktrajAdc[0].reshape(nLines, nPerLine)
    ky = ktrajAdc[1].reshape(nLines, nPerLine)
    kz = ktrajAdc[2].reshape(nLines, nPerLine)
    tL = tAdc.reshape(nLines, nPerLine)
    if isNav is None or isNav.size != nLines:
        isNav = np.zeros(nLines, bool)
    if slc is None or slc.size != nLines:
        slc = np.zeros(nLines, int)

    # lines of the first excitation (first slice in acquisition order)
    tEnd = tExc[1] if len(tExc) > 1 else np.inf
    first = (tL[:, 0] > tExc[0]) & (tL[:, 0] < tEnd)
    img = np.where(first & ~isNav)[0]
    nav = np.where(first & isNav)[0]

    # ------------------------------------------------------------------ k-space
    print('\n[4] k-space (first slice)')
    dkx, dky = 1 / fovX, 1 / fovY
    yIdx = ky[img].mean(axis=1) / dky
    check(np.allclose(ky[img].std(axis=1), 0, atol=1e-3 * dky),
          'ky constant during each ADC (blips only between the samples)',
          'the half blips must lie outside the ADC window (on the unsampled part of the RO ramps)')
    onGrid = np.allclose(yIdx, np.round(yIdx), atol=0.02)
    check(onGrid, f'ky on the grid 1/FOVy = {dky:.2f} 1/m', 'blip area must be 1/fovY, prephaser area a multiple of it')
    yIdx = np.round(yIdx).astype(int)
    steps = np.diff(yIdx)
    check(steps.size > 0 and np.all(steps == steps[0]) and abs(steps[0]) == 1,
          f'{len(img)} imaging lines, ky step of exactly one line ({yIdx[0]} -> {yIdx[-1]})',
          'every line needs one blip of area 1/fovY, the same sign for all lines')
    full = set(range(-ny // 2, ny // 2))
    measured = set(yIdx.tolist())
    check(0 in measured and len(measured) >= ny // 2 + 1 and measured <= full | {ny // 2}
          and (min(measured) == -ny // 2 or max(measured) >= ny // 2 - 1),
          f'ky covers k-space center and one full half ({len(measured)} of {ny} lines, '
          f'partial Fourier {len(measured) / ny:.3f})',
          'check the PE prephaser (nYpre lines) and the number of lines')
    pol = np.sign(kx[:, -1] - kx[:, 0])
    check(np.all(pol[img][1:] == -pol[img][:-1]), 'readout polarity alternates from line to line',
          'ro for even lines, roNeg for odd lines')
    kxLo, kxHi = -nx / 2 * dkx, (nx / 2 - 1) * dkx
    cover = [(kx[i].min() <= kxLo + dkx / 2) and (kx[i].max() >= kxHi - dkx / 2) for i in img]
    check(all(cover), f'every line covers kx = {kxLo:.0f} ... {kxHi:.0f} 1/m '
          f'(measured {kx[img].min():.0f} ... {kx[img].max():.0f})',
          'RO area inside the ADC window must be Nx/fovX, ADC centered, prephaser area -ro.area/2')
    spacing = np.max(np.abs(np.diff(kx[img], axis=1)))
    check(spacing <= dkx * 1.01, f'kx sample spacing <= 1/FOVx (max {spacing / dkx:.3f} x 1/FOVx)',
          'too few ADC samples / dwell time too long')
    check(np.max(np.abs(kz[img])) < 0.05 * dkx, f'kz = 0 during the readout (max |kz| = {np.max(np.abs(kz[img])):.2f} 1/m)',
          'slice rephaser or crushers are not balanced (same crusher on both sides of the 180°)')

    # ------------------------------------------------------------------ TE
    print('\n[5] echo time')
    check(abs((tRef[0] - tExc[0]) - te / 2) < 2e-6,
          f'180° center at TE/2 ({(tRef[0] - tExc[0]) * 1e3:.3f} ms, expected {te / 2 * 1e3:.3f} ms)',
          'delayTE1 or the minimal time exc -> ref is wrong')
    i0 = img[np.argmin(np.abs(yIdx))]
    s0 = np.argmin(np.abs(kx[i0]))
    tEcho = tL[i0, s0] - tExc[0]
    dwell = tL[0, 1] - tL[0, 0]
    check(abs(tEcho - te) <= dwell,
          f'k-space center (kx = ky = 0) sampled at TE ({tEcho * 1e3:.3f} ms, expected {te * 1e3:.3f} ms)',
          'delayTE2 or the minimal time ref -> echo is wrong (lines before ky = 0, half a line)')

    # ------------------------------------------------------------------ diffusion
    print('\n[6] diffusion weighting')
    # b along each axis from the gradient waveforms between excitation and echo (sign flip at the 180°)
    tt = np.arange(tExc[0], tExc[0] + te, 1e-6)
    gt = np.array([np.interp(tt, wave[a][0], wave[a][1], left=0, right=0) if wave[a].size else 0 * tt
                   for a in range(3)])
    gt[:, tt > tRef[0]] *= -1
    kt = np.cumsum(gt, axis=1) * 1e-6
    bMat = (2 * np.pi) ** 2 * (kt @ kt.T) * 1e-6 * 1e-6          # s/m^2 -> s/mm^2
    dDir = get_def(seq, 'DiffusionDirection')
    if dDir is not None and len(np.atleast_1d(dDir)) == 3:
        n = np.asarray(dDir, float)
        n = n / np.linalg.norm(n)
        bMeas = float(n @ bMat @ n)
        txt = f'along {np.round(n, 3)}'
    else:
        bMeas = float(np.trace(bMat))
        txt = '(trace)'
    tol = max(5.0, 0.03 * bDef)
    if ms >= 2 or bDef > 0:
        check(bDef > 0 or ms < 2, f'diffusion switched on (BValue = {bDef:g})', 'milestone 2 needs b_value > 0')
        check(abs(bMeas - bDef) <= tol, f'b-value from the waveforms {bMeas:.1f} s/mm^2 {txt}, definition {bDef:g}',
              'check the amplitude scaling (b ~ G^2) and that both diffusion gradients have the SAME sign')
    else:
        report('INFO', f'b = 0 file, b from the imaging gradients: {bMeas:.2f} s/mm^2 {txt}')

    # ------------------------------------------------------------------ navigators
    print('\n[7] navigators')
    if len(nav) == 0:
        if ms >= 3:
            check(False, 'navigator lines (label NAV = True) present',
                  "NAV = True on the 1st navigator ADC, NAV = False on the 1st EPI line")
        else:
            report('INFO', 'no navigators (label NAV) found')
    else:
        nNavDef = get_def(seq, 'NavigatorLines')
        check(nNavDef is None or int(nNavDef) == len(nav), f'{len(nav)} navigator lines per slice')
        check(np.all(tL[nav, 0] < tRef[0]), 'navigators before the 180°', 'they belong into the 1st TE/2 interval')
        check(np.allclose(ky[nav], 0, atol=1e-3 * dky), 'navigators at ky = 0', 'no blips on the navigator lines')
        check(np.all(pol[nav][1:] == -pol[nav][:-1]), 'navigator polarity alternates')
        cover = [(kx[i].min() <= kxLo + dkx / 2) and (kx[i].max() >= kxHi - dkx / 2) for i in nav]
        check(all(cover), 'navigators cover the same kx range as the imaging lines', 'navPre area -ro.area/2')

    # ------------------------------------------------------------------ multi-slice
    print('\n[8] slices')
    nExc = len(exc)
    nRep = int(np.max(labels['REP'])) + 1 if 'REP' in labels else 1
    nSl = nExc // nRep
    check(nSl == nSlicesDef, f'{nSl} excitation(s) per repetition, NSlices = {nSlicesDef}')
    check(abs(seq.duration()[0] - nRep * tr) < 1e-4, f'total duration {seq.duration()[0]:.3f} s = n_reps x TR',
          'delayTR = tr / n_slices - (duration of one slice)')
    if nSl > 1 or ms >= 4:
        if not check(nSl > 1, 'more than one slice', 'milestone 4 needs n_slices > 1'):
            return finish()
        e, r = exc[:nSl], ref[:nSl]
        zExc = np.array([x['f'] / x['gz'] for x in e])
        zRef = np.array([x['f'] / x['gz'] for x in r])
        check(np.allclose(zExc, zRef, atol=1e-5), 'same slice position for 90° and 180° (f / G_slice)',
              'each pulse needs freq_offset = its own slice gradient amplitude * z')
        zs = np.sort(zExc)
        dist = np.diff(zs)
        thk = get_def(seq, 'SliceThickness', fov[2] if fov.size > 2 else None)
        gapF = get_def(seq, 'SliceGapFactor')
        expDist = float(thk) * float(gapF) if thk is not None and gapF is not None else dist.mean()
        check(np.allclose(dist, expDist, atol=1e-6),
              f'slice positions {np.round(zs * 1e3, 2)} mm, distance {expDist * 1e3:.2f} mm',
              'z = (spatial index - n_slices // 2) * slice_gap_factor * slice_thickness')
        check(np.min(np.abs(zs)) < 1e-6, 'one slice at the isocenter', 'slice n_slices // 2 must be at z = 0')
        spatial = [int(s) for s in np.searchsorted(zs, zExc)]
        expOrder = list(range(0, nSl, 2)) + list(range(1, nSl, 2))
        check(spatial == expOrder, f"interleaved acquisition order {spatial}",
              f'expected {expOrder} (even spatial indices first, then odd)')
        # SLC label of each slice = spatial index
        slcOfExc = []
        for k in range(nSl):
            tE = tExc[k + 1] if k + 1 < len(tExc) else np.inf
            sel = (tL[:, 0] > tExc[k]) & (tL[:, 0] < tE)
            slcOfExc.append(int(slc[sel][0]) if sel.any() else -1)
        check(slcOfExc == spatial, f'label SLC = spatial slice index {slcOfExc}',
              'SLC must be the spatial index (position), not the acquisition counter')
        # phase offsets: phase at the pulse center must be the same for all slices
        for name, pulses in (('90°', e), ('180°', r)):
            iso = pulses[int(np.argmin(np.abs([x['f'] for x in pulses])))]
            tc = pp.calc_rf_center(iso['rf'])[0]
            dev = [np.angle(np.exp(1j * (x['ph'] + 2 * np.pi * x['f'] * tc - iso['ph']))) for x in pulses]
            check(np.allclose(dev, 0, atol=1e-3),
                  f'{name}: phase_offset compensates the frequency offset (phase at pulse center constant)',
                  'phase_offset = phase0 - 2*pi*freq_offset*t_center, t_center = pp.calc_rf_center(rf)[0]')
    else:
        report('INFO', 'single slice')

    return finish()


def finish():
    nFail = results.count('FAIL')
    nPass = results.count('PASS')
    print(f'\n{nPass} passed, {nFail} failed')
    if nFail == 0:
        print('Well done -- this sequence is ready for simulation (SIMULATE = True at the bottom of the level file).')
    return nFail


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('seq')
    ap.add_argument('--milestone', type=int, default=0)
    ap.add_argument('--max-grad', type=float, default=90, help='mT/m (default 90)')
    ap.add_argument('--max-slew', type=float, default=130, help='T/m/s per axis (default 130)')
    args = ap.parse_args()
    return 1 if run_check(args.seq, args.milestone, args.max_grad, args.max_slew) else 0


if __name__ == '__main__':
    sys.exit(main())
