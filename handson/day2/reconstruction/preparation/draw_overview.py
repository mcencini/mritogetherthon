"""Draw the reconstruction overview used in the Day 2 workshop notebook."""

from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


def pipeline():
    """Readout corrections are shared; the acquisition mask selects a reconstruction."""
    fig, ax = plt.subplots(figsize=(14.0, 5.25), layout='constrained')
    ax.set(xlim=(0, 14.5), ylim=(0, 5.64))
    ax.axis('off')
    ink = '#162f3b'
    teal = '#126e74'
    routes = '#536c76'
    blue = '#dfeaf3'
    sand = '#f5e4d6'
    parallel_imaging = 'Parallel imaging reconstruction'
    partial_fourier = 'Partial Fourier reconstruction'

    def box(x, y, width, height, title, subtitle, fill):
        ax.add_patch(FancyBboxPatch((x, y), width, height,
                                    boxstyle='round,pad=0.012,rounding_size=0.09',
                                    facecolor=fill, edgecolor='none'))
        ax.text(x + .15, y + height*.66, title, color=ink, ha='left', va='center',
                fontsize=12, weight='semibold')
        ax.text(x + .15, y + height*.27, subtitle, color=ink, ha='left', va='center',
                fontsize=10.4)

    def arrow(start, end, color=routes):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', color=color,
                                     mutation_scale=13, linewidth=1.5, shrinkA=0, shrinkB=0))

    ax.text(.10, 5.47, 'From native EPI echoes to an image', color=ink,
            fontsize=16, va='center', weight='bold')
    ax.text(.12, 4.79, 'Readout correction', color=teal, weight='semibold', fontsize=11)
    box(.12, 3.21, 3.29, 1.04, 'Nyquist ghost correction',
        'Fit delay and even–odd phase error\nat b=0. Apply at every b-value.', '#cce6e5')
    arrow((1.76, 3.17), (1.76, 2.74), teal)
    box(.12, 1.62, 3.29, 1.05, 'Ramp sampling correction',
        'Interpolate the corrected echoes\nonto a uniform kₓ grid.', '#dceceb')

    ax.text(4.18, 4.79, 'Phase-encode sampling', color=routes, weight='semibold', fontsize=11)
    ax.text(7.11, 4.79, 'Reconstruction', color=routes, weight='semibold', fontsize=11)
    centers = [4.09, 2.97, 1.85, .60]
    bus_x = 3.76
    ax.plot([3.43, bus_x], [2.15, 2.15], color=routes, lw=1.4)
    ax.plot([bus_x, bus_x], [centers[-1], centers[0]], color=routes, lw=1.4)
    patterns = ['Complete coverage', 'Skipped interleaves', 'Missing edge band',
                'Skipped interleaves\nand missing edge band']
    for y, pattern in zip(centers, patterns):
        arrow((bus_x, y), (4.03, y))
        ax.text(4.18, y, pattern, ha='left', va='center', fontsize=12, color=ink,
                linespacing=1.2)
        arrow((6.55, y), (7.02, y))

    h = .88
    box(7.11, centers[0]-h/2, 7.26, h, 'Inverse Fourier transform',
        'Apply along the readout and phase-encode axes.', '#eef1f1')
    box(7.11, centers[1]-h/2, 7.26, h, parallel_imaging,
        'Use receive-coil encoding to unfold the image.', blue)
    box(7.11, centers[2]-h/2, 7.26, h, partial_fourier,
        'Estimate image phase from central data in this volume.', sand)

    box(7.11, centers[3]-h/2, 3.41, h, parallel_imaging,
        'Fill skipped lines in the acquired band.', blue)
    arrow((10.55, centers[3]), (10.83, centers[3]))
    box(10.89, centers[3]-h/2, 3.48, h, partial_fourier,
        'Reconstruct the missing edge.', sand)
    return fig

if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'figures' / 'pipeline.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    fig = pipeline()
    fig.savefig(output, dpi=145, bbox_inches='tight', pad_inches=.13, facecolor='white')
    plt.close(fig)
