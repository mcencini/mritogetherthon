#!/bin/bash
# NIRAL's DTIPlaygroundTools, the compiled tools DTIPlayground's DTI_Estimate
# (dtiestim), DTI_Register and BRAIN_Tractography call, built as upstream
# builds them (CentOS 7, CMake 3.16.4, `cmake .. && make`, statically), for the
# processor it runs on. Run inside centos:7:
#   bash niral-build.sh /opt/dtiplayground-tools
# installs the programs there, in the layout DTIPlayground looks them up in.
set -euxo pipefail
dest=$1
mkdir -p /tmp/niral
sed -i -e 's/^mirrorlist/#mirrorlist/' -e 's|^#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|' /etc/yum.repos.d/CentOS-*.repo
yum -q -y groupinstall "Development Tools"
yum -q -y install python-devel qt5-qtbase-devel qt4-devel wget openssl-devel freeglut-devel qt5-qtx11extras-devel qt5-qtsvg-devel which
cd /tmp/niral
# CMake 3.16.4, as upstream's image builds it: from source (Kitware has no
# arm64 binary of it).
curl -fsSL https://github.com/Kitware/CMake/releases/download/v3.16.4/cmake-3.16.4.tar.gz | tar xz
(cd cmake-3.16.4 && ./bootstrap --parallel="$(nproc)" --prefix=/tmp/niral/cmake -- -DCMAKE_USE_OPENSSL=ON > cmake-bootstrap.log 2>&1 \
  && make -j"$(nproc)" install >> cmake-bootstrap.log 2>&1) || { tail -50 cmake-3.16.4/cmake-bootstrap.log; exit 1; }
export PATH=/tmp/niral/cmake/bin:$PATH
git clone -q https://github.com/NIRALUser/DTIPlaygroundTools.git src
(cd src && git checkout -q 28f0bdb8ff946259b18e17c88c68dd7bafa45ca7 && git log -1 --format='DTIPlaygroundTools %H %cd')
# Only what DTIPlayground's DTI_Estimate (dtiestim), DTI_Register and
# BRAIN_Tractography call; the superbuild adds their dependencies itself.
python - <<'PY'
import re
p = 'src/SuperBuild.cmake'
s = open(p).read()
s, n = re.subn(r'list\( APPEND \$\{LOCAL_PROJECT_NAME\}_DEPENDENCIES ITKv4 .*?\n\s*\)',
               'list( APPEND ${LOCAL_PROJECT_NAME}_DEPENDENCIES ITKv4 VTK SlicerExecutionModel teem ANTs '
               'BRAINSTools BatchMake JPEG TIFF DCMTK DTIProcess DTI-Reg ResampleDTIlogEuclidean '
               'niral_utilities ITKTransformTools )', s, flags=re.S)
assert n == 1, 'dependency list'
open(p, 'w').write(s)
p = 'src/SuperBuild/External_ANTs.cmake'
s = open(p).read()
assert s.count('-DBUILD_ALL_ANTS_APPS:BOOL=ON') == 1
s = s.replace('-DBUILD_ALL_ANTS_APPS:BOOL=ON', '-DBUILD_ALL_ANTS_APPS:BOOL=OFF -DANTS_BUILD_ANTS:BOOL=ON '
              '-DANTS_BUILD_WarpImageMultiTransform:BOOL=ON -DANTS_BUILD_WarpTensorImageMultiTransform:BOOL=ON')
open(p, 'w').write(s)
p = 'src/DTIPlaygroundTools.cmake'
s = open(p).read()
s, n = re.subn(r'install ?\((PROGRAMS|DIRECTORY) \$\{(MriWatcher|Trafic|AtlasWerks)_[A-Z_]+\}.*?\)\s*\n', '', s, flags=re.S)
assert n == 3, n
open(p, 'w').write(s)
PY
mkdir src/build && cd src/build
# GitHub no longer serves git://
# VTK 8.1.1's HDF5 (H5detect.c) needs POSIX's sigjmp_buf, which its strict C mode hides.
cmake -DUSE_GIT_PROTOCOL_DTIPlaygroundTools=OFF -DUSE_GIT_PROTOCOL=OFF \
  -DCMAKE_C_FLAGS=-D_GNU_SOURCE .. > cmake.log 2>&1 || { tail -50 cmake.log; exit 1; }
make -j"$(nproc)" > make.log 2>&1 || { grep -nE ': error|\*\*\* \[' make.log | head -30; tail -30 make.log; exit 1; }
# The programs alone, where DTIPlayground's software_paths.yml expects them.
tools=DTIPlaygroundTools-install/dtiplayground-tools
for p in DTIProcess/bin/dtiprocess DTIProcess/bin/dtiestim DTIProcess/bin/dtiaverage DTIProcess/bin/fiberprocess \
         DTI-Reg/bin/DTI-Reg BRAINSTools/bin/BRAINSFit BRAINSTools/bin/BRAINSDemonWarp \
         ResampleDTIlogEuclidean/bin/ResampleDTIlogEuclidean ITKTransformTools/bin/ITKTransformTools \
         niral_utilities/bin/ImageMath niral_utilities/bin/CropDTI teem/bin/unu \
         ANTs/bin/ANTS ANTs/bin/WarpImageMultiTransform ANTs/bin/WarpTensorImageMultiTransform; do
    install -D -m 755 "$tools/$p" "$dest/$p"
done
cp "$tools/info.yml" "$dest/info.yml"
cd / && rm -rf /tmp/niral
