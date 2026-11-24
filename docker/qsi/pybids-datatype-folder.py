"""Make pybids read a file's datatype from the folder that holds it, only.

pybids matches its datatype pattern anywhere in a file's absolute path, so a
dataset stored under a folder named after a datatype has its files misread.
pybids 0.22, which this environment needs (niworkflows, sdcflows, smriprep),
knows three datatypes 0.15 did not, motion, mrs and nirs: a dataset under, say,
~/motion/ loses its diffusion images, where QSIPrep's official image (0.15)
finds them. In BIDS the datatype folder always holds the file, so the pattern is
anchored there: for every dataset laid out as BIDS says, the result is pybids'
own, and so the official image's.

Usage: python pybids-datatype-folder.py
"""

import json
import re
from pathlib import Path

import bids

config = Path(bids.__file__).parent / "layout" / "config" / "bids.json"
spec = json.loads(config.read_text())
(entity,) = [e for e in spec["entities"] if e["name"] == "datatype"]
old = entity["pattern"]
# "[/\\]+(anat|...|pet)[/\\]+" followed by the file name, and nothing else.
assert old.startswith("[/\\\\]+(") and old.endswith(")[/\\\\]+"), old
entity["pattern"] = old + "(?=[^/\\\\]+$)"
config.write_text(json.dumps(spec, indent=4) + "\n")

pattern = re.compile(entity["pattern"])
for path, datatype in [
    ("/home/mri/motion/ds/sub-01/dwi/sub-01_dwi.nii.gz", "dwi"),
    ("/data/trxscan/motion/sub-motion/dwi/sub-motion_dwi.nii.gz", "dwi"),
    ("/home/mri/ds/sub-01/ses-1/anat/sub-01_ses-1_T1w.nii.gz", "anat"),
    ("/home/mri/ds/sub-01/mrs/sub-01_svs.nii.gz", "mrs"),
    ("/home/mri/ds/dataset_description.json", None),
]:
    match = pattern.search(path)
    assert (match and match.group(1)) == datatype, (path, match and match.group(1))
print(f"pybids {bids.__version__}: datatype read from the file's own folder ({config})")
