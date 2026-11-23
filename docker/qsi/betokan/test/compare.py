"""Compares brain masks from the harness and from FSL's bet2.

    python compare.py arch INPUTS RESULTS     # one runner: original / ours / bet2
    python compare.py cross AMD64 ARM64       # the two runners' results

RESULTS holds, per input NAME: NAME.orig.raw (original x86 library, amd64
only), NAME.ours.raw (this reimplementation), NAME_bet2_mask.nii.gz (bet2 -m).
Masks are binarised as TORTOISE's create_mask does (nonzero is brain). Writes
RESULTS/metrics.json and NIfTI copies of the harness masks, and prints a
Markdown table.
"""
import json
import sys
from pathlib import Path

import nibabel as nb
import numpy as np

SENTINEL = -7.0  # harness.cpp's fill value: voxels mainokan did not write


def load_raw(path, shape):
    return np.fromfile(path, dtype=np.float32).reshape(shape, order="F")


def pair(a, b):
    if a is None or b is None:
        return {}
    inter = np.count_nonzero(a & b)
    tot = np.count_nonzero(a) + np.count_nonzero(b)
    return {"dice": 2 * inter / tot if tot else 1.0, "differ": int(np.count_nonzero(a != b))}


def fmt_pair(p):
    return f"{p['dice']:.6f} / {p['differ']}" if p else "-"


def arch(inputs, results):
    rows = {}
    for txt in sorted(inputs.glob("*.txt")):
        name = txt.stem
        nx, ny, nz = map(int, txt.read_text().split()[:3])
        img = nb.load(inputs / f"{name}.nii.gz")
        row = {"shape": [nx, ny, nz], "zooms": [float(z) for z in img.header.get_zooms()[:3]]}
        masks = {}
        for kind in ["orig", "ours"]:
            f = results / f"{name}.{kind}.raw"
            if not f.exists():
                continue
            v = load_raw(f, (nx, ny, nz))
            vals = np.unique(v)
            row[f"{kind}_unwritten"] = int(np.count_nonzero(v == SENTINEL))
            row[f"{kind}_values"] = [float(x) for x in vals[:5]] + (["..."] if len(vals) > 5 else [])
            masks[kind] = v != 0
            nb.Nifti1Image(masks[kind].astype(np.uint8), img.affine).to_filename(results / f"{name}.{kind}_mask.nii.gz")
        f = results / f"{name}_bet2_mask.nii.gz"
        if f.exists():
            masks["bet2"] = np.asanyarray(nb.load(f).dataobj) != 0
        for kind, m in masks.items():
            row[f"{kind}_voxels"] = int(np.count_nonzero(m))
        row["orig_vs_ours"] = pair(masks.get("orig"), masks.get("ours"))
        row["ours_vs_bet2"] = pair(masks.get("ours"), masks.get("bet2"))
        row["orig_vs_bet2"] = pair(masks.get("orig"), masks.get("bet2"))
        rows[name] = row
    (results / "metrics.json").write_text(json.dumps(rows, indent=1))

    print("| input | size, mm | voxels: original / ours / bet2 | original vs ours: Dice / differ | ours vs bet2 | original vs bet2 | original's output values |")
    print("|---|---|---|---|---|---|---|")
    for name, r in rows.items():
        counts = " / ".join(str(r.get(f"{k}_voxels", "-")) for k in ["orig", "ours", "bet2"])
        size = "x".join(map(str, r["shape"])) + ", " + "x".join(f"{z:g}" for z in r["zooms"])
        vals = ", ".join(map(str, r.get("orig_values", []))) or "-"
        if r.get("orig_unwritten"):
            vals += f" ({r['orig_unwritten']} unwritten)"
        print(f"| {name} | {size} | {counts} | {fmt_pair(r['orig_vs_ours'])} | "
              f"{fmt_pair(r['ours_vs_bet2'])} | {fmt_pair(r['orig_vs_bet2'])} | {vals} |")


def cross(amd, arm):
    a, b = (json.loads((d / "metrics.json").read_text()) for d in (amd, arm))
    print("| input | ours voxels: amd64 / arm64 | ours amd64 vs arm64: Dice / differ | bet2 voxels: amd64 / arm64 | bet2 amd64 vs arm64 | original (amd64) vs ours (arm64) |")
    print("|---|---|---|---|---|---|")
    for name, r in a.items():
        shape = tuple(r["shape"])
        load = lambda d, k: load_raw(d / f"{name}.{k}.raw", shape) != 0 if (d / f"{name}.{k}.raw").exists() else None
        bet = lambda d: (np.asanyarray(nb.load(d / f"{name}_bet2_mask.nii.gz").dataobj) != 0
                         if (d / f"{name}_bet2_mask.nii.gz").exists() else None)
        s = b.get(name, {})
        print(f"| {name} | {r.get('ours_voxels', '-')} / {s.get('ours_voxels', '-')} | "
              f"{fmt_pair(pair(load(amd, 'ours'), load(arm, 'ours')))} | "
              f"{r.get('bet2_voxels', '-')} / {s.get('bet2_voxels', '-')} | "
              f"{fmt_pair(pair(bet(amd), bet(arm)))} | "
              f"{fmt_pair(pair(load(amd, 'orig'), load(arm, 'ours')))} |")


if __name__ == "__main__":
    mode, x, y = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    arch(x, y) if mode == "arch" else cross(x, y)
