"""Helpers for inspecting pypulseq RF pulses, built on pypulseq functionality wherever possible.

pypulseq functions used:
    pp.Sequence / seq.add_block      wrap each pulse (rf + slice-select + rephaser) in its own sequence
    seq.plot(overlay=...)            native time-domain plot, multiple pulses overlaid
    seq.waveforms(append_RF=True)    exact RF and gradient waveforms (incl. ramps and rephaser)
    pp.calc_rf_bandwidth             FFT spectrum (small-tip slice profile) and bandwidth
    pp.calc_duration                 block durations

pypulseq has no Bloch simulator, so that part is implemented here, but it is driven
entirely by the waveforms returned by seq.waveforms().

Usage in the tutorial script:

    from tools.rf_profile import plot_rf_profile, plot_rf_profiles

    # single pulse
    plot_rf_profile(rfexc, gz, gzr, system=system, slice_thickness=slice_thickness)

    # several pulses overlaid: tuples (rf, gz, gzr, label); gz/gzr may be None
    plot_rf_profiles(
        [(rfexc, gz_exc, gzr_exc, 'Exc 90°'), (rfref, gz_ref, None, 'Ref 180°')],
        system=system,
        slice_thickness=slice_thickness,
    )
"""

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pypulseq as pp

PLOT_DIR = Path(__file__).resolve().parent / 'export'      # tools/export
NON_INTERACTIVE = ('agg', 'pdf', 'svg', 'ps', 'cairo', 'template')

INTERACTIVE_HELP = """plots: navigate like in MATLAB --
  mouse wheel        zoom the time (x) axis at the cursor     (+ shift: y axis, + ctrl: both)
  toolbar / keys     o = zoom rectangle,  p = pan (drag),  h = home,  c / v = back / forward
  stacked channels share the time axis: zooming one channel zooms all"""
_help_shown = False


def add_scroll_zoom(fig, factor=1.25):
    """Mouse-wheel zoom for a matplotlib figure, centred at the cursor.

    wheel: x axis, shift + wheel: y axis, ctrl + wheel: both.
    Axes created with sharex (e.g. seq.plot(stacked=True)) follow automatically.
    """
    if getattr(fig, '_scroll_zoom', False):
        return
    fig._scroll_zoom = True

    def on_scroll(event):
        ax = event.inaxes
        if ax is None or event.xdata is None:
            return
        scale = 1 / factor if event.button == 'up' else factor
        key = event.key or ''
        zoom_x = 'shift' not in key or 'control' in key or 'ctrl' in key
        zoom_y = 'shift' in key or 'control' in key or 'ctrl' in key
        if zoom_x:
            x0, x1 = ax.get_xlim()
            ax.set_xlim(event.xdata - (event.xdata - x0) * scale, event.xdata + (x1 - event.xdata) * scale)
        if zoom_y:
            y0, y1 = ax.get_ylim()
            ax.set_ylim(event.ydata - (event.ydata - y0) * scale, event.ydata + (y1 - event.ydata) * scale)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect('scroll_event', on_scroll)


def show_or_save(title):
    """Show figures interactively (with mouse-wheel zoom), or save them as PNG if no display is available."""
    global _help_shown
    if matplotlib.get_backend().lower() in NON_INTERACTIVE:
        PLOT_DIR.mkdir(exist_ok=True)
        stem = ''.join(c if c.isalnum() else '_' for c in title).strip('_')
        for n in plt.get_fignums():
            path = PLOT_DIR / f'{stem}_fig{n}.png'
            plt.figure(n).savefig(path, dpi=120)
            print(f'saved {path}')
        plt.close('all')
    elif 'inline' in matplotlib.get_backend().lower():
        plt.show()                      # notebook, static images
    else:
        for n in plt.get_fignums():     # plot window or notebook widget (ipympl): zoomable
            add_scroll_zoom(plt.figure(n))
        if not _help_shown:
            print(INTERACTIVE_HELP)
            _help_shown = True
        plt.show()


def build_pulse_sequence(rf, gz=None, gzr=None, system=None):
    """Put a pulse (with optional slice-select and rephasing gradient) into its own pp.Sequence."""
    seq = pp.Sequence(system)
    seq.add_block(*[e for e in (rf, gz) if e is not None])
    if gzr is not None:
        seq.add_block(gzr)
    return seq


def bloch_slice_profile(seq, z, axis=2):
    """Bloch simulation of the whole sequence for positions z (m), starting from M = (0, 0, 1).

    RF (Hz) and gradient (Hz/m) are taken from seq.waveforms(append_RF=True), so ramps and
    the rephasing lobe are included exactly as pypulseq will play them out.
    Returns the transverse magnetisation Mxy (complex) and Mz at the end of the sequence.
    """
    waves = seq.waveforms(append_RF=True)
    grad_wave = waves[axis]  # rows: time, amplitude (piecewise linear)
    rf_wave = waves[-1]  # rows: time, complex signal

    dt = seq.system.rf_raster_time
    t_end = sum(pp.calc_duration(seq.get_block(i)) for i in seq.block_events)
    t = np.arange(0, t_end, dt) + dt / 2

    t_rf = rf_wave[0].real
    b1 = np.interp(t, t_rf, rf_wave[1].real, left=0, right=0) + 1j * np.interp(
        t, t_rf, rf_wave[1].imag, left=0, right=0
    )
    if grad_wave.shape[1] > 0:
        g = np.interp(t, grad_wave[0], grad_wave[1], left=0, right=0)
    else:
        g = np.zeros_like(t)

    mx = np.zeros_like(z, dtype=float)
    my = np.zeros_like(z, dtype=float)
    mz = np.ones_like(z, dtype=float)

    for b, gi in zip(b1, g):
        # rotation vector (rad) in the rotating frame
        wx = np.full_like(z, 2 * np.pi * dt * b.real)
        wy = np.full_like(z, 2 * np.pi * dt * b.imag)
        wz = 2 * np.pi * dt * gi * z
        phi = np.sqrt(wx**2 + wy**2 + wz**2)
        phi_safe = np.where(phi == 0, 1, phi)
        nx, ny, nz = wx / phi_safe, wy / phi_safe, wz / phi_safe
        c, s = np.cos(phi), np.sin(phi)
        # Rodrigues rotation of M about n by -phi (left-handed precession, Bloch convention)
        dot = nx * mx + ny * my + nz * mz
        cx = ny * mz - nz * my
        cy = nz * mx - nx * mz
        cz = nx * my - ny * mx
        mx, my, mz = (
            mx * c - cx * s + nx * dot * (1 - c),
            my * c - cy * s + ny * dot * (1 - c),
            mz * c - cz * s + nz * dot * (1 - c),
        )

    return mx + 1j * my, mz


def _normalise_entries(pulses):
    """Accept (rf,), (rf, gz), (rf, gz, gzr) or (rf, gz, gzr, label) and fill in the gaps."""
    entries = []
    for i, p in enumerate(pulses):
        p = tuple(p) if isinstance(p, (tuple, list)) else (p,)
        p = p + (None,) * (4 - len(p))
        rf, gz, gzr, label = p[:4]
        entries.append((rf, gz, gzr, label or f'Pulse {i + 1}'))
    return entries


def plot_rf_profiles(pulses, system=None, slice_thickness=None, title='RF pulses', time_disp='ms'):
    """Overlay several pulses.

    Figures 1/2: native pypulseq sequence plot (RF magnitude/phase, gradients), overlaid via seq.plot(overlay=...).
    Figure 3: slice profiles, from pp.calc_rf_bandwidth (small-tip FFT) and from a Bloch simulation.

    pulses: list of tuples (rf, gz, gzr, label); trailing elements may be omitted, gz/gzr may be None.
    system: pp.Opts used to create the pulses (default: pp.Opts()).
    slice_thickness: optional nominal slice thickness (m), drawn as dashed lines.
    """
    entries = _normalise_entries(pulses)
    seqs = [build_pulse_sequence(rf, gz, gzr, system) for rf, gz, gzr, _ in entries]
    labels = [label for *_, label in entries]

    # --- time domain: pypulseq's own plot, overlaid ---
    seq_plot = None
    for seq in seqs:
        seq_plot = seq.plot(time_disp=time_disp, grad_disp='mT/m', plot_now=False, overlay=seq_plot)
    seq_plot.fig1.suptitle(f'{title}: RF')
    seq_plot.fig2.suptitle(f'{title}: gradients')

    # --- slice profiles ---
    with_gz = [(seq, rf, gz, label) for seq, (rf, gz, _, label) in zip(seqs, entries) if gz is not None]
    if not with_gz:
        show_or_save(title)
        return seq_plot, None

    # slice thickness from pypulseq's bandwidth: thk = BW / G
    bw_thk = {
        label: float(np.squeeze(pp.calc_rf_bandwidth(rf))) / abs(gz.amplitude) for _, rf, gz, label in with_gz
    }
    z_max = 3 * (slice_thickness or max(bw_thk.values()))
    z = np.linspace(-z_max, z_max, 601)
    z_mm = z * 1e3

    fig, (ax_fft, ax_bloch, ax_phase) = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
    fig.suptitle(f'{title}: slice profiles')

    for seq, rf, gz, label in with_gz:
        _, spectrum, freq = pp.calc_rf_bandwidth(rf, return_spectrum=True, return_axis=True)
        z_fft = freq / gz.amplitude  # frequency -> position
        keep = np.abs(z_fft) <= z_max
        order = np.argsort(z_fft[keep])
        mag = np.abs(spectrum[keep][order])
        (line,) = ax_fft.plot(
            z_fft[keep][order] * 1e3, mag / mag.max(), label=f'{label} (BW/G = {bw_thk[label] * 1e3:.2f} mm)'
        )
        color = line.get_color()

        mxy, mz = bloch_slice_profile(seq, z)
        ax_bloch.plot(z_mm, np.abs(mxy), color=color, label=f'{label} |Mxy|')
        ax_bloch.plot(z_mm, mz, color=color, ls=':', label=f'{label} Mz')

        inside = np.abs(mxy) > 0.1 * np.abs(mxy).max()
        ax_phase.plot(z_mm[inside], np.angle(mxy[inside]), '.', ms=2, color=color, label=label)

    ax_fft.set(ylabel='normalised |FFT|', title='Small-tip profile (pp.calc_rf_bandwidth)')
    ax_bloch.set(ylabel='M / M0', title='Bloch simulation (waveforms from seq.waveforms)')
    ax_phase.set(xlabel='z [mm]', ylabel='phase [rad]', title='Phase of Mxy at end of sequence')
    for ax in (ax_fft, ax_bloch, ax_phase):
        if slice_thickness:
            for edge in (-slice_thickness / 2, slice_thickness / 2):
                ax.axvline(edge * 1e3, color='gray', ls='--')
        ax.grid(True)
        ax.legend(fontsize='small')
    fig.tight_layout()

    show_or_save(title)
    return seq_plot, fig


def plot_exc_inv_profiles(exc, inv, system=None, slice_thickness=None, title='Excitation vs. inversion profile'):
    """Overlay the excitation profile |Mxy| and the inversion efficiency (1 - Mz) / 2 in one plot.

    Both curves run from 0 (outside the slice) to 1 (full excitation / full inversion).

    exc: (rf, gz, gzr) of the excitation pulse; gzr may be None.
    inv: (rf, gz) or (rf, gz, gzr) of the inversion/refocusing pulse.
    Both are Bloch-simulated from M = (0, 0, 1).
    """
    seq_exc = build_pulse_sequence(*exc[:3], system=system)
    seq_inv = build_pulse_sequence(*inv[:3], system=system)

    z_max = 3 * (slice_thickness or float(np.squeeze(pp.calc_rf_bandwidth(exc[0]))) / abs(exc[1].amplitude))
    z = np.linspace(-z_max, z_max, 601)
    mxy_exc, _ = bloch_slice_profile(seq_exc, z)
    _, mz_inv = bloch_slice_profile(seq_inv, z)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(z * 1e3, np.abs(mxy_exc), label='excitation |Mxy|')
    ax.plot(z * 1e3, (1 - mz_inv) / 2, label='inversion (1 - Mz) / 2')
    if slice_thickness:
        for edge in (-slice_thickness / 2, slice_thickness / 2):
            ax.axvline(edge * 1e3, color='gray', ls='--')
    ax.set(xlabel='z [mm]', ylabel='normalised profile', title=title)
    ax.grid(True)
    ax.legend()
    fig.tight_layout()

    show_or_save(title)
    return fig


def compare_ref_profiles(exc, refs, system=None, slice_thickness=None, title='Refocusing pulses'):
    """Compare refocusing pulses (e.g. sinc vs. SLR) for a spin echo.

    Top:    RF amplitude of each refocusing pulse in uT, with its peak B1 in the legend
    Middle: excitation profile |Mxy| and refocusing efficiency (1 - Mz) / 2 of each pulse
    Bottom: spin-echo slice profile = |Mxy| (excitation) x (1 - Mz) / 2 (refocusing)

    exc:  (rf, gz, gzr) of the excitation pulse
    refs: list of (rf, gz, label) of the refocusing pulses
    """
    gamma = (system or pp.Opts()).gamma
    seq_exc = build_pulse_sequence(*exc[:3], system=system)
    z_max = 3 * (slice_thickness or float(np.squeeze(pp.calc_rf_bandwidth(exc[0]))) / abs(exc[1].amplitude))
    z = np.linspace(-z_max, z_max, 601)
    z_mm = z * 1e3
    mxy_exc = np.abs(bloch_slice_profile(seq_exc, z)[0])

    fig, (ax_rf, ax_ref, ax_se) = plt.subplots(3, 1, figsize=(8, 10))
    fig.suptitle(title)
    ax_ref.plot(z_mm, mxy_exc, 'k--', label='excitation |Mxy|')
    for rf, gz, label in refs:
        _, mz = bloch_slice_profile(build_pulse_sequence(rf, gz, system=system), z)
        eff = (1 - mz) / 2
        b1 = rf.signal / gamma * 1e6
        (line,) = ax_rf.plot((rf.t - rf.t[0]) * 1e3, b1.real,
                             label=f'{label}: peak B1 = {np.max(np.abs(b1)):.1f} uT')
        ax_ref.plot(z_mm, eff, color=line.get_color(), label=f'{label}: (1 - Mz) / 2')
        ax_se.plot(z_mm, mxy_exc * eff, color=line.get_color(), label=label)
    ax_rf.set(xlabel='t [ms]', ylabel='B1 [uT]', title='RF pulse shape')
    ax_ref.set(xlabel='z [mm]', ylabel='profile', title='Excitation and refocusing (Bloch simulation)')
    ax_se.set(xlabel='z [mm]', ylabel='echo amplitude', title='Spin-echo slice profile = excitation x refocusing')
    for ax in (ax_rf, ax_ref, ax_se):
        ax.grid(True)
        ax.legend(fontsize='small')
    if slice_thickness:
        for ax in (ax_ref, ax_se):
            for edge in (-slice_thickness / 2, slice_thickness / 2):
                ax.axvline(edge * 1e3, color='gray', ls='--')
    fig.tight_layout()

    show_or_save(title)
    return fig


def plot_rf_profile(rf, gz=None, gzr=None, system=None, slice_thickness=None, title='RF pulse'):
    """Single pulse (shorthand for plot_rf_profiles)."""
    return plot_rf_profiles([(rf, gz, gzr, title)], system=system, slice_thickness=slice_thickness, title=title)


if __name__ == '__main__':
    # Demo: same slice (3 mm), different time-bandwidth products
    system = pp.Opts(
        max_grad=32,
        grad_unit='mT/m',
        max_slew=130,
        slew_unit='T/m/s',
        rf_ringdown_time=30e-6,
        rf_dead_time=100e-6,
    )
    pulses = []
    for tbw in (2, 4, 8):
        rf, gz, gzr = pp.make_sinc_pulse(
            flip_angle=np.pi / 2,
            duration=3e-3,
            slice_thickness=3e-3,
            apodization=0.5,
            time_bw_product=tbw,
            system=system,
            return_gz=True,
            use='excitation',
        )
        pulses.append((rf, gz, gzr, f'TBW {tbw}'))
    plot_rf_profiles(pulses, system=system, slice_thickness=3e-3, title='90° sinc, 3 mm')
