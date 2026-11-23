#!/bin/sh
# QSIPrep's and QSIRecon's unit tests, and the tools they call, inside the :qsi
# image: docker exec mritogetherthon sh /tests/qsi.sh
# The tests run from the packages' sources, at the versions installed, patched
# as the image patches them, with pytest installed in the running container only.
# With the test data mounted at /data, the tests that need it run too.
set -eu
cd /tmp
for tool in eddy_cpu topup bet flirt fslmaths antsRegistration antsApplyTransforms \
    N4BiasFieldCorrection mrconvert dwidenoise mrdegibbs dwi2tensor dwibiascorrect \
    dwidenoise2 ss3t_csd_beta1 niimath svht_denoise TORTOISEProcess DIFFPREP DRBUDDI unpile dsi_studio 3dresample 3dcalc 3dAutobox 3dTstat 3dTcat 3dWarp 3dAutomask 3dTsplit4D; do
    command -v "$tool" >/dev/null || { echo "missing: $tool"; exit 1; }
done
echo "every tool is on PATH"
antsRegistration --version | head -1
mrconvert -version | head -1
pip install -q --user pytest pytest-xdist pytest-env
data=""
[ -d /data ] && data="--data_dir=/data --output_dir=/tmp/qsi-out --working_dir=/tmp/qsi-work" \
    && mkdir -p /tmp/qsi-out /tmp/qsi-work
for spec in qsiprep:$(python -c 'import qsiprep;print(qsiprep.__version__)') \
            qsirecon:$(python -c 'import qsirecon;print(qsirecon.__version__)'); do
    name=${spec%%:*} version=${spec#*:}
    rm -rf "$name"
    git clone -q --depth 1 --branch "$version" "https://github.com/PennLINC/$name.git"
    grep -rl 'np\.row_stack(' "$name/$name" --include='*.py' | xargs -r sed -i 's/np\.row_stack(/np.vstack(/g'
    (cd "$name" && python -m pytest "$name/tests" -n auto -q -p no:cacheprovider $data \
        --junitxml="${REPORTS:-$HOME}/$name.xml") || status=1
done
exit ${status:-0}
