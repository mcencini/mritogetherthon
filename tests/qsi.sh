#!/bin/sh
# QSIPrep's, QSIRecon's and MRIQC's unit tests, and the tools they call, inside
# the :qsi image: docker exec mritogetherthon sh /tests/qsi.sh
# The tests run from the packages' sources, at the versions installed, patched
# as the image patches them, with pytest installed in the running container only.
# With the test data mounted at /data, the tests that need it run too.
# Runs every check and every test whatever fails before. Exits 3 when a tool is
# missing or broken (listed in missing.txt and broken.txt, beside the reports),
# 2 when the tools are there and some tests fail, which tests/compare_junit.py
# judges against the official images, and 1 when the script itself fails.
set -eu
cd /tmp
# Every program QSIPrep and QSIRecon call (their interfaces' commands, CPU
# builds), and FSL's QSIPrep runs. A missing one is reported with the others,
# and fails the script once the tests have run, so that one run tells all. TORTOISE's DIFFPREP is a stage
# of TORTOISEProcess, not a program of its own.
missing=""
for tool in eddy_cpu topup bet flirt fslmaths \
    antsRegistration antsApplyTransforms antsMultivariateTemplateConstruction2.sh \
    N4BiasFieldCorrection ImageMath CompositeTransformUtil ConvertTransformFile \
    mrconvert mrinfo mrcalc mrtransform transformconvert dwidenoise mrdegibbs dwi2tensor \
    dwi2fod dwibiascorrect mtnormalise tckglobal tcksift2 tck2connectome connectome2tck \
    dwidenoise2 ss3t_csd_beta1 niimath svht_denoise unpile \
    dsi_studio dsi_studio_chen 3dresample 3dcalc 3dAutobox 3dTstat 3dTcat 3dWarp 3dAutomask \
    3dTsplit4D 3dvolreg 3dTqual 3dToutcount 3dDespike 3dFWHMx @compute_gcor c3d_affine_tool \
    TORTOISEProcess DRBUDDI CreateMask SelectBestB0 Gibbs EstimateTensor EstimateMAPMRI \
    FSLBVecsToTORTOISEBmatrix TORTOISEBmatrixToFSLBVecs CreateGradientNonlinearityBMatrix \
    CreateNonlinearityDisplacementMap ComputeFAMap ComputeADMap ComputeRDMap ComputeLIMap \
    ComputeMAPMRI_NG ComputeMAPMRI_PA ComputeMAPMRI_RTOP \
    qsiprep qsirecon mriqc trxviz-cli synthstrip mri_synthstrip mri_synthseg Xvfb pandoc dot \
    dmriplayground dmriprep eddy_quad; do
    command -v "$tool" >/dev/null || missing="$missing $tool"
done
echo "$missing" | tr ' ' '\n' | sed '/^$/d' > "${REPORTS:-$HOME}/missing.txt"
if [ -n "$missing" ]; then echo "missing:$missing"; else echo "every tool is on PATH"; fi
# Every MRtrix3 Python command (stable, dev, 3Tissue) starts: those of 3.0.4
# and its forks import modules Python 3.12 removed. (Those that do not use
# MRtrix3's library, such as blend, have no -help.)
for dir in /usr/lib/mrtrix3/bin /opt/mrtrix3-dev/bin /opt/3Tissue/bin; do
    for f in "$dir"/*; do
        head -n 1 "$f" 2>/dev/null | grep -q '^#!.*python' || continue
        grep -q 'import mrtrix3' "$f" || continue
        "$f" -help >/dev/null 2>&1 || broken="${broken:-} $f"
    done
done
echo "MRtrix3 Python commands that do not start:${broken:- none}"
antsRegistration --version | head -1
mrconvert -version | head -1
# SynthStrip on the MNI template's head, against the template's own brain mask.
# A failure is reported at the end, after the tests.
python - <<'EOF' || broken="${broken:-} mri_synthstrip"
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
# A dataset stored under a folder named after a BIDS datatype (here motion,
# which pybids 0.22 knows and the official images' 0.15 does not) keeps its
# diffusion images, as in the official images.
python - <<'EOF' || broken="${broken:-} pybids"
import json, os, tempfile
import bids
root = os.path.join(tempfile.mkdtemp(), 'motion', 'ds')
os.makedirs(f'{root}/sub-01/dwi')
json.dump({'Name': 'x', 'BIDSVersion': '1.8.0'}, open(f'{root}/dataset_description.json', 'w'))
open(f'{root}/sub-01/dwi/sub-01_dwi.nii.gz', 'w').close()
found = bids.BIDSLayout(root, validate=False).get(subject='01', datatype='dwi', suffix='dwi', extension='.nii.gz')
print(f'pybids {bids.__version__}, dataset under motion/: {len(found)} diffusion image')
assert len(found) == 1
EOF
# DTIPlayground configures itself without a question, with the image's FSL.
home=$(mktemp -d)
HOME="$home" dmriplayground init </dev/null >/dev/null 2>&1 || true
grep -q "path: $FSLDIR" "$home/.niral-dti/global_variables.yml" 2>/dev/null \
    && echo "DTIPlayground configured with $FSLDIR" || broken="${broken:-} dtiplayground-init"
# NIRAL's tools, which DTIPlayground finds through DTIPLAYGROUNDTOOLS: each starts.
for p in DTIProcess/bin/dtiprocess DTIProcess/bin/dtiestim DTIProcess/bin/dtiaverage DTIProcess/bin/fiberprocess \
         DTI-Reg/bin/DTI-Reg BRAINSTools/bin/BRAINSFit BRAINSTools/bin/BRAINSDemonWarp \
         ResampleDTIlogEuclidean/bin/ResampleDTIlogEuclidean ITKTransformTools/bin/ITKTransformTools \
         niral_utilities/bin/ImageMath niral_utilities/bin/CropDTI teem/bin/unu \
         ANTs/bin/ANTS ANTs/bin/WarpImageMultiTransform ANTs/bin/WarpTensorImageMultiTransform; do
    out=$("$DTIPLAYGROUNDTOOLS/$p" --help 2>&1 | head -c 2000) || true
    echo "$out" | grep -qiE 'usage|description|option' || broken="${broken:-} $p"
done
pip install -q --user pytest pytest-xdist pytest-env
data=""
[ -d /data ] && data="--data_dir=/data --output_dir=/tmp/qsi-out --working_dir=/tmp/qsi-work" \
    && mkdir -p /tmp/qsi-out /tmp/qsi-work
# SynthSeg's test runs alone, after the others: it peaks near 10 GB, which does
# not fit beside three other workers on a 16 GB runner. Its report is
# qsiprep-synthseg.xml, read with qsiprep.xml.
synthseg=qsiprep/tests/test_interfaces_freesurfer.py::test_synthseg_interface
# QSIRecon's RSI port is checked against ABCD's original script, which QSIRecon
# keeps unmodified and runs as the reference: that script imports
# scipy.special.sph_harm, which SciPy 1.17 removed for sph_harm_y. These two
# tests run apart, with sph_harm given back to that script as SciPy defines the
# change, sph_harm(m, n, phi, theta) = sph_harm_y(n, m, theta, phi); QSIRecon's
# own port calls sph_harm_y. Their report is qsirecon-rsi.xml.
rsi="qsirecon/tests/test_rsi.py::test_rsi_matches_upstream qsirecon/tests/test_rsi.py::test_rsi_matches_upstream_custom_settings"
for name in qsiprep qsirecon; do
    # The tag, or the commit a development version names (+g<commit>).
    ref=$(python -c "import re, $name; v = $name.__version__; m = re.search(r'\+g([0-9a-f]{7,})', v); print(m.group(1) if m else v)")
    rm -rf "$name"
    git clone -q --filter=blob:none "https://github.com/PennLINC/$name.git" && git -C "$name" checkout -q "$ref"
    grep -rl 'np\.row_stack(' "$name/$name" --include='*.py' | xargs -r sed -i 's/np\.row_stack(/np.vstack(/g'
    alone=""; [ "$name" = qsiprep ] && alone="--deselect $synthseg"
    [ "$name" = qsirecon ] && for t in $rsi; do alone="$alone --deselect $t"; done
    (cd "$name" && python -m pytest "$name/tests" -n auto -q -p no:cacheprovider $data $alone \
        --junitxml="${REPORTS:-$HOME}/$name.xml") || status=1
done
(cd qsiprep && python -m pytest "$synthseg" -q -p no:cacheprovider $data \
    --junitxml="${REPORTS:-$HOME}/qsiprep-synthseg.xml") || status=1
shim=$(mktemp -d)
cat > "$shim/sitecustomize.py" <<'EOF'
import scipy.special
if not hasattr(scipy.special, 'sph_harm'):
    scipy.special.sph_harm = lambda m, n, phi, theta: scipy.special.sph_harm_y(n, m, theta, phi)
EOF
(cd qsirecon && PYTHONPATH="$shim${PYTHONPATH:+:$PYTHONPATH}" python -m pytest $rsi -q -p no:cacheprovider $data \
    --junitxml="${REPORTS:-$HOME}/qsirecon-rsi.xml") || status=1
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
# DTIPlayground's tests, from its tag, at the version installed.
version=$(python -c 'from importlib.metadata import version; print(version("dtiplayground"))')
rm -rf dtiplayground
git clone -q --depth 1 --branch "v$version" https://github.com/NIRALUser/DTIPlayground.git dtiplayground
(cd dtiplayground && HOME=$(mktemp -d) python -m pytest tests -q -p no:cacheprovider \
    --junitxml="${REPORTS:-$HOME}/dtiplayground.xml") || status=1
echo "${broken:-}" | tr ' ' '\n' | sed '/^$/d' > "${REPORTS:-$HOME}/broken.txt"
[ -z "${broken:-}" ] || echo "broken: $broken"
[ -z "$missing" ] || echo "missing:$missing"
[ -z "${broken:-}$missing" ] || exit 3
[ -z "${status:-}" ] || exit 2
