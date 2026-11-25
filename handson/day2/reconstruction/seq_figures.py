"""Figures and one-step omission controls for the sequence-matched phantom."""

import matplotlib.pyplot as plt
import numpy as np

from bart_io import bart
from epi_recon import adc_trajectory, cartesian_kx, correct_native, fit_b0, pocs, regrid


def show_acquisition(scan):
    """Readout events, physical ADC spacing and the phase-encode coverage."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.5), layout="constrained")
    ax_events, ax_mask, ax_grad, ax_spacing = axes.flat
    nav = scan["event_is_nav"].astype(bool)
    sign = scan["event_polarity"]
    times = scan["event_adc_times_s"]
    ky = scan["event_ky_cpm"] * scan["fov_m"][1]
    event_time = 1000 * times.mean(axis=1)
    colors = {1: "#196b86", -1: "#ad5921"}

    for polarity, label in [(1, "Positive readout"), (-1, "Negative readout")]:
        chosen = (sign == polarity) & ~nav
        ax_events.scatter(event_time[chosen], ky[chosen], s=14, label=label,
                          color=colors[polarity])
    ax_events.scatter(event_time[nav], ky[nav], s=28, marker="x",
                      color="#313741", label="Navigator")
    for field, label in [("excitation_time_s", "Excitation"),
                         ("refocusing_time_s", "Refocusing")]:
        t_rf = float(scan[field]) * 1000
        ax_events.axvline(t_rf, color=".56", lw=1, ls=":")
        ax_events.text(t_rf + .6, .50, label, rotation=90, va="center", fontsize=8,
                       transform=ax_events.get_xaxis_transform())
    nav_label = "  ".join("+" if p > 0 else "−" for p in sign[nav])
    ax_events.annotate(nav_label, (np.mean(event_time[nav]), np.mean(ky[nav])),
                       xytext=(0, 9), textcoords="offset points", ha="center", fontsize=8)
    first = np.flatnonzero(~nav)[0]
    ax_events.annotate("First imaging echo (+)", (event_time[first], ky[first]),
                       xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8)
    ax_events.set(title="Navigators and imaging echoes", xlabel="Sequence time (ms)",
                  ylabel=r"Phase-encode index  $k_y\,\mathrm{FOV}_y$")
    ax_events.set_xlim(-1, event_time.max() + 3)
    ax_events.margins(y=.17)
    ax_events.legend(loc="lower left", fontsize=8, frameon=False)

    ny = int(scan["matrix_xy"][1])
    ky_indices = np.arange(ny) - ny // 2
    measured = np.isin(np.arange(ny), scan["ky_idx"])
    symmetric = measured & np.isin(-ky_indices, ky_indices[measured])
    for keep, y, label, color in [(measured, 1., "Acquired", colors[1]),
                                  (~measured, 1., "Missing", "#c7ccd0"),
                                  (symmetric, 0., "Symmetric center", "#607f46")]:
        ax_mask.scatter(ky_indices[keep], np.full(np.count_nonzero(keep), y),
                        marker="|", s=175, linewidths=1.8, color=color, label=label)
    ax_mask.axvline(0, color=".35", lw=.8, ls=":")
    ax_mask.set(title="One phase-encode edge is missing",
                xlabel=r"Phase-encode index  $k_y\,\mathrm{FOV}_y$",
                yticks=[0, 1], yticklabels=["Symmetric pairs", "Imaging echoes"], ylim=(-.7,1.7))
    ax_mask.legend(loc="lower center", bbox_to_anchor=(.5, -.02), ncol=3, fontsize=8,
                   frameon=False)

    time_knots, gradient = scan["gx_time_s"], scan["gx_tm"] * 1e3
    for polarity in (1, -1):
        idx = np.flatnonzero((sign == polarity) & ~nav)[0]
        t_adc = times[idx]
        origin = t_adc.mean()
        margin = .20 * np.ptp(t_adc)
        lo, hi = t_adc[0] - margin, t_adc[-1] + margin
        waveform_t = np.r_[lo, time_knots[(time_knots > lo) & (time_knots < hi)], hi]
        ax_grad.plot((waveform_t - origin) * 1e6, np.interp(waveform_t, time_knots, gradient),
                     color=colors[polarity], lw=1)
        adc_g = np.interp(t_adc, time_knots, gradient)
        ax_grad.scatter((t_adc - origin) * 1e6, adc_g,
                        s=5, color=colors[polarity], zorder=3)
        if polarity == 1:
            plateau = np.flatnonzero(np.isclose(adc_g, adc_g.max()))
            regions = np.split(np.arange(len(adc_g)), [plateau[0], plateau[-1] + 1])
            for name, region in zip(["rise", "plateau", "fall"], regions):
                x = (t_adc[region].mean() - origin) * 1e6
                ax_grad.text(x, 0, f"{len(region)}\n{name}", ha="center",
                             va="center", color="#39414a", fontsize=8)
        kx = scan["event_kx_cpm"][idx]
        mid = .5 * (t_adc[1:] + t_adc[:-1])
        ax_spacing.plot((mid - origin) * 1e6, np.diff(kx) * scan["fov_m"][0],
                        color=colors[polarity], lw=2)
    ax_grad.set(title="Gradient waveform and ADC centers", xlabel="Time from echo center (µs)",
                ylabel=r"Readout gradient $G_x$ (mT/m)")
    ax_spacing.axhline(0, color=".65", lw=.7)
    ax_spacing.set(title="Distance between successive ADC samples",
                   xlabel="Time from echo center (µs)", ylabel=r"Signed $\Delta k_x\,\mathrm{FOV}_x$")
    return fig


def _homodyne_volumes(kspace, fraction):
    # Volume is BART dimension 4, outside all three spatial transform dimensions.
    stack = np.stack(kspace, axis=-1)[:, :, None, None, :]
    images = bart(["homodyne", "-C", "1", str(fraction)], stack)
    return images[:, :, 0, 0, :].real.transpose(2, 0, 1)


def omission_images(scan, delay_us, phase_error_rad, uncorrected, zero_fill):
    """Change one step at a time, using the baseline fit and exactly the same raw echoes."""
    ny = int(scan["matrix_xy"][1])
    fraction = len(scan["ky_idx"]) / ny
    nominal = adc_trajectory(scan)
    delayed = adc_trajectory(scan, delay_us)
    # Keep the fitted delay displacement and the endpoints. Change only the
    # assumption about nominal sample spacing along each ramp-sampled echo.
    uniform = np.linspace(nominal[:, 0], nominal[:, -1], nominal.shape[1], axis=1)
    assume_uniform = uniform + (delayed - nominal)
    grid = cartesian_kx(scan)
    no_ramp = []
    for raw in scan["raw"]:
        corrected = correct_native(raw, scan["pol"], phase_error_rad)
        no_ramp.append(regrid(corrected, assume_uniform, grid, scan["ky_idx"], ny))
    return {
        "Nyquist ghost correction": _homodyne_volumes(uncorrected, fraction),
        "Ramp sampling correction": _homodyne_volumes(no_ramp, fraction),
        "Partial Fourier reconstruction": np.asarray(zero_fill),
    }


def _display_grid(scan):
    """Physical axes and a central readout view spanning the full phase-encode FOV."""
    matrix = scan["matrix_xy"]
    fov = 1000 * scan["fov_m"][:2]
    dx, dy = fov / matrix
    x, y = [(np.arange(n) - n // 2) * step for n, step in zip(matrix, [dx, dy])]
    extent = [x[0] - dx/2, x[-1] + dx/2, y[0] - dy/2, y[-1] + dy/2]
    half_width = min(fov) / 2
    center_x = (extent[0] + extent[1]) / 2
    return x, y, extent, [center_x - half_width, center_x + half_width]


def show_omissions(scan, complete, omitted):
    titles = ["Full reference", "All three steps", "Omit Nyquist ghost\ncorrection",
              "Omit ramp sampling\ncorrection", "Omit partial Fourier\nreconstruction"]
    reference = np.abs(scan["reference"])
    columns = [reference, complete, *omitted.values()]
    x, y, extent, x_view = _display_grid(scan)
    fig, axes = plt.subplots(2, len(columns), figsize=(12, 5.9), layout="constrained")
    signal, ghost = scan["signal_mask"], scan["ghost_mask"]
    for row, ref in enumerate(reference):
        limit = np.percentile(ref[signal], 98.5)
        for col, (title, images) in enumerate(zip(titles, columns)):
            ax = axes[row, col]
            mag = np.abs(images[row])
            ax.imshow(mag.T, origin="lower", extent=extent, vmin=0, vmax=limit,
                      interpolation="nearest", cmap="gray")
            ax.set(xlim=x_view, xticks=[], yticks=[])
            if row == 0:
                ax.set_title(title, fontsize=10)
            if col == 0:
                ax.contour(x, y, signal.T, [.5], colors=["#5dd2d3"], linewidths=.65)
                ax.contour(x, y, ghost.T, [.5], colors=["#ffb159"], linewidths=.65)
                ax.set_ylabel(f'b={scan["b_values"][row]:g}', fontweight="bold")
                ax.set_xlabel("Object (cyan) • Ghost (orange)", fontsize=8)
            else:
                nrmse = np.linalg.norm(mag - ref) / np.linalg.norm(ref)
                ratio = mag[ghost].mean() / mag[signal].mean()
                ax.set_xlabel(f"NRMSE {nrmse:.3f}\nGhost / signal {ratio:.1%}", fontsize=9)
    return fig


def show_omission_changes(scan, complete, omitted):
    """Compare magnitude changes and central readout profiles at both weightings."""
    reference = np.abs(scan["reference"])
    x, y, extent, x_view = _display_grid(scan)
    fig, axes = plt.subplots(2, 4, figsize=(12.3, 6), layout="constrained",
                             width_ratios=[1, 1, 1, 1.55])
    names = ["Nyquist ghost\ncorrection", "Ramp sampling\ncorrection",
             "Partial Fourier\nreconstruction"]
    max_change = 25
    for row, ref in enumerate(reference):
        full = np.abs(complete[row])
        window = np.percentile(ref[scan["signal_mask"]], 98.5)
        for col, (title, images) in enumerate(zip(names, omitted.values())):
            ax = axes[row, col]
            change = 100 * np.abs(np.abs(images[row]) - full) / window
            panel = ax.imshow(change.T, origin="lower", extent=extent, cmap="gray",
                              vmin=0, vmax=max_change, interpolation="nearest")
            ax.set(xlim=x_view, xticks=[], yticks=[])
            if row == 0:
                ax.set_title(f"Omit {title}", fontsize=10)
            if col == 0:
                ax.set_ylabel(f'b={scan["b_values"][row]:g}', fontweight="bold")
            if col == 1:
                ax.axhline(0, color="#72c4d1", lw=.7, ls="--")
        profile = axes[row, -1]
        mid = len(y) // 2
        curves = [(ref, "Reference", "#262626", "-"),
                  (full, "All steps", "#168097", "--"),
                  (np.abs(omitted["Ramp sampling correction"][row]),
                   "Omit ramp sampling correction", "#b45b27", "-")]
        for image, label, color, style in curves:
            profile.plot(x, image[:, mid], label=label, color=color, ls=style, lw=1.2)
        profile.set(xlim=x_view, ylabel="Magnitude (a.u.)")
        if row == 0:
            profile.set_title("Readout profile at y = 0 mm", fontsize=10)
            profile.legend(fontsize=7.5, frameon=False, handlelength=1.8,
                           loc="upper center")
        else:
            profile.set_xlabel("Readout x (mm)")
    bar = fig.colorbar(panel, ax=axes[:, :3], orientation="horizontal", shrink=.64,
                       aspect=30, extend="max", ticks=[0, 5, 10, 15, 20, 25])
    bar.set_label("Magnitude change from all three steps (% of row display window)")
    return fig


def reconstruct_adc_rois(scan, rois):
    """Reconstruct each series volume once and measure every requested ROI."""
    te = scan["series_te_ms"]
    b_values = scan["series_b"]
    raw = scan["series_raw"]
    rois = np.asarray(rois, dtype=bool)
    if rois.ndim != 3 or tuple(rois.shape[1:]) != tuple(scan["matrix_xy"]):
        raise ValueError("Supply a list of ROI masks on the reconstruction grid.")
    if np.any(rois.sum(axis=(1, 2)) == 0):
        raise ValueError("Each ROI must contain at least one voxel.")
    ny = int(scan["matrix_xy"][1])
    grid, rows = cartesian_kx(scan), scan["ky_idx"]
    acquired = np.isin(np.arange(ny), rows)
    fits = {}
    signals = np.empty((len(rois), len(raw)))
    for echo_time in np.unique(te):
        group = np.flatnonzero(te == echo_time)
        baseline, = group[b_values[group] == 0]
        delay, error = fit_b0(raw[baseline], scan)
        fits[float(echo_time)] = (delay, error)
        coords = adc_trajectory(scan, delay)
        for i in group:
            native = correct_native(raw[i], scan["pol"], error)
            kspace = regrid(native, coords, grid, rows, ny)
            image = np.abs(pocs(kspace, acquired))
            for row, roi in enumerate(rois):
                signals[row, i] = image[roi].mean()
    return fits, signals


def reconstruct_adc_roi(scan, roi=None):
    """Return the baseline fits and the reconstructed signal for one ROI."""
    if roi is None:
        roi = scan["adc_roi"]
    fits, signals = reconstruct_adc_rois(scan, [roi])
    return fits, signals[0]


def show_adc(scan, signal):
    """Plot directional fits for one compartment or for directional and isotropic ROIs."""
    b, te, direction = scan["series_b"], scan["series_te_ms"], scan["series_direction"]
    signals = np.atleast_2d(signal)
    definitions = [("Directional compartment", scan["adc_roi"], scan["adc_truth_xy"])]
    if len(signals) == 2:
        definitions.append(("Isotropic compartment", scan["adc_iso_roi"],
                            np.repeat(scan["adc_iso_truth"], 2)))
    if len(signals) != len(definitions):
        raise ValueError("Use the directional ROI alone or pass both expected ROI series.")
    fig, axes = plt.subplots(len(signals), 3, figsize=(10.7, 3.0 * len(signals)),
                             squeeze=False, layout="constrained")
    reference = np.abs(scan["reference"][0])
    x, y, extent, x_view = _display_grid(scan)
    for row_axes, signal_row, (title, roi, truth) in zip(axes, signals, definitions):
        ax = row_axes[0]
        ax.imshow(reference.T, origin="lower", extent=extent, cmap="gray", vmin=0,
                  vmax=np.percentile(reference, 99), interpolation="nearest")
        ax.contour(x, y, roi.T, [.5], colors=["#ffb159"], linewidths=1.5)
        ax.set(title=title, xlim=x_view, xticks=[], yticks=[])
        true_adc = 1000 * truth
        ax.set_xlabel(f"Model ADC (10⁻³ mm²/s)\nx {true_adc[0]:.2f}   •   y {true_adc[1]:.2f}")
        for ax, echo_time in zip(row_axes[1:], np.unique(te)):
            group = te == echo_time
            for name, color in [("x", "#196b86"), ("y", "#ad5921")]:
                mask = group & ((direction == name) | (b == 0))
                order = np.argsort(b[mask])
                weights = b[mask][order]
                log_signal = np.log(signal_row[mask][order])
                slope, intercept = np.polyfit(weights, log_signal, 1)
                ax.scatter(weights, log_signal, color=color, s=20)
                ax.plot(weights, intercept + weights * slope, color=color, lw=1.5,
                        label=f"{name}   {(-slope * 1000):.2f}")
            ax.set(title=f"TE {echo_time:g} ms", xlabel="b (s/mm²)", ylabel="ln(mean ROI magnitude)")
            ax.legend(title="ADC (10⁻³ mm²/s)", fontsize=8, title_fontsize=8, frameon=False)
    return fig
