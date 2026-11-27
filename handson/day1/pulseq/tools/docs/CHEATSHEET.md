# pypulseq cheat sheet (version 1.5.0.post1)

Units: s, m, Hz, gradient amplitude in **Hz/m**, gradient area and k in **1/m**.
`system.gamma` = 42.576e6 Hz/T, so mT/m = amplitude / gamma * 1e3.

## Python in 12 lines (everything you need for level 1)

```python
x = 2 * np.pi * 3e-3          # numbers: 3e-3 = 0.003, always SI units (s, m, Hz)
y = x**2                      # power (not x^2!)
np.sqrt(x), np.ceil(x), np.round(x), np.max(np.abs(arr))      # numpy functions
n = int(np.ceil(x / 4)) * 4   # round UP to a multiple of 4, as an integer
a if condition else b         # one-line if, e.g.  ro if i % 2 == 0 else roNeg   (i % 2: remainder)
list(range(0, 5, 2))          # [0, 2, 4]
g = pp.make_trapezoid(channel='x', area=100, system=system)   # call with named arguments
g.area, g.amplitude           # attributes of an event;  print(g) shows all of them
rf, gz, gzr = pp.make_sinc_pulse(...)   # a function can return several objects
seq.add_block(*my_list)       # * unpacks a list into single arguments
help(pp.make_trapezoid)       # documentation of a function (in a Python console)
```

## Events

| Function | Returns / note |
|---|---|
| `pp.Opts(max_grad=, grad_unit='mT/m', max_slew=, slew_unit='T/m/s', ...)` | system limits, pass `system=system` everywhere |
| `pp.make_sinc_pulse(flip_angle, duration, slice_thickness, time_bw_product, apodization, return_gz=True, use=, system=)` | `rf, gz, gzr` |
| `sigpy_n_seq(flip_angle, duration, slice_thickness, time_bw_product, phase_offset, return_gz=True, pulse_cfg=pp.SigpyPulseOpts(pulse_type='slr', ptype='se'), use=, plot=False, system=)` | `rf, gz, gzr` (from `pypulseq.make_sigpy_pulse`) |
| `pp.make_trapezoid(channel, area=, system=)` | shortest trapezoid/triangle with this area |
| `pp.make_trapezoid(channel, area=, duration=, system=)` | given total duration |
| `pp.make_trapezoid(channel, amplitude=, rise_time=, flat_time=, system=)` | fully specified |
| `pp.make_adc(num_samples=, dwell=, delay=, system=)` | ADC; `adc.delay` can be changed later |
| `pp.make_delay(d)` | pure delay block |
| `pp.make_label(label='SLC', type='SET', value=...)` | labels for the recon (`SLC`, `REP`, `NAV`, ...) |

Useful attributes: `g.amplitude`, `g.area`, `g.flat_area`, `g.rise_time`, `g.flat_time`, `g.fall_time`, `g.delay`,
`rf.freq_offset`, `rf.phase_offset`, `rf.delay`, `rf.signal`.

## Tools

| Function | What it does |
|---|---|
| `pp.calc_duration(e1, e2, ...)` | duration of a block made of these events |
| `pp.calc_rf_center(rf)` | `(t_center, index)`, t measured from the start of the RF shape (add `rf.delay`) |
| `pp.scale_grad(g, s)` | gradient scaled by s (area etc. updated) |
| `pp.split_gradient_at(grad, time_point, system=)` | splits a trapezoid into extended-trapezoid parts |
| `pp.align(left=..., center=..., right=...)` | sets delays so the events start / are centered / end together |
| `pp.add_gradients([g1, g2], system=)` | sum of gradients on the same axis (one waveform) |
| `compare_ref_profiles(exc, [(rf, gz, label), ...], system=, slice_thickness=)` | (from `tools.rf_profile`) RF shapes with peak B1, excitation vs. refocusing profile, spin-echo profile |
| `seq.add_block(e1, e2, ...)` | all events of a block start at the same time; block duration = longest event |
| `seq.check_timing()` | `(ok, errors)` |
| `seq.plot(time_range=(t0, t1), stacked=True)` | sequence diagram |
| `seq.calculate_kspace()` | `k_adc, k, t_exc, t_ref, t_adc` |
| `seq.set_definition(key=, value=)`, `seq.write(file)` | export |

## Formulas

**RF pulse:** bandwidth = TBW / duration, slice gradient G = bandwidth / thickness, peak B1 = max|rf.signal| / gamma.

**Readout bandwidth:** BW per pixel ≈ 1 / (ADC window of one line). EPI: typically ~1000 – 2500 Hz/pixel.

**k-space:** Δk = 1 / FOV, extent of a line = N / FOV. k(t) = ∫ G dt  (G in Hz/m).

**Triangle with area A and slew rate S** (amplitude in Hz/m, slew in Hz/m/s): duration = 2·sqrt(A / S).

**Ramp sampling:** ADC window T, of which a part s at the start and at the end lies on the ramps (slope S = G / t_rise):

    area inside the ADC window = G·T − S·s²   (must be Nx / FOVx)

**Spin echo timing:** 180° center at TE/2 after the 90° center, echo (kx = ky = 0) at TE.

**Stejskal-Tanner b-value** for two trapezoids (amplitude G in Hz/m, ramp ε, δ = ε + flat, onset distance Δ):

    b = (2π G)² [ δ² (Δ − δ/3) + ε³/30 − δ ε²/6 ]       (s/m² → ·1e-6 for s/mm²)

b ∝ G², so for a fixed timing: G = G_max · sqrt(b / b_max).

**Off-center slices:** f = G_slice · z,  phase_offset = φ0 − 2π · f · t_center  (per pulse, with its own G_slice).
