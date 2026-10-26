import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_distribution.py"
PAYLOAD = {
    "server.py": b"# server\n",
    "a2a_wait.py": b"# wait\n",
    "ticket_roles.py": b"# roles\n",
    "thrift_compress.py": b"# thrift\n",
    "dashboard_live.py": b"# dashboard\n",
    "onboard_server.py": b"# launcher\n",
    "docs/assets/on-board-icon.png": b"\x89PNG\r\n\x1a\n",
}
META = "onboard_memory_mcp-4.0.2.dist-info/"


def artifacts(tmp_path, *, omit=None, extra=None, sdist_extra=None, metadata=None, entrypoint=None):
    wheel = dict(PAYLOAD)
    if omit:
        wheel.pop(omit)
    wheel.update(extra or {})
    wheel[META + "METADATA"] = metadata or b"Metadata-Version: 2.3\nName: onboard-memory-mcp\nVersion: 4.0.2\n"
    wheel[META + "entry_points.txt"] = entrypoint or b"[console_scripts]\nonboard-memory-mcp = server:main\n"
    with zipfile.ZipFile(tmp_path / "onboard_memory_mcp-4.0.2-py3-none-any.whl", "w") as archive:
        for name, body in wheel.items():
            archive.writestr(name, body)
    sources = {**PAYLOAD, "pyproject.toml": b"[project]\n", **(sdist_extra or {})}
    with tarfile.open(tmp_path / "onboard_memory_mcp-4.0.2.tar.gz", "w:gz") as archive:
        for name, body in sources.items():
            info = tarfile.TarInfo("onboard_memory_mcp-4.0.2/" + name)
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))


def check(path):
    return subprocess.run([sys.executable, str(CHECKER), str(path)], text=True, capture_output=True)


def test_valid_distribution_passes(tmp_path):
    artifacts(tmp_path)
    result = check(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", ["ticket_roles.py", "docs/assets/on-board-icon.png"])
def test_missing_runtime_payload_is_rejected(tmp_path, name):
    artifacts(tmp_path, omit=name)
    result = check(tmp_path)
    assert result.returncode == 1
    assert name in result.stdout


def test_unexpected_test_module_in_wheel_is_rejected(tmp_path):
    artifacts(tmp_path, extra={"test_private.py": b"private fixture"})
    result = check(tmp_path)
    assert result.returncode == 1
    assert "test_private.py" in result.stdout


@pytest.mark.parametrize("name", [".agent-mem/memories.json", ".onboard/linked-projects.json", ".env", "../outside.py"])
def test_private_or_escaping_sdist_member_is_rejected(tmp_path, name):
    artifacts(tmp_path, sdist_extra={name: b"private"})
    result = check(tmp_path)
    assert result.returncode == 1
    assert name in result.stdout


@pytest.mark.parametrize("kwargs", [
    {"metadata": b"Name: another-package\nVersion: 4.0.2\n"},
    {"entrypoint": b"[console_scripts]\nonboard-memory-mcp = wrong:main\n"},
])
def test_incorrect_installed_identity_is_rejected(tmp_path, kwargs):
    artifacts(tmp_path, **kwargs)
    result = check(tmp_path)
    assert result.returncode == 1
    assert "onboard-memory-mcp" in result.stdout


def test_corrupt_archive_returns_diagnostic_without_traceback(tmp_path):
    artifacts(tmp_path)
    next(tmp_path.glob("*.whl")).write_bytes(b"not a zip")
    result = check(tmp_path)
    assert result.returncode == 1
    assert ".whl" in result.stdout
    assert "Traceback" not in result.stderr


def test_missing_distributions_are_rejected(tmp_path):
    result = check(tmp_path)
    assert result.returncode == 1
    assert "wheel" in result.stdout.lower()
    assert "sdist" in result.stdout.lower()
