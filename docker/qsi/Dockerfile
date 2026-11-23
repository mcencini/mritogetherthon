# QSIPrep and QSIRecon, with the external tools they call, added to the
# TogetherThon's environment: CPU only, for amd64 and arm64, and published as
# its own tag (:qsi), so that :latest is not touched until this one passes.
#
#   docker build -f docker/qsi/Dockerfile -t mritogetherthon:qsi .

ARG BASE=ghcr.io/mcencini/mritogetherthon:latest
ARG QSIPREP_REF=26.2.0
ARG QSIRECON_REF=26.0.1

# micromamba, to install FSL from its own conda channel, and ANTs from
# conda-forge where it is built.
FROM debian:trixie-slim AS mamba
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends bzip2 ca-certificates curl \
 && case "$TARGETARCH" in arm64) p=linux-aarch64 ;; *) p=linux-64 ;; esac \
 && curl -fsSL "https://micro.mamba.pm/api/micromamba/$p/2.3.3" | tar -xj -C /usr/local bin/micromamba

# FSL's tools that QSIPrep and QSIRecon call, at QSIPrep's versions: eddy's CPU
# build (eddy_cpu), not its CUDA one. FSL publishes them for both processors.
FROM mamba AS fsl
RUN micromamba create -y -p /opt/fsl \
      -c https://fsl.fmrib.ox.ac.uk/fsldownloads/fslconda/public -c conda-forge \
      fsl-base fsl-avwutils fsl-warpfns \
      fsl-bet2=2111.9 fsl-flirt=2111.4 fsl-fast4=2111.3 fsl-fugue=2603.0 \
      fsl-mcflirt=2111.0 fsl-miscmaths=2412.6 fsl-mist=2512.2 fsl-topup=2203.5 \
      fsl-eddy=2602.0 \
 && micromamba clean -a -y

# ANTs 2.6: conda-forge's build on amd64; built from source on arm64, for which
# neither conda-forge nor ANTs publishes one.
FROM mamba AS ants-amd64
RUN micromamba create -y -p /opt/ants -c conda-forge ants=2.6 && micromamba clean -a -y

FROM debian:trixie-slim AS ants-arm64
ARG ANTS_REF=v2.6.5
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake git zlib1g-dev \
 && git clone --depth 1 --branch "$ANTS_REF" https://github.com/ANTsX/ANTs.git /src/ants \
 && cmake -S /src/ants -B /build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
      -DRUN_LONG_TESTS=OFF -DRUN_SHORT_TESTS=OFF -DBUILD_SHARED_LIBS=OFF \
      -DCMAKE_INSTALL_PREFIX=/opt/ants \
 && cmake --build /build -j"$(nproc)" \
 && cmake --install /build/ANTS-build --prefix /opt/ants \
 && rm -rf /src /build

FROM ants-${TARGETARCH} AS ants

# unpile, QSIPrep's distortion correction, is a Rust program packaged as a wheel:
# PyPI has it for amd64 Linux and arm64 macOS only, so on arm64 Linux it is built
# from its source, at the version QSIPrep requires.
FROM debian:trixie-slim AS unpile-amd64
RUN mkdir /wheels

FROM rust:1-slim-trixie AS unpile-arm64
ARG UNPILE_REF=0.2.0
RUN apt-get update && apt-get install -y --no-install-recommends git python3-venv \
 && python3 -m venv /maturin && /maturin/bin/pip install -q "maturin>=1.7,<2" \
 && git clone -q --depth 1 --branch "$UNPILE_REF" https://github.com/PennLINC/unpile-rs.git /src \
 && cd /src && /maturin/bin/maturin build --release --compatibility linux -o /wheels

FROM unpile-${TARGETARCH} AS unpile

# The tools, built apart so that their (long) builds are cached on their own.
FROM scratch AS tools
COPY --from=fsl /opt/fsl /opt/fsl
COPY --from=ants /opt/ants /opt/ants
COPY --from=unpile /wheels /wheels

FROM ${BASE}
ARG QSIPREP_REF
ARG QSIRECON_REF
USER root

# MRtrix3 3.0.4, the stable version QSIPrep's image pins, from Debian, which
# builds it for both processors.
RUN apt-get update \
 && apt-get install -y --no-install-recommends mrtrix3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=tools /opt/fsl /opt/fsl
COPY --from=tools /opt/ants /opt/ants
# FSL's and ANTs' own folders go after the environment's, so that their Python
# and libraries never shadow the notebooks'. FSL's commands are in its bin:
# the wrappers its packages make in share/fsl/bin need post-link scripts, which
# micromamba does not run.
ENV FSLDIR=/opt/fsl FSLOUTPUTTYPE=NIFTI_GZ FSLMULTIFILEQUIT=TRUE \
    ANTSPATH=/opt/ants/bin \
    PATH="$PATH:/opt/ants/bin:/opt/fsl/bin" \
    TEMPLATEFLOW_HOME=/opt/templateflow DIPY_HOME=/opt/dipy \
    IS_DOCKER_8395080871=1

# QSIPrep and QSIRecon in the environment's own Python, every package already
# there kept at its version: their caps on numpy, pandas and the others are
# lifted (overrides.txt). numpy 2 removed np.row_stack, an alias of np.vstack,
# which both call; the patch leaves their versions as tagged. One of pyAFQ's
# dependencies (phamt) is compiled.
COPY docker/qsi/overrides.txt /tmp/overrides.txt
COPY --from=tools /wheels /wheels
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
 && pip install --no-cache-dir uv \
 && pip list --format=freeze > /tmp/constraints.txt \
 && git clone -q --depth 1 --branch "$QSIPREP_REF" https://github.com/PennLINC/qsiprep.git /tmp/qsiprep \
 && git clone -q --depth 1 --branch "$QSIRECON_REF" https://github.com/PennLINC/qsirecon.git /tmp/qsirecon \
 && grep -rl 'np\.row_stack(' /tmp/qsiprep/qsiprep /tmp/qsirecon/qsirecon --include='*.py' \
      | xargs sed -i 's/np\.row_stack(/np.vstack(/g' \
 && SETUPTOOLS_SCM_PRETEND_VERSION_FOR_QSIPREP="$QSIPREP_REF" \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_QSIRECON="$QSIRECON_REF" \
    uv pip install --system --no-cache --find-links /wheels --constraints /tmp/constraints.txt \
      --overrides /tmp/overrides.txt /tmp/qsiprep /tmp/qsirecon toml \
 && apt-get purge -y --auto-remove gcc libc6-dev && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/qsi && cp -r /tmp/qsiprep/scripts /opt/qsi/qsiprep-scripts \
 && cp -r /tmp/qsirecon/scripts /opt/qsi/qsirecon-scripts \
 && rm -rf /tmp/qsiprep /tmp/qsirecon /tmp/constraints.txt /tmp/overrides.txt /wheels \
 && python -c "import qsiprep, qsirecon; assert qsiprep.__version__ == '$QSIPREP_REF', qsiprep.__version__; assert qsirecon.__version__ == '$QSIRECON_REF', qsirecon.__version__" \
 && command -v unpile

# The templates both prefetch, and QSIRecon's atlases at the path it looks for
# them, outside /home/mri, where the attendee's folder is mounted over the image.
RUN python /opt/qsi/qsiprep-scripts/fetch_templates.py --tf-dir "$TEMPLATEFLOW_HOME" \
 && python /opt/qsi/qsirecon-scripts/fetch_templates.py --tf-dir "$TEMPLATEFLOW_HOME" \
 && mkdir -p /home/qsirecon/.cache/qsirecon && cd /tmp \
 && curl -fsSL -o a.tgz https://upenn.box.com/shared/static/0gxdoe77tuih5p9ainn4utdqj3kcq7p1.tar.gz \
 && echo "543db13adbef32a9d913f5aac9234e9a77a0a5963ae9ac57d3c8bd4ede65cb92  a.tgz" | sha256sum -c - \
 && tar -xzf a.tgz && mv AtlasPack /home/qsirecon/.cache/qsirecon/AtlasPack \
 && curl -fsSL -o b.tgz https://upenn.box.com/shared/static/2p5lfjw3435h9dd8c2oul5j5r6v2ie00.tar.gz \
 && echo "5493db75ca94711595b6f746ea51c0f83097f8e09471f80fde1973e80714556e  b.tgz" | sha256sum -c - \
 && tar -xzf b.tgz && mv qsirecon_atlases /home/qsirecon/.cache/qsirecon/QSIReconAtlases \
 && rm -rf a.tgz b.tgz ._* \
 && mkdir -p "$DIPY_HOME" && (cd /opt/qsi/qsirecon-scripts && python set_up_amico.py) \
 && chmod -R a+rX /opt/templateflow /opt/dipy /home/qsirecon

USER mri
