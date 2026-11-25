"""Plotting for the MRI Together EPI practical."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

def _image(ax, a, title, vmax):
    ax.imshow(np.abs(a).T, origin='lower', cmap='gray', vmin=0, vmax=vmax, interpolation='nearest')
    ax.set(title=title, xticks=[], yticks=[])

def _limit(a):
    a = np.abs(a)
    return .82 * a.max()

def _phantom_detail(ax, shape):
    # Square physical pixels in this acquisition. Keep the complete phase FOV.
    nx, ny = shape[:2]
    if nx > ny:
        left = (nx - ny) // 2 - .5
        ax.set_xlim(left, left + ny)


def show_phantom_reference(scan):
    """Show the phantom in its full physical FOV on one magnitude scale."""
    refs = np.abs(scan['reference'])
    fov = 1000 * scan['fov_m']
    spacing = fov / scan['matrix_xy']
    # Center pixel floor(N/2) has physical coordinate 0.
    left, bottom = -fov/2 - spacing/2
    extent = [left, left + fov[0], bottom, bottom + fov[1]]
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.1), layout='constrained')
    for ax, ref, b in zip(axes, refs, scan['b_values']):
        im = ax.imshow(ref.T, origin='lower', extent=extent, interpolation='nearest',
                       cmap='gray', vmin=0, vmax=_limit(refs[0]))
        ax.set(title=f'b={b:g} s/mm²', xlabel='Readout x (mm)')
    axes[0].set_ylabel('Phase encode y (mm)')
    fig.colorbar(im, ax=axes, shrink=.85, label='Magnitude (a.u.)')
    return fig

def show_correction(before, after, data):
    fig, axes = plt.subplots(2, 3, figsize=(9.8, 4.9), layout='constrained')
    fig.suptitle('Nyquist ghost correction of zero-filled EPI images', fontsize=14)
    for v in (0,1):
        reference = np.abs(data['reference'][v])
        lim = _limit(reference)
        for j, (image,title) in enumerate([(before[v], 'Without correction'), (after[v], 'With correction')]):
            _image(axes[v,j], image, title if v==0 else '', lim)
            ratio = np.abs(image)[data['ghost_mask']].mean()/np.abs(image)[data['signal_mask']].mean()
            error = np.linalg.norm(np.abs(image) - reference) / np.linalg.norm(reference)
            axes[v,j].set_xlabel(f'Ghost-to-signal {100*ratio:.1f}%\nMagnitude NRMSE {error:.3f}')
        axes[v,0].set_ylabel(f'b={data["b_values"][v]:g} image')
        _image(axes[v,2], data['reference'][v], 'Regions on reference' if v==0 else '', lim)
        for mask,color in [(data['signal_mask'],'#5dd2d3'), (data['ghost_mask'],'#ffb159')]:
            axes[v,2].contour(mask.T, levels=[.5], colors=[color], linewidths=.9)
        axes[v,2].set_xlabel('Object (cyan)\nGhost (orange)')
        for ax in axes[v]:
            _phantom_detail(ax, reference.shape)
    plt.show()

def show_partial(zero, homodyne, pocs_result, data):
    fig, axes = plt.subplots(2,4,figsize=(11.7,4.25),layout='constrained')
    fig.suptitle('Partial Fourier reconstruction at each diffusion weighting', fontsize=14)
    for v in (0,1):
        ref = np.abs(data['reference'][v])
        for j,(col,title) in enumerate([(zero,'Zero fill'),(homodyne,'BART homodyne'),
                                        (pocs_result,'POCS · 24 iterations'),(data['reference'],'Full reference')]):
            im = np.abs(col[v])
            _image(axes[v,j], im, title if v==0 else '', _limit(ref))
            if j < 3:
                axes[v,j].set_xlabel(f'Magnitude NRMSE {np.linalg.norm(im-ref)/np.linalg.norm(ref):.3f}')
            _phantom_detail(axes[v,j], ref.shape)
        axes[v,0].set_ylabel(f'b={data["b_values"][v]:g} image')
    plt.show()

def show_siemens(before, after):
    fig, axes = plt.subplots(1,2,figsize=(6.9,3.6),layout='constrained')
    fig.suptitle('Navigator-based Nyquist ghost correction', fontsize=14)
    limit = np.percentile(after,97)
    for ax,im,title in zip(axes,[before,after],['Without navigator fit','With navigator fit']):
        _image(ax,im,title,limit)
        ax.add_patch(Rectangle((-.5,-.5),12,16,fill=False,edgecolor='#ffb159',lw=1))
        corner = im[:12,:16].mean()/limit
        ax.set_xlabel(f'Box mean / display limit = {100*corner:.1f}%')
    plt.show()

def show_shots(shots, rsos):
    fig, axes = plt.subplots(1,3,figsize=(8.9,3.2),layout='constrained')
    fig.suptitle('Parallel imaging reconstruction of each diffusion shot', fontsize=14)
    vmax = np.percentile(np.abs(shots),99.5)
    for ax,im,title in zip(axes, [shots[0],shots[1],rsos],
                           ['Shot 1','Shot 2','rSOS across shots']):
        _image(ax, im, title, vmax*np.sqrt(len(shots)) if ax is axes[-1] else vmax)
        _phantom_detail(ax, im.shape)
    plt.show()


def show_phase_transfer(phases, own_image, borrowed_image, scan):
    """Hold the higher-b data fixed and change only the phase used by POCS."""
    fig, axes = plt.subplots(1, 4, figsize=(11.6, 2.7), layout='constrained')
    roi = scan['object_mask']
    for ax, phase, b in zip(axes[:2], phases, scan['b_values']):
        values = np.ma.masked_where(~roi, np.angle(phase))
        color = ax.imshow(values.T, origin='lower', cmap='twilight', vmin=-np.pi, vmax=np.pi)
        ax.set(title=f'Image phase at b={b:g}', xticks=[], yticks=[])
        _phantom_detail(ax, roi.shape)
    bar = fig.colorbar(color, ax=axes[:2], orientation='horizontal', shrink=.55,
                       aspect=32, ticks=[-np.pi, 0, np.pi])
    bar.set_ticklabels(['−π', '0', 'π'])
    bar.set_label('Estimated phase (rad)')
    truth = np.abs(scan['reference'][1])
    for ax, image, title in zip(axes[2:], (own_image, borrowed_image),
                                ('Use higher-b image phase', 'Reuse b=0 image phase')):
        _image(ax, image, title, _limit(truth))
        _phantom_detail(ax, truth.shape)
        error = np.linalg.norm(np.abs(image) - truth) / np.linalg.norm(truth)
        ax.set_xlabel(f'Magnitude NRMSE {error:.3f}')
    return fig


def show_slice_phase(check):
    """Use the central echo and the on-isocenter point as a common reference."""
    supplied = check[check['case'] == 'supplied']
    extra, = check[check['case'] == 'shifted']
    fig, (ax, phasor) = plt.subplots(1, 2, figsize=(9, 3.2), layout='constrained',
                                     width_ratios=(1.6, 1))
    ax.axhline(0, color='.8', lw=.8)
    for rows, color in ((supplied, '#196b86'), (np.atleast_1d(extra), '#ad5921')):
        ax.scatter(rows['z_mm'], rows['predicted_deg'], s=76, marker='o',
                   facecolors='none', edgecolors=color)
        ax.scatter(rows['z_mm'], rows['simulated_deg'], s=36, marker='+', color=color)
    ax.scatter([], [], s=76, marker='o', facecolors='none', edgecolors='.25', label='Prediction')
    ax.scatter([], [], s=36, marker='+', color='.25', label='KomaMRI')
    ax.annotate('Additional test position', (extra['z_mm'], extra['simulated_deg']),
                xytext=(0, 12), textcoords='offset points', ha='center', color='#974919')
    ax.set(title='RF phase adjustments on versus off', xlabel='Slice center z (mm)',
           ylabel='Echo rotation (degrees)', yticks=[-120, -60, 0], ylim=(-146, 24))
    ax.legend(loc='center right', frameon=False, fontsize=9)
    angles = np.linspace(0, 2 * np.pi, 150)
    phasor.plot(np.cos(angles), np.sin(angles), color='.85', lw=1)
    for key, name, color in [('phase_off_vs_center_deg', 'Off', '#196b86'),
                             ('phase_on_vs_center_deg', 'On', '#ad5921')]:
        angle = np.deg2rad(extra[key])
        x, y = np.cos(angle), np.sin(angle)
        phasor.annotate('', (x, y), (0, 0), arrowprops={'arrowstyle':'->', 'lw':2.4, 'color':color})
        phasor.text(1.14*x, 1.14*y, name, color=color, ha='center', va='center')
    phasor.set(title='Complex echo at the test position', aspect='equal',
               xlim=(-1.28, 1.32), ylim=(-1.27, 1.13), xticks=[], yticks=[],
               xlabel='Angles relative to the isocenter echo')
    return fig
