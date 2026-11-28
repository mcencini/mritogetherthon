# The MRI TogetherThon's environment: JupyterLab with a Python and a Julia
# kernel, and a bash shell, holding every tool the hands-on sessions use.
# Run without a command, it serves JupyterLab on port 8888 from /home/mri,
# where the launcher mounts the attendee's own folder, so that their notebooks,
# their team's copy of the pipeline repository and their git login outlive the
# container:
#
#   docker run -d --name mritogetherthon -p 127.0.0.1:8888:8888 \
#     -v ~/mritogetherthon:/home/mri ghcr.io/mcencini/mritogetherthon
#
# Any other command runs in JupyterLab's place, as `bash` opens a shell.

FROM python:3.12-slim

ARG JULIA_VERSION=1.10.4
ARG TARGETARCH

# git and the GitHub CLI for the team's repository, BART for reconstruction,
# and what a shell is expected to hold.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bart ca-certificates curl gh git git-lfs less nano openssh-client \
      procps tini unzip vim-tiny \
 && rm -rf /var/lib/apt/lists/*

# torch's CPU build: no session needs a graphics card. torchvision and
# torchaudio are declared by TADRED, so they come from the same index, at the
# versions that match torch, rather than being pulled in later from PyPI.
RUN pip install --no-cache-dir torch==2.15.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# finufft, the NUFFT of mri-nufft, has no prebuilt wheel for Linux on Arm, where
# Apple Silicon's Docker runs: it is compiled there, with tools removed after.
RUN if [ "$TARGETARCH" = arm64 ]; then \
      apt-get update \
   && apt-get install -y --no-install-recommends build-essential cmake libfftw3-dev \
   && pip install --no-cache-dir finufft==2.5.1 \
   && apt-get purge -y --auto-remove build-essential cmake \
   && rm -rf /var/lib/apt/lists/*; \
    else pip install --no-cache-dir finufft==2.5.1; fi

# Day 3's motion correction, with the tools of the ISMRM MoCo workshop that run
# on this Python and torch: MERLIN's torch layers, installed without their
# dependencies, which pin documentation tools, and BART's and ESPIRiT's Python
# modules, which the workshop's code imports. bart.py imports wslsupport.py, and
# medutils looks for the BART toolbox in TOOLBOX_PATH: both are set to the folder
# of the apt package's binary.
ENV BART_TOOLBOX_PATH=/usr/bin TOOLBOX_PATH=/usr/bin
ARG BART_REF=672a840ff88117e09dc9803e0d9c8c5a7f1c42a9
ARG ESPIRIT_REF=dedabac4e0ecc1b1b94830fa8bd4b32cec36ca9a
RUN pip install --no-cache-dir --no-deps merlinpy-mri==0.4.0 merlinth-mri==0.4.2 \
 && SITE=$(python -c "import sysconfig; print(sysconfig.get_path('purelib'))") \
 && git clone --filter=blob:none https://github.com/mrirecon/bart /tmp/bart \
 && git -C /tmp/bart checkout "$BART_REF" \
 && cp /tmp/bart/python/cfl.py /tmp/bart/python/bart.py /tmp/bart/python/wslsupport.py "$SITE/" \
 && git clone --filter=blob:none https://github.com/mikgroup/espirit-python /tmp/espirit \
 && git -C /tmp/espirit checkout "$ESPIRIT_REF" \
 && cp /tmp/espirit/espirit.py "$SITE/" \
 && rm -rf /tmp/bart /tmp/espirit

# Day 4's protocol optimisation: ED_MRI and TADRED, at fixed commits, installed
# in place (-e) so that ED_MRI's results folder, which sits beside its code,
# can be written by the attendee.
ARG EDMRI_REF=070c387d673618c66d76f02b42950afbb9acf565
ARG TADRED_REF=781ab5eb9301d2a01dd1065b9d9de7d3a8c9a003
RUN git clone https://github.com/sbb-gh/ED_MRI /opt/ED_MRI \
 && git -C /opt/ED_MRI checkout "$EDMRI_REF" \
 && git clone https://github.com/PaddySlator/tadred.git /opt/tadred \
 && git -C /opt/tadred checkout "$TADRED_REF" \
 && pip install --no-cache-dir -e /opt/ED_MRI -e /opt/tadred \
 && mkdir -p /opt/ED_MRI/results && chmod -R a+rwX /opt/ED_MRI/results

# Julia and KomaMRI, at the versions of docker/julia/Manifest.toml, in a depot
# of their own that is stacked behind the attendee's, so that a package they
# add lands in /home/mri/.julia and the image's precompiled ones still load.
# They are compiled for the processors Julia's own builds target, not for the
# one that builds the image, so that no laptop compiles them again.
RUN case "$TARGETARCH" in \
      arm64) arch=aarch64 dir=aarch64 \
             target="generic;cortex-a57;thunderx2t99;carmel,clone_all;apple-m1,base(3);neoverse-512tvb,base(3)" ;; \
      *) arch=x86_64 dir=x64 \
         target="generic;sandybridge,-xsaveopt,clone_all;haswell,-rdrnd,base(1);x86-64-v4,-rdrnd,base(1)" ;; \
    esac \
 && curl -fsSL "https://julialang-s3.julialang.org/bin/linux/$dir/${JULIA_VERSION%.*}/julia-$JULIA_VERSION-linux-$arch.tar.gz" \
    | tar -xz -C /opt \
 && ln -s /opt/julia-$JULIA_VERSION/bin/julia /usr/local/bin/julia \
 && echo "$target" > /opt/julia-cpu-target
COPY docker/julia/Project.toml docker/julia/Manifest.toml /opt/julia/env/
RUN JULIA_DEPOT_PATH=/opt/julia/depot: JULIA_PROJECT=/opt/julia/env \
    JULIA_CPU_TARGET="$(cat /opt/julia-cpu-target)" JUPYTER_DATA_DIR=/usr/local/share/jupyter \
    julia -e 'using Pkg; Pkg.instantiate(); Pkg.precompile(); \
      using IJulia; installkernel("Julia"; env=Dict("JULIA_NUM_THREADS" => "auto"))' \
 && chmod -R a+rX /opt/julia
ENV JULIA_DEPOT_PATH=/home/mri/.julia:/opt/julia/depot: \
    JULIA_LOAD_PATH=@:@v#.#:/opt/julia/env:@stdlib

# The attendee, whose home the launcher replaces with their own folder. The
# launcher runs the container as the attendee's own user where Docker shares
# the folder with their ids, so the home must be writable by any of them.
RUN useradd --create-home --uid 1000 --shell /bin/bash mri \
 && chmod 777 /home/mri
ENV HOME=/home/mri SHELL=/bin/bash
WORKDIR /home/mri

# Notebooks are committed without their outputs, in every repository, so that
# the teams' pull requests compare code rather than plots.
RUN nbstripout --install --system

COPY --chmod=755 docker/check-setup docker/sync-material docker/github-login docker/team docker/submit /usr/local/bin/
COPY docker/START_HERE.md /usr/local/share/mritogetherthon/START_HERE.md
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py

USER mri
EXPOSE 8888
ENTRYPOINT ["tini", "--", "sh", "/usr/local/bin/entrypoint.sh"]
