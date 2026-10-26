#!/usr/bin/env python3
"""Exercise a wheel-installed runtime outside its source checkout, without MCP requests."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


SMOKE = r'''
import asyncio
import os
from pathlib import Path
import subprocess
import sys

import server
import a2a_wait
import ticket_roles
import thrift_compress

prefix = Path(sys.prefix).resolve()
for module in (server, a2a_wait, ticket_roles, thrift_compress):
    assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
icons = server._server_icons()
assert icons and icons[0].src.startswith("data:image/png;base64,"), "installed icon missing"
tools = asyncio.run(server.mcp.list_tools())
prompts = asyncio.run(server.mcp.list_prompts())
assert len(tools) == 30 and len(prompts) == 2, (len(tools), len(prompts))
command = Path(sys.executable).parent / ("onboard-memory-mcp.exe" if os.name == "nt" else "onboard-memory-mcp")
result = subprocess.run([str(command)], input="", text=True, capture_output=True, timeout=15)
assert result.returncode == 0, result.stderr
print(f"Installed runtime passed: {len(tools)} tools, {len(prompts)} prompts, icon and console entrypoint")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("python", type=Path, help="Python executable in the wheel-only virtual environment")
    python = parser.parse_args().python.absolute()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="onboard-installed-smoke-") as directory:
        env["AGENT_PROJECT_DIR"] = directory
        result = subprocess.run([str(python), "-I", "-c", SMOKE], cwd=directory, env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
