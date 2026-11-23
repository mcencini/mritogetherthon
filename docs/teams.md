# Working as a team

Every team of the TogetherThon builds the same pipeline for placenta diffusion
MRI, from the sequence to the analysis, one stage a day. This page explains
where your work lives, how the team shares it, and how it reaches the
organisers.

## Two folders

- **`material`** holds the organisers' notebooks and data, a folder for each
  day. The environment downloads it on its first start and replaces it with the
  latest on every start, so that a tutor's fix arrives overnight. It is
  read-only, and nothing of yours is in it: do not work there. After each
  session, the organisers' answers to its notebook appear in `material/answers`.
- **`team`** holds your team's work: its copy of the
  [pipeline repository](https://github.com/mcencini/mritogetherthon-pipeline),
  with a folder for each day. At every start, a notebook that has arrived in
  `material` and that neither you nor your team's fork has yet is copied there. A
  notebook you have is never touched: if the organisers fix it later, the fix is
  in `material`, and you can copy it by hand.

Your work is in your home folder on your computer (`mritogetherthon`, or
`%USERPROFILE%\mritogetherthon` on Windows), which stays through every restart of
your computer, of Docker and of the environment, and through every update of the
environment. The team's shared copy and backup is on GitHub, in a *fork* of the
pipeline repository that one member makes.

Packages you install with `pip install --user` or Julia's `Pkg.add` land in
your home folder too, but the pipeline must not depend on them: ask for a
package in a
[Discussion](https://github.com/mcencini/mritogetherthon/discussions) so that it
is added to the environment, for everyone.

## Setting up your team, once

One member of the team makes the fork. In a JupyterLab terminal, with the
number the organisers gave your team:

```bash
team 07
```

The first time, it prints a code: open <https://github.com/login/device> in your
browser and enter it. It then forks the repository to that member's GitHub
account, and copies it to `team`. To let teammates push to the fork, invite them
by their GitHub login:

```bash
team add bob carol
```

GitHub sends them an invitation. Each teammate then runs, with the login of the
member who made the fork:

```bash
team 07 alice
```

A teammate without a GitHub account can join too: they copy the fork and work in
their own notebooks. To push, they create an account, ask for an invitation, and
run the same command again.

## Working

Your team works together on Airmeet: one member shares their screen and types,
the others follow. How the team shares files is up to it. With git, as usual: in
`team`, `git pull` brings what a teammate pushed, and `git add`, `git commit` and
`git push` send yours, to the team's fork. If git refuses a `git pull` because a
notebook is in your folder and in a teammate's commit, that is two members who
copied the same new notebook before either pushed: move yours away, pull, and
copy back what you need. Nothing is lost. Without git, one member keeps the
team's notebooks and runs `submit`.

## Sending your work

At the end of each session, and whenever something works, one member of the team
runs `submit`. It commits what is not committed, pushes to the team's fork, and
opens a pull request from the fork's `main` to your team's branch, `team-07`, of
the pipeline repository, or updates it if it is open. Each notebook with results
is sent as a page too, for the jury to read.

`submit` is only a shortcut: with git you can commit and push yourself as often
as you like, and open the pull request on GitHub, from your fork's `main` to
`team-07`. Never to `main`.

## Large files

Do not put data or large results in the repository. A notebook that needs other
data downloads it from a public, permanent address such as Zenodo.
