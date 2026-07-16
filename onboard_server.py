#!/usr/bin/env python3
"""On Board MCP runtime launcher.

Use this as the MCP command target through `python3 onboard_server.py`.
It uses only the Python standard library, so it can rebuild the local `.venv`
with `uv sync --inexact` before execing the real MCP server.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv" / "bin" / "python"
SERVER = ROOT / "server.py"


def main() -> int:
    if not PY.exists():
        uv = shutil.which("uv")
        if not uv:
            print("On Board runtime is missing and uv is not installed.", file=sys.stderr)
            print(f"Install uv, then run: cd {ROOT!s} && uv sync --inexact", file=sys.stderr)
            return 127
        subprocess.run([uv, "sync", "--inexact"], cwd=ROOT, check=True)

    os.execv(str(PY), [str(PY), str(SERVER), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
