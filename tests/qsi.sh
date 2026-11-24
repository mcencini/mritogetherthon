#!/bin/sh
# QSIPrep's, QSIRecon's and MRIQC's unit tests, and the tools they call, inside
# the :qsi image: docker exec mritogetherthon sh /tests/qsi.sh
# The tests run from the packages' sources, at the versions installed, patched
# as the image patches them, with pytest installed in the running container only.
# With the test data mounted at /data, the tests that need it run too.
# Exits 1 when a tool is missing or broken, and 2 when the tools work and some
# tests fail: which of those failures count is for tests/compare_junit.py to say,
# against the official images.
set -eu
cd /tmp
for tool in eddy_cpu topup bet flirt fslmaths antsRegistration antsApplyTransforms \
    N4BiasFieldCorrection mrconvert dwidenoise mrdegibbs dwi2tensor dwibiascorrect \
    dwidenoise2 ss3t_csd_beta1 niimath svht_denoise unpile \
    dsi_studio 3dresample 3dcalc 3dAutobox 3dTstat 3dTcat 3dWarp 3dAutomask 3dTsplit4D \
    3dvolreg 3dTqual 3dToutcount 3dDespike 3dFWHMx @compute_gcor c3d_affine_tool \
    qsiprep qsirecon mriqc synthstrip mri_synthstrip; do
    command -v "$tool" >/dev/null || { echo "missing: $tool"; exit 1; }
done
# TORTOISE's DIFFPREP is a stage of TORTOISEProcess, not a program of its own.
for tool in TORTOISEProcess DRBUDDI CreateMask; do
    command -v "$tool" >/dev/null || { echo "missing: $tool"; exit 1; }
done
echo "every tool is on PATH"
antsRegistration --version | head -1
mrconvert -version | head -1
# SynthStrip on the MNI template's head, against the template's own brain mask.
python - <<'EOF'
import subprocess, tempfile
import nibabel as nb
from templateflow import api as tf
head = tf.get('MNI152NLin2009cAsym', resolution=2, suffix='T1w', desc=None)
brain = tf.get('MNI152NLin2009cAsym', resolution=2, suffix='mask', desc='brain')
mask = tempfile.mkdtemp() + '/mask.nii.gz'
subprocess.run(['mri_synthstrip', '-i', str(head), '-m', mask], check=True)
a, b = (nb.load(f).get_fdata() > 0 for f in (mask, brain))
dice = 2 * (a & b).sum() / (a.sum() + b.sum())
print(f'mri_synthstrip on the MNI template: Dice {dice:.3f} with its brain mask')
assert dice > 0.85
EOF
pip install -q --user pytest pytest-xdist pytest-env
data=""
[ -d /data ] && data="--data_dir=/data --output_dir=/tmp/qsi-out --working_dir=/tmp/qsi-work" \
    && mkdir -p /tmp/qsi-out /tmp/qsi-work
for name in qsiprep qsirecon; do
    version=$(python -c "import $name; print($name.__version__)")
    rm -rf "$name"
    git clone -q --depth 1 --branch "$version" "https://github.com/PennLINC/$name.git"
    grep -rl 'np\.row_stack(' "$name/$name" --include='*.py' | xargs -r sed -i 's/np\.row_stack(/np.vstack(/g'
    (cd "$name" && python -m pytest "$name/tests" -n auto -q -p no:cacheprovider $data \
        --junitxml="${REPORTS:-$HOME}/$name.xml") || status=1
done
# MRIQC's, as its CI runs them (without stopping at the first failure), from its
# sources with the installed _version.py, as its CI's build of the sources writes
# (python -I, so that the installed MRIQC is imported, not the sources' copy).
version=$(python -c 'import mriqc; print(mriqc.__version__)')
rm -rf mriqc
git clone -q --depth 1 --branch "$version" https://github.com/nipreps/mriqc.git
cp "$(python -I -c 'import mriqc, os; print(os.path.dirname(mriqc.__file__))')/_version.py" mriqc/mriqc/
(cd mriqc && python -m pytest mriqc -o addopts= -ra -p no:cacheprovider -p no:datalad -n auto \
    --doctest-modules --ignore=mriqc/bin --ignore=mriqc/interfaces/transitional.py \
    --junitxml="${REPORTS:-$HOME}/mriqc.xml") || status=1
[ -z "${status:-}" ] || exit 2
