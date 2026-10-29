# The MRI TogetherThon's environment: JupyterLab with a Python and a Julia
# kernel, and a bash shell, holding every tool the hands-on sessions use.
# Run without a command, it serves JupyterLab on port 8888 from /home/mri,
# where the launcher mounts the attendee's own folder, so that their notebooks,
# their clones of the team repositories and their git login outlive the
# container:
#
#   docker run -d --name mritogetherthon -p 127.0.0.1:8888:8888 \
#     -v ~/mritogetherthon:/home/mri ghcr.io/mcencini/mritogetherthon
#
# Any other command runs in JupyterLab's place, as `bash` opens a shell.

FROM python:3.12-slim

ARG JULIA_VERSION=1.12.7
ARG TARGETARCH

# git and the GitHub CLI for the teams' repositories, BART for reconstruction,
# and what a shell is expected to hold.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bart ca-certificates curl gh git git-lfs less nano openssh-client \
      procps tini unzip vim-tiny \
 && rm -rf /var/lib/apt/lists/*

# torch's CPU build: no session needs a graphics card.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY docker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

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
# the teams' merges compare code rather than plots.
RUN nbstripout --install --system

COPY --chmod=755 docker/check-setup /usr/local/bin/check-setup
COPY docker/START_HERE.md /usr/local/share/mritogetherthon/START_HERE.md
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/jupyter_server_config.py /etc/jupyter/jupyter_server_config.py

USER mri
EXPOSE 8888
ENTRYPOINT ["tini", "--", "sh", "/usr/local/bin/entrypoint.sh"]
