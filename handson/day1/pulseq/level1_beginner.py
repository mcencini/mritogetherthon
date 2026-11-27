"""
Hands-on workshop: diffusion-weighted spin-echo EPI with pypulseq  --  LEVEL 1 (beginner)
=========================================================================================

One slice of the sequence (blocks in time order):

|  90°  |gzr| nav +-+ |  diff 1  | delayTE1 |cr| 180° |cr|  diff 2  | delayTE2 |pre|  EPI echo train (blips) ........  |
    ^                                              ^                                              ^
    |<------------------- TE/2 ------------------->|<------------------- TE/2 ------------------->|
  center of 90°                              center of 180°                              echo (ky = 0)

    90°, 180°   excitation / refocusing pulse with slice-select gradient      (STEP 2)
    gzr         slice rephaser                                                (STEP 2)
    nav +-+     navigator lines at ky = 0, alternating RO polarity            (STEP 5)
    diff 1/2    diffusion gradients (Stejskal-Tanner)                         (STEP 9)
    delayTE1/2  fill time so that the 180° is at TE/2 and the echo at TE      (STEP 8, 10)
    cr          crushers                                                      (STEP 6)
    pre         RO / PE prephaser to the first k-space line                   (STEP 4)
    EPI         bipolar readout with ramp sampling and partial Fourier        (STEP 3, 4)

Features
    - bipolar, continuous EPI readout with ramp sampling
    - partial Fourier in phase-encoding direction
    - navigator echoes (ky = 0) for odd/even phase correction
    - Stejskal-Tanner diffusion gradients with a target b-value
    - multi-slice, interleaved, with one slice always at the isocenter

Units (pypulseq works in SI units, gradients already multiplied by gamma):
    time s,  length m,  frequency Hz,  gradient amplitude Hz/m,  slew rate Hz/m/s,
    gradient area = k-space position 1/m.     mT/m = (Hz/m) / gamma * 1e3,  gamma = 42.576e6 Hz/T

How to work with this file
    The sequence is built in numbered STEPs. Read the ASCII drawings first: they are your main help,
    almost every number you need can be read off a drawing.

    Everything YOU have to do is in a box, separated from the explanations and drawings:

        ╔═══ TODO 3.2a ═══      a gap you fill in (the code line(s) directly below the box).
        ║  ...                   The script stops at the first open gap and tells you its number,
        ╚════════════════        so run it often:   python level1_beginner.py

        ┌─── QUESTION 3.4 ───   a question to think about (or to discuss with your neighbour).
        │  ...                   No code needed.
        └──────────────────

    Work in 4 milestones (MILESTONE at the bottom of the file). Steps of later milestones are skipped
    automatically, so you always have a sequence that runs:

        milestone 1   spin-echo EPI (RF, readout, partial Fourier, crushers, TE)   ~ 90 min
        milestone 2   + diffusion gradients with an exact b-value                   ~ 35 min
        milestone 3   + navigator echoes                                            ~ 20 min
        milestone 4   + multi-slice                                                 ~ 25 min
        done early?   BONUS tasks at the very bottom of this file

    Each run writes tools/export/my_dwepi_M<milestone>.seq and checks it automatically (PASS / FAIL + hint).
    Want to see an image? SIMULATE = True at the very bottom simulates and reconstructs it (MRzero).

    Many values are YOUR choice (pulse durations, bandwidths, ...): try, look at the plots and the console,
    change, try again. If you get "TE ... is too short" or "b ... not reachable", your choices made the
    sequence longer: use the minimum TE from the message (te=... in MILESTONES at the bottom of the file).

    Stuck?  help(pp.make_trapezoid)  in a Python console,  print(ro)  shows all attributes of an event,
            tools/docs/CHEATSHEET.md,  your neighbour,  a tutor.  The plots (sequence diagram, k-space) show most errors.
"""

import tools.workshop_env  # noqa: F401  (first start: sets everything up; always runs in the workshop Python)

import sys
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pypulseq as pp
from pypulseq.make_sigpy_pulse import sigpy_n_seq

from tools.check_seq import run_check
from tools.rf_profile import compare_ref_profiles, show_or_save

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
    slice_gap_factor: float = 3,                       # center-to-center distance in units of the slice thickness
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

    # ┌─── QUESTION 1.1 ────────────────────────────────────────────────────────────────────
    # │  print(system.max_grad, system.max_slew): which units does pypulseq use internally?
    # │  How long does a gradient need to ramp from 0 to max_grad?  (we use this in STEP 3 and 9)
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 2: RF pulses
    # ======================================================================================
    # 2a) 90° excitation: windowed sinc
    #     A sinc in time is (nearly) a rectangle in frequency -> rectangular slice profile.
    #     time-bandwidth product TBW = duration * bandwidth  (number of zero crossings: sharper profile
    #     for larger TBW)        ->   bandwidth = TBW / duration
    #     A slice-select gradient G turns frequency into position (f = G * z), so the slice thickness is
    #         thickness = bandwidth / G       ->      G = bandwidth / thickness   [Hz/m]
    #     apodization (0 ... 1) = a window over the sinc: fewer ripples in the slice profile.
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
    #     The RF pulse is played on the flat top of gz, its center in the middle of the flat top.
    #     Spins excited at the pulse center then dephase during the 2nd half of gz (= 1/2 of the gz area,
    #     the ramp down included). The rephaser gzr directly after gz has exactly -1/2 of the gz area and
    #     rephases them. (pypulseq makes gzr as short as possible: a triangle with a higher amplitude than
    #     gz; it is drawn with the same amplitude here so that the areas are easy to compare.)
    #     return_gz=True returns all three: pulse, slice-select gradient, rephaser.

    # ╔═══ TODO 2.1 ════════════════════════════════════════════════════════════════════════
    # ║  90° excitation pulse: pp.make_sinc_pulse(...)        (help(pp.make_sinc_pulse) shows all arguments)
    # ║  flip_angle in rad, slice_thickness=slice_thickness, return_gz=True, use='excitation', system=system
    # ║
    # ║  duration, time_bw_product, apodization: YOUR choice. Start with anything sensible and
    # ║  iterate with the profile plot (2e) and the B1 check (2f). If the slice gradient would be
    # ║  stronger than max_grad, pypulseq stops with an error: then your pulse is too "fast".
    # ║
    # ║  It returns 3 objects: the pulse, the slice-select gradient and the rephaser.
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    rfexc, gz_ex, gzr_ex = TODO('2.1')


    # 2b) 180° refocusing, 1st try: the same sinc recipe with flip angle 180°
    #     phase_offset = pi/2: refocusing axis perpendicular to the excitation axis (CPMG condition).
    #     No rephaser needed: the 180° pulse is symmetric, the gradient areas before and after its
    #     center cancel each other (the 180° inverts the phase in between).

    # ╔═══ TODO 2.2 ════════════════════════════════════════════════════════════════════════
    # ║  180° sinc pulse: pp.make_sinc_pulse again, with flip angle 180°, phase_offset=np.pi / 2,
    # ║  use='refocusing'. Duration, TBW and apodization: your choice again.
    # ║  The 3rd return value (rephaser) is not needed:   rfref_sinc, gz_ref_sinc, _ = ...
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    rfref_sinc, gz_ref_sinc, _ = TODO('2.2')


    # 2c) 180° refocusing, 2nd try: an SLR pulse
    #     The sinc idea "slice profile = Fourier transform of the pulse" is the small-tip approximation.
    #     It holds for small flip angles, but not at 180°: the flip angle is no longer proportional to B1.
    #     The SLR (Shinnar-Le Roux) algorithm designs the pulse for the large flip angle directly.
    #     sigpy does it for us (ptype='se' optimises the spin-echo profile):
    #
    #         sigpy_n_seq(flip_angle=..., duration=..., time_bw_product=..., phase_offset=...,
    #                     slice_thickness=..., return_gz=True, use='refocusing', system=system,
    #                     pulse_cfg=pp.SigpyPulseOpts(pulse_type='slr', ptype='se'),
    #                     plot=False)        # plot=False, otherwise sigpy opens its own plots

    # ╔═══ TODO 2.3 ════════════════════════════════════════════════════════════════════════
    # ║  SLR 180° pulse with the SAME duration and TBW as your sinc 180° -> a fair comparison
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    rfref_slr, gz_ref_slr, _ = TODO('2.3')


    # 2d) Wider refocusing slice
    #     The same bandwidth with a weaker slice-select gradient gives a thicker slice (thickness = BW / G).
    #     With gzScale < 1 the refocused slice is 1 / gzScale times thicker than the excited one, so the
    #     edges of the excited slice are fully refocused, too:
    #
    #       refocused (180°)      __________________
    #                            |                  |
    #       excited (90°)        |    __________    |
    #                            |   |          |   |
    #       _____________________|___|__________|___|______________   z
    #
    #     pp.scale_grad scales amplitude AND the stored areas consistently.

    # ╔═══ TODO 2.4 ════════════════════════════════════════════════════════════════════════
    # ║  choose gzScale (try a few values with the plot of 2e) and scale the slice-select
    # ║  gradients of BOTH 180° pulses with it                      (pp.scale_grad)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    gzScale = TODO('2.4 gzScale')
    gz_ref_sinc = TODO('2.4 sinc')
    gz_ref_slr = TODO('2.4 slr')

    # ┌─── QUESTION 2.4 ────────────────────────────────────────────────────────────────────
    # │  Why is it fine to scale only the gradient and not the RF pulse?
    # └─────────────────────────────────────────────────────────────────────────────────────


    # 2e) Compare the slice profiles (Bloch simulation, tools/rf_profile.py)
    #     refocusing efficiency (1 - Mz)/2: 1 = perfect 180°, 0 = no refocusing.
    #     The echo of a spin at position z is  excitation |Mxy(z)|  x  refocusing (1 - Mz(z))/2.
    if plot:
        compare_ref_profiles((rfexc, gz_ex, gzr_ex),
                             [(rfref_sinc, gz_ref_sinc, 'sinc 180°'), (rfref_slr, gz_ref_slr, 'SLR 180°')],
                             system=system, slice_thickness=slice_thickness)

    # ┌─── QUESTION 2.5 ────────────────────────────────────────────────────────────────────
    # │  Look at the plot: which 180° pulse has a flat top? Which one refocuses the whole excited slice?
    # │  How thick is the sinc 180° slice compared to what you asked for? Which one needs more B1?
    # └─────────────────────────────────────────────────────────────────────────────────────

    # ╔═══ TODO 2.5 ════════════════════════════════════════════════════════════════════════
    # ║  the winner is used in the sequence:   rfref, gz_ref = ...
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    rfref, gz_ref = TODO('2.5')


    # 2f) Peak B1 check
    #     rf.signal is the RF amplitude in Hz (= gamma * B1), divide by gamma for Tesla.
    #     Typical body-coil limit: ~20 uT (and the SAR, ~ B1^2 x duration, limits the power).
    for name, rf, gz in (('excitation', rfexc, gz_ex), ('refocusing sinc', rfref_sinc, gz_ref_sinc),
                         ('refocusing SLR', rfref_slr, gz_ref_slr)):

        # ╔═══ TODO 2.6 ════════════════════════════════════════════════════════════════════════
        # ║  peak B1 in Tesla: the largest |rf.signal| (in Hz), divided by gamma (system.gamma, Hz/T)
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        b1Peak = TODO('2.6')
        print(f'{name}: peak B1 = {b1Peak * 1e6:.1f} uT, slice gradient {gz.amplitude / system.gamma * 1e3:.1f} mT/m')
        if b1Peak > 20e-6:
            print(f'  WARNING: {name} pulse exceeds 20 uT')

    # ┌─── QUESTION 2.6 ────────────────────────────────────────────────────────────────────
    # │  Experiment: change ONE parameter of your pulses at a time, re-run, and fill in the table
    # │  (x 2, / 2, = ...) from the console output and the profile plot:
    # │
    # │      change                    bandwidth    slice gradient    peak B1    profile
    # │      duration / 2                  ?               ?              ?          ?
    # │      TBW x 2                       ?               ?              ?          ?
    # │      flip angle 90° -> 180°        ?               ?              ?          ?
    # │
    # │  Why can you not simply make all pulses short with a high bandwidth?
    # │  Why is the 180° usually longer than the 90°? What does the better SLR profile cost?
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 3: EPI readout (bipolar, continuous, ramp sampling)
    # ======================================================================================
    # EPI acquires all k-space lines after ONE excitation: the readout gradient alternates its sign
    # (one line left -> right, the next right -> left) and a small PE blip moves ky by one line in between:
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
    # The k-space grid follows from the field of view:
    #     delta k = 1 / FOV  (Nyquist: no aliasing inside the FOV),   resolution = FOV / N
    #     one line covers N * delta k = N / FOV  (from -N/2 to N/2 - 1 in units of delta k)
    #
    # Readout bandwidth: the ADC window of one line, T = roDur, sets the bandwidth per pixel, BW/px ~ 1 / T.
    # EPI uses a HIGH bandwidth, typically ~1000 - 2500 Hz/pixel: short lines -> short echo spacing ->
    # less distortion and T2* blurring. The price: a stronger readout gradient and more noise
    # (SNR ~ 1 / sqrt(BW)).

    # ╔═══ TODO 3.0 ════════════════════════════════════════════════════════════════════════
    # ║  choose the bandwidth per pixel and compute the ADC window of one line from it,
    # ║  on the gradient raster:  np.round(x / rast) * rast
    # ║  (later: try other values and watch "RO:", "echo spacing" and "TE min" in the console)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    bwPixel = TODO('3.0 bwPixel')                   # [Hz/pixel]
    roDur = TODO('3.0 roDur')                       # [s]

    # fov: one value (square) or (fov_x, fov_y)
    fovX, fovY = (fov, fov) if np.isscalar(fov) else fov

    # ╔═══ TODO 3.1 ════════════════════════════════════════════════════════════════════════
    # ║  k-space steps in 1/m (formulas just above)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    xBlip = TODO('3.1 xBlip')     # delta k_x
    yBlip = TODO('3.1 yBlip')     # delta k_y
    xRO = TODO('3.1 xRO')         # k-space extent of one readout line


    # 3a) PE blip
    #     The blip moves ky by one line between two readout lines. Its area must be exactly yBlip = 1/fovY.
    #     It should be as short as possible: it sits on the RO ramps (3d), so a short blip allows short
    #     RO ramps and therefore a short echo spacing (less distortion, shorter TE).
    #
    #     Shortest gradient with area A: a triangle that ramps up and down at the maximum slew rate S.
    #
    #                                         peak amplitude  G = S * T/2
    #                    /\                   area            A = 1/2 * T * G = S * T^2 / 4
    #                   /  \
    #                  /    \                 ->   T = 2 * sqrt(A / S)
    #                 /      \
    #       _________/        \__________
    #                |<- T -->|
    #
    #     Units in pypulseq: A in 1/m, S in Hz/m/s  ->  A/S in s^2  ->  T in s.
    #
    #     The duration is rounded UP to a multiple of 2 x the gradient raster (10 us): in 3d the blip
    #     is cut in half, and both halves must again lie on the raster.
    #     Rounding up makes the blip slightly longer -> make_trapezoid with area + duration uses a
    #     slightly lower slew rate, the area stays exactly yBlip.
    #
    #     Sign: negative area, because we start at the top of k-space (+ky) and walk down line by line.

    # ╔═══ TODO 3.2a ═══════════════════════════════════════════════════════════════════════
    # ║  shortest blip duration T from the triangle drawing (area yBlip, slew system.max_slew)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    byDur = TODO('3.2a')
    byDur = np.ceil(byDur / rast / 2) * rast * 2          # round up to 2 x raster (given)

    # ╔═══ TODO 3.2b ═══════════════════════════════════════════════════════════════════════
    # ║  the blip: pp.make_trapezoid on channel 'y' with the area (sign!) and the duration byDur
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    by = TODO('3.2b')
    print(f'blip duration: {byDur * 1e6:.0f} us')


    # 3b) RO gradient with ramp sampling
    #     The ADC window roDur is centered on the RO trapezoid. Without ramp sampling the ADC only samples
    #     the flat top. With ramp sampling the ADC window is longer than the flat top, and the outer
    #     parts of the window lie on the ramps:
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
    #
    #     ramp_sampling (%) is the fraction of the ADC window on the ramps:  2 s = T * ramp_sampling / 100
    #
    #     Area inside the ADC window (= kx distance covered while sampling), with ramp slope S = G / rise:
    #         flat top:          G * F
    #         sampled ramp part: a trapezoid from G - S*s up to G over the time s  ->  G*s - S*s^2/2  (x 2 ramps)
    #         sum:               G * F + 2*G*s - S*s^2  =  G * T - S * s^2
    #     It must be xRO = n_x / fovX:
    #         G * T - S * s^2 = xRO
    #
    #     The unsampled part of the ramp (rise - s, at the bottom) is where the half blips go (3d).
    #     Why ramp sampling? For the same k-space line the gradient can be weaker and/or the line shorter
    #     -> shorter echo spacing. Price: non-uniform kx sampling, the recon has to regrid.

    # ╔═══ TODO 3.3 ════════════════════════════════════════════════════════════════════════
    # ║  the readout trapezoid with ramp sampling -- the hardest part of the whole sequence!
    # ║  One possible recipe in pseudo-code (T = roDur, s = sRamp, F = roFlat, S = slope of the ramps):
    # ║
    # ║    roFlat = the part of T that is NOT on the ramps            (ramp_sampling is in %)
    # ║             -> on the gradient raster:   np.round(x / rast) * rast
    # ║    sRamp  = the sampled part of ONE ramp                      (T = F + 2 s)
    # ║    roAmp  = 1st guess: solve  G*T - S*s^2 = xRO  for G,  with S = system.max_slew
    # ║             (= the ramps as steep as the hardware allows)
    # ║    roRise = the LONGER of   roAmp / system.max_slew     the hardware cannot ramp faster
    # ║                             sRamp + byDur / 2           room for half a blip below the ADC (3d)
    # ║             -> rounded UP to the raster:   np.ceil(x / rast - 1e-9) * rast
    # ║                (the -1e-9 avoids that 3.0000000001 raster steps are rounded up to 4)
    # ║    now the ramp may be LONGER than in the 1st guess, its slope is only S = roAmp / roRise:
    # ║    roAmp  = solve  G*T - (G / roRise) * s^2 = xRO  for G  again  (S depends on G now!)
    # ║    ro     = pp.make_trapezoid on channel 'x' with amplitude, rise_time and flat_time
    # ║
    # ║  Check: "RO: ... mT/m" in the console must stay below max_grad, and check_seq.py tests that
    # ║  every line covers -kx,max ... +kx,max.
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    roFlat = TODO('3.3 roFlat')
    sRamp = TODO('3.3 sRamp')
    roAmp = TODO('3.3 roAmp 1st guess')
    roRise = TODO('3.3 roRise')
    roAmp = TODO('3.3 roAmp')
    ro = TODO('3.3 ro')
    # every 2nd line runs in the opposite direction: same trapezoid with negative sign

    # ╔═══ TODO 3.3e ═══════════════════════════════════════════════════════════════════════
    # ║  roNeg = ro with the opposite sign (you already used the function in STEP 2)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    roNeg = TODO('3.3e')
    # one line = one RO trapezoid. The lines follow each other without gaps, so the duration of one
    # trapezoid is the echo spacing (time between two neighbouring k-space lines).
    dRO = pp.calc_duration(ro)
    print(f'RO: {roAmp / system.gamma * 1e3:.1f} mT/m, rise {roRise * 1e6:.0f} us, flat {roFlat * 1e6:.0f} us, '
          f'echo spacing {dRO * 1e3:.3f} ms')


    # 3c) ADC
    #     Nyquist: two neighbouring samples may be at most delta kx = xBlip apart in k-space.
    #     On the flat top, kx moves with speed G (1/m per s), so the dwell time must be <= xBlip / G.
    #     Number of samples over the whole window roDur:
    #         adcSamples >= roDur / (xBlip / G)        (rounded UP to a multiple of 4, a scanner requirement)
    #     The samples are spread evenly over roDur. On the ramps the gradient is weaker, so these samples
    #     lie closer together in k-space -> non-uniform kx, regridded in the recon (drawing above).
    #
    #     The dwell time must be a multiple of 100 ns: rounded DOWN, so the ADC is never longer than roDur.
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

    # ╔═══ TODO 3.4a ═══════════════════════════════════════════════════════════════════════
    # ║  number of ADC samples (Nyquist on the flat top, see above), rounded UP to a multiple of 4
    # ║  -> must be an int:  int(np.ceil(x / 4)) * 4
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    adcSamples = TODO('3.4a')
    adcDwell = np.floor(roDur / adcSamples * 1e7) * 1e-7      # on the 100 ns raster (given)

    # ╔═══ TODO 3.4b ═══════════════════════════════════════════════════════════════════════
    # ║  the ADC: pp.make_adc(num_samples=..., dwell=..., system=system)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    adc = TODO('3.4b')
    #     Center the ADC on the RO gradient, so that kx = 0 is in the middle of the samples
    #     (see the drawing in the RO step above: center line, adc.delay):
    #
    #     adc.delay = rise + flat/2 - (adcSamples x adcDwell)/2
    #     Ramp sampling: s = 15 % of the ADC window on each ramp (30 % in total) = 40 % of the ramp duration,
    #     i.e. the ADC starts at 60 % of the ramp height. There G is only ~0.6 x the flat-top value, so the
    #     outermost kx steps are ~0.6 x delta kx and grow linearly with G up to delta kx = 1/FOVx on the
    #     flat top -> non-uniform kx, regridded in the recon.
    #
    #     The delay is rounded to 1 us (RF/ADC raster of the delay).

    # ╔═══ TODO 3.4c ═══════════════════════════════════════════════════════════════════════
    # ║  ADC start relative to the start of ro (adc.delay in the RO drawing of 3b)
    # ║  ro.rise_time, ro.flat_time, adcDwell, adcSamples
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    adc.delay = TODO('3.4c')
    adc.delay = round(adc.delay * 1e6) * 1e-6
    onRamp = max(0, adcSamples * adcDwell - ro.flat_time) / (adcSamples * adcDwell)
    print(f'ADC: {adcSamples} samples, dwell {adcDwell * 1e6:.2f} us, {onRamp * 100:.0f} % on ramps')

    # ┌─── QUESTION 3.4 ────────────────────────────────────────────────────────────────────
    # │  There are more ADC samples than n_x. Why? (look at the kx positions drawing)
    # └─────────────────────────────────────────────────────────────────────────────────────


    # 3d) Blips on the RO ramps
    #     The blip is played where the RO gradient changes its sign, i.e. across the border between two
    #     blocks (one block = one line). A block can only contain what starts in it, so the blip is cut
    #     in two halves:
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
    #
    #     byUp     1st half, aligned to the END of a block    (pp.align right=...)
    #     byDown   2nd half, starts at the BEGINNING of a block (pp.align left=...)
    #     byDownUp both halves in one waveform (pp.add_gradients) for all middle lines
    #     Passing ro to pp.align makes all parts exactly as long as one RO trapezoid.
    #     The ADC must be off during the blip (ky would change while sampling) -> the half blip has to
    #     fit on the unsampled part of the RO ramp, which is why roRise >= sRamp + byDur / 2 (3b).
    byParts = pp.split_gradient_at(grad=by, time_point=byDur / 2, system=system)
    byUp, byDown, _ = pp.align(right=byParts[0], left=[byParts[1], ro])

    # ╔═══ TODO 3.5 ════════════════════════════════════════════════════════════════════════
    # ║  byDownUp: both halves in ONE waveform, for all middle lines       (pp.add_gradients)
    # ║  pp.add_gradients takes a list/tuple of gradients and system=system
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    byDownUp = TODO('3.5')

    # ┌─── QUESTION 3.5 ────────────────────────────────────────────────────────────────────
    # │  Why must the half blips lie on the UNSAMPLED part of the ramps?
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 4: phase encoding / partial Fourier
    # ======================================================================================
    # k-space is acquired from top to bottom. With partial Fourier only part of the upper half is
    # measured; the missing lines are filled in the recon (zero-filling, or POCS/homodyne using the
    # conjugate symmetry of k-space):
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
    #   nYpost = n_y/2 + 1  lines from ky = 0 down to -n_y/2 (always measured)
    #   nYpre               lines above ky = 0 (the rest of the measured lines)
    #   example: n_y = 64, part_fourier = 0.75 -> nYmeas = 48, nYpost = 33, nYpre = 15
    #
    # Fewer lines BEFORE the center -> the center is reached earlier -> shorter TE (less T2 decay),
    # and a shorter echo train (less T2* blurring).
    nYpost = n_y // 2 + 1

    # ╔═══ TODO 4.1 ════════════════════════════════════════════════════════════════════════
    # ║  measured lines (an int!) and lines BEFORE ky = 0  (check: 48 and 15 for the defaults)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    nYmeas = TODO('4.1 nYmeas')
    nYpre = TODO('4.1 nYpre')
    if nYpre < 0:
        raise ValueError(f'part_fourier = {part_fourier} too small, minimum is {nYpost / n_y:.3f}')
    print(f'PE lines: {nYmeas} of {n_y} (partial Fourier {part_fourier}), {nYpre} before k-space center')

    # Prephasers: move k from the center (0, 0) to the start of the first line:
    #     kx: -ro.area / 2   (one RO trapezoid moves kx from -area/2 to +area/2, center of the line at kx = 0)
    #     ky: +nYpre * yBlip (top of the measured k-space)
    #     (real proportions of the default parameters: 1 column = 20 us, 1 row = 2.6 mT/m,
    #      i.e. a 45° line = 130 T/m/s = max slew rate; byPre is drawn with 45° ramps, it is relaxed later)
    #
    #
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
    #
    # Both are played in ONE block. pp.align(right=...) lets them end at the same time; then byPre is
    # recomputed with the full block duration -> lower amplitude and slew rate (less PNS), same area.

    # ╔═══ TODO 4.2 ════════════════════════════════════════════════════════════════════════
    # ║  readout prephaser: kx from 0 to the start of line 0 (see the k-space path above).
    # ║  pp.make_trapezoid with ONLY channel, area and system -> the shortest possible gradient
    # ║  (every gradient object knows its area: ro.area)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    roPre = TODO('4.2')
    byPre = None
    if nYpre > 0:

        # ╔═══ TODO 4.3 ════════════════════════════════════════════════════════════════════════
        # ║  phase prephaser: ky from 0 up to the first measured line (sign!), shortest gradient
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        byPre = TODO('4.3')
        roPre, byPre = pp.align(right=roPre, left=byPre)
        byPre = pp.make_trapezoid(channel='y', area=byPre.area, duration=pp.calc_duration(roPre, byPre), system=system)
    prePhasers = [g for g in (roPre, byPre) if g is not None]

    # ┌─── QUESTION 4 ──────────────────────────────────────────────────────────────────────
    # │  Which part of k-space is missing with part_fourier = 0.75? How can the recon fill it?
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 5: navigators
    # ======================================================================================
    # Why: in EPI, lines measured with + and - RO polarity are slightly shifted against each other
    # (eddy currents, gradient delays). The alternating error produces an N/2 ghost.
    # Navigators are lines at ky = 0 (no blips) with the same RO and ADC, polarity +, -, +, ...
    # They contain the same object information, so any difference between + and - lines is the error.
    # The recon measures it (phase phi(x) = phi0 + phi1 * x in hybrid space) and removes it from the image lines.
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
    # Placed in the 1st TE/2 interval (right after the excitation): there is idle time anyway, so they
    # do not lengthen TE. Afterwards kx must be back at 0: the 180° inverts k (k -> -k, see STEP 6),
    # a remaining kx offset would shift the whole echo train.
    # kx after nNav lines: starting at -ro.area/2, every line adds +ro.area or -ro.area:
    #     nNav odd  -> +ro.area/2,     nNav even -> -ro.area/2
    nNav = n_nav
    dNav = 0
    if nNav > 0:

        # ╔═══ TODO 5.1 ════════════════════════════════════════════════════════════════════════
        # ║  navigator prephaser: kx from 0 to -kx,max (same area as roPre, but no ky part)
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        navPre = TODO('5.1')

        # ╔═══ TODO 5.2 ════════════════════════════════════════════════════════════════════════
        # ║  kx after the last navigator line (kx path above). Must work for odd AND even nNav!
        # ║  tip: nNav % 2 is 1 for odd, 0 for even nNav
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        kxNavEnd = TODO('5.2')

        # ╔═══ TODO 5.3 ════════════════════════════════════════════════════════════════════════
        # ║  rewinder: from kxNavEnd back to kx = 0, shortest gradient
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        navRew = TODO('5.3')

        # ╔═══ TODO 5.4 ════════════════════════════════════════════════════════════════════════
        # ║  total navigator duration: navPre + nNav lines (dRO each) + navRew   (pp.calc_duration)
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        dNav = TODO('5.4')


    # ======================================================================================
    # STEP 6: crushers around the refocusing pulse
    # ======================================================================================
    # An imperfect 180° pulse also creates NEW transverse magnetisation (its own FID) and leaves part of
    # the old one unrefocused. Crushers with the same area on both sides of the 180° separate these paths:
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
    # The same in k-space: the 180° inverts the phase of every spin, i.e. it mirrors k at the origin
    # (k -> -k). This is THE rule of the spin echo, you need it again for the navigator rewinder (STEP 5)
    # and the diffusion gradients (STEP 9).  k(t) along the crusher axis, A = area of one crusher:
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
    #
    # Area: the crusher must dephase the unwanted signal within a voxel. A gradient area A [1/m] winds the
    # phase by A * slice_thickness cycles across the slice. A few cycles are enough (more = longer TE).
    # make_trapezoid with ONLY the area gives the shortest waveform within max_grad / max_slew:
    #   a triangle if the peak stays below max_grad, otherwise a trapezoid with flat top at max_grad.

    # ╔═══ TODO 6.1 ════════════════════════════════════════════════════════════════════════
    # ║  choose the crusher area [1/m] (think in cycles across the slice) and make the shortest
    # ║  crusher on channel 'z'
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    crArea = TODO('6.1 crArea')
    cr = TODO('6.1 cr')
    print(f'crusher: area {crArea:.0f} 1/m, {cr.amplitude / system.gamma * 1e3:.1f} mT/m, '
          f'rise {cr.rise_time * 1e6:.0f} us, flat {cr.flat_time * 1e6:.0f} us')

    # ┌─── QUESTION 6 ──────────────────────────────────────────────────────────────────────
    # │  What would happen to the echo if the 2nd crusher had the opposite sign? (k(t) drawing)
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 7: slice positions (multi-slice, interleaved)
    # ======================================================================================
    # center-to-center distance d = slice_gap_factor * slice_thickness (1.0 = contiguous slices)
    # slice n_slices // 2 is always at the isocenter (z = 0); example n_slices = 5:
    #
    #       z          -2d      -d       0       +d      +2d
    #                 |###|    |###|   |###|    |###|    |###|      ### = slice_thickness
    #       index       0        1       2        3        4        (spatial order, used as label SLC)
    #       acquired   1st      4th     2nd      5th      3rd       sliceOrder = [0, 2, 4, 1, 3]
    #
    # Interleaved: the slice profiles are not perfectly rectangular, a pulse also touches the neighbouring
    # slices. Exciting the neighbours directly after each other would saturate them -> first all even,
    # then all odd spatial indices.
    sliceDist = slice_gap_factor * slice_thickness
    iCenter = n_slices // 2
    if n_slices == 1:
        slicePos, sliceOrder = np.zeros(1), [0]          # milestones 1-3: one slice at the isocenter
    else:

        # ╔═══ TODO 7.1 ════════════════════════════════════════════════════════════════════════
        # ║  slice positions in spatial order [m], slice iCenter at z = 0 (drawing above)
        # ║  np.arange(n_slices) gives the array 0, 1, 2, ...
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        slicePos = TODO('7.1')

        # ╔═══ TODO 7.2 ════════════════════════════════════════════════════════════════════════
        # ║  acquisition order: all even spatial indices, then all odd ones -> [0, 2, 4, 1, 3]
        # ║  list(range(start, stop, step)) + list(range(...))
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        sliceOrder = TODO('7.2')
    print(f'slices: {n_slices}, positions {np.round(slicePos * 1e3, 2)} mm, acquisition order {sliceOrder}')


    # ======================================================================================
    # STEP 8: TE timing
    # ======================================================================================
    # Spin echo: the 180° center must be at TE/2, the k-space center (ky = 0, kx = 0) at TE, both measured
    # from the center of the 90° pulse:
    #
    #   |  exc  | gzr |   nav   |  diff 1  |  delayTE1 | cr |  ref  | cr |  diff 2  |delayTE2| pre |  nYpre lines  |  line nYpre | ...
    #       ^                                                   ^                                                   ^
    #       |<--------------------- TE/2 ---------------------->|<--------------------- TE/2 ---------------------->|
    #   90° center                                       180° center                                        echo (ky = 0)
    #
    #   tExcRefMin : center of exc -> center of ref, WITHOUT diffusion gradient and delay
    #   tRefEchoMin: center of ref -> echo,          WITHOUT diffusion gradient and delay
    #   (nav = 0 if there are no navigators)
    #   The larger of the two minimal times limits TE:  TE_min = 2 * max(tExcRefMin, tRefEchoMin).
    #   The free time in both halves is used for the diffusion gradients (STEP 9) and filled with delays (STEP 10).
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

    # block durations
    dExc = pp.calc_duration(rfexc, gz_ex)
    dGzr = pp.calc_duration(gzr_ex)

    # ╔═══ TODO 8.1 ════════════════════════════════════════════════════════════════════════
    # ║  the other block durations, same way (which events are in the block?)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    dCr = TODO('8.1 dCr')
    dRef = TODO('8.1 dRef')
    dPre = TODO('8.1 dPre')          # tip: *prePhasers unpacks the list

    # RF centers within their blocks: rf.delay (dead time / gradient ramp before the pulse)
    # + center of the pulse shape (pp.calc_rf_center, the peak of the pulse)
    tExc = rfexc.delay + pp.calc_rf_center(rfexc)[0]

    # ╔═══ TODO 8.2 ════════════════════════════════════════════════════════════════════════
    # ║  the same for the refocusing pulse (Zoom 1)
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    tRef = TODO('8.2')

    # ╔═══ TODO 8.3 ════════════════════════════════════════════════════════════════════════
    # ║  the two minimal times: walk along the block diagram above and add up what lies between
    # ║  the two centers (Zoom 1 and Zoom 2). Leave out diffusion and delays (they come later).
    # ║  Available: dExc dGzr dNav dCr dRef dPre dRO   tExc tRef   nYpre
    # ║  check: TE min = 31.96 ms with the default parameters
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    tExcRefMin = TODO('8.3 tExcRefMin')
    tRefEchoMin = TODO('8.3 tRefEchoMin')
    teMin = 2 * max(tExcRefMin, tRefEchoMin)
    print(f'TE min (without diffusion): {teMin * 1e3:.2f} ms')
    if te < teMin:
        raise ValueError(f'TE = {te * 1e3:.1f} ms is too short, minimum is {teMin * 1e3:.2f} ms')

    # ┌─── QUESTION 8 ──────────────────────────────────────────────────────────────────────
    # │  Which half limits TE here, before or after the 180°? What would make TE shorter?
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 9: diffusion gradients (Stejskal-Tanner)
    # ======================================================================================
    # Two identical gradients on both sides of the 180°. Static spins: the phase of the 1st gradient is
    # inverted by the 180° and undone by the 2nd. Moving (diffusing) spins are at a different position
    # during the 2nd gradient -> remaining random phase -> signal loss  S = S0 * exp(-b * D).
    # Both gradients have the SAME sign, because the 180° already inverts the phase.
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
    # direction: 'x' / 'y' / 'z' or a vector (x = RO, y = PE, z = slice), normalised to length 1
    diffDir = {'x': (1, 0, 0), 'y': (0, 1, 0), 'z': (0, 0, 1)}.get(diff_axis, diff_axis)
    diffDir = np.asarray(diffDir, dtype=float)
    diffDir = diffDir / np.linalg.norm(diffDir)

    # Strongest gradient along diffDir without exceeding max_grad on any axis: the largest component
    # limits it. Example (1, 1, 0)/sqrt(2): each axis at max_grad -> total amplitude sqrt(2) * max_grad.
    # Ramps at max slew rate, rounded up to the gradient raster.
    gDiffMax = system.max_grad / np.max(np.abs(diffDir))
    riseDiff = np.ceil(gDiffMax / system.max_slew / rast) * rast

    # Timing: the 1st diffusion gradient starts right after the navigators, the 2nd right after the
    # 2nd crusher. Both must have the same duration, so the shorter of the two free intervals limits them:
    #     gap1 = TE/2 - tExcRefMin     free time before the 180°
    #     gap2 = TE/2 - tRefEchoMin    free time after the 180°
    #     Delta (onset to onset) = gap1 + cr + ref + cr       (diffusion 1 + delayTE1 fill exactly gap1)
    #
    #       |exc|gzr|nav|<-------- gap1 -------->|cr| ref |cr|<-------- gap2 -------->|pre| lines ...
    #                   | diff 1     | delayTE1  |          | diff 2     | delayTE2  |
    #                   |<- dDiff -->|                      |<- dDiff -->|
    #                   |<------------------ Delta -------->|
    #
    #       gap1 = TE/2 - tExcRefMin,   gap2 = TE/2 - tRefEchoMin,   dDiff = min(gap1, gap2) (on the raster)
    #       the longer gap gets the bigger delay; in the picture gap1 = gap2, so delayTE1 = delayTE2
    def diffTiming(teX):
        gap1 = teX / 2 - tExcRefMin
        gap2 = teX / 2 - tRefEchoMin
        dDiff = np.floor(min(gap1, gap2) / rast) * rast
        flatDiff = dDiff - 2 * riseDiff

        # ╔═══ TODO 9.1 ════════════════════════════════════════════════════════════════════════
        # ║  Delta = onset of diffusion 1 -> onset of diffusion 2 (drawing above)
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        bigDelta = TODO('9.1')
        return dDiff, flatDiff, bigDelta

    def bValue(g, rise, flat, bigDelta):
        # Stejskal-Tanner for a trapezoid pair, g in Hz/m -> b in s/mm^2
        smallDelta = rise + flat

        # ╔═══ TODO 9.2 ════════════════════════════════════════════════════════════════════════
        # ║  Stejskal-Tanner formula from the drawing (e = rise, delta = smallDelta, Delta = bigDelta)
        # ║  powers in Python: x**2
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        b = TODO('9.2')
        return b * 1e-6

    # Approach: use the longest possible gradients at full amplitude -> bMax. If bMax >= b_value, keep
    # the timing and lower the amplitude: b ~ G^2  ->  G = gDiffMax * sqrt(b_value / bMax).
    # If bMax < b_value, TE is too short: search the minimal TE (0.1 ms steps) and report it.
    diffGrads = []
    dDiff = 0
    if b_value > 0:
        dDiff, flatDiff, bigDelta = diffTiming(te)
        bMax = bValue(gDiffMax, riseDiff, flatDiff, bigDelta) if flatDiff >= 0 else 0
        if bMax < b_value:
            teNeed = te
            while True:
                teNeed += 1e-4
                _, fD, bD = diffTiming(teNeed)
                if fD >= 0 and bValue(gDiffMax, riseDiff, fD, bD) >= b_value:
                    break
            raise ValueError(
                f'b = {b_value} s/mm^2 not reachable at TE = {te * 1e3:.1f} ms '
                f'(max {bMax:.0f} s/mm^2), minimum TE is {teNeed * 1e3:.1f} ms'
            )

        # ╔═══ TODO 9.3 ════════════════════════════════════════════════════════════════════════
        # ║  amplitude that gives exactly b_value (bMax is the b-value at amplitude gDiffMax, b ~ G^2)
        # ╚═════════════════════════════════════════════════════════════════════════════════════
        gDiff = TODO('9.3')
        # one trapezoid per axis (component of diffDir), all with the same timing -> one block
        for ch, n in zip('xyz', diffDir):
            if abs(n) > 1e-6:

                # ╔═══ TODO 9.4 ════════════════════════════════════════════════════════════════════════
                # ║  trapezoid on channel ch: amplitude = gDiff x component n, ramps riseDiff,
                # ║  flat top flatDiff
                # ╚═════════════════════════════════════════════════════════════════════════════════════
                diffGrads.append(TODO('9.4'))
        print(f'diffusion: b = {b_value} s/mm^2, dir = {np.round(diffDir, 3)}, '
              f'G = {gDiff / system.gamma * 1e3:.1f} mT/m, delta = {(riseDiff + flatDiff) * 1e3:.2f} ms, '
              f'Delta = {bigDelta * 1e3:.2f} ms')

    # ┌─── QUESTION 9 ──────────────────────────────────────────────────────────────────────
    # │  Why do both diffusion gradients have the SAME sign? (k(t) drawing in STEP 6)
    # └─────────────────────────────────────────────────────────────────────────────────────


    # ======================================================================================
    # STEP 10: fill delays (TE and TR)
    # ======================================================================================
    # TE: whatever is left of each TE/2 half after the minimal blocks and the diffusion gradient
    # (see the diagram in STEP 8), rounded to the gradient raster.

    # ╔═══ TODO 10.1 ═══════════════════════════════════════════════════════════════════════
    # ║  delays that fill up each TE/2 half (dDiff = 0 without diffusion),
    # ║  rounded to the gradient raster:  np.round(x / rast) * rast
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    delayTE1 = TODO('10.1 delayTE1')      # before the 180° (after the 1st diffusion gradient)
    delayTE2 = TODO('10.1 delayTE2')      # after the 180° (after the 2nd diffusion gradient)

    # TR is shared by all slices: every slice gets TR / n_slices, the rest after its echo train is a delay.
    #
    #       |<----------------------------------- TR ----------------------------------->|
    #       | slice 0 | delayTR | slice 2 | delayTR | slice 4 | delayTR | slice 1 | ...    |
    #       |<---- TR / n_slices --->|
    #
    # The same slice is excited again after exactly TR.
    dSlice = dExc + dGzr + dNav + 2 * dDiff + delayTE1 + 2 * dCr + dRef + delayTE2 + dPre + nYmeas * dRO
    if tr < n_slices * dSlice:
        raise ValueError(f'TR = {tr * 1e3:.1f} ms is too short for {n_slices} slices, '
                         f'minimum is {n_slices * dSlice * 1e3:.2f} ms')

    # ╔═══ TODO 10.2 ═══════════════════════════════════════════════════════════════════════
    # ║  delay after each slice (drawing above), on the gradient raster
    # ╚═════════════════════════════════════════════════════════════════════════════════════
    delayTR = TODO('10.2')
    print(f'per slice: {dSlice * 1e3:.2f} ms (+ {delayTR * 1e3:.2f} ms delay), TR {tr * 1e3:.0f} ms')


    # ======================================================================================
    # STEP 11: build the sequence
    # ======================================================================================
    # seq.add_block(event1, event2, ...): all events of a block start together (plus their own delay),
    # the block lasts as long as its longest event. The blocks are played one after the other.
    #
    # Off-center slices: a frequency offset f shifts the excited slice to z = f / G_slice.
    # The RF pulse is then played as  B1(t) * exp(i * (2 pi f t + phase_offset)),  t from the start of the
    # pulse. At the pulse center (t_center) the phase would be 2 pi f t_center, different for every slice.
    # The magnetisation takes the phase of the pulse center, so phase_offset = phase0 - 2 pi f t_center
    # makes it the same (phase0) for all slices:
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
    #
    # 90° and 180° have different slice-select gradients -> different frequency offsets.
    phaseExc0 = rfexc.phase_offset
    phaseRef0 = rfref.phase_offset
    tCenterExc = pp.calc_rf_center(rfexc)[0]        # pulse center, measured from the start of the RF shape
    tCenterRef = pp.calc_rf_center(rfref)[0]

    # Blocks of one slice (one line = one seq.add_block call):
    #
    #   rfexc+gz_ex | gzr_ex | navPre | ro+adc | roNeg+adc | ro+adc | navRew | diff 1 | delayTE1 | cr | rfref+gz_ref | cr
    #   | diff 2 | delayTE2 | roPre+byPre | ro+byUp+adc | roNeg+byDownUp+adc | ro+byDownUp+adc | ... | ..+byDown+adc | delayTR
    #
    #   milestone 1 (no navigators, no diffusion): leave out navPre ... navRew and diff 1/2
    for iRep in range(n_reps):
        for iSlice in sliceOrder:
            # --- slice position: frequency offset + phase correction ---
            if n_slices > 1:          # milestone 4

                # ╔═══ TODO 11.1 ═══════════════════════════════════════════════════════════════════════
                # ║  frequency offset f = G_slice * z  (G_slice = amplitude of THE pulse's own slice
                # ║  gradient, z = slicePos[iSlice]) and the phase correction from the drawing above
                # ╚═════════════════════════════════════════════════════════════════════════════════════
                rfexc.freq_offset = TODO('11.1 exc freq')
                rfexc.phase_offset = TODO('11.1 exc phase')     # phaseExc0, tCenterExc
                rfref.freq_offset = TODO('11.1 ref freq')
                rfref.phase_offset = TODO('11.1 ref phase')     # phaseRef0, tCenterRef

            # --- excitation + slice rephaser ---

            # ╔═══ TODO 11.2 ═══════════════════════════════════════════════════════════════════════
            # ║  two blocks: pulse + its slice gradient, then the rephaser     (seq.add_block)
            # ╚═════════════════════════════════════════════════════════════════════════════════════
            TODO('11.2')

            # Labels are stored with a block and tell the recon what an ADC is:
            #   SLC = spatial slice index, REP = repetition, NAV = navigator line (True) or image line (False).
            # SET labels keep their value until they are set again, so they are only needed once per slice:
            # on the 1st ADC block of the slice (1st navigator, or 1st EPI line if there are no navigators).
            sliceLabels = [pp.make_label(label='SLC', type='SET', value=iSlice),
                           pp.make_label(label='REP', type='SET', value=iRep)]

            # --- navigators (ky = 0, label NAV), then rewind kx ---
            if nNav > 0:
                seq.add_block(navPre)
                for iNav in range(nNav):

                    # ╔═══ TODO 11.3 ═══════════════════════════════════════════════════════════════════════
                    # ║  ro for iNav = 0, 2, 4, ...  and roNeg for 1, 3, ...
                    # ║  Python:  a if condition else b,   iNav % 2 == 0 for even iNav
                    # ╚═════════════════════════════════════════════════════════════════════════════════════
                    roNav = TODO('11.3')
                    if iNav == 0:
                        seq.add_block(roNav, adc, *sliceLabels, pp.make_label(label='NAV', type='SET', value=True))
                        sliceLabels = []          # already set
                    else:
                        seq.add_block(roNav, adc)
                seq.add_block(navRew)

            # --- 1st diffusion gradient ---
            if diffGrads:
                seq.add_block(*diffGrads)
            if delayTE1 > 0:
                seq.add_block(pp.make_delay(delayTE1))

            # --- refocusing with crushers ---

            # ╔═══ TODO 11.4 ═══════════════════════════════════════════════════════════════════════
            # ║  three blocks: crusher | 180° pulse + its slice gradient | crusher
            # ╚═════════════════════════════════════════════════════════════════════════════════════
            TODO('11.4')

            # --- 2nd diffusion gradient (same sign: the 180° inverts the phase) ---
            if diffGrads:
                seq.add_block(*diffGrads)
            if delayTE2 > 0:
                seq.add_block(pp.make_delay(delayTE2))

            # --- EPI echo train ---
            # one block per line: RO (alternating polarity) + blip halves + ADC
            #
            #       line      0          1            2         ...      nYmeas-1
            #       RO        ro         roNeg        ro                 ro / roNeg
            #       blip      byUp       byDownUp     byDownUp           byDown
            #                 (no blip before the 1st line, no blip after the last one)
            seq.add_block(*prePhasers)
            for iLine in range(nYmeas):

                # ╔═══ TODO 11.5 ═══════════════════════════════════════════════════════════════════════
                # ║  readout polarity of line iLine (like 11.3)
                # ╚═════════════════════════════════════════════════════════════════════════════════════
                roLine = TODO('11.5')

                # ╔═══ TODO 11.6 ═══════════════════════════════════════════════════════════════════════
                # ║  blip part of line iLine: byUp, byDownUp or byDown (table above)
                # ║  first line iLine == 0, last line iLine == nYmeas - 1
                # ╚═════════════════════════════════════════════════════════════════════════════════════
                blip = TODO('11.6')
                if iLine == 0:
                    # first line: labels of the slice (if not set by a navigator), navigator flag off
                    seq.add_block(roLine, blip, adc, *sliceLabels, pp.make_label(label='NAV', type='SET', value=False))
                else:
                    seq.add_block(roLine, blip, adc)

            # --- fill up to TR / n_slices ---
            if delayTR > 0:
                seq.add_block(pp.make_delay(delayTR))


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
# BONUS tasks (milestone 4 passes? then try these, check_seq.py must still pass)
# ==========================================================================================
#   B1  Ramp sampling: run with ramp_sampling = 0, 30, 60. How do the echo spacing and TE min change?
#       Look at the k-space plot: where are the samples on the ramps?
#   B1b Bandwidth: try bwPixel = 1000, 1500, 2000, 2500. Which one gives the shortest echo spacing?
#       Why does a higher bandwidth not always help? (look at "RO: ... rise ...")
#   B2  Diffusion along (1, 1, 0): main(..., diff_axis=(1, 1, 0)). Which amplitude per axis? Why is the
#       total gradient sqrt(2) x stronger than along 'x'?
#   B3  b = 1000 s/mm^2 at TE = 47 ms: read the error message, set the minimum TE and check again.
#   B4  n_nav = 2 (even!): does your kxNavEnd still bring kx back to 0? (check_seq.py, k-space plot)
#   B5  Partial Fourier 5/8 (0.625) and 1.0: how much TE do you save? What is the minimum part_fourier?
#   B6  TE = 'min': compute the shortest TE for the given b-value automatically (a few lines in STEP 8/9).
#   B7  Non-square FOV: fov = 220e-3, n_x = n_y = 96. Which numbers in the console change?
#   B8  Simulation: SIMULATE = True (below), then GRADIENT_DELAY = 3e-6 -> what do the navigators fix?
#       Compare milestone 1 (b = 0) with milestone 2 (b = 500): what happens to the CSF (ventricles)?
#   B9  EPI distortions: fov = 240e-3 (the whole head fits into the FOV), SIMULATE = True, B0_SCALE = 0, 1, 3.
#       In which direction is the image distorted, and why only in this one? The bandwidth per pixel in
#       phase-encoding direction is only BW_PE = 1 / (echo spacing x n_y): how large is it, and how many pixels
#       does a voxel with 40 Hz off-resonance move? What helps: bwPixel, ramp_sampling, part_fourier?

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
