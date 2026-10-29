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

The pipeline lives in
[mritogetherthon-pipeline](https://github.com/mcencini/mritogetherthon-pipeline),
with one folder per stage and a contract per stage, in the stage's README,
naming the files it reads and writes. Its README explains how the stages are
run, and how they are joined on day 5.

Each team works in its own folder of the stage it takes on,
`stages/<stage>/<team>/`, so that the teams' pull requests never conflict,
whether a stage has one team or several.

## Setting up your team

One member of the team, the team lead, forks the pipeline repository on GitHub
and adds the teammates to the fork in *Settings → Collaborators*. Every member
then clones the fork in a JupyterLab terminal:

```bash
gh repo clone <team-lead>/mritogetherthon-pipeline
```

and the team lead starts the team's folder, and pushes it:

```bash
python -m pipeline new <stage> <team>                    # in Python
python -m pipeline new <stage> <team> --language julia   # in Julia
```

## Every day

1. **Start.** Open JupyterLab and pull your teammates' work:
   `git pull` in your clone.
2. **Work** in notebooks to explore, and move what works into your folder's
   `run.py` (or `run.jl`), which is what the pipeline runs. Run it, and check
   the files it writes against the stage's contract, with
   `python -m pipeline check <stage>/<team>`.
3. **Commit and push** at the end of the session, and whenever something works:

   ```bash
   git add stages/<stage>/<team>
   git commit -m "What changed"
   git push
   ```

   Notebooks are committed without their outputs (the environment strips them),
   so that teammates' changes merge as code.
4. **Open a pull request** from your team's fork to the pipeline repository by
   the end of each day. Its checks run your stage in the same environment as
   yours, and accept a pull request that changes your team's folder alone.

## Large files

Do not commit data or results. The pipeline repository's `data/` holds the
files every run starts from, and each stage writes its results under
`outputs/`, which git ignores. A stage that needs other data downloads it in its `run`
entry point, from a public, permanent address such as Zenodo.
