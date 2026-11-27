"""
Hands-on workshop: diffusion-weighted spin-echo EPI with pypulseq  --  LEVEL 2 (advanced)
========================================================================================

One slice of the sequence (blocks in time order):

|  90°  |gzr| nav +-+ |  diff 1  | delayTE1 |cr| 180° |cr|  diff 2  | delayTE2 |pre|  EPI echo train (blips) ........  |
    ^                                              ^                                              ^
    |<------------------- TE/2 ------------------->|<------------------- TE/2 ------------------->|
  center of 90°                              center of 180°                              echo (ky = 0)

Level 2 gives you per STEP only
    IDEA      what the step has to achieve and why
    drawings  the ASCII drawings are your main help: read the numbers and relations off them
and then YOUR TASK in a box, directly above the TODO line that you replace with your code:

    ╔═══ TODO 3  (your code) ═══
    ║  SPEC     the parameters to use (so that check_seq.py and the recon accept your sequence)
    ║  USEFUL   pypulseq functions that do the job
    ║  PROVIDE  the variable names that later steps (and the given STEP 12) use
    ╚═══════════════════════════

Work in 4 milestones (MILESTONE at the bottom). Steps of later milestones are skipped automatically:
    1  spin-echo EPI (RF, readout, partial Fourier, crushers, TE)     2  + diffusion (exact b-value)
    3  + navigator echoes                                             4  + multi-slice
Each run writes tools/export/my_dwepi_M<milestone>.seq and checks it automatically (PASS / FAIL + hint).
SIMULATE = True at the very bottom simulates and reconstructs the image (MRzero).
Need more help for a step? The same step in level1_beginner.py has the formulas and smaller gaps.

Units (pypulseq works in SI units, gradients already multiplied by gamma):
    time s,  length m,  frequency Hz,  gradient amplitude Hz/m,  slew rate Hz/m/s,
    gradient area = k-space position 1/m.     mT/m = (Hz/m) / gamma * 1e3,  gamma = 42.576e6 Hz/T
"""

import tools.workshop_env  # noqa: F401  (first start: sets everything up; always runs in the workshop Python)

import sys
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pypulseq as pp
from pypulseq.make_sigpy_pulse import sigpy_n_seq  # noqa: F401  (SLR pulse, STEP 2)

from tools.check_seq import run_check
from tools.rf_profile import compare_ref_profiles, show_or_save  # noqa: F401

EXPORT = Path(__file__).resolve().parent / 'tools' / 'export'      # your .seq files (and the plots without a display)


def TODO(task):
    """Placeholder for code you still have to write."""
    raise NotImplementedError(f'TODO {task} is not done yet -> search for "TODO {task}" in this file')

def main(
    plot: bool = True,
    test_report: bool = False,
    write_seq: bool = True,
    seq_filename: str = 'my_dwepi.seq',
    *,
    # ---- geometry ----
    fov: float | tuple[float, float] = (240e-3, 120e-3),   # (fov_x, fov_y) or one value for a square FOV [m]
    n_x: int = 128,
    n_y: int = 64,
    slice_thickness: float = 3e-3,                       # [m]
    n_slices: int = 5,
    slice_gap_factor: float = 3,                         # center-to-center distance in units of the slice thickness
    # ---- contrast / timing ----
    te: float = 47e-3,                                   # [s]
    tr: float = 8.0,                                     # [s], for all slices together
    n_reps: int = 1,
    b_value: float = 500,                                # [s/mm^2], 0 = no diffusion weighting
    diff_axis: str | tuple[float, float, float] = 'x',   # 'x', 'y', 'z' or a vector, e.g. (1, 1, 0)
    # ---- EPI readout ----
    ramp_sampling: float = 30,                           # [%] of the ADC window on the RO ramps, 0 = flat top only
    part_fourier: float = 0.75,                          # fraction of PE lines measured, e.g. 0.75 = 6/8
    n_nav: int = 3,                                      # navigator echoes after the excitation, 0 = none
):
    # ======================================================================================
    # STEP 1: system limits
    # ======================================================================================
    # Gradient/RF limits of the scanner. pypulseq checks every event against these values.
    # Use values slightly below the real hardware limits.
    #
    #   max_grad   maximum gradient amplitude per axis          (internally converted to Hz/m)
    #   max_slew   maximum slew rate per axis                   (internally converted to Hz/m/s)
    #   rf_dead_time / rf_ringdown_time: the RF amplifier needs time before and after a pulse,
    #   pypulseq adds them automatically as RF delay and as extra block duration:
    #
    #       block   |<----------------------- duration ------------------------->|
    #       RF      | dead time |~~~~~~~~~~~ RF pulse ~~~~~~~~~~~| ringdown time |
    #               |  100 us   |                                |     100 us    |
    #
    # Raster times (defaults): gradients 10 us, RF 1 us, ADC 100 ns, blocks 10 us.
    # Every gradient timing (ramps, flat top, delays) must be a multiple of the gradient raster.
    system = pp.Opts(
        max_grad=90,
        grad_unit='mT/m',
        max_slew=130,
        slew_unit='T/m/s',
        rf_ringdown_time=100e-6,
        rf_dead_time=100e-6,
    )
    seq = pp.Sequence(system)
    rast = system.grad_raster_time          # 10 us

    # pypulseq in one picture: EVENTS and BLOCKS
    #     A sequence is a list of blocks, played one after the other without gaps.
    #     A block holds events: at most one RF, one gradient per axis (gx, gy, gz), one ADC, labels.
    #     All events of a block start at the block start (+ their own .delay), and the block lasts
    #     as long as its longest event (pp.calc_duration(e1, e2, ...) tells you how long):
    #
    #                    block 1                        block 2                    block 3
    #            |<--------------------->|<------------------------------------->|<---------->|
    #       RF   |   /\/\/\/\/\/\/\/\    |                                       |            |
    #       Gz   |  _________________    |                                       |            |
    #            | /                 \   |                                       |            |
    #       Gx   |                       |    ________________________________   |            |
    #            |                       |   /                                \  |            |
    #       ADC  |                       |       | | | | | | | | | | | | | |     |            |
    #            |                       |<----->|                               |            |
    #            |                       | adc.delay                             |            |
    #
    #       seq.add_block(rf, gz)         seq.add_block(gx, adc)                  seq.add_block(pp.make_delay(d))
    #
    #     Everything you create with pp.make_*(..., system=system) is checked against the limits above.


    # ======================================================================================
    # STEP 2: RF pulses                                                      (milestone 1)
    # ======================================================================================
    # IDEA  A slice-selective 90° (sinc, small-tip: profile ~ Fourier transform of the pulse) and a 180°.
    #       The slice-select gradient turns frequency into position, G = bandwidth / thickness. After the
    #       90°, the 2nd half of gz has dephased the spins: a rephaser with -1/2 of the gz area undoes it.
    #       For the 180°, build BOTH a sinc and an SLR pulse (same duration and TBW) and compare their
    #       slice profiles and peak B1: why does almost everybody use SLR for refocusing, and what does it
    #       cost? Then play with duration and TBW: why can you not make the pulses arbitrarily short with a
    #       high bandwidth?
    #
    #       RF
    #                                       _________
    #                                      /         \
    #                                     /           \
    #                                    /             \
    #                                   /   main lobe   \
    #                                  /                 \
    #                                 /                   \
    #                                /                     \
    #       _____________           /                       \           _____________
    #                    \_________/                         \_________/
    #                   side lobe (negative)                side lobe (negative)
    #
    #                   |<---------------- RF duration ---------------->|
    #
    #       gz          ________________________________________________
    #                  /                        ^                       \
    #                 /                   pulse center                   \
    #       _________/                                                    \                            ______
    #                                                                      \                          /
    #                                                                       \                        /
    #                                                                        \______________________/
    #
    #                                                                      gzr: area = -1/2 x area of gz
    #                                                                            (slice rephaser)
    #
    #       The refocused slice is made wider than the excited one (weaker gz, same bandwidth), so the
    #       edges of the excited slice are fully refocused:
    #
    #       refocused (180°)      __________________
    #                            |                  |
    #       excited (90°)        |    __________    |
    #                            |   |          |   |
    #       _____________________|___|__________|___|______________   z

    # ╔═══ TODO 2  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    durations, TBW, apodization, refocused slice width: your choice.
    # ║          use='excitation' / use='refocusing', 180° with phase_offset pi/2 (CPMG),
    # ║          peak B1 <= 20 uT (print it), slice gradients <= max_grad.
    # ║  USEFUL  pp.make_sinc_pulse(..., return_gz=True)
    # ║          sigpy_n_seq(..., return_gz=True, pulse_cfg=pp.SigpyPulseOpts(pulse_type='slr', ptype='se'), plot=False)
    # ║          pp.scale_grad,  rf.signal (Hz),  system.gamma
    # ║          compare_ref_profiles((rfexc, gz_ex, gzr_ex), [(rf1, gz1, 'sinc 180°'), (rf2, gz2, 'SLR 180°')],
    # ║                               system=system, slice_thickness=slice_thickness)
    # ║                   -> RF shapes with peak B1, excitation vs. refocusing profile, spin-echo profile
    # ║  PROVIDE rfexc, gz_ex, gzr_ex, rfref, gz_ref
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('2')


    # ======================================================================================
    # STEP 3: EPI readout (bipolar, continuous, ramp sampling)               (milestone 1)
    # ======================================================================================
    # IDEA  All k-space lines after ONE excitation: the readout gradient alternates its sign, a small
    #       phase-encoding blip moves ky by one line between two lines. Lines follow each other without gaps.
    #
    #       ky
    #        ^     ---------------------->      line 0   (ro, +)
    #        |                            |     blip
    #        |     <----------------------      line 1   (roNeg, -)
    #        |     |                            blip
    #        |     ---------------------->      line 2   (ro, +)
    #        |                            |
    #        |                 ...
    #        +-------------------------------> kx
    #
    #       delta k = 1 / FOV,  one line covers N / FOV.


    # 3a) Blip: area 1/fovY, as short as possible (it has to fit on the RO ramps):
    #
    #
    #                                         peak amplitude  G = S * T/2
    #                    /\                   area            A = 1/2 * T * G = S * T^2 / 4
    #                   /  \
    #                  /    \                 ->   T = 2 * sqrt(A / S)
    #                 /      \
    #       _________/        \__________
    #                |<- T -->|


    # 3b) Readout with ramp sampling: the ADC window is longer than the flat top, its ends lie on the
    #     ramps. The k-space area covered INSIDE the ADC window must be n_x / fovX. Derive the amplitude
    #     from the drawing (area of the flat top + area of the sampled ramp parts).
    #
    #                                                       v center of ro = rise + flat/2 = center of the ADC window
    #       G                             ____________________________________                        T = roDur  = ADC window = F + 2 s
    #                                    /                  :                 \                       F = roFlat = flat top
    #                                   /                   :                  \                      s = sRamp  = sampled part of ONE ramp
    #                                  /     flat top F     :                   \                     : = start / end of the ADC
    #                                 /      G constant,    :                    \
    #       ramp:                    /   kx step = delta kx :                     \                   1 column = 10 us, 1 row = 1.3 mT/m,
    #       G smaller,              /                       :                      \                  a 45° line = max slew rate
    #       kx steps               /                        :                       \
    #       smaller               /                         :                        \
    #                            /:                         :                         \
    #                           / :                         :                         :\
    #                          /  :                         :                         : \
    #                         /   :                         :                         :  \
    #                        /    :                         :                         :   \
    #                       /     :                         :                         :    \
    #                      /      :                         :                         :     \
    #                     /       :                         :                         :      \
    #                    /        :                         :                         :       \
    #                   /         :                         :                         :        \
    #                  /          :                         :                         :         \
    #       __________/           :                         :                         :          \__________
    #       ADC                    | | | | | | | | | | | | | | | | | | | | | | | | | |                samples evenly spaced in time (dwell)
    #                             |<--s-->|<--------------- F --------------->|<--s-->|
    #                             |<- T = ADC window roDur = adcSamples x adcDwell -->|
    #                 |<----- rise ------>|                                   |<----- rise ------>|
    #                 | adc.delay |
    #                 |<---------- rise + flat/2 ---------->|


    # 3c) ADC: Nyquist on the flat top (sample distance in k <= 1/fovX), centered on the RO trapezoid.
    #
    #     kx positions of the samples of ONE line (equal time steps, but G changes on the ramps):
    #
    #       -kx,max                                   kx = 0                                    +kx,max
    #          | |  |  |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |  |  | |
    #          |<- ramp ->|<------------- flat top: step = dwell * G <= 1/FOVx ------------->|<- ramp ->|
    #           steps grow                                                               steps shrink
    #
    #     after regridding in the recon: n_x points, exactly 1/FOVx apart
    #          |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |


    # 3d) Blips on the RO ramps: a block holds only what starts in it, so the blip is split at its center.
    #
    #                       block i (ro)                      block i+1 (roNeg)
    #                                               :
    #       RO  __________________________          :
    #                                     \         :
    #                                      \        :  <- ADC on: sampled part of the ramp (80 us)
    #                                       \       :
    #                                        \      :
    #                                         \     :
    #                                          \    :
    #                                           \   :  <- ADC off: unsampled part (120 us)
    #                                            \  :
    #                                             \ :
    #           .  .  .  .  .  .  .  .  .          \:           .  .  .  .  .  .  .  .  . 0
    #                                               \
    #                                               :\
    #           ADC off: unsampled part ->          : \
    #                                               :  \
    #                                               :   \
    #                                               :    \
    #                                               :     \
    #           ADC on: sampled part ->             :      \
    #                                               :       \
    #                                               :        \__________________________
    #                                               :
    #                                               :
    #                                        byUp     byDown
    #       PE  __________________________________    ____________________________________
    #                                             \  /
    #                                              \/
    #
    #       ADC      | | | | | | | | | | | | |             | | | | | | | | | | | | |
    #                                         |< ADC off >|
    #                                             |<>| <- blip (80 us), centered on the zero crossing

    # ╔═══ TODO 3  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    readout bandwidth: your choice. EPI typically uses ~1000 - 2500 Hz/pixel (BW/px ~ 1 / ADC
    # ║          window of one line): short lines -> short echo spacing, but stronger gradients, less SNR.
    # ║          ramp_sampling % of the ADC window on the ramps, ADC samples a multiple
    # ║          of 4, dwell a multiple of 100 ns, adc.delay on 1 us, all gradient times on the 10 us raster.
    # ║          Blip area NEGATIVE (we walk from +ky downwards). The ADC must be OFF during the blip.
    # ║  USEFUL  pp.make_trapezoid(channel, area=, duration=) / (channel, amplitude=, rise_time=, flat_time=)
    # ║          pp.make_adc(num_samples=, dwell=),  pp.scale_grad,  pp.calc_duration
    # ║          pp.split_gradient_at(grad, time_point),  pp.align(left=..., right=...),  pp.add_gradients
    # ║  PROVIDE roDur (ADC window of one line), xBlip, yBlip (delta k), ro, roNeg, dRO (duration of one
    # ║          line), adc, byUp, byDown, byDownUp
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    fovX, fovY = (fov, fov) if np.isscalar(fov) else fov
    TODO('3')


    # ======================================================================================
    # STEP 4: phase encoding / partial Fourier                               (milestone 1)
    # ======================================================================================
    # IDEA  k-space is acquired from top to bottom. Partial Fourier skips lines BEFORE ky = 0, so the
    #       echo comes earlier (shorter TE). A prephaser moves k from the center to the start of line 0.
    #
    #       ky [lines]
    #       +n_y/2 - 1   . . . . . . . . . .     not measured
    #                    . . . . . . . . . .
    #       +nYpre       ===================     1st measured line  <- the prephaser goes here
    #                    ===================
    #        0           ===================     k-space center = echo at TE
    #                    ===================
    #       -n_y/2       ===================     last line
    #
    #                                                                                                       k-space path of the gradients on the left:
    #       Gx                            :         __________________          :
    #                                     :        /                  \         :                           ky = +nYpre * delta ky
    #                                     :       /                    \        :                             *-------------------------------------------------------> line 0 (ro)
    #                                     :      /                      \       :                             ^    o                                                  | blip
    #                                     :     /                        \      :                      byPre  |        o                               ... <----------+ line 1 (roNeg)
    #                                     :    /                          \     :                             |             o
    #                                     :   /         line 0 (ro)        \    :                             |                  o
    #                                     :  /                              \   :                             |                      o      roPre + byPre (same block)
    #                                     : /                                \  :                             <---------------------------x
    #                                     :/                                  \ :                            roPre                      k = 0
    #       ______                        /                                    \:                          kx = -kx,max
    #             \                      /:                                     \
    #              \                    / :                                     :\
    #               \                  /  :                                     : \
    #                \                /   :                                     :  \        line 1 (roNeg)
    #                 \     roPre    /    :                                     :   \
    #                  \            /     :                                     :    \
    #                   \          /      :                                     :     \
    #                    \        /       :                                     :      \
    #                     \      /        :                                     :       \
    #                      \    /         :                                     :        \ ...
    #                       \  /          :                                     :
    #                        \/           :                                     :
    #                                     :                                     :
    #                                     :                                     :
    #                                     :                                     :
    #       Gy        ________________    :                                     :
    #                /                \   :                                     :
    #               /       byPre      \  :                                     :
    #              /                    \ :                                     :
    #       ______/                      \____________________________________  : ____________
    #                                     :                                   \ :/  blip, centered on the zero crossing of Gx
    #                                     :                                    \/
    #
    #       ADC                                  | | | | | | | | | | | | |             | |
    #             |<-------- pre -------->|<------------- line 0 -------------->|
    #             ONE block: roPre and byPre end together

    # ╔═══ TODO 4  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    measured lines round(part_fourier * n_y), of which n_y/2 + 1 from ky = 0 downwards.
    # ║          Clear error if part_fourier is too small.
    # ║  USEFUL  pp.make_trapezoid(channel, area=) (shortest),  pp.align(right=...),  pp.calc_duration
    # ║  PROVIDE nYmeas (lines per shot), nYpre (lines before ky = 0), prePhasers (list of gradients, one block)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('4')


    # ======================================================================================
    # STEP 5: navigators                                                     (milestone 3)
    # ======================================================================================
    # IDEA  Lines with + and - readout polarity are slightly shifted against each other (eddy currents,
    #       gradient delays) -> N/2 ghost. Navigators = lines at ky = 0 (no blips) with alternating polarity;
    #       the recon compares them and corrects the image lines. They fit into the idle time before the 180°.
    #
    #       Gx                 ______________                              ______________
    #                         /              \                            /              \
    #                        /                \                          /                \
    #                       /                  \                        /                  \
    #       __             /                    \                      /                    \             _____
    #         \           /                      \                    /                      \           /
    #          \         /                        \                  /                        \         /
    #           \       /                          \                /                          \       /
    #            \_____/                            \______________/                            \_____/
    #
    #       ADC              ||||||||||||||||||    ||||||||||||||||||    ||||||||||||||||||
    #          navPre               nav +                 nav -                 nav +           navRew
    #
    #       kx path (here nNav = 3), ky stays 0 the whole time:
    #
    #                    -kx,max                      0                      +kx,max
    #                       :                         :                         :
    #       navPre          <-------------------------x                         :     start at k = 0
    #       nav 0  (ro)     |-------------------------------------------------->|
    #       nav 1  (roNeg)  |<--------------------------------------------------|
    #       nav 2  (ro)     |-------------------------------------------------->|     kxNavEnd
    #       navRew          :                         x<------------------------|     back to k = 0
    #
    #       every line moves kx by +ro.area (ro) or -ro.area (roNeg); navPre by -ro.area/2
    #
    #       kx must be back at 0 before the 180° (it mirrors k, see STEP 6).

    # ╔═══ TODO 5  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    nNav lines, same ro/roNeg/adc as the echo train, directly after the slice rephaser.
    # ║          Must work for odd AND even nNav.
    # ║  USEFUL  pp.make_trapezoid(channel, area=),  ro.area,  pp.calc_duration
    # ║  PROVIDE navPre, navRew, dNav (total duration navPre + lines + navRew)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    nNav = n_nav
    dNav = 0
    if nNav > 0:
        TODO('5')


    # ======================================================================================
    # STEP 6: crushers around the refocusing pulse                           (milestone 1)
    # ======================================================================================
    # IDEA  The 180° also creates its own FID and leaves unrefocused signal. Equal crushers on both sides
    #       keep only the spin-echo path. The rule behind it (needed again in STEP 5 and 9): k -> -k.
    #
    #       RF                            180°
    #                                     _____
    #                                    /     \
    #                                   /       \
    #                                  /         \
    #       __________________        /           \        ________________________
    #                         \______/             \______/
    #
    #       Gz   ________                                       ________
    #           /        \    _____________________________    /        \
    #          /          \  /                             \  /          \
    #       __/            \/                               \/            \________
    #              cr                    gz_ref                    cr
    #
    #   refocused echo:   phase +phi (cr 1) -> inverted by the 180° (-phi) -> +phi (cr 2) = 0   -> survives
    #   FID of the 180°:  sees only cr 2                                     -> phase phi       -> dephased
    #
    #        k ^
    #       +A |          ____________________                    __________   FID of the 180°: sees only cr 2
    #          |         /                    :                  /             -> ends at +A -> dephased
    #          |        /                     :                 /
    #        0 |________                      :. . . . . . . . .  /_________   spin echo: -A + A = 0 -> refocused
    #          |                              :                  /
    #          |                              :                 /
    #       -A |                              :_________________
    #          +-------------------------------------------------------------> t
    #                   cr 1                 180°           cr 2
    #                                    (k jumps to -k)

    # ╔═══ TODO 6  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    area: your choice -- an area A [1/m] winds the phase by A * slice_thickness cycles across
    # ║          the slice; a few cycles are enough. On 'z', shortest waveform.
    # ║  USEFUL  pp.make_trapezoid(channel, area=)
    # ║  PROVIDE cr
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('6')


    # ======================================================================================
    # STEP 7: slice positions (multi-slice, interleaved)                     (milestone 4)
    # ======================================================================================
    # IDEA  Neighbouring slices overlap a little (non-rectangular profiles): acquire them interleaved.
    #
    #       z          -2d      -d       0       +d      +2d
    #                 |###|    |###|   |###|    |###|    |###|      ### = slice_thickness
    #       index       0        1       2        3        4        (spatial order, used as label SLC)
    #       acquired   1st      4th     2nd      5th      3rd       sliceOrder = [0, 2, 4, 1, 3]

    # ╔═══ TODO 7  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    center-to-center distance slice_gap_factor * slice_thickness, slice n_slices // 2 at z = 0,
    # ║          order: all even spatial indices, then all odd ones. Must also work for n_slices = 1.
    # ║  PROVIDE slicePos (array, spatial order) [m], sliceOrder (list of spatial indices)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    slicePos, sliceOrder = np.zeros(1), [0]              # milestones 1-3: one slice at the isocenter
    if n_slices > 1:
        TODO('7')


    # ======================================================================================
    # STEP 8: TE timing                                                      (milestone 1)
    # ======================================================================================
    # IDEA  Spin echo: 180° center at TE/2, k-space center (kx = ky = 0) at TE, both from the 90° center.
    #       First compute both halves WITHOUT diffusion gradients and fill delays -> minimal TE.
    #
    #   |  exc  | gzr |   nav   |  diff 1  |  delayTE1 | cr |  ref  | cr |  diff 2  |delayTE2| pre |  nYpre lines  |  line nYpre | ...
    #       ^                                                   ^                                                   ^
    #       |<--------------------- TE/2 ---------------------->|<--------------------- TE/2 ---------------------->|
    #   90° center                                       180° center                                        echo (ky = 0)
    #
    #   Zoom 1: where is the pulse center inside its block?
    #
    #       exc block                                   ref block
    #       |<-------------- dExc ------------->|       |<------------------- dRef ------------------->|
    #       | rf.delay |/\/\/\/\/^\/\/\/\/\|    |       | rf.delay  |/\/\/\/\/\/\/^\/\/\/\/\/\/\|      |
    #       |<-------- tExc ---->|              |       |<---------- tRef ------->|                    |
    #       |                    |<------------>|       |                         |<------------------>|
    #                              dExc - tExc                                         dRef - tRef
    #
    #       tExc = rf.delay + pp.calc_rf_center(rf)[0]       (rf.delay: dead time or the gz ramp-up)
    #       Only the part of the exc block AFTER the center counts for TE/2, and only the part of the
    #       ref block BEFORE its center (and vice versa for the 2nd half).
    #
    #   Zoom 2: where is the echo inside the echo train?
    #
    #       |    pre    | line 0 | line 1 | ... | line nYpre-1 |      line nYpre      | line nYpre+1 | ...
    #       |<- dPre -->|<-------------- nYpre * dRO -------->|<- dRO/2 ->^
    #                                                                     echo: kx = ky = 0
    #       (the ADC is centered on each line, kx = 0 is in the middle of the line)

    # ╔═══ TODO 8  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    clear error if TE < TE_min
    # ║  USEFUL  pp.calc_duration(e1, e2, ...),  pp.calc_rf_center(rf)[0] (from the start of the shape),  rf.delay
    # ║  PROVIDE dExc, dGzr, dCr, dRef, dPre (block durations),
    # ║          tExcRefMin (90° center -> 180° center), tRefEchoMin (180° center -> echo), both without
    # ║          diffusion and delays
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('8')


    # ======================================================================================
    # STEP 9: diffusion gradients (Stejskal-Tanner)                          (milestone 2)
    # ======================================================================================
    # IDEA  Two equal gradients around the 180°. Static spins are refocused, moving spins keep a random
    #       phase -> S = S0 exp(-b D). Use the free time of both TE/2 halves: longest gradients that fit,
    #       then scale the amplitude to the requested b (b ~ G^2).
    #
    #       RF
    #                                                                                      /\                                                                         echo
    #          /\                                                                         /  \                                                                          v
    #       __/  \_______________________________________________________________________/    \______________________________________________________________________________
    #          90°                                                                        180°
    #           :                 G                                                         :                  G                                                        :
    #       Gdiff         ________________                                                  :          ________________                                                 :
    #           :        /                \                                                 :         /                \                                                :
    #           :       /                  \                                                :        /                  \                                               :
    #           :      /                    \                                               :       /                    \                                              :
    #           :     /                      \                                              :      /                      \                                             :
    #           :    /                        \                                             :     /                        \   . . . . . . . . . . . . . . . . . . . . .:. . .
    #       ________/                          \_________________________________________________/                          \__                                         :
    #               |<e>|                 |<e>|                                                                                EPI readout
    #               |<------ delta ------>|
    #               |<--------------------------------- Delta ---------------------------------->|
    #               e = ramp time (epsilon), delta = ramp + flat top, Delta = onset to onset
    #
    # b-value of two trapezoids (amplitude G in Hz/m):
    #     b = (2 pi G)^2 * [ delta^2 (Delta - delta/3) + e^3/30 - delta e^2/6 ]       [s/m^2], * 1e-6 -> s/mm^2
    #
    #       |exc|gzr|nav|<-------- gap1 -------->|cr| ref |cr|<-------- gap2 -------->|pre| lines ...
    #                   | diff 1     | delayTE1  |          | diff 2     | delayTE2  |
    #                   |<- dDiff -->|                      |<- dDiff -->|
    #                   |<------------------ Delta -------->|
    #
    #       gap1 = TE/2 - tExcRefMin,   gap2 = TE/2 - tRefEchoMin,   dDiff = min(gap1, gap2) (on the raster)
    #       the longer gap gets the bigger delay; in the picture gap1 = gap2, so delayTE1 = delayTE2

    # ╔═══ TODO 9  (your code) ═════════════════════════════════════════════════════════════
    # ║  SPEC    exact b_value along diff_axis ('x'/'y'/'z' or a vector, normalise it), no axis above max_grad,
    # ║          ramps at max slew on the 10 us raster. Clear error (with the minimum TE) if b is not reachable.
    # ║  USEFUL  pp.make_trapezoid(channel, amplitude=, rise_time=, flat_time=)  (one per axis, same timing)
    # ║  PROVIDE diffGrads (list of gradients for ONE block, empty for b = 0), dDiff (duration, 0 for b = 0),
    # ║          diffDir (unit vector, used in STEP 12)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    diffGrads, dDiff, diffDir = [], 0, np.array([1.0, 0.0, 0.0])     # milestone 1: no diffusion
    if b_value > 0:
        TODO('9')


    # ======================================================================================
    # STEP 10: fill delays (TE and TR)                                       (milestone 1)
    # ======================================================================================
    # IDEA  Fill each TE/2 half up to exactly TE/2 (drawings in STEP 8 and 9). TR is shared by all slices:
    #
    #       |<----------------------------------- TR ----------------------------------->|
    #       | slice 0 | delayTR | slice 2 | delayTR | slice 4 | delayTR | slice 1 | ...    |
    #       |<---- TR / n_slices --->|

    # ╔═══ TODO 10  (your code) ════════════════════════════════════════════════════════════
    # ║  SPEC    delays on the gradient raster, clear error if TR is too short for n_slices
    # ║  PROVIDE delayTE1, delayTE2, dSlice (active duration of one slice, used for the plot), delayTR
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('10')


    # ======================================================================================
    # STEP 11: build the sequence                                       (milestones 1 - 4)
    # ======================================================================================
    # IDEA  Loop over repetitions and slices, add the blocks of one slice in time order.
    #
    # Blocks of one slice (one line = one seq.add_block call):
    #
    #   rfexc+gz_ex | gzr_ex | navPre | ro+adc | roNeg+adc | ro+adc | navRew | diff 1 | delayTE1 | cr | rfref+gz_ref | cr
    #   | diff 2 | delayTE2 | roPre+byPre | ro+byUp+adc | roNeg+byDownUp+adc | ro+byDownUp+adc | ... | ..+byDown+adc | delayTR
    #
    #   milestone 1 (no navigators, no diffusion): leave out navPre ... navRew and diff 1/2
    #
    #       line      0          1            2         ...      nYmeas-1
    #       RO        ro         roNeg        ro                 ro / roNeg
    #       blip      byUp       byDownUp     byDownUp           byDown
    #                 (no blip before the 1st line, no blip after the last one)
    #
    #       Off-center slices: freq_offset = G_slice * z shifts the slice (each pulse has its own G_slice).
    #       The phase at the pulse center must be the same for every slice:
    #
    #       RF phase^                                                   o
    #               |                           :                   o   :   o  without correction: phase = 2 pi f t
    #               |                           :               o       :      (at t_center: 2 pi f t_center, different for every slice)
    #               |                           :           o           :
    #               |                           :       o               :
    #               |                           :   o                   :   O  with correction: shifted down by 2 pi f t_center
    #       2pi f tc|- - - - - - - - - - - - - -o                       O      -> phase0 (here 0) at t_center, for every slice
    #               |                       o   :                   O   :
    #               |                   o       :               O       :
    #               |               o           :           O           :
    #               |           o               :       O               :
    #               |       o                   :   O                   :
    #       0       |---o-----------------------O----------------------------------> t
    #               |                       O   :                       :
    #               |                   O       :                       :
    #               |               O           :                       :
    #               |           O               :                       :
    #               |       O                   :                       :
    #               pulse start             t_center                 pulse end

    # ╔═══ TODO 11  (your code) ════════════════════════════════════════════════════════════
    # ║  SPEC    labels on ADC blocks (the recon needs them):
    # ║            SLC = spatial slice index and REP = repetition, SET on the 1st ADC of every slice,
    # ║            NAV = True on the 1st navigator, NAV = False on the 1st EPI line
    # ║  USEFUL  seq.add_block(...),  pp.make_delay(d),  pp.make_label(label='SLC', type='SET', value=...),
    # ║          rf.freq_offset, rf.phase_offset, pp.calc_rf_center(rf)[0]
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    TODO('11')


    # ======================================================================================
    # STEP 12: checks, plots, definitions, export
    # ======================================================================================
    # check_timing: every event on its raster, no event longer than its block, dead/ringdown times kept
    ok, error_report = seq.check_timing()
    if ok:
        print('Timing check passed successfully')
    else:
        print('Timing check failed. Error listing follows:')
        [print(e) for e in error_report]

    # test_report: summary (number of blocks, TE/TR estimate, max gradient and slew rate, ...).
    # Note: its TE is the first navigator echo (not the image TE), and its slew rate is the vector norm
    # over all axes (can be above the per-axis limit while every axis is fine).
    if test_report:
        print(seq.test_report())

    if plot:
        # sequence diagram of the first slice (only the active part, the rest is the TR delay)
        sp = seq.plot(time_range=(0, dSlice), time_disp='ms', grad_disp='mT/m', show_blocks=False,
                      plot_now=False, stacked=True)
        sp.fig1.set_size_inches(10, 10)     # stacked = all channels in one figure, needs some height
        sp.fig1.tight_layout()

        # k-space trajectory (pypulseq calculate_kspace, including the k-inversion by the 180°),
        # plotted like the Pulseq/MATLAB demos: whole path in blue, ADC samples in red
        ktrajAdc, ktraj, _, _, tAdc = seq.calculate_kspace()
        fig, (axT, axK) = plt.subplots(1, 2, figsize=(12, 5))
        axT.plot(tAdc * 1e3, ktrajAdc[0], '.', ms=2, label='kx')
        axT.plot(tAdc * 1e3, ktrajAdc[1], '.', ms=2, label='ky')
        axT.set(xlabel='t [ms]', ylabel='k [1/m]', title='k-space at ADC samples')
        axT.legend()
        axT.grid(True)
        axK.plot(ktraj[0], ktraj[1], 'b-', lw=0.5)
        axK.plot(ktrajAdc[0], ktrajAdc[1], 'r.', ms=2)
        axK.set(xlabel='kx [1/m]', ylabel='ky [1/m]', title='k-space trajectory')
        axK.axis('equal')
        axK.grid(True)
        fig.tight_layout()

        show_or_save('SE-EPI')

    # definitions: free key/value pairs in the [DEFINITIONS] section of the .seq file.
    # The scanner interpreter ignores most of them, but the recon reads them (matrix, FOV, ...).
    seq.set_definition(key='Name', value='epi_se_rs')
    # geometry / resolution
    seq.set_definition(key='FOV', value=[fovX, fovY, slice_thickness])
    seq.set_definition(key='SliceThickness', value=slice_thickness)
    seq.set_definition(key='NSlices', value=n_slices)
    seq.set_definition(key='SliceGapFactor', value=slice_gap_factor)    # center-to-center / thickness
    seq.set_definition(key='Nx', value=n_x)
    seq.set_definition(key='Ny', value=n_y)
    # timing
    seq.set_definition(key='TE', value=te)
    seq.set_definition(key='TR', value=tr)
    # EPI readout
    seq.set_definition(key='PartialFourier', value=part_fourier)
    seq.set_definition(key='NyMeasured', value=nYmeas)                  # imaging lines per shot
    seq.set_definition(key='NyBeforeCenter', value=nYpre)               # lines before ky = 0
    seq.set_definition(key='RampSampling', value=ramp_sampling)         # [%] of the ADC window on the RO ramps
    seq.set_definition(key='ROduration', value=roDur)
    seq.set_definition(key='NavigatorLines', value=nNav)                # ky = 0 lines after the excitation, label NAV
    # diffusion
    seq.set_definition(key='BValue', value=b_value)                     # [s/mm^2]
    seq.set_definition(key='DiffusionDirection', value=list(diffDir))   # x = RO, y = PE, z = slice

    if write_seq:
        Path(seq_filename).parent.mkdir(parents=True, exist_ok=True)
        seq.write(seq_filename)
        print(f'written: {seq_filename}')

    return seq

# ==========================================================================================
# Milestones: each one adds a feature. Set MILESTONE to the one you are working on.
# ==========================================================================================
MILESTONES = {
    1: dict(b_value=0, n_nav=0, n_slices=1),       # spin-echo EPI (ramp sampling, partial Fourier)
    2: dict(b_value=500, n_nav=0, n_slices=1),     # + diffusion weighting
    3: dict(b_value=500, n_nav=3, n_slices=1),     # + navigator echoes
    4: dict(b_value=500, n_nav=3, n_slices=5),     # + multi-slice
}
MILESTONE = 1

# ==========================================================================================
# CHALLENGES (milestone 4 passes? check_seq.py must still pass afterwards)
# ==========================================================================================
#   C1  TE = 'min': compute the shortest TE for the given b-value (closed form or search).
#   C2  b-value table: one .seq with b = 0 and several b-values / directions (extra loop + a label for the recon).
#   C3  Fat saturation: spectrally selective pulse (-3.45 ppm) + spoiler before every excitation.
#   C4  Echo spacing: find the bandwidth and ramp_sampling that minimise the echo spacing for this hardware.
#   C5  Robustness: sweep n_nav (0..4), part_fourier (0.55..1), ramp_sampling (0..60), diff_axis vectors
#       and run check_seq.py on every file (a small loop over main(...) does it).
#   C6  Simulation: SIMULATE = True and GRADIENT_DELAY = 3e-6 (below). Compare b = 0 and b = 500.
#   C7  Multi-shot / interleaved EPI: 2 shots, each with every 2nd line (blip area 2/fovY).
#   C8  EPI distortions: fov = 240e-3, SIMULATE = True, B0_SCALE = 3. Predict the shift from
#       BW_PE = 1 / (echo spacing x n_y), then minimise the distortion with the readout parameters.
#       (C7 halves the effective echo spacing: compare!)

# ==========================================================================================
# Simulation (MRzero): after the check, simulate the isocenter k-space and reconstruct the image
# ==========================================================================================
SIMULATE = False             # True: simulate + reconstruct (a few seconds)
GRADIENT_DELAY = 0.0         # in SECONDS: e.g. 3e-6 = a 3 us gradient delay -> N/2 ghost (navigators fix it)
B0_SCALE = 1.0               # off-resonance of the phantom: 0 = none, 1 = realistic, 3 = strong -> EPI distortions

if __name__ == '__main__':
    seq_file = EXPORT / f'my_dwepi_M{MILESTONE}.seq'
    try:
        main(plot=True, seq_filename=str(seq_file), **MILESTONES[MILESTONE])
    except NotImplementedError as gap:
        # an open gap: short message with the line number (Ctrl+click on it in the VS Code terminal)
        where = traceback.extract_tb(gap.__traceback__)[-2]
        sys.exit(f'\n>>> {gap}\n    {where.filename}:{where.lineno}')
    # automatic check of the written file (the same as:  python tools/check_seq.py <file> --milestone N)
    print()
    run_check(seq_file, milestone=MILESTONE)
    if SIMULATE:
        from tools.simulation.simulate import run
        print()
        run(seq_file, GRADIENT_DELAY, B0_SCALE)
