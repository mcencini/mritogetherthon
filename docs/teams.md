# Working as a team

Every team builds the same pipeline for placenta diffusion MRI, one stage a day.
Your team keeps its work in a fork of the
[pipeline repository](https://github.com/mcencini/mritogetherthon-pipeline) on
GitHub, and sends it to the organisers at the end of each session.

## Two folders

- **`material`** holds the organisers' notebooks and data, a folder for each day.
  The environment replaces it with their latest at every start and every half
  hour, so a tutor's fix arrives while you work. It is read-only, and nothing of
  yours is in it: do not work there. After each session, its answers appear in
  `material/answers`.
- **`team`** holds your team's work: its copy of the pipeline repository, with a
  folder for each day. A notebook that arrives in `material` and that neither you
  nor your team's fork has is copied there at the same moments. A notebook you have
  is never touched.

Both are in your home folder on your computer (`mritogetherthon`, or
`%USERPROFILE%\mritogetherthon` on Windows), which stays through every restart and
update. Packages you install yourself are kept there too, but the pipeline must
not depend on them: ask for a package in a
[Discussion](https://github.com/mcencini/mritogetherthon/discussions), so that it
is added for everyone.

## Setting up your team, once

In a JupyterLab terminal, with the number the organisers gave your team (`07`
here):

1. One member with a [GitHub account](https://github.com/signup) runs `team 07`.
   The first time, it prints a code to enter at <https://github.com/login/device>.
   It forks the repository to that member's account and copies it to `team`.
2. That member invites the others, by their GitHub login: `team add bob carol`.
3. Each of the others runs `team 07 alice`, with the login of the member who made
   the fork. Without a GitHub account, this follows the fork read-only: you work
   in your own notebooks and see what the others push. To push, create an
   account, ask for an invitation, and run it again.

## Working and sending

Your team works together on Airmeet: one member shares their screen and types.
How the team shares files is up to it. With git, as usual, in `team`: `git pull`,
`git add`, `git commit`, `git push`. If git refuses a `git pull` because a
notebook is in your folder and in a teammate's commit, two members copied the same
new notebook before either pushed: move yours away, pull, and copy back what you
need. Nothing is lost.

At the end of each session, one member runs `submit`. It commits what is not
committed, pushes to the team's fork, and opens a pull request from the fork's
`main` to your team's branch, `team-07`, of the pipeline repository, or updates it
if it is open. Each notebook with results is sent as a page too, for the jury to
read. You can do the same by hand, with git and the GitHub website: the pull
request goes from your fork's `main` to `team-07`, never to `main`.

Do not put data or large results in the repository: a notebook that needs other
data downloads it from a public, permanent address such as Zenodo.
