#!/bin/sh
# MRIQC's pipeline test, as its CircleCI runs it on its arm64 runners (no WebAPI):
# participant and group level on the circle-tests dataset, then the outputs
# against .circleci/circle_<MODALITY>.txt and the IQMs against
# mriqc/data/testdata/group_<MODALITY>.tsv (dfcheck).
#   sh tests/mriqc-pipeline.sh IMAGE MODALITY [--strict]
# MODALITY is T1w or bold; --strict is how MRIQC's amd64 CI checks the IQMs.
# Run on the host, from a folder holding the dataset in data/circle-tests.
# Writes reports/mriqc_MODALITY.xml, one test case per check, for
# tests/compare_junit.py; exits 0 once it is written.
set -u
image=$1 mod=$2 strict=${3:-}
version=26.1.1
lower=$(echo "$mod" | tr A-Z a-z)
docker pull -q "$image"
rm -rf mriqc-src scratch && git clone -q --depth 1 --branch "$version" https://github.com/nipreps/mriqc.git mriqc-src
mkdir -p scratch/work scratch/derivatives reports && chmod -R a+rwX scratch reports
printf "[execution]\nstop_on_first_crash = true\npoll_sleep_duration = 0.01\nhash_method = content\n" > scratch/nipype.cfg
case $mod in
    T1w) extra="--random-seed 42" ;;
    bold) extra="--testing" ;;
esac
run() {
    docker run -u "$(id -u)" --rm -e MRIQC_DEV=1 -e HOME=/tmp \
        -v "$PWD/data/circle-tests:/data:ro" -v "$PWD/scratch:/scratch" -v "$PWD/mriqc-src:/src:ro" \
        -w /scratch "$@"
}
cases=""
record() {  # name, outcome (0 = passed), message
    if [ "$2" -eq 0 ]; then
        cases="$cases<testcase classname=\"mriqc.pipeline.$mod\" name=\"$1\"/>"
    else
        cases="$cases<testcase classname=\"mriqc.pipeline.$mod\" name=\"$1\"><failure message=\"$3\"/></testcase>"
    fi
}
run --entrypoint mriqc "$image" /data derivatives/ participant -vv --verbose-reports -m "$mod" \
    --dsname circletests $extra --no-sub --n_procs 2 --ants-nthreads 1 --ants-float \
  && run --entrypoint mriqc "$image" /data derivatives/ group -m "$mod" -vv
record participant_and_group $? "MRIQC failed: see the job's log"
# The listing as CircleCI makes it, whose root line is its own path.
(cd scratch && find derivatives) | sed "s+^derivatives/++; s+^derivatives\$+/tmp/$lower/derivatives+" \
    | LC_ALL=C sort > outputs.out
diff "mriqc-src/.circleci/circle_$mod.txt" outputs.out
record outputs $? "the outputs differ from .circleci/circle_$mod.txt: see the job's log"
run --entrypoint dfcheck "$image" -i "/scratch/derivatives/group_$mod.tsv" \
    -r "/src/mriqc/data/testdata/group_$mod.tsv" $strict
record iqms $? "the IQMs differ from mriqc/data/testdata/group_$mod.tsv: see the job's log"
printf '<?xml version="1.0"?><testsuites><testsuite name="mriqc-pipeline">%s</testsuite></testsuites>\n' \
    "$cases" > "reports/mriqc_$mod.xml"
cat "reports/mriqc_$mod.xml"
