# Hands-on: diffusion-weighted spin-echo EPI with pypulseq

In this workshop (about 3 hours) you program a complete **multi-slice diffusion-weighted spin-echo EPI**
with [pypulseq](https://github.com/imr-framework/pypulseq), the Python version of [Pulseq](https://pulseq.github.io):

```
90° | navigators | diffusion | 180° | diffusion | EPI echo train (ramp sampling, partial Fourier)     (per slice)
```

Your sequence is checked automatically, and with one switch you simulate it with
[MRzero](https://github.com/MRsources/MRzero-Core) and see the reconstructed image.

You do **not** need much Python or pypulseq experience: choose level 1 and follow the boxes in the file.

---

## 1. Working Environment
There two main options for working with this tutorial, which are described in the following subsections.

### 1.1. In the browser: Google Colab (nothing to install)

Click on your level (you need a Google account):

| Level | |
|---|---|
| Level 1 (beginner) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/andih98/MRI_together_pypulseq/blob/main/notebooks/level1_beginner.ipynb) |
| Level 2 (advanced) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/andih98/MRI_together_pypulseq/blob/main/notebooks/level2_advanced.ipynb) |
| Level 3 (expert) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/andih98/MRI_together_pypulseq/blob/main/notebooks/level3_expert.ipynb) |
| Reference solution (try without it first!) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/andih98/MRI_together_pypulseq/blob/main/notebooks/solution.ipynb) |

1. **File → Save a copy in Drive** first. Otherwise your work is lost when you close the tab.
2. Run the first code cell (**setup**, ~1 min, once per session).
3. Work through the cells from top to bottom: every STEP is one cell, the notebook explains the rest.

The notebooks contain the same material as the level files (sections 2 and 3 apply to them, too). Instead of
running the whole file, you run one STEP after the other, set `MILESTONE` in the parameter cell, and the check
and the simulation are cells at the end. The rest of this page is about working on your own computer.

---

### 1.2. Setup on your own computer (before the workshop, ~10 min, mostly waiting)

**1. Install Python and VS Code** (skip what you already have):

| | Where | Note |
|---|---|---|
| **Python** (any version from 3.8 on) | https://www.python.org/downloads/ | **Windows:** tick *"Add python.exe to PATH"* in the installer |
| **VS Code** (recommended) | https://code.visualstudio.com | then install the extension *Python* (by Microsoft); VS Code suggests it when you open a `.py` file |

The workshop brings its own Python 3.13, so the version on your computer does not matter.

**2. Download this repository**, either way:

- **with Git** (https://git-scm.com/downloads): copy the URL from the green **Code** button on this page, then in a terminal
  ```bash
  git clone --recursive <URL>
  ```
- **without Git:** green **Code** button → **Download ZIP**, then unzip it.

**3. Start level 1 once.** Open the folder in VS Code (*File → Open Folder…*), open `level1_beginner.py` and press
**▶** (top right). Or in a terminal, inside the folder:

```bash
python level1_beginner.py          # Windows: python or py,  macOS / Linux: python3
```

**The first start sets up everything automatically** (only once, 3–10 min depending on your internet connection,
~1.5 GB on disk): Python 3.13, a separate environment `.venv` with all packages (pypulseq, MRzero for the
simulation, ...), and a check that everything works. At the end it shows

```
All good, have fun!
...
>>> TODO 2.1 is not done yet -> search for "TODO 2.1" in this file
    .../level1_beginner.py:218
```

That is the expected result: your first task is waiting. You are ready for the workshop.

Afterwards VS Code asks whether to use the new environment `.venv`: click **Yes**. (Or `Ctrl+Shift+P` →
*Python: Select Interpreter* → `.venv`.) Running the files works anyway, but debugging (F5) and code completion
need it.

---

## 2. Choose your level

All levels build **the same sequence**. Only the amount of help differs.
You can switch at any time: stuck in level 2? The same step in level 1 has more help.

| File | For you if ... | What you do |
|---|---|---|
| `level1_beginner.py` | you have never written a Pulseq sequence | The structure is given. You fill in ~55 small gaps, each one in a box (`TODO 3.2a`). Every box tells you which pypulseq function to use. The values you read off the ASCII drawings, or you choose them yourself (pulse durations, bandwidths, ...) and test them with the plots. Plus questions to think about and bonus tasks. |
| `level2_advanced.py` | you know MR physics and some Python / Pulseq | Per step only the **idea**, the drawings, the specification and useful functions. You write each step yourself. Plus challenges. |
| `level3_expert.py` | you have written Pulseq sequences before | A diagram of the sequence. Nothing else. |

Level 3 / your own scripts: write them in this folder and put `import tools.workshop_env` as the first line, then they
run in the workshop environment like the level files (and `from tools.check_seq import run_check` checks your file).

---

## 3. How to work (levels 1 and 2)

**Run the file often** (▶ in VS Code, or `python level1_beginner.py`). Every gap is a `TODO(...)` call: the script
stops at the first open gap and tells you its number. Search for it (`Ctrl+F`), fill it in, run again.

**Milestones.** The sequence is built in 4 milestones. Set `MILESTONE = 1, 2, 3, 4` at the bottom of the file.
Steps of later milestones are skipped automatically, so after each milestone you have a working sequence.

| Milestone | Feature | Steps | Guide time |
|---|---|---|---|
| 1 | spin-echo EPI: RF pulses, EPI readout with ramp sampling, partial Fourier, crushers, TE timing | 2, 3, 4, 6, 8, 10, 11 | 90 min |
| 2 | + diffusion gradients with exact b-value | 9 | 35 min |
| 3 | + navigator echoes | 5, 11 | 20 min |
| 4 | + multi-slice (interleaved, off-center frequency and phase) | 7, 11 | 25 min |

**Automatic check.** Each run writes your sequence (`tools/export/my_dwepi_M<milestone>.seq`) and checks it right
away: timing, hardware limits, k-space, TE, b-value, navigators, slices. Every `FAIL` comes with a hint.

**Simulation.** Set `SIMULATE = True` at the bottom of the file: after the check, the image is simulated and
reconstructed (a few seconds). Things to try:
- milestone 1 (b = 0) vs. milestone 2 (b = 500): the CSF in the ventricles is bright at b = 0 and dark at b = 500;
- `GRADIENT_DELAY = 3e-6`: an N/2 ghost appears in the uncorrected image, the navigators (milestone 3) remove it.
- `B0_SCALE = 3` (off-resonance of the phantom x 3) with `fov = 240e-3`: EPI distortions in phase-encoding direction.
  The phantom has a realistic B0 map (about -46 ... +43 Hz, strongest above the sinuses); `B0_SCALE = 0` switches it off.

Only **one k-space** is simulated: the slice at the isocenter, first repetition. The other slices and repetitions
are cut out of the sequence before the simulation (the script tells you so), because each of them would cost
the same simulation time again, and the phantom is 2D (it only exists at z = 0).

**Plots.** The sequence diagram and the k-space trajectory show most errors.
Navigate like in MATLAB: **mouse wheel** zooms the time axis at the cursor (shift: y axis, ctrl: both),
the toolbar (or the keys `o` zoom, `p` pan, `h` home) zooms and pans. All channels share the time axis.
**The script continues when you close the plot windows.**

**Help.** [`tools/docs/CHEATSHEET.md`](../tools/docs/CHEATSHEET.md): pypulseq functions, formulas, Python basics.
`print(ro)` shows all attributes of an event. The full solution is in
[`tools/solution/tut_dw_se_epi_rs.py`](../tools/solution/tut_dw_se_epi_rs.py) (try without it first!).

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `python` is not found | Windows: reinstall Python with *"Add python.exe to PATH"*, or use `py` instead of `python`. macOS / Linux: use `python3`. |
| The first start stops with *"The installation failed"* | Usually the internet connection (or a proxy). Run it again: `python tools/install.py`. It continues where it stopped. |
| Something is broken in the environment | `python tools/install.py --fresh` deletes `.venv` and sets it up again. |
| *"download failed"* for uv / Python 3.13 (firewall) | Install Python 3.13 from python.org and start the level file with it: `py -3.13 level1_beginner.py` (Windows) or `python3.13 level1_beginner.py`. The setup then uses this Python. |
| The script seems to hang | A plot window is open (maybe behind other windows): close it, the script continues. |
| No plot windows, *"saved ... .png"* instead | No display (SSH, container): the plots are in `tools/export/`. On a normal desktop: `python tools/install.py`. |
| `TE ... is too short` / `b ... not reachable` | Your pulses / bandwidth made the sequence longer: use the minimum TE from the message (`te=...` in `MILESTONES`). |
| `>>> TODO 2.1 is not done yet` | That's how it should be: fill in that gap next (Ctrl+click on the line number jumps there). |
| Not enough disk space for the simulation (~1 GB) | `python tools/install.py --no-sim` installs everything except the simulation. |
| You manage your Python environments yourself | Set the environment variable `WORKSHOP_NO_VENV=1`, then the level files use the current Python. Packages: `pip install -r tools/requirements.txt -r tools/requirements-sim.txt` (from the `tools` folder). |

---

## What is where

```
level1_beginner.py          start here (beginner)
level2_advanced.py          start here (advanced)
level3_expert.py            start here (expert)
notebooks/                  the three levels and the solution as Google Colab notebooks (section 0)
tools/                      everything else -- you do not need to open it
    install.py              the setup (runs automatically on the first start)
    workshop_env.py         lets the level files run in the workshop environment
    check_setup.py          installation check
    check_seq.py            automatic check of a .seq file (run by the level files)
    rf_profile.py           plot helpers: RF slice profiles (Bloch simulation), zoomable plots
    simulation/             MRzero simulation of the isocenter k-space + reconstruction
    solution/               reference solution, fully commented
    make_colab.py           creates notebooks/*.ipynb from the level files (after changing a level file:
                            python tools/make_colab.py)
    docs/CHEATSHEET.md      pypulseq functions, formulas, Python basics
    external/               git submodules: pypulseq 1.5.0.post1 (installed from here), Pulseq (MATLAB, reference)
    requirements*.txt       the Python packages (installed by install.py)
    export/                 everything the scripts write: .seq files, raw data, plots (not in git)
.venv/                      the workshop environment with Python 3.13 (created by install.py, not in git)
```

The setup in detail (`tools/install.py`, each step is skipped if it is already done):
1. downloads the git submodules if needed (with a ZIP download, pypulseq 1.5.0.post1 comes from PyPI instead);
2. downloads [uv](https://github.com/astral-sh/uv) (a small tool) to `tools/.uv`, which downloads Python 3.13;
3. creates the environment `.venv` with it (if uv is not available: with your Python, if it is 3.10 – 3.13);
4. installs `tools/requirements.txt` and `tools/requirements-sim.txt` (MRzero, PyTorch **CPU** version, no CUDA);
5. installs PyQt6 if no GUI toolkit for plot windows is available;
6. runs the installation check.

Everything stays inside the repository folder: deleting the folder removes everything.

---

## Parameters

All parameters are arguments of `main()` in levels 1 and 2 and the solution. Change them in the `MILESTONES`
dictionary at the bottom of the file, e.g. `4: dict(b_value=1000, n_nav=3, n_slices=5, te=60e-3)`.

| Parameter | Meaning |
|---|---|
| `fov`, `n_x`, `n_y`, `slice_thickness` | geometry / matrix; `fov` is one value (square) or `(fov_x, fov_y)` |
| `n_slices`, `slice_gap_factor` | number of slices; center-to-center distance in units of the slice thickness. Slice `n_slices // 2` is at the isocenter, acquisition is interleaved |
| `te`, `tr`, `n_reps` | timing (`tr` is shared by all slices) |
| `b_value`, `diff_axis` | b-value [s/mm²] (0 = no diffusion), direction `'x'`, `'y'`, `'z'` or a vector, e.g. `(1, 1, 0)` |
| `ramp_sampling` | % of the ADC window on the readout ramps (0 = flat top only) |
| `part_fourier` | fraction of phase-encoding lines measured, e.g. `0.75` = 6/8 |
| `n_nav` | navigator echoes (ky = 0) after the excitation, 0 = none |

## Good to know

- One b-value and one direction per file. No fat saturation.
- System limits `max_grad = 90 mT/m`, `max_slew = 130 T/m/s`: adapt them to your scanner before measuring.
  PNS and forbidden echo spacings are not checked.
- Simulation: only the isocenter k-space, 2D phantom (141 × 161 voxels of 1.4 × 1.2 mm, CSF with a higher diffusion coefficient),
  no eddy currents. MRzero uses a phase-graph simulation with simplified RF pulses: slice profiles are not simulated.
- Reconstruction: single coil, partial Fourier by zero-filling.
- `seq.test_report()` shows a wrong TE (it takes the first navigator echo); the actual TE is the `te` parameter.

## License

[MIT](../LICENSE). The libraries in `tools/external` keep their own (MIT) licenses.

## Acknowledgements

Based on the pypulseq example `write_epi_se_rs.py` and the Pulseq demo `writeEpiSpinEchoRS.m`.
Uses [pypulseq](https://github.com/imr-framework/pypulseq) and [Pulseq](https://github.com/pulseq/pulseq)
(MIT licensed) as git submodules, [MRzero](https://github.com/MRsources/MRzero-Core) for the simulation and
[uv](https://github.com/astral-sh/uv) for the setup.

The workshop material was developed with the help of Claude (Anthropic).
