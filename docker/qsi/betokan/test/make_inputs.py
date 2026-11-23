"""Test volumes for libbetokan: MNI templates from TemplateFlow, mean b=0
volumes from dipy's example data and from any DWI datasets found under the
directories given after the output directory (QSIPrep's test data).

Each volume NAME is written three ways, with the same voxels in the same order
(the file's, which is also ITK's buffer order):
  NAME.txt   "nx ny nz dx dy dz"   for the harness
  NAME.raw   float32, x fastest    for the harness
  NAME.nii.gz float32              for FSL's bet2

    python make_inputs.py OUTDIR [DWI_DIR ...]
"""
import sys
from pathlib import Path

import nibabel as nb
import numpy as np


def write(out, name, data, zooms, affine):
    data = np.asarray(data, dtype=np.float32)
    (out / f"{name}.txt").write_text("%d %d %d %.9g %.9g %.9g\n" % (*data.shape, *zooms))
    data.ravel(order="F").tofile(out / f"{name}.raw")
    img = nb.Nifti1Image(data, affine)
    img.header.set_zooms(zooms)
    img.to_filename(out / f"{name}.nii.gz")
    print(f"{name}: {data.shape} {zooms}")


def mean_b0(dwi, bval):
    img = nb.load(dwi)
    bvals = np.loadtxt(bval).ravel()
    data = np.asarray(img.dataobj, dtype=np.float64)
    return data[..., bvals <= 50].mean(axis=-1), img


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    import templateflow.api as tflow
    for tpl, res, suffix in [
        ("MNI152NLin2009cAsym", 1, "T1w"),
        ("MNI152NLin2009cAsym", 2, "T1w"),
        ("MNI152NLin2009cAsym", 1, "T2w"),
        ("MNI152NLin6Asym", 2, "T1w"),
    ]:
        f = tflow.get(tpl, resolution=res, suffix=suffix, desc=None, extension=".nii.gz")
        img = nb.load(f)
        write(out, f"{tpl}_res-{res}_{suffix}", img.get_fdata(), img.header.get_zooms()[:3], img.affine)

    from dipy.data import get_fnames
    for name in ["stanford_hardi", "sherbrooke_3shell"]:
        dwi, bval, _ = get_fnames(name=name)
        data, img = mean_b0(dwi, bval)
        write(out, f"{name}_meanb0", data, img.header.get_zooms()[:3], img.affine)
    # A single b=0, noisier than the mean TORTOISE usually passes.
    dwi, bval, _ = get_fnames(name="stanford_hardi")
    img = nb.load(dwi)
    write(out, "stanford_hardi_b0first", img.dataobj[..., 0], img.header.get_zooms()[:3], img.affine)

    for d in sys.argv[2:]:
        dwis = [f for f in sorted(Path(d).rglob("*_dwi.nii.gz")) if "part-phase" not in f.name]
        for dwi in dwis[:2]:
            bval = Path(str(dwi).replace(".nii.gz", ".bval"))
            if not bval.exists():
                bval = Path(str(bval).replace("_part-mag", ""))
            if not bval.exists():
                print(f"no bval for {dwi}")
                continue
            data, img = mean_b0(dwi, bval)
            name = Path(d).name + "_" + dwi.name.replace("_dwi.nii.gz", "") + "_meanb0"
            write(out, name, data, img.header.get_zooms()[:3], img.affine)


if __name__ == "__main__":
    main()
