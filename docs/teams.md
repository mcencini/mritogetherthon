# Working as a team

The TogetherThon builds one open-source pipeline for placenta diffusion MRI,
from the sequence to the analysis. Teams build its parts during days 1 to 4,
and on day 5 the parts are joined into the complete pipeline. This page explains
how your work is saved and how it reaches the final pipeline.

## Where your work lives

- **On your computer.** The environment's home folder is the `mritogetherthon`
  folder in your own home folder (`%USERPROFILE%\mritogetherthon` on Windows).
  Everything you save in JupyterLab is there, and it stays through every
  restart of your computer, of Docker and of the environment, and through every
  update of the environment.
- **On GitHub.** Your team's work is a fork of the pipeline repository. Push to
  it at the end of every session: that is the copy your teammates see, the copy
  that is merged, and your backup.

Only what you put under your home folder is kept. Packages you install with
`pip install --user` or Julia's `Pkg.add` land there too, but the pipeline must
not depend on them: ask for a package in a
[Discussion](https://github.com/mcencini/mritogetherthon/discussions) so that it
is added to the environment, for everyone.

## Before the TogetherThon: log in to GitHub, once

In a JupyterLab terminal:

```bash
git config --global user.name "Your Name"
git config --global user.email you@example.org
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

`gh auth login` prints a code: open <https://github.com/login/device> in your
browser and enter it. Your login is kept in your folder, so you do this once.
`check-setup` then shows ✅ for git and GitHub.

## The pipeline repository

The pipeline repository is announced before the TogetherThon. The pipeline
lives in one repository, with one folder per stage, and a
contract per stage that names the files it reads and writes:

| Stage | Day | Reads | Writes |
|---|---|---|---|
| `sequence` | 1 | protocol parameters | Pulseq `.seq` |
| `simulation` | 2 | `.seq`, the placenta phantom | raw data, ISMRMRD `.mrd` |
| `reconstruction` | 2 | `.mrd` | images, NIfTI `.nii.gz` |
| `motion` | 3 | `.mrd`, or images | corrected images, NIfTI |
| `analysis` | 4 | images, NIfTI | parameter maps, NIfTI, and `metrics.json` |

Each team works in its own folder of the stage it takes on,
`stages/<stage>/<team>/`, and provides a `run` entry point that honours the
stage's contract. Because no two teams write in the same folder, their pull
requests never conflict, whether a stage has one team or several.

On day 5 the stages are joined into the pipeline, which runs them one after the
other. `pipeline.yaml` names, for each stage, the team whose implementation the
pipeline runs:

- **A stage with one team** is merged as it is: its implementation is the
  stage's.
- **A stage with several teams** is decided first: the teams' implementations
  run on the same data, their results are compared with the analysis stage's
  metrics, and the stage's implementation is chosen, or is merged from the best
  parts of several, by the stage's teams together.

Because every implementation honours the same contract, any choice runs with
the other stages, and the comparison is fair.

## Every day

1. **Start.** Open JupyterLab and pull your teammates' work:
   `git pull` in your clone.
2. **Work** in notebooks to explore, and move what works into the stage's
   `run` entry point, which is what the pipeline calls.
3. **Commit and push** at the end of the session, and whenever something works:

   ```bash
   git add stages/<stage>/<team>
   git commit -m "What changed"
   git push
   ```

   Notebooks are committed without their outputs (the environment strips them),
   so that teammates' changes merge as code.
4. **Open a pull request** from your team's fork to the pipeline repository by
   the end of each day. Its checks run your stage against the contract in the
   same environment as yours, so what passes there runs in the final pipeline.

## Setting up your team

One member of the team, the team lead:

1. Forks the pipeline repository on GitHub.
2. Adds the teammates to the fork in *Settings → Collaborators*.
3. Creates the team's folder from the stage's template,
   `stages/<stage>/_template`, and pushes it.

Every member then clones the fork in a JupyterLab terminal:

```bash
gh repo clone <team-lead>/<pipeline-repository>
```

## Large files

Do not commit data or results. The environment carries the phantoms and the
data of the sessions, and each stage writes its results under `outputs/`,
which git ignores. A stage that needs other data downloads it in its `run`
entry point, from a public, permanent address such as Zenodo.
