# Source

The Pulseq hands-on of day 1, copied from
[pulseq/MRI_together_2026_pypulseq](https://github.com/pulseq/MRI_together_2026_pypulseq)
at commit `7fe4f91345f10bf6a10da6c7d159da678faa99f4`, without its two git
submodules: the environment has pypulseq 1.5.0.post1, the version they pin,
and the MATLAB Pulseq they hold is a reference only.

Its instructions are in [`.github/README.md`](.github/README.md), which
JupyterLab's file browser hides; they are also on the repository's GitHub page.

In the environment:

- Work in your team's copy, `~/team/day1/pulseq`: the scripts write to
  `tools/export`, and `~/material` is read-only.
- The notebooks, in `notebooks/`, run in the *Python 3* kernel. Their first cell
  finds every package installed already, and their plots appear in the cells,
  zoomable.
- The level files run in a terminal, with the environment's Python:
  `python level1_beginner.py`. A terminal has no screen for plot windows, so
  they are saved in `tools/export` instead, where JupyterLab opens them.
- The simulation downloads its phantom (178 KB) the first time it runs.

To update it to a newer commit of the speakers, copy the repository at that
commit over this folder (without `.git` and the submodules) and change the
commit above.
