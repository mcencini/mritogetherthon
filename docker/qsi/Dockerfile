# QSIPrep, QSIRecon and MRIQC, with the external tools they call, added to the
# TogetherThon's environment: CPU only, for amd64 and arm64, and published as
# its own tag (:qsi), so that :latest is not touched until this one passes.
#
#   docker build -f docker/qsi/Dockerfile -t mritogetherthon:qsi .
#
# Every tool compiled here is compiled, on arm64, with -fsigned-char: plain char
# is unsigned on Linux arm64 and signed on x86-64, which these tools assume, as
# MRIQC's image (github.com/nipreps/mriqc, Dockerfile.base) does.

ARG BASE=ghcr.io/mcencini/mritogetherthon:latest
ARG QSIPREP_REF=26.2.0
ARG QSIRECON_REF=26.0.1
ARG MRIQC_REF=26.1.1

# micromamba, to install FSL from its own conda channel, and ANTs from
# conda-forge where it is built.
FROM debian:trixie-slim AS mamba
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends bzip2 ca-certificates curl \
 && case "$TARGETARCH" in arm64) p=linux-aarch64 ;; *) p=linux-64 ;; esac \
 && curl -fsSL "https://micro.mamba.pm/api/micromamba/$p/2.3.3" | tar -xj -C /usr/local bin/micromamba

# A compiler's image, which records the flag the processor needs.
FROM debian:trixie-slim AS builder
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates cmake curl git ninja-build patchelf python3 unzip zlib1g-dev \
 && if [ "$TARGETARCH" = arm64 ]; then echo -fsigned-char; fi > /signed-char.flag

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
# neither conda-forge nor ANTs publishes one, with MRIQC's patch for plain char
# in antsApplyTransforms (ANTsX/ANTs#2032, after v2.6.5).
FROM mamba AS ants-amd64
RUN micromamba create -y -p /opt/ants -c conda-forge ants=2.6 && micromamba clean -a -y

FROM builder AS ants-arm64
ARG ANTS_REF=v2.6.5
COPY docker/qsi/ants-2.6.5-signed-char.patch /tmp/
RUN git clone -q --depth 1 --branch "$ANTS_REF" https://github.com/ANTsX/ANTs.git /src/ants \
 && git -C /src/ants apply /tmp/ants-2.6.5-signed-char.patch \
 && export CFLAGS="$(cat /signed-char.flag)" CXXFLAGS="$(cat /signed-char.flag)" \
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
 && export CFLAGS=-fsigned-char CXXFLAGS=-fsigned-char \
 && cd /src && /maturin/bin/maturin build --release --compatibility linux -o /wheels

FROM unpile-${TARGETARCH} AS unpile

# The tools QSIPrep's image builds from source, from its recipes
# (github.com/PennLINC/qsiprep_build) at the same commits, on Debian instead of
# nvidia/cuda, whose images serve those recipes only as an Ubuntu with
# compilers: none of them is built with CUDA.

# MRtrix3's development tree, with dwidenoise2, which only it has. It goes last
# on PATH, so that the stable 3.0.4 answers every command both have.
FROM builder AS mrtrix3dev
ARG MRTRIX3_SHA=b98b54e9ae8168eeb9af23322a07011d4754456d
ARG DWIDENOISE2_COMMIT=54e613f4e03fa5c1ee650afbe267f227c7022206
RUN apt-get install -y --no-install-recommends libfftw3-dev libpng-dev libtiff-dev pkg-config \
 && export CFLAGS="$(cat /signed-char.flag)" CXXFLAGS="$(cat /signed-char.flag)" \
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
FROM builder AS tissue3
ARG MRTRIX_SHA=5f4c31bc93008520c61d59b94af0db3f17b4ab76
RUN apt-get install -y --no-install-recommends libeigen3-dev libfftw3-dev libpng-dev libtiff-dev python-is-python3 \
 && export CFLAGS="$(cat /signed-char.flag)" \
 && cd /opt && curl -fsSLO "https://github.com/PennLINC/MRtrix3Tissue/archive/$MRTRIX_SHA.zip" \
 && unzip -q "$MRTRIX_SHA.zip" && mv "MRtrix3Tissue-$MRTRIX_SHA" /opt/3Tissue && rm "$MRTRIX_SHA.zip" \
 && cd /opt/3Tissue && ./configure -nogui && ./build \
 && rm -rf /opt/3Tissue/tmp /opt/3Tissue/core /opt/3Tissue/cmd /opt/3Tissue/src

# niimath and svht_denoise.
FROM builder AS niimath
ARG NIIMATH_SHA=95645c2447ae4c5853d23c3e449a5b32e8aafe23
ARG SVHT_SHA=f04dbceabf50eea7eaeff736c399b44976f88b1d
RUN git clone -q https://github.com/rordenlab/niimath.git /tmp/niimath && cd /tmp/niimath \
 && git checkout -q "$NIIMATH_SHA" && SKULLSTRIP=1 make -C src -j"$(nproc)" CC="gcc $(cat /signed-char.flag)" \
 && mkdir -p /opt/niimath/bin && cp src/niimath /opt/niimath/bin/ \
 && /opt/niimath/bin/niimath 2>&1 | grep -q -- '-fmapprep' \
 && git clone -q https://github.com/rordenlab/svht_denoise.git /tmp/svht && cd /tmp/svht \
 && git checkout -q "$SVHT_SHA" && make -C src ZLIBNG=0 DEGIBBS=1 CPPFLAGS="$(cat /signed-char.flag)" \
 && make -C src test \
 && cp src/svht_denoise /opt/niimath/bin/ && rm -rf /tmp/niimath /tmp/svht

# TORTOISE (DIFFPREP and DRBUDDI), CPU build, on its own ITK 5.3, whose headers,
# like DSI Studio's, use uint8_t without including <cstdint>, which GCC 14 needs:
# <stdint.h> is included instead, which ITK's copy of HDF5, compiled as C++98,
# also accepts.
FROM builder AS tortoise
ARG ITK_SHA=1fc47c7bec4ee133318c1892b7b745763a17d411
ARG TORTOISE_SHA=6108a894203d60b6cb9188107e5183b17af95b4a
RUN apt-get install -y --no-install-recommends \
      libboost-dev libboost-filesystem-dev libboost-iostreams-dev libboost-regex-dev \
      libboost-system-dev libeigen3-dev libfftw3-dev \
 && export CFLAGS="$(cat /signed-char.flag)" CXXFLAGS="-include stdint.h $(cat /signed-char.flag)" \
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
# TIPL uses uint8_t without including <cstdint>, which GCC 11, on QSIPrep's
# Ubuntu, included through other headers and GCC 14, on Debian's, does not.
FROM builder AS dsistudio
ARG DSI_SHA=03476a67bc96a1d0c90928001b5dd1c490539ee0
ARG TIPL_SHA=ebd2d8b1ee13d6f87e78db62f2f1a1400b353898
ARG ATLAS_SHA=bf5afab9b2405f076b1acdf4706c9688525eb713
ARG UNET_SHA=2e839aae744883983974194dcf6aeff154a82197
RUN apt-get install -y --no-install-recommends \
      libboost-all-dev libglu1-mesa-dev libqt5charts5-dev libqt5opengl5-dev qtbase5-dev qt5-qmake \
 && mkdir -p /opt/dsi-studio && cd /opt/dsi-studio \
 && curl -fsSLO "https://github.com/frankyeh/DSI-Studio/archive/$DSI_SHA.zip" \
 && unzip -q "$DSI_SHA.zip" && mv "DSI-Studio-$DSI_SHA" src && rm "$DSI_SHA.zip" \
 && curl -fsSLO "https://github.com/frankyeh/TIPL/archive/$TIPL_SHA.zip" \
 && unzip -q "$TIPL_SHA.zip" && mv "TIPL-$TIPL_SHA" src/TIPL && rm "$TIPL_SHA.zip" \
 && mkdir build && cd build \
 && qmake ../src QMAKE_CFLAGS+="$(cat /signed-char.flag)" \
      QMAKE_CXXFLAGS+="-include cstdint $(cat /signed-char.flag)" \
 && make -j"$(nproc)" \
 && cd /opt/dsi-studio && mv build/dsi_studio . && chmod 755 dsi_studio \
 && cp -R src/other/* . && rm -rf src build \
 && curl -fsSLO "https://github.com/frankyeh/UNet-Studio-Data/archive/$UNET_SHA.zip" \
 && unzip -q "$UNET_SHA.zip" && rm "$UNET_SHA.zip" \
 && mv "UNet-Studio-Data-$UNET_SHA/network" . && rm -rf "UNet-Studio-Data-$UNET_SHA" \
 && curl -fsSLO "https://github.com/frankyeh/DSI-Studio-atlas/archive/$ATLAS_SHA.zip" \
 && unzip -q "$ATLAS_SHA.zip" && rm "$ATLAS_SHA.zip" \
 && rm -rf "atlas-$ATLAS_SHA/.git" && mv "atlas-$ATLAS_SHA" atlas

# AFNI: the programs QSIPrep's image ships (3dresample, 3dcalc, 3dAutobox and
# the others its workflows call) and those MRIQC's ships, built from source at
# QSIPrep's tag, statically, without the GUI, SUMA, Python or R, as MRIQC builds
# them; and MRIQC's @compute_gcor script. QSIPrep's image also ships 3dSeg and
# 3dSkullStrip, which AFNI builds only with SUMA and none of the three calls:
# QSIPrep's skull stripping is niimath's.
FROM builder AS afni
ARG AFNI_REF=AFNI_25.2.09
RUN apt-get install -y --no-install-recommends libexpat1-dev libgsl-dev libqhull-dev \
 && git clone -q --depth 1 --branch "$AFNI_REF" https://github.com/afni/afni.git /src/afni \
 && export CC=gcc CXX=g++ CFLAGS="$(cat /signed-char.flag)" CXXFLAGS="$(cat /signed-char.flag)" \
 && cmake -S /src/afni -B /build -GNinja -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
      -DCOMP_GUI=OFF -DCOMP_SUMA=OFF -DCOMP_PYTHON=OFF -DCOMP_RSTATS=OFF -DCOMP_ATLASES=OFF \
      -DBUILD_TESTING=OFF -DAFNI_COMPILER_CHECK=OFF -DREMOVE_BUILD_PARITY_CHECKS=ON \
 && progs="3dAutobox 3dAutomask 3dFWHMx 3dQwarp 3dTcat 3dTshift \
      3dTsplit4D 3dTstat 3dUnifize 3dWarp 3dZeropad 3dcalc 3drefit 3dresample 3dvolreg \
      3dDespike 3dinfo 3dmaskave 3dTnorm 3dToutcount 3dTqual" \
 && ninja -C /build $progs \
 && mkdir -p /opt/afni/bin \
 && for p in $progs; do install -m 0755 "$(find /build -type f -name "$p" -perm -u+x | head -1)" /opt/afni/bin/; done \
 && install -m 0755 /src/afni/src/scripts_install/@compute_gcor /opt/afni/bin/ \
 && ! ldd /opt/afni/bin/3d* | grep 'not found' \
 && /opt/afni/bin/3dresample -help >/dev/null \
 && rm -rf /src /build

# Convert3D (c3d_affine_tool, which QSIPrep's gradient rotation calls), on the
# ITK built for TORTOISE, whose libraries the image ships with TORTOISE.
FROM tortoise AS c3d
ARG C3D_REF=v1.4.6
RUN git clone -q --depth 1 --branch "$C3D_REF" https://github.com/pyushkevich/c3d.git /src/c3d \
 && export CFLAGS="$(cat /signed-char.flag)" CXXFLAGS="-include stdint.h $(cat /signed-char.flag)" \
 && cmake -S /src/c3d -B /tmp/c3d-build -GNinja -DCMAKE_BUILD_TYPE=Release \
      -DITK_DIR=/opt/tortoise-itk/lib/cmake/ITK-5.3 -DCONVERT3D_USE_ITK_REMOTE_MODULES=OFF \
      -DCMAKE_INSTALL_PREFIX=/opt/c3d \
 && cmake --build /tmp/c3d-build && cmake --install /tmp/c3d-build \
 && find /opt/c3d/bin -type f -exec patchelf --force-rpath --set-rpath /src/TORTOISEV4/bin/lib/itk {} \; \
 && rm -rf /src/c3d /tmp/c3d-build

# SynthStrip's model, which MRIQC runs on torch: a data file, the same for both
# processors, from the image MRIQC's own takes it from.
FROM --platform=linux/amd64 freesurfer/synthstrip@sha256:f19578e5f033f2c707fa66efc8b3e11440569facb46e904b45fd52f1a12beb8b AS synthstrip

# MRIQC's wheel. MRIQC 26 declares Python 3.13, while this environment is on
# 3.12, which its code runs on: the wheel is built from its tag with the floor
# lowered, at the tag's version.
FROM python:3.12-slim AS mriqc-wheel
ARG MRIQC_REF
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && pip install -q build \
 && git clone -q --depth 1 --branch "$MRIQC_REF" https://github.com/nipreps/mriqc.git /src/mriqc \
 && sed -i 's/^requires-python = ">=3.13"/requires-python = ">=3.12"/' /src/mriqc/pyproject.toml \
 && grep -q '^requires-python = ">=3.12"' /src/mriqc/pyproject.toml \
 && SETUPTOOLS_SCM_PRETEND_VERSION="$MRIQC_REF" python -m build --wheel -o /wheels /src/mriqc \
 && ls /wheels/mriqc-"$MRIQC_REF"-*.whl

# The tools, built apart so that their (long) builds are cached on their own.
FROM scratch AS tools
COPY --from=fsl /opt/fsl /opt/fsl
COPY --from=ants /opt/ants /opt/ants
COPY --from=unpile /wheels /wheels
COPY --from=mriqc-wheel /wheels /wheels
COPY --from=mrtrix3dev /opt/mrtrix3-dev /opt/mrtrix3-dev
COPY --from=tissue3 /opt/3Tissue /opt/3Tissue
COPY --from=niimath /opt/niimath /opt/niimath
COPY --from=tortoise /src/TORTOISEV4/bin /src/TORTOISEV4/bin
COPY --from=tortoise /src/TORTOISEV4/settings /src/TORTOISEV4/settings
COPY --from=dsistudio /opt/dsi-studio /opt/dsi-studio
COPY --from=afni /opt/afni /opt/afni
COPY --from=c3d /opt/c3d /opt/c3d
COPY --from=synthstrip /freesurfer/models/synthstrip.1.pt /opt/freesurfer/models/synthstrip.1.pt

FROM ${BASE}
ARG QSIPREP_REF
ARG QSIRECON_REF
ARG MRIQC_REF
USER root

# MRtrix3 3.0.4, the stable version QSIPrep's image pins, from Debian, which
# builds it for both processors; the libraries DSI Studio and TORTOISE run on;
# and tcsh, for AFNI's @compute_gcor.
RUN apt-get update \
 && apt-get install -y --no-install-recommends mrtrix3 libfftw3-double3 libfftw3-single3 \
      libboost-filesystem1.83.0 libboost-iostreams1.83.0 libboost-regex1.83.0 libboost-system1.83.0 \
      libgomp1 libqt5charts5 libqt5gui5t64 libqt5network5t64 libqt5opengl5t64 libqt5sql5t64 \
      libqt5svg5 libqt5widgets5t64 libgsl28 libqhull-r8.0 libqhull8.0 libexpat1 tcsh \
 && rm -rf /var/lib/apt/lists/*

COPY --from=tools /opt/fsl /opt/fsl
COPY --from=tools /opt/ants /opt/ants
COPY --from=tools /opt/mrtrix3-dev /opt/mrtrix3-dev
COPY --from=tools /opt/3Tissue /opt/3Tissue
COPY --from=tools /opt/niimath /opt/niimath
COPY --from=tools /src/TORTOISEV4 /src/TORTOISEV4
COPY --from=tools /opt/dsi-studio /opt/dsi-studio
COPY --from=tools /opt/afni /opt/afni
COPY --from=tools /opt/c3d /opt/c3d
COPY --from=tools /opt/freesurfer /opt/freesurfer
# FSL's and ANTs' own folders go after the environment's, so that their Python
# and libraries never shadow the notebooks'. FSL's commands are in its bin:
# the wrappers its packages make in share/fsl/bin need post-link scripts, which
# micromamba does not run.
ENV FSLDIR=/opt/fsl FSLOUTPUTTYPE=NIFTI_GZ FSLMULTIFILEQUIT=TRUE \
    ANTSPATH=/opt/ants/bin \
    PATH="$PATH:/opt/c3d/bin:/opt/afni/bin:/opt/dsi-studio:/opt/ants/bin:/opt/fsl/bin:/opt/niimath/bin:/src/TORTOISEV4/bin:/opt/mrtrix3-dev/bin:/opt/3Tissue/bin" \
    TEMPLATEFLOW_HOME=/opt/templateflow DIPY_HOME=/opt/dipy \
    FREESURFER_HOME=/opt/freesurfer \
    AFNI_IMSAVE_WARNINGS=NO \
    MRTRIX3_STABLE_HOME=/usr/lib/mrtrix3 MRTRIX3_STABLE_VERSION=3.0.4 \
    MRTRIX3_DEV_HOME=/opt/mrtrix3-dev MRTRIX3_DEV_VERSION=3.0.8-2071-gb98b54e9 \
    IS_DOCKER_8395080871=1

# QSIPrep, QSIRecon and MRIQC in the environment's own Python, every package
# already there kept at its version: their caps on numpy, pandas and the others
# are lifted (overrides.txt). numpy 2 removed np.row_stack, an alias of
# np.vstack, which QSIPrep and QSIRecon call: the installed files are patched, so
# that the versions stay as tagged. One of pyAFQ's dependencies (phamt) is
# compiled.
COPY docker/qsi/overrides.txt /tmp/overrides.txt
COPY --from=tools /wheels /wheels
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev \
 && pip install --no-cache-dir uv \
 && pip list --format=freeze > /tmp/constraints.txt \
 && git clone -q --depth 1 --branch "$QSIPREP_REF" https://github.com/PennLINC/qsiprep.git /tmp/qsiprep \
 && git clone -q --depth 1 --branch "$QSIRECON_REF" https://github.com/PennLINC/qsirecon.git /tmp/qsirecon \
 && uv pip install --system --no-cache --find-links /wheels --constraints /tmp/constraints.txt \
      --overrides /tmp/overrides.txt /tmp/qsiprep /tmp/qsirecon /wheels/mriqc-*.whl toml \
 && SITE=$(python -c "import sysconfig; print(sysconfig.get_path('purelib'))") \
 && grep -rl 'np\.row_stack(' "$SITE/qsiprep" "$SITE/qsirecon" --include='*.py' \
      | xargs sed -i 's/np\.row_stack(/np.vstack(/g' \
 && ! grep -rq 'np\.row_stack(' "$SITE/qsiprep" "$SITE/qsirecon" --include='*.py' \
 && apt-get purge -y --auto-remove gcc libc6-dev && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/qsi && cp -r /tmp/qsiprep/scripts /opt/qsi/qsiprep-scripts \
 && cp -r /tmp/qsirecon/scripts /opt/qsi/qsirecon-scripts \
 && rm -rf /tmp/qsiprep /tmp/qsirecon /tmp/constraints.txt /tmp/overrides.txt /wheels \
 && python -c "import qsiprep, qsirecon, mriqc; \
      assert qsiprep.__version__ == '$QSIPREP_REF', qsiprep.__version__; \
      assert qsirecon.__version__ == '$QSIRECON_REF', qsirecon.__version__; \
      assert mriqc.__version__ == '$MRIQC_REF', mriqc.__version__" \
 && for c in unpile mriqc synthstrip; do command -v "$c" >/dev/null || exit 1; done \
 && test "$(/usr/lib/mrtrix3/bin/mrinfo -version | head -1 | awk '{print $3}')" = "$MRTRIX3_STABLE_VERSION" \
 && test "$(/opt/mrtrix3-dev/bin/mrinfo -version | head -1 | awk '{print $3}')" = "$MRTRIX3_DEV_VERSION" \
 && ! ldd /opt/dsi-studio/dsi_studio /src/TORTOISEV4/bin/TORTOISEProcess /opt/3Tissue/bin/ss3t_csd_beta1 \
        /opt/mrtrix3-dev/bin/dwidenoise2 /opt/niimath/bin/niimath /opt/c3d/bin/c3d_affine_tool \
        /opt/afni/bin/3dresample /opt/afni/bin/3dTqual | grep 'not found'

# The templates the three prefetch, and QSIRecon's atlases at the path it looks
# for them, outside /home/mri, where the attendee's folder is mounted over the
# image. TemplateFlow's and DIPY's caches stay writable, as in QSIPrep's image,
# so that a template not prefetched can still be downloaded.
RUN python /opt/qsi/qsiprep-scripts/fetch_templates.py --tf-dir "$TEMPLATEFLOW_HOME" \
 && python /opt/qsi/qsirecon-scripts/fetch_templates.py --tf-dir "$TEMPLATEFLOW_HOME" \
 && python -c "from templateflow import api as tf; \
      tf.get('MNI152NLin2009cAsym', resolution=[1, 2], suffix=['T1w', 'T2w'], desc=None); \
      tf.get('MNI152NLin2009cAsym', resolution=[1, 2], suffix='mask', desc=['brain', 'head']); \
      tf.get('MNI152NLin2009cAsym', resolution=1, suffix='dseg', desc='carpet'); \
      tf.get('MNI152NLin2009cAsym', resolution=1, suffix='probseg', label=['CSF', 'GM', 'WM']); \
      tf.get('MNI152NLin2009cAsym', resolution=[1, 2], suffix='boldref')" \
 && mkdir -p /home/qsirecon/.cache/qsirecon && cd /tmp \
 && curl -fsSL -o a.tgz https://upenn.box.com/shared/static/0gxdoe77tuih5p9ainn4utdqj3kcq7p1.tar.gz \
 && echo "543db13adbef32a9d913f5aac9234e9a77a0a5963ae9ac57d3c8bd4ede65cb92  a.tgz" | sha256sum -c - \
 && tar -xzf a.tgz && mv AtlasPack /home/qsirecon/.cache/qsirecon/AtlasPack \
 && curl -fsSL -o b.tgz https://upenn.box.com/shared/static/2p5lfjw3435h9dd8c2oul5j5r6v2ie00.tar.gz \
 && echo "5493db75ca94711595b6f746ea51c0f83097f8e09471f80fde1973e80714556e  b.tgz" | sha256sum -c - \
 && tar -xzf b.tgz && mv qsirecon_atlases /home/qsirecon/.cache/qsirecon/QSIReconAtlases \
 && rm -rf a.tgz b.tgz ._* \
 && mkdir -p "$DIPY_HOME" && (cd /opt/qsi/qsirecon-scripts && python set_up_amico.py) \
 && chmod -R a+rwX /opt/templateflow /opt/dipy && chmod -R a+rX /home/qsirecon /opt/freesurfer

USER mri
