"""Makes MRtrix3 3.0.4's Python commands (dwibiascorrect, dwi2response and the
others), as Debian packages them, run on Python 3.12, which removed the two
modules they import: imp, with which bin/mrtrix3.py finds the library, and
distutils, for find_executable. MRtrix3 replaced both from 3.0.5 on; QSIPrep
pins 3.0.4. The behaviour is unchanged: importlib finds and loads the same
module, and shutil.which is what find_executable did.

Usage: python mrtrix3-python312.py /usr/lib/mrtrix3
"""

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])

loader = root / "bin" / "mrtrix3.py"
text = loader.read_text()
old_import = "import imp, os, sys\nfrom distutils.spawn import find_executable\n"
old_imported = """def imported(lib_path):
  success = False
  fp = None
  try:
    fp, pathname, description = imp.find_module('mrtrix3', [ lib_path ])
    imp.load_module('mrtrix3', fp, pathname, description)
    success = True
  except ImportError:
    pass
  finally:
    if fp:
      fp.close()
  return success
"""
new_import = "import importlib.machinery, importlib.util, os, sys\nfrom shutil import which as find_executable\n"
new_imported = """def imported(lib_path):
  spec = importlib.machinery.PathFinder.find_spec('mrtrix3', [ lib_path ])
  if spec is None:
    return False
  module = importlib.util.module_from_spec(spec)
  sys.modules['mrtrix3'] = module
  spec.loader.exec_module(module)
  return True
"""
assert old_import in text and old_imported in text, f"{loader} is not 3.0.4's"
loader.write_text(text.replace(old_import, new_import).replace(old_imported, new_imported))

patched = [loader]
for path in root.rglob("*.py"):
    text = path.read_text()
    if "from distutils.spawn import find_executable" in text:
        path.write_text(text.replace("from distutils.spawn import find_executable",
                                     "from shutil import which as find_executable"))
        patched.append(path)
# Imports and calls only: comments may still name distutils.
stale = re.compile(r"^\s*(from|import)\s+(distutils|imp)\b|\bimp\.", re.MULTILINE)
left = [p for p in root.rglob("*.py") if stale.search(p.read_text())]
assert not left, f"still importing distutils or imp: {left}"
print("patched", len(patched), "files")
