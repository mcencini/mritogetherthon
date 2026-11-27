"""Generate the Google Colab notebooks (notebooks/*.ipynb) from the level files.

The level files (level1_beginner.py, ...) are the only source: after changing them, run

    python tools/make_colab.py

and commit the regenerated notebooks. Every STEP of a level file becomes one notebook cell, so a cell can
always be run again (e.g. after a correction) without side effects on the cells above it.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'notebooks'
REPO = 'andih98/MRI_together_pypulseq'
BRANCH = 'main'
LEVELS = [('level1_beginner', 'LEVEL 1 (beginner)'), ('level2_advanced', 'LEVEL 2 (advanced)'),
          ('level3_expert', 'LEVEL 3 (expert)')]


def badge(name):
    url = f'https://colab.research.google.com/github/{REPO}/blob/{BRANCH}/notebooks/{name}.ipynb'
    return f'[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)]({url})'


def md(text):
    return {'cell_type': 'markdown', 'metadata': {}, 'source': text.strip('\n').splitlines(keepends=True)}


def code(text):
    return {'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
            'source': text.strip('\n').splitlines(keepends=True)}


def fenced(text):
    return '```text\n' + text.strip('\n') + '\n```'


SETUP = f'''# ▶ Run this cell first (once per session, ~1 min): gets the workshop files and installs the packages.
import importlib
import importlib.util
import os
import sys

REPO_URL = 'https://github.com/{REPO}.git'
if 'google.colab' in sys.modules:
    if not os.path.isdir('/content/MRI_together_pypulseq'):
        !git clone --quiet --depth 1 -b {BRANCH} {{REPO_URL}} /content/MRI_together_pypulseq
    %cd /content/MRI_together_pypulseq
    from google.colab import output
    output.enable_custom_widget_manager()
elif os.path.basename(os.getcwd()) == 'notebooks':      # local Jupyter: work in the repository folder
    %cd ..
sys.path.insert(0, os.getcwd())


def missing(*modules):      # quick check: which packages are not installed yet?
    importlib.invalidate_caches()
    return [m for m in modules if importlib.util.find_spec(m) is None]


# %pip installs into the environment of this notebook (also in a local Jupyter); skipped if already there
if missing('pypulseq', 'sigpy', 'ipympl'):
    %pip install --quiet -r notebooks/requirements-colab.txt
if missing('MRzeroCore'):
    %pip install --quiet MRzeroCore
    if missing('MRzeroCore'):
        print('MRzero (only for the simulation) could not be installed.')
if missing('pypulseq'):
    print('pypulseq is missing -- the installation failed, see the messages above.')
try:
    get_ipython().run_line_magic('matplotlib', 'widget')     # zoomable plots (toolbar: zoom, pan, home)
except Exception:
    get_ipython().run_line_magic('matplotlib', 'inline')     # fallback: static plots
print('setup done')'''

HOWTO = '''## How to work in Colab

1. **File → Save a copy in Drive** first. Otherwise your work is lost when you close the tab.
2. Run the **setup cell** below (▶ or `Shift+Enter`), once per session (~1 min).
3. Run the cells **from top to bottom**. Every STEP is one cell. Fill in the gaps in the code and run the cell again.
   A cell stops at the first open gap: `>>> TODO 2.1 is not done yet ...`
4. Changed a cell? Run it and all cells below it again: click into it, then **Runtime → Run after**
   (or run it, then the cells below one by one).
5. **Milestones:** set `MILESTONE` in the parameter cell, then **Runtime → Run all**.
   Steps of later milestones are skipped automatically.
6. The **check** cell at the end checks your sequence (PASS / FAIL + hint), the **simulation** cell shows the image.
7. Session lost ("runtime disconnected")? Your code is saved in the notebook: run the setup cell again,
   then **Runtime → Run all**.
'''


def parse(py):
    s = py.read_text(encoding='utf-8')
    doc = s.split('"""')[1]
    lines = s.splitlines()
    i_def = next(i for i, l in enumerate(lines) if l.startswith('def main('))
    i_sig = next(i for i in range(i_def, len(lines)) if lines[i] == '):')
    i_ret = next(i for i in range(i_sig, len(lines)) if lines[i] == '    return seq')
    header = lines[:i_def]
    imports = [l.split('  # noqa')[0] for l in header if (l.startswith('import ') or l.startswith('from '))
               and 'workshop_env' not in l and not l.startswith('import traceback')]
    params = []
    for l in lines[i_def + 1:i_sig]:
        m = re.match(r'^\s+(\w+): [^=]+= (.+?),\s*(#.*)?$', l)
        if m and m.group(1) not in ('plot', 'test_report', 'write_seq', 'seq_filename'):
            params.append((f'{m.group(1)} = {m.group(2)}'.ljust(52) + (m.group(3) or '')).rstrip())
        elif l.strip().startswith('# ----'):
            params.append(l.strip())
    body = [l[4:] if l.startswith('    ') else l for l in lines[i_sig + 1:i_ret]]
    tail = '\n'.join(lines[i_ret + 1:])
    milestones = re.search(r'^MILESTONES = \{.*?^\}', tail, re.S | re.M)
    milestones = milestones.group(0) if milestones else None
    extras = re.search(r'^# (BONUS|CHALLENGES).*?\n# =+\n(.*?)\n\n', tail, re.S | re.M)
    return doc, imports, params, body, milestones, extras


def steps(body):
    """split the body at the STEP separators: [(title, code), ...]"""
    out, cur, title = [], [], None
    i = 0
    while i < len(body):
        if body[i].startswith('# =====') and i + 1 < len(body) and body[i + 1].startswith('# STEP '):
            if title is not None:
                out.append((title, cur))
            title, cur = body[i + 1][2:].strip(), []
            i += 3                                   # separator, title, separator
            continue
        cur.append(body[i])
        i += 1
    out.append((title, cur))
    return [(t, '\n'.join(c).strip('\n')) for t, c in out]


def step_cells(body):
    cells = []
    for t, c in steps(body):
        if t is None:
            continue
        if t.startswith('STEP 11'):
            c = ('seq = pp.Sequence(system)      # a new, empty sequence: this cell can be run again\n\n' + c)
        m = re.match(r'(STEP \d+: .*?)\s{2,}\((.*)\)\s*$', t)
        head = f'## {m.group(1)}\n\n*{m.group(2)}*' if m else f'## {t}'
        cells.append(md(head))
        cells.append(code(c))
    return cells


def simulation_cells():
    cells = []
    cells.append(md('''## Simulation (MRzero)

Simulates the k-space of the slice at the isocenter and reconstructs the image (a few seconds).
Only **one** k-space is simulated: the other slices / repetitions are cut out of the sequence, because each of them
would cost the same simulation time again, and the phantom is 2D (it only exists at z = 0).

Things to try: milestone 1 (b = 0) vs. milestone 2 (b = 500): what happens to the CSF in the ventricles?
`GRADIENT_DELAY = 3e-6`: an N/2 ghost appears without correction; the navigators (milestone 3) remove it.
`B0_SCALE = 3` (with `fov = 240e-3` in the parameter cell): EPI distortions in phase-encoding direction.'''))
    cells.append(code('''GRADIENT_DELAY = 0.0          # in SECONDS: e.g. 3e-6 = a 3 us gradient delay
B0_SCALE = 1.0                # off-resonance of the phantom: 0 = none, 1 = realistic, 3 = strong -> distortions

from tools.simulation.simulate import run
run(seq_filename, GRADIENT_DELAY, B0_SCALE);      # the ; hides the return value'''))
    return cells


def level_notebook(name, label):
    doc, imports, params, body, milestones, extras = parse(ROOT / f'{name}.py')
    title = f'# Diffusion-weighted spin-echo EPI with pypulseq: {label}'
    intro = doc.strip('\n')
    first = intro.index('One slice of the sequence') if 'One slice of the sequence' in intro else 0
    cut = min(intro.index(m) for m in ('How to work with this file', 'Work in 4 milestones') if m in intro)
    overview = intro[first:cut].rstrip()
    help_text = ''
    if 'Everything YOU have to do' in intro:                     # level 1: the boxes and the tips
        a = intro.index('Everything YOU have to do')
        help_text = intro[a:intro.index('Work in 4 milestones')].rstrip()
        b = intro.index('Many values are YOUR choice')
        help_text += '\n\n' + intro[b:].rstrip()
        help_text = help_text.replace('(te=... in MILESTONES at the bottom of the file)', '(te in the parameter cell)')

    cells = [md(title + '\n\n' + badge(name)), md(fenced(overview)), md(HOWTO)]
    if help_text:
        cells.append(md(fenced(help_text)))
    cells.append(code(SETUP))

    cells.append(md('## Imports and helpers'))
    cells.append(code('import traceback\n' + '\n'.join(imports) + '''

EXPORT = Path('tools/export')      # your .seq files go here


class TodoNotDone(Exception):
    def _render_traceback_(self):      # short message in the notebook instead of a long traceback
        tb = traceback.extract_tb(self.__traceback__)
        return [f'>>> {self}   (line {tb[-2].lineno if len(tb) > 1 else "?"} of the cell)']


def TODO(task):
    """Placeholder for code you still have to write."""
    raise TodoNotDone(f'TODO {task} is not done yet -> search for "TODO {task}" in this cell')'''))

    cells.append(md('## Parameters\n\nSet the milestone you are working on, then **Runtime → Run all**.'))
    cells.append(code('MILESTONE = 1\n\n' + milestones + '\n\n' + '\n'.join(params) + '''

# the milestone sets b_value, n_nav and n_slices (change them in MILESTONES above)
globals().update(MILESTONES[MILESTONE])
seq_filename = str(EXPORT / f'my_dwepi_M{MILESTONE}.seq')
plot, test_report, write_seq = True, False, True
print(f'milestone {MILESTONE}: b = {b_value}, {n_nav} navigators, {n_slices} slice(s)')'''))

    cells += step_cells(body)

    cells.append(md('## Check\n\nChecks the written sequence: timing, hardware limits, k-space, TE, b-value, '
                    'navigators, slices. Every FAIL comes with a hint.'))
    cells.append(code('run_check(seq_filename, milestone=MILESTONE)'))
    cells += simulation_cells()
    if extras:
        text = '\n'.join(l[2:] if l.startswith('# ') else l.lstrip('#') for l in extras.group(2).splitlines())
        text = (text.replace('SIMULATE = True (below), then GRADIENT_DELAY = 3e-6',
                             'the simulation cell, then GRADIENT_DELAY = 3e-6')
                    .replace('SIMULATE = True, B0_SCALE', 'the simulation cell with B0_SCALE')
                    .replace('fov = 240e-3, SIMULATE = True, B0_SCALE', 'fov = 240e-3, the simulation cell with B0_SCALE')
                    .replace('SIMULATE = True', 'the simulation cell')
                    .replace('SIMULATE = True and GRADIENT_DELAY = 3e-6 (below)',
                             'the simulation cell with GRADIENT_DELAY = 3e-6'))
        text = re.sub(r'main\(\.\.\., (\w+)=(.*?)\)\.', r'\1 = \2 in the parameter cell.', text)
        head = 'BONUS tasks' if extras.group(1) == 'BONUS' else 'CHALLENGES'
        cells.append(md(f'## {head}\n\nMilestone 4 passes? Then try these (the check must still pass):\n\n'
                        + fenced(text)))
    return cells


SOLUTION_HOWTO = '''## How to use this notebook

This is the **reference solution** of the workshop: the complete sequence, fully commented.
Try the level notebooks first!

1. Run the **setup cell** below (once per session, ~1 min), then **Runtime → Run all**.
2. Every STEP is one cell, with the same explanations and drawings as in the levels.
3. Change parameters in the parameter cell (e.g. `b_value = 0`, `n_slices = 1`, `ramp_sampling = 60`)
   and run all cells again: the check and the simulation at the end show the effect.
'''


def solution_notebook():
    src = 'tools/solution/tut_dw_se_epi_rs.py'
    doc, imports, params, body, _, _ = parse(ROOT / src)
    intro = doc.strip('\n')
    overview = intro[intro.index('One slice of the sequence'):intro.index('The script is split')].rstrip()
    name = 'solution'
    cells = [md('# Diffusion-weighted spin-echo EPI with pypulseq: REFERENCE SOLUTION\n\n' + badge(name)),
             md(fenced(overview)), md(SOLUTION_HOWTO), code(SETUP),
             md('## Imports'),
             code('\n'.join(l for l in imports if not l.startswith('import sys'))
                  + "\n\nEXPORT = Path('tools/export')      # the .seq file goes here"),
             md('## Parameters\n\nAll features are switched on. The milestones of the levels correspond to\n'
                '`b_value = 0, n_nav = 0, n_slices = 1` (milestone 1), `b_value = 500` (2), `n_nav = 3` (3) and '
                '`n_slices = 5` (4).'),
             code('\n'.join(params) + """

seq_filename = str(EXPORT / 'solution.seq')
plot = True
test_report = False         # True: pypulseq's test report (long)
write_seq = True""")]
    cells += step_cells(body)
    cells.append(md('## Check'))
    cells.append(code('from tools.check_seq import run_check\n\nrun_check(seq_filename)'))
    cells += simulation_cells()
    return cells


def expert_notebook():
    doc = (ROOT / 'level3_expert.py').read_text(encoding='utf-8').split('"""')[1]
    lines = doc.strip('\n').splitlines()
    return [md(f'# {lines[0]}\n\n{badge("level3_expert")}'),
            md(fenced('\n'.join(lines[2:]))),
            code(SETUP),
            code('')]


def write(name, cells):
    nb = {'nbformat': 4, 'nbformat_minor': 0,
          'metadata': {'colab': {'provenance': [], 'toc_visible': True},
                       'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
                       'language_info': {'name': 'python'}},
          'cells': cells}
    path = OUT / f'{name}.ipynb'
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'written {path.relative_to(ROOT)} ({len(cells)} cells)')


def main():
    OUT.mkdir(exist_ok=True)
    for name, label in LEVELS[:2]:
        write(name, level_notebook(name, label))
    write('level3_expert', expert_notebook())
    write('solution', solution_notebook())


if __name__ == '__main__':
    main()
