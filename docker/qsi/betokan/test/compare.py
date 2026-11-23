"""Compares the brain images from the harness and from FSL's bet2.

    python compare.py arch INPUTS RESULTS     # one runner: original / ours / bet2
    python compare.py cross AMD64 ARM64       # the two runners' results

RESULTS holds, per input NAME: NAME.orig.raw (original x86 library, amd64
only) and NAME.ours.raw (this reimplementation), the buffers mainokan wrote,
and NAME_bet2.nii.gz, bet2's brain image. The mask is their nonzero voxels,
as TORTOISE's create_mask takes it. Writes RESULTS/metrics.json and NIfTI
copies of the harness masks, and prints a Markdown table.
"""
import json
import sys
from pathlib import Path

import nibabel as nb
import numpy as np


def outputs(results, name, shape):
    """Each program's output for one input, as float32 arrays."""
    out = {}
    for kind in ["orig", "ours"]:
        f = results / f"{name}.{kind}.raw"
        if f.exists():
            out[kind] = np.fromfile(f, dtype=np.float32).reshape(shape, order="F")
    f = results / f"{name}_bet2.nii.gz"
    if f.exists():
        out["bet2"] = np.asanyarray(nb.load(f).dataobj).astype(np.float32)
    return out


def pair(a, b):
    """Dice and differing voxels of the two masks, and voxels whose values differ."""
    if a is None or b is None:
        return {}
    ma, mb = a != 0, b != 0
    tot = np.count_nonzero(ma) + np.count_nonzero(mb)
    same = (a == b) | (np.isnan(a) & np.isnan(b))
    return {"dice": 2 * np.count_nonzero(ma & mb) / tot if tot else 1.0,
            "differ": int(np.count_nonzero(ma != mb)),
            "values_differ": int(np.count_nonzero(~same))}


def fmt(p):
    return f"{p['dice']:.6f} / {p['differ']} / {p['values_differ']}" if p else "-"


def arch(inputs, results):
    rows = {}
    for txt in sorted(inputs.glob("*.txt")):
        name = txt.stem
        shape = tuple(map(int, txt.read_text().split()[:3]))
        zooms = [float(z) for z in txt.read_text().split()[3:6]]
        out = outputs(results, name, shape)
        row = {"shape": shape, "zooms": zooms}
        for kind, v in out.items():
            row[f"{kind}_voxels"] = int(np.count_nonzero(v != 0))
            row[f"{kind}_unwritten"] = int(np.count_nonzero(np.isnan(v)))
        for kind in ["orig", "ours"]:
            if kind in out:
                nb.Nifti1Image((out[kind] != 0).astype(np.uint8), np.diag([-zooms[0], *zooms[1:], 1])
                               ).to_filename(results / f"{name}.{kind}_mask.nii.gz")
        row["orig_vs_ours"] = pair(out.get("orig"), out.get("ours"))
        row["ours_vs_bet2"] = pair(out.get("ours"), out.get("bet2"))
        rows[name] = row
    (results / "metrics.json").write_text(json.dumps(rows, indent=1))

    print("Mask voxels are the nonzero voxels of each output; pairs give Dice / voxels in one mask only / voxels whose output values differ.")
    print()
    print("| input | size, mm | mask voxels: original / ours / bet2 | original vs ours | ours vs bet2 | unwritten voxels: original / ours |")
    print("|---|---|---|---|---|---|")
    for name, r in rows.items():
        counts = " / ".join(str(r.get(f"{k}_voxels", "-")) for k in ["orig", "ours", "bet2"])
        unwritten = " / ".join(str(r.get(f"{k}_unwritten", "-")) for k in ["orig", "ours"])
        size = "x".join(map(str, r["shape"])) + ", " + "x".join(f"{z:g}" for z in r["zooms"])
        print(f"| {name} | {size} | {counts} | {fmt(r['orig_vs_ours'])} | {fmt(r['ours_vs_bet2'])} | {unwritten} |")


def cross(amd, arm):
    rows = json.loads((amd / "metrics.json").read_text())
    print("Pairs give Dice / voxels in one mask only / voxels whose output values differ.")
    print()
    print("| input | mask voxels, ours: amd64 / arm64 | ours, amd64 vs arm64 | bet2, amd64 vs arm64 | original (amd64) vs ours (arm64) |")
    print("|---|---|---|---|---|")
    for name, r in rows.items():
        a = outputs(amd, name, tuple(r["shape"]))
        b = outputs(arm, name, tuple(r["shape"]))
        nb_arm = int(np.count_nonzero(b["ours"] != 0)) if "ours" in b else "-"
        print(f"| {name} | {r.get('ours_voxels', '-')} / {nb_arm} | {fmt(pair(a.get('ours'), b.get('ours')))} | "
              f"{fmt(pair(a.get('bet2'), b.get('bet2')))} | {fmt(pair(a.get('orig'), b.get('ours')))} |")


if __name__ == "__main__":
    mode, x, y = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    arch(x, y) if mode == "arch" else cross(x, y)
