#!/bin/sh
# One of QSIPrep's integration tests, in an image, as QSIPrep's CI runs it:
#   sh tests/qsi-integration.sh IMAGE MARKER
# run on the host, from a folder holding the test data in data/. Writes
# reports/MARKER.xml, and QSIPrep's outputs to out/. The same command runs in
# :qsi and in the official image, which holds no pytest: pytest is installed on
# the host, for the image's Python, and mounted. Exits 0 when the report is
# written, whatever the test's outcome, which tests/compare_junit.py judges.
set -eu
image=$1 marker=$2
version=26.2.0
docker pull -q "$image"
py=$(docker run --rm --entrypoint python "$image" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
python3 -m pip install -q --target deps --python-version "$py" --only-binary=:all: \
    pytest pytest-env exceptiongroup tomli
rm -rf src && git clone -q --depth 1 --branch "$version" https://github.com/PennLINC/qsiprep.git src
# As the :qsi image patches its installed copy (numpy 2 removed np.row_stack).
grep -rl 'np\.row_stack(' src/qsiprep --include='*.py' | xargs -r sed -i 's/np\.row_stack(/np.vstack(/g'
mkdir -p reports out work && chmod a+rwx reports out work
docker run --rm --entrypoint bash -e PYTHONPATH=/deps -e CIRCLE_CPUS="$(nproc)" \
    -v "$PWD/deps:/deps:ro" -v "$PWD/src:/src:ro" -v "$PWD/data:/data:ro" \
    -v "$PWD/reports:/reports" -v "$PWD/out:/out" -v "$PWD/work:/work" "$image" -c \
    "cp -r /src /tmp/src && cd /tmp/src && python -m pytest --strict-markers -rP -o log_cli=true \
       -m $marker --junitxml=/reports/$marker.xml -o junit_logging=no \
       --data_dir=/data --output_dir=/out --working_dir=/work qsiprep" || true
test -s "reports/$marker.xml"
