"""PyInstaller entry point; keep the package entry point's relative imports."""
import sys

from splicelet.runtime import ARTIFACTS

if getattr(sys,'frozen',False):
    ARTIFACTS.mkdir(parents=True,exist_ok=True)
    log = (ARTIFACTS/'application.log').open('a',encoding='utf-8',buffering=1)
    sys.stdout = log
    sys.stderr = log

import splicelet.__main__
