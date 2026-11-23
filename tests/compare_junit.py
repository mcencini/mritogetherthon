"""Lists the tests that fail in the :qsi image but pass in the official one.

Usage: python tests/compare_junit.py OURS.xml BASELINE.xml
Exits 1 when there is any, so that only the failures that are ours count.
"""

import sys
import xml.etree.ElementTree as ET


def outcomes(path):
    result = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        key = f"{case.get('classname')}::{case.get('name')}"
        bad = case.find("failure") if case.find("failure") is not None else case.find("error")
        if bad is not None:
            result[key] = (bad.get("message") or "").splitlines()[0][:160] if bad.get("message") else "failed"
        elif case.find("skipped") is not None:
            result[key] = "skipped"
        else:
            result[key] = "passed"
    return result


ours, base = outcomes(sys.argv[1]), outcomes(sys.argv[2])
count = lambda d, v: sum(1 for x in d.values() if (x == v) if v in ("passed", "skipped") else x not in ("passed", "skipped"))
print(f"ours:     {count(ours, 'passed')} passed, {count(ours, 'failed')} failed or errors, {count(ours, 'skipped')} skipped")
print(f"official: {count(base, 'passed')} passed, {count(base, 'failed')} failed or errors, {count(base, 'skipped')} skipped")
worse = {k: v for k, v in ours.items() if v not in ("passed", "skipped") and base.get(k) == "passed"}
better = [k for k, v in base.items() if v not in ("passed", "skipped") and ours.get(k) == "passed"]
print(f"pass in the official image only: {len(worse)}")
for k, v in sorted(worse.items()):
    print(f"  {k}: {v}")
print(f"pass in ours only: {len(better)}")
sys.exit(1 if worse else 0)
