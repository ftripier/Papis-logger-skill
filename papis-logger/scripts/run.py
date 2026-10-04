"""Bootstrap under `papis exec`, whose exec scope is not a normal module."""
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(sys.argv[0]).resolve().with_name("logger.py")), run_name="__main__")
