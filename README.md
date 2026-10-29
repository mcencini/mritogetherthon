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

Set it up **before 23 November**, so that a problem can be solved before day 1.

## What you need

- macOS (Intel or Apple Silicon), Linux, or Windows 10/11 with WSL2
- [Docker](https://docs.docker.com/get-started/get-docker/): Docker Desktop on
  macOS and Windows, Docker Engine or Docker Desktop on Linux, with at least
  8 GB of memory for Docker (16 GB in the computer is recommended)
- about 40 GB of free disk
- a [GitHub account](https://github.com/signup), to ask for help and to work
  with your team

Installing Docker needs administrator rights: on a computer managed by your
institution, ask your IT department early. On Windows, `wsl --status` in a
terminal tells you whether WSL2 is on. Docker Desktop is free for personal use,
education and small organisations; employees of larger companies may need a
paid subscription.

## Set up

1. Install Docker and start it. The [hub page](https://mcencini.github.io/mritogetherthon/)
   has the installers for Windows and macOS, and the commands for Linux's
   package managers (APT, DNF, zypper, pacman).
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
launcher again does the same.

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

Online install sessions are held in the week of 23 November; they are announced
in Discussions.

## Working as a team

Teams build the pipeline's stages during days 1 to 4, and the stages are joined
on day 5. [docs/teams.md](docs/teams.md) explains how your work is saved, how
your team shares it on GitHub, and how it reaches the final pipeline.

## What the environment holds

| | |
|---|---|
| Notebooks | JupyterLab, Jupyter Notebook, Python 3.12 and Julia 1.12 kernels, Jupytext |
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
| [`docker/`](docker) | The image: `Dockerfile`, the pinned Python (`requirements.in` → `requirements.txt`) and Julia (`julia/Project.toml`, `julia/Manifest.toml`) packages, `check-setup`, and JupyterLab's configuration |
| [`web/`](web) | The hub page and its launchers, served by GitHub Pages |
| [`tests/`](tests) | The launchers against a stand-in for Docker, and a notebook in each kernel inside the image |
| [`.github/`](.github) | The workflows, and the issue and discussion templates |

- **Image:** every push to `main` builds the image on amd64 and arm64 runners,
  starts it as the launcher does, runs `check-setup` and a notebook in each
  kernel, and publishes `ghcr.io/mcencini/mritogetherthon:latest`. Make the
  package public in its settings once, so that the launcher downloads it
  without a login.
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
