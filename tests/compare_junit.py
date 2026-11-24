"""Lists the tests that fail in the :qsi image but pass in the official one.

Usage: python tests/compare_junit.py --ours A.xml [B.xml ...] --official C.xml [D.xml ...]
                                     [--expected tests/qsi-expected.txt]

Each side's reports are merged. A test listed in the expected file (one
classname::name per line, # for comments) is reported but not counted: it is a
difference the image is known to have, such as a program left out on purpose.
Exits 1 when any other test passes in the official image only, so that only the
failures that are ours count.
"""

import argparse
import sys
import xml.etree.ElementTree as ET


def outcomes(paths):
    result = {}
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            key = f"{case.get('classname')}::{case.get('name')}"
            bad = case.find("failure") if case.find("failure") is not None else case.find("error")
            if bad is not None:
                message = (bad.get("message") or "failed").splitlines() or ["failed"]
                result[key] = message[0][:160]
            elif case.find("skipped") is not None:
                result[key] = "skipped"
            else:
                result[key] = "passed"
    return result


def summary(results):
    passed = sum(v == "passed" for v in results.values())
    skipped = sum(v == "skipped" for v in results.values())
    return f"{passed} passed, {len(results) - passed - skipped} failed or errors, {skipped} skipped"


parser = argparse.ArgumentParser()
parser.add_argument("--ours", nargs="+", required=True)
parser.add_argument("--official", nargs="+", required=True)
parser.add_argument("--expected")
args = parser.parse_args()

expected = set()
if args.expected:
    with open(args.expected) as f:
        expected = {line.split("#")[0].strip() for line in f} - {""}

ours, base = outcomes(args.ours), outcomes(args.official)
print(f"ours:     {summary(ours)}")
print(f"official: {summary(base)}")
worse = {k: v for k, v in ours.items() if v not in ("passed", "skipped") and base.get(k) == "passed"}
better = sorted(k for k, v in base.items() if v not in ("passed", "skipped") and ours.get(k) == "passed")
known = {k: v for k, v in worse.items() if k in expected}
new = {k: v for k, v in worse.items() if k not in expected}
print(f"pass in the official image only: {len(new)}, and {len(known)} expected")
for k, v in sorted(new.items()):
    print(f"  {k}: {v}")
for k, v in sorted(known.items()):
    print(f"  (expected) {k}: {v}")
print(f"pass in ours only: {len(better)}")
for k in better:
    print(f"  {k}")
sys.exit(1 if new else 0)
