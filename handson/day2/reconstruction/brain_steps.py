"""Leave-one-step-out reconstruction of a measured R=2 brain EPI/DWI slice."""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

import brain_dwi as scanner
from bart_io import bart


def keep_band(cartesian, retained):
    """Drop the high-ky edge before any interpolation between phase-encode lines."""
    return [np.where(retained[None, :, None], k, 0) for k in cartesian]


def show_measured_band(measured_rows, retained):
    """Mark the withheld edge in the same index convention as the scanner data."""
    fig, ax = plt.subplots(figsize=(9, 2.25), layout="constrained")
    grid = np.arange(len(retained))
    sampled = np.isin(grid, measured_rows)
    last = np.flatnonzero(retained)[-1]
    ax.axvspan(last + .5, len(grid) - .5, color="#f4dfca", zorder=0)
    for y, used in [(1, sampled), (0, sampled & retained)]:
        ax.scatter(grid[used], np.full(used.sum(), y), marker="|", s=180,
                   color="#196b86", linewidths=1.5)
    gaps = retained & ~sampled
    ax.scatter(grid[gaps], np.zeros(gaps.sum()), s=12, facecolors="none",
               edgecolors="#566060", label="Skipped within the retained band")
    ax.text((last + len(grid)) / 2, .49, "Withheld edge", ha="center", color="#7c401a")
    ax.set(xlim=(-1, len(grid)), ylim=(-.52, 1.5), yticks=[0, 1],
           yticklabels=["Omission exercise", "Original acquisition"],
           xlabel="Phase-encode line index", title="Phase-encode coverage in the real brain acquisition")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    return fig


def grappa_in_band(measured, acs, retained):
    """Fill interior odd rows from retained even neighbors using a separate ACS train."""
    rows = np.flatnonzero(retained)
    if rows.size <= len(retained)//2 or not np.array_equal(rows, np.arange(rows.size)) or rows[-1] % 2:
        raise ValueError("Use a contiguous low-ky band ending on a measured even row.")
    if any(np.any(k[:, ~retained]) for k in measured):
        raise ValueError("Withhold the upper edge with keep_band before fitting the missing interleaves.")
    targets = rows[1::2]
    weights = scanner.fit_grappa_weights(acs)
    return [scanner.grappa_fill(k, weights, targets) for k in measured]


def _bart_coil_array(volumes):
    # BART axes: readout, phase encode, slice, coil, volume.
    return np.stack(volumes, axis=-1)[:, :, None, :, :]


def _combine_coils(images):
    combined = bart(['rss', '8'], images)
    return combined[:, :, 0, 0, :].real.transpose(2, 0, 1)


def partial_fourier_rss(kspace, retained):
    """Use BART homodyne separately for each complex coil and volume; then coil RSS."""
    coils = bart(['homodyne', '-C', '1', str(retained.mean())], _bart_coil_array(kspace))
    return _combine_coils(coils)


def omit_one_step(brain, geom, readout_fit, retained, measured_band, grappa_band):
    """Reconstruct the same retained imaging data with one operation disabled at a time."""
    omitted = {}
    for name, settings in [('Nyquist ghost correction', {'ghost': False}),
                           ('Ramp sampling correction', {'ramp': False})]:
        # Readout interpolation and oversampling removal act independently on each ky.
        # Match ACS and image preprocessing before fitting the variant's GRAPPA weights.
        cartesian, acs = scanner.correct_and_regrid(brain, geom, readout_fit, **settings)
        band = keep_band(cartesian, retained)
        completed_band = grappa_in_band(band, acs, retained)
        omitted[name] = partial_fourier_rss(completed_band, retained)

    # Only even lines are present. Homodyne's weighted and low-resolution coil images
    # both repeat at half FOV. Their phase projection therefore preserves the fold.
    omitted['Parallel imaging reconstruction'] = partial_fourier_rss(measured_band, retained)
    # Leave the unmeasured edge at zero; the odd lines inside the band are GRAPPA values.
    coils = bart(['fft', '-iu', '3'], _bart_coil_array(grappa_band))
    omitted['Partial Fourier reconstruction'] = _combine_coils(coils)
    return omitted


def _name_rows(axes, b_values):
    for ax, b in zip(axes, b_values):
        ax.set_ylabel(f'b={b:g}', fontsize=11, weight='bold')


def show_omissions(reference, complete, omitted, b_values):
    """Matched magnitude displays and NRMSE against the original full-band R=2 reconstruction."""
    reference = np.asarray(reference)
    titles = ['Full-band\nreference', 'Combined\nreconstruction',
              'Omit Nyquist ghost\ncorrection', 'Omit ramp sampling\ncorrection',
              'Omit parallel imaging\nreconstruction', 'Omit partial Fourier\nreconstruction']
    sets = [reference, complete, *omitted.values()]
    fig, axes = plt.subplots(2,len(sets),figsize=(14.5,5.25),layout='constrained')
    for row, ref in enumerate(reference):
        window = np.percentile(ref,98.5)
        for col, (title, images) in enumerate(zip(titles, sets)):
            ax = axes[row, col]
            ax.imshow(images[row].T, cmap='gray', origin='lower', interpolation='nearest',
                      vmin=0, vmax=window)
            ax.set(xticks=[],yticks=[])
            if row==0:
                ax.set_title(title,fontsize=11)
            if col:
                difference = np.linalg.norm(images[row]-ref)/np.linalg.norm(ref)
                ax.set_xlabel(f'NRMSE {difference:.3f}', fontsize=9.5)
    _name_rows(axes[:,0],b_values)
    fig.suptitle('Real brain EPI/DWI  ·  one reconstruction step omitted', fontsize=15)
    return fig


def show_changes(reference, complete, omitted, b_values):
    """Absolute omission-minus-complete magnitude change, normalized to the shared window."""
    norm = Normalize(0, 15, clip=False)
    fig, axes = plt.subplots(2,4,figsize=(11.9,5.3),layout='constrained')
    titles = ['Nyquist ghost correction','Ramp sampling correction',
              'Parallel imaging reconstruction','Partial Fourier reconstruction']
    for row, ref in enumerate(reference):
        window = np.percentile(ref,98.5)
        for col, (title, images) in enumerate(zip(titles, omitted.values())):
            ax = axes[row,col]
            change = 100*np.abs(images[row]-complete[row])/window
            im = ax.imshow(change.T,cmap='magma',origin='lower',interpolation='nearest',norm=norm)
            ax.set(xticks=[],yticks=[])
            if row==0:
                ax.set_title(title,fontsize=11)
    _name_rows(axes[:,0],b_values)
    bar = fig.colorbar(im,ax=axes,shrink=.83,extend='max',ticks=[0,5,10,15])
    bar.set_label('Absolute change (% of row window)')
    fig.suptitle('Change in magnitude when each step is omitted',fontsize=15)
    return fig
