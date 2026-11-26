# MRI TogetherThon 2026: environment and help

[![Image](https://github.com/mcencini/mritogetherthon/actions/workflows/image.yml/badge.svg)](https://github.com/mcencini/mritogetherthon/actions/workflows/image.yml)
[![Launcher](https://github.com/mcencini/mritogetherthon/actions/workflows/launcher.yml/badge.svg)](https://github.com/mcencini/mritogetherthon/actions/workflows/launcher.yml)

The [MRI TogetherThon](https://mritogether.esmrmb.org/26m/) (30 November – 4
December 2026) builds an open-source, end-to-end pipeline for placenta
diffusion MRI, from the sequence to the analysis. Every hands-on session runs in
one environment on your own computer: **JupyterLab with a Python and a Julia
kernel, and a bash shell**, holding every tool the sessions use. This repository
is that environment, and the place to ask for help.

**→ Set it up from the hub page: <https://mcencini.github.io/mritogetherthon/>**

## What you need

- macOS (Intel or Apple Silicon), Linux, or Windows 10/11 with WSL2
- [Docker](https://docs.docker.com/get-started/get-docker/): Docker Desktop on
  macOS and Windows, Docker Engine or Docker Desktop on Linux, with at least
  8 GB of memory for Docker (16 GB in the computer is recommended)
- about 25 GB of free disk (the download is about 5 to 6 GB, and the environment takes about 15 to 17 GB once installed)
- a [GitHub account](https://github.com/signup), to ask for help; and for one
  member of your team, to send the team's work

Installing Docker needs administrator rights: on a computer managed by your
institution, ask your IT department early. On Windows, `wsl --status` in a
terminal tells you whether WSL2 is on. Docker Desktop is free for personal use,
education and small organisations; employees of larger companies may need a
paid subscription.

## Set up

1. Install Docker and start it, unless it is already installed and running
   (`docker version` tells you; do not install it again over a working one). The [hub page](https://mcencini.github.io/mritogetherthon/)
   has the installers for Windows and macOS, and the commands for Linux's
   package managers (APT, DNF, zypper, pacman). On Windows, if you already work
   in a WSL2 Linux terminal, you can follow the Linux instructions there.
2. Run the launcher once. It downloads the environment (several GB, once),
   starts it and opens JupyterLab.
   - **Windows:** download
     [`mritogetherthon.bat`](https://mcencini.github.io/mritogetherthon/mritogetherthon.bat)
     and double-click it.
   - **macOS and Linux:** in a terminal,

     ```bash
     curl -fsSL https://mcencini.github.io/mritogetherthon/mritogetherthon.sh -o ~/mritogetherthon.sh && sh ~/mritogetherthon.sh
     ```

3. In JupyterLab, open a terminal and run `check-setup`. Every line should be ✅.

From then on the hub page's **Open JupyterLab** button starts the environment,
updates it when a newer one is published, and opens JupyterLab. Running the
launcher again updates the environment when it is outdated; when it is up to
date and running, the launcher says so and exits.

Your work lives in the `mritogetherthon` folder of your home folder, which is
your home in JupyterLab: it stays on your computer through every restart and
every update. A shell on your computer opens with
`docker exec -it mritogetherthon bash`.

## Help

- **The environment does not install, start, or pass `check-setup`:** open a
  [Setup problem](https://github.com/mcencini/mritogetherthon/issues/new?template=setup-problem.yml)
  issue with the output of `check-setup`.
- **A notebook of the sessions fails:** open a
  [Problem in the hands-on material](https://github.com/mcencini/mritogetherthon/issues/new?template=material-bug.yml)
  issue.
- **Anything else**, including finding a team:
  [Discussions](https://github.com/mcencini/mritogetherthon/discussions).

## Working as a team

Every team builds the same pipeline during days 1 to 4, one stage a day.
[docs/teams.md](docs/teams.md) explains how a team sets up its fork of the
[pipeline repository](https://github.com/mcencini/mritogetherthon-pipeline),
where its work is saved, and how it sends it to the organisers.

## What the environment holds

| | |
|---|---|
| Notebooks | JupyterLab, Jupyter Notebook, Python 3.12 and Julia 1.10 kernels, Jupytext |
| Sequences | PyPulseq |
| Simulation | KomaMRI (KomaMRICore, KomaMRIFiles, KomaMRIPlots) |
| Reconstruction | BART, SigPy, PyTorch (CPU) |
| Analysis | DIPY, scikit-image, NiBabel, SciPy |
| Files | ISMRMRD, h5py, pydicom, NiBabel |
| Shell | bash, git, GitHub CLI, nano, vim |

No session needs a graphics card. A tool the sessions need that is missing is
asked for in Discussions and added to the environment, for everyone.

## For organisers

| Path | What it is |
|---|---|
| [`docker/`](docker) | The image: `Dockerfile`, the pinned Python (`requirements.in` → `requirements.txt`) and Julia (`julia/Project.toml`, `julia/Manifest.toml`) packages, `check-setup`, the attendee's commands `team` and `submit`, `sync-material`, which downloads and updates the hands-on material, and JupyterLab's configuration |
| [`handson/`](handson), [`data/`](data) | The hands-on material: the notebook of each day, and the phantoms. The environment downloads it, and the tutors change it until the last day |
| [`web/`](web) | The hub page and its launchers, served by GitHub Pages |
| [`tests/`](tests) | The launchers against a stand-in for Docker, the attendee's commands against a stand-in for GitHub, and a notebook in each kernel inside the image |
| [`.github/`](.github) | The workflows, and the issue and discussion templates |

- **Image:** every push to `main` builds the base environment on amd64 and
  arm64 runners, starts it as the launcher does, runs `check-setup` and a
  notebook in each kernel, and publishes it as
  `ghcr.io/mcencini/mritogetherthon:base`. The QSI workflow then adds QSIPrep,
  QSIRecon and MRIQC (`docker/qsi`), runs their tests in it and in the official
  images, and publishes the result as `:latest`, the image the launcher starts,
  when no test fails in it only. Make the package public in its settings once,
  so that the launcher downloads it without a login.
- **Python packages:** edit `docker/requirements.in`, then
  `uv pip compile --universal --python-version 3.12 docker/requirements.in -o docker/requirements.txt`.
- **Julia packages:** `julia --project=docker/julia -e 'using Pkg; Pkg.add("...")'`,
  which updates both TOML files.
- **Hub page:** in *Settings → Pages*, set the source to *GitHub Actions*.
- **Discussions:** enable them in *Settings → General*, and create the
  categories *Install help* (`install-help`) and *Teams* (`teams`), whose forms
  are in `.github/DISCUSSION_TEMPLATE`.
- **Freeze:** after the speakers' dependencies are in, the image changes only to
  fix what fails.

The launchers follow [pulserver](https://github.com/pulserver/pulserver)'s
launchers for its virtual scanner.
