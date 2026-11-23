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
# from its source, at the version QSIPrep requires. It compiles a copy of HDF5.
FROM debian:trixie-slim AS unpile-amd64
RUN mkdir /wheels

FROM rust:1-slim-trixie AS unpile-arm64
ARG UNPILE_REF=0.2.0
RUN apt-get update && apt-get install -y --no-install-recommends cmake g++ git make python3-venv \
 && python3 -m venv /maturin && /maturin/bin/pip install -q "maturin>=1.7,<2" \
 && git clone -q --depth 1 --branch "$UNPILE_REF" https://github.com/PennLINC/unpile-rs.git /src \
 && cd /src && /maturin/bin/maturin build --release --compatibility linux -o /wheels

FROM unpile-${TARGETARCH} AS unpile

# The tools QSIPrep's image builds from source, from its recipes
# (github.com/PennLINC/qsiprep_build) at the same commits, on Debian instead of
# nvidia/cuda, whose images serve those recipes only as an Ubuntu with
# compilers: none of them is built with CUDA.

# MRtrix3's development tree, with dwidenoise2, which only it has. It goes last
# on PATH, so that the stable 3.0.4 answers every command both have.
FROM debian:trixie-slim AS mrtrix3dev
ARG MRTRIX3_SHA=b98b54e9ae8168eeb9af23322a07011d4754456d
ARG DWIDENOISE2_COMMIT=54e613f4e03fa5c1ee650afbe267f227c7022206
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates cmake g++ git libfftw3-dev libpng-dev libtiff-dev ninja-build \
      pkg-config python3 zlib1g-dev \
 && git init -q /src/dwidenoise2 && cd /src/dwidenoise2 \
 && git remote add origin https://github.com/tsalo/dwidenoise2.git \
 && git fetch -q --depth 1 origin "$DWIDENOISE2_COMMIT" && git checkout -q --detach FETCH_HEAD \
 && git clone -q --filter=blob:none --no-checkout https://github.com/MRtrix3/mrtrix3.git /src/mrtrix3 \
 && cd /src/mrtrix3 && git checkout -q --detach "$MRTRIX3_SHA" \
 && cp /src/dwidenoise2/cpp/cmd/dwidenoise2.cpp /src/dwidenoise2/cpp/cmd/dwi2noise.cpp cpp/cmd/ \
 && cp -r /src/dwidenoise2/cpp/core/denoise cpp/core/denoise \
 && cp -r /src/dwidenoise2/share/dwidenoise2/. share/mrtrix3/ \
 && cmake -B build -GNinja -DMRTRIX_BUILD_GUI=OFF -DMRTRIX_ENABLE_GPU=OFF \
      -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_INSTALL_RPATH='$ORIGIN/../lib' \
      -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON --preset=release \
 && cmake --build build && cmake --install build --prefix /opt/mrtrix3-dev \
 && /opt/mrtrix3-dev/bin/dwidenoise2 -version && rm -rf /src

# MRtrix3Tissue, for the 3-tissue response functions.
FROM debian:trixie-slim AS tissue3
ARG MRTRIX_SHA=5f4c31bc93008520c61d59b94af0db3f17b4ab76
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl g++ libeigen3-dev libfftw3-dev libpng-dev libtiff-dev \
      python-is-python3 python3 unzip zlib1g-dev \
 && cd /opt && curl -fsSLO "https://github.com/PennLINC/MRtrix3Tissue/archive/$MRTRIX_SHA.zip" \
 && unzip -q "$MRTRIX_SHA.zip" && mv "MRtrix3Tissue-$MRTRIX_SHA" /opt/3Tissue && rm "$MRTRIX_SHA.zip" \
 && cd /opt/3Tissue && ./configure -nogui && ./build \
 && rm -rf /opt/3Tissue/tmp /opt/3Tissue/core /opt/3Tissue/cmd /opt/3Tissue/src

# niimath and svht_denoise.
FROM debian:trixie-slim AS niimath
ARG NIIMATH_SHA=95645c2447ae4c5853d23c3e449a5b32e8aafe23
ARG SVHT_SHA=f04dbceabf50eea7eaeff736c399b44976f88b1d
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates git zlib1g-dev \
 && git clone -q https://github.com/rordenlab/niimath.git /tmp/niimath && cd /tmp/niimath \
 && git checkout -q "$NIIMATH_SHA" && SKULLSTRIP=1 make -C src -j"$(nproc)" \
 && mkdir -p /opt/niimath/bin && cp src/niimath /opt/niimath/bin/ \
 && /opt/niimath/bin/niimath 2>&1 | grep -q -- '-fmapprep' \
 && git clone -q https://github.com/rordenlab/svht_denoise.git /tmp/svht && cd /tmp/svht \
 && git checkout -q "$SVHT_SHA" && make -C src ZLIBNG=0 DEGIBBS=1 && make -C src test \
 && cp src/svht_denoise /opt/niimath/bin/ && rm -rf /tmp/niimath /tmp/svht

# TORTOISE (DIFFPREP and DRBUDDI), CPU build, on its own ITK 5.3.
FROM debian:trixie-slim AS tortoise
ARG ITK_SHA=1fc47c7bec4ee133318c1892b7b745763a17d411
ARG TORTOISE_SHA=6108a894203d60b6cb9188107e5183b17af95b4a
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake git libboost-dev libboost-filesystem-dev \
      libboost-iostreams-dev libboost-regex-dev libboost-system-dev libeigen3-dev \
      libfftw3-dev ninja-build patchelf zlib1g-dev \
 && git clone -q https://github.com/InsightSoftwareConsortium/ITK.git /tmp/itk && cd /tmp/itk \
 && git checkout -q "$ITK_SHA" \
 && cmake -S /tmp/itk -B /tmp/itk-build -GNinja -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF \
      -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/tortoise-itk \
 && cmake --build /tmp/itk-build && cmake --install /tmp/itk-build && rm -rf /tmp/itk /tmp/itk-build \
 && git clone -q https://github.com/PennLINC/qsiprep_TORTOISE.git /src/TORTOISEV4 \
 && cd /src/TORTOISEV4 && git checkout -q "$TORTOISE_SHA" && cd TORTOISEV4 \
 && sed -i '/BrukerBmatToTORTOISEBMTXT/d; /JoanahRegisterAlongAxes/d' CMakeLists.txt \
 && sed -i -E '/^[[:space:]]*(add_executable|target_include_directories|target_link_libraries|target_compile_definitions)\(DRTAMAS/d' CMakeLists.txt \
 && cmake . -DUSECUDA=0 -DQSIPREP=1 -DITK_DIR=/opt/tortoise-itk/lib/cmake/ITK-5.3 -DISDEBUG=0 \
 && cmake --build . -j"$(nproc)" \
 && mkdir -p /src/TORTOISEV4/bin/lib/itk && cp -a /opt/tortoise-itk/lib/*.so* /src/TORTOISEV4/bin/lib/itk/ \
 && find /src/TORTOISEV4/bin/lib/itk -type f -name '*.so*' -exec patchelf --force-rpath --set-rpath '$ORIGIN' {} \; \
 && find /src/TORTOISEV4/bin -maxdepth 1 -type f -executable -exec patchelf --force-rpath --set-rpath '$ORIGIN/lib/itk' {} \; \
 && ! ldd /src/TORTOISEV4/bin/TORTOISEProcess | grep -q 'not found'

# DSI Studio, with its atlases and UNet-Studio's networks, at QSIPrep's commits.
FROM debian:trixie-slim AS dsistudio
ARG DSI_SHA=03476a67bc96a1d0c90928001b5dd1c490539ee0
ARG TIPL_SHA=ebd2d8b1ee13d6f87e78db62f2f1a1400b353898
ARG ATLAS_SHA=bf5afab9b2405f076b1acdf4706c9688525eb713
ARG UNET_SHA=2e839aae744883983974194dcf6aeff154a82197
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl libboost-all-dev libglu1-mesa-dev \
      libqt5charts5-dev libqt5opengl5-dev qtbase5-dev qt5-qmake unzip zlib1g-dev \
 && mkdir -p /opt/dsi-studio && cd /opt/dsi-studio \
 && curl -fsSLO "https://github.com/frankyeh/DSI-Studio/archive/$DSI_SHA.zip" \
 && unzip -q "$DSI_SHA.zip" && mv "DSI-Studio-$DSI_SHA" src && rm "$DSI_SHA.zip" \
 && curl -fsSLO "https://github.com/frankyeh/TIPL/archive/$TIPL_SHA.zip" \
 && unzip -q "$TIPL_SHA.zip" && mv "TIPL-$TIPL_SHA" src/TIPL && rm "$TIPL_SHA.zip" \
 && mkdir build && cd build && qmake ../src && make -j"$(nproc)" \
 && cd /opt/dsi-studio && mv build/dsi_studio . && chmod 755 dsi_studio \
 && cp -R src/other/* . && rm -rf src build \
 && curl -fsSLO "https://github.com/frankyeh/UNet-Studio-Data/archive/$UNET_SHA.zip" \
 && unzip -q "$UNET_SHA.zip" && rm "$UNET_SHA.zip" \
 && mv "UNet-Studio-Data-$UNET_SHA/network" . && rm -rf "UNet-Studio-Data-$UNET_SHA" \
 && curl -fsSLO "https://github.com/frankyeh/DSI-Studio-atlas/archive/$ATLAS_SHA.zip" \
 && unzip -q "$ATLAS_SHA.zip" && rm "$ATLAS_SHA.zip" \
 && rm -rf "DSI-Studio-atlas-$ATLAS_SHA/.git" && mv "DSI-Studio-atlas-$ATLAS_SHA" atlas

# AFNI: the 17 programs QSIPrep's image ships (3dresample, 3dcalc, 3dAutobox
# and the others its workflows call), built from source at its tag, without the
# GUI, SUMA, Python, R or tcsh, with the shared libraries they link to.
FROM debian:trixie-slim AS afni
ARG AFNI_REF=AFNI_25.2.09
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake git libexpat1-dev libgsl-dev libqhull-dev \
      ninja-build patchelf python3 zlib1g-dev \
 && git clone -q --depth 1 --branch "$AFNI_REF" https://github.com/afni/afni.git /src/afni \
 && cmake -S /src/afni -B /build -GNinja -DCMAKE_BUILD_TYPE=Release \
      -DCOMP_GUI=OFF -DCOMP_SUMA=OFF -DCOMP_PYTHON=OFF -DCOMP_TCSH=OFF -DCOMP_RSTATS=OFF \
      -DCOMP_ATLASES=OFF -DBUILD_TESTING=OFF -DAFNI_COMPILER_CHECK=OFF \
 && progs="3dAutobox 3dAutomask 3dFWHMx 3dQwarp 3dSeg 3dSkullStrip 3dTcat 3dTshift \
      3dTsplit4D 3dTstat 3dUnifize 3dWarp 3dZeropad 3dcalc 3drefit 3dresample 3dvolreg" \
 && cmake --build /build --target $progs \
 && mkdir -p /opt/afni/bin /opt/afni/lib \
 && for p in $progs; do cp "$(find /build -type f -name "$p" -perm -u+x | head -1)" /opt/afni/bin/; done \
 && for lib in $(ldd /opt/afni/bin/* | awk '/=> \/build/ {print $3}' | sort -u); do cp "$lib" /opt/afni/lib/; done \
 && find /opt/afni/bin -type f -exec patchelf --force-rpath --set-rpath '$ORIGIN/../lib' {} \; \
 && find /opt/afni/lib -type f -exec patchelf --force-rpath --set-rpath '$ORIGIN' {} \; \
 && ! ldd /opt/afni/bin/* | grep 'not found' \
 && /opt/afni/bin/3dresample -help >/dev/null \
 && rm -rf /src /build

# The tools, built apart so that their (long) builds are cached on their own.
FROM scratch AS tools
COPY --from=fsl /opt/fsl /opt/fsl
COPY --from=ants /opt/ants /opt/ants
COPY --from=unpile /wheels /wheels
COPY --from=mrtrix3dev /opt/mrtrix3-dev /opt/mrtrix3-dev
COPY --from=tissue3 /opt/3Tissue /opt/3Tissue
COPY --from=niimath /opt/niimath /opt/niimath
COPY --from=tortoise /src/TORTOISEV4/bin /src/TORTOISEV4/bin
COPY --from=tortoise /src/TORTOISEV4/settings /src/TORTOISEV4/settings
COPY --from=dsistudio /opt/dsi-studio /opt/dsi-studio
COPY --from=afni /opt/afni /opt/afni

FROM ${BASE}
ARG QSIPREP_REF
ARG QSIRECON_REF
USER root

# MRtrix3 3.0.4, the stable version QSIPrep's image pins, from Debian, which
# builds it for both processors; and the libraries DSI Studio and TORTOISE run on.
RUN apt-get update \
 && apt-get install -y --no-install-recommends mrtrix3 libfftw3-double3 libfftw3-single3 \
      libboost-filesystem1.83.0 libboost-iostreams1.83.0 libboost-regex1.83.0 libboost-system1.83.0 \
      libgomp1 libqt5charts5 libqt5gui5t64 libqt5network5t64 libqt5opengl5t64 libqt5sql5t64 \
      libqt5svg5 libqt5widgets5t64 libgsl28 libqhull-r8.0 libqhull8.0 libexpat1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=tools /opt/fsl /opt/fsl
COPY --from=tools /opt/ants /opt/ants
COPY --from=tools /opt/mrtrix3-dev /opt/mrtrix3-dev
COPY --from=tools /opt/3Tissue /opt/3Tissue
COPY --from=tools /opt/niimath /opt/niimath
COPY --from=tools /src/TORTOISEV4 /src/TORTOISEV4
COPY --from=tools /opt/dsi-studio /opt/dsi-studio
COPY --from=tools /opt/afni /opt/afni
# FSL's and ANTs' own folders go after the environment's, so that their Python
# and libraries never shadow the notebooks'. FSL's commands are in its bin:
# the wrappers its packages make in share/fsl/bin need post-link scripts, which
# micromamba does not run.
ENV FSLDIR=/opt/fsl FSLOUTPUTTYPE=NIFTI_GZ FSLMULTIFILEQUIT=TRUE \
    ANTSPATH=/opt/ants/bin \
    PATH="$PATH:/opt/afni/bin:/opt/dsi-studio:/opt/ants/bin:/opt/fsl/bin:/opt/niimath/bin:/src/TORTOISEV4/bin:/opt/mrtrix3-dev/bin:/opt/3Tissue/bin" \
    TEMPLATEFLOW_HOME=/opt/templateflow DIPY_HOME=/opt/dipy \
    AFNI_IMSAVE_WARNINGS=NO \
    IS_DOCKER_8395080871=1

# QSIPrep and QSIRecon in the environment's own Python, every package already
# there kept at its version: their caps on numpy, pandas and the others are
# lifted (overrides.txt). numpy 2 removed np.row_stack, an alias of np.vstack,
# which both call: the installed files are patched, so that the versions stay
# as tagged. One of pyAFQ's dependencies (phamt) is compiled.
COPY docker/qsi/overrides.txt /tmp/overrides.txt
COPY --from=tools /wheels /wheels
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
 && pip install --no-cache-dir uv \
 && pip list --format=freeze > /tmp/constraints.txt \
 && git clone -q --depth 1 --branch "$QSIPREP_REF" https://github.com/PennLINC/qsiprep.git /tmp/qsiprep \
 && git clone -q --depth 1 --branch "$QSIRECON_REF" https://github.com/PennLINC/qsirecon.git /tmp/qsirecon \
 && uv pip install --system --no-cache --find-links /wheels --constraints /tmp/constraints.txt \
      --overrides /tmp/overrides.txt /tmp/qsiprep /tmp/qsirecon toml \
 && SITE=$(python -c "import sysconfig; print(sysconfig.get_path('purelib'))") \
 && grep -rl 'np\.row_stack(' "$SITE/qsiprep" "$SITE/qsirecon" --include='*.py' \
      | xargs sed -i 's/np\.row_stack(/np.vstack(/g' \
 && ! grep -rq 'np\.row_stack(' "$SITE/qsiprep" "$SITE/qsirecon" --include='*.py' \
 && apt-get purge -y --auto-remove gcc libc6-dev && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/qsi && cp -r /tmp/qsiprep/scripts /opt/qsi/qsiprep-scripts \
 && cp -r /tmp/qsirecon/scripts /opt/qsi/qsirecon-scripts \
 && rm -rf /tmp/qsiprep /tmp/qsirecon /tmp/constraints.txt /tmp/overrides.txt /wheels \
 && python -c "import qsiprep, qsirecon; assert qsiprep.__version__ == '$QSIPREP_REF', qsiprep.__version__; assert qsirecon.__version__ == '$QSIRECON_REF', qsirecon.__version__" \
 && command -v unpile \
 && ! ldd /opt/dsi-studio/dsi_studio /src/TORTOISEV4/bin/TORTOISEProcess /opt/3Tissue/bin/ss3t_csd_beta1 \
        /opt/mrtrix3-dev/bin/dwidenoise2 /opt/niimath/bin/niimath | grep 'not found'

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
