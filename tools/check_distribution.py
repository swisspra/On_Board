#!/usr/bin/env python3
"""Validate release archives before installation or publishing (stdlib only)."""
from __future__ import annotations

import argparse
import configparser
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


PAYLOAD = frozenset({
    "server.py", "a2a_wait.py", "ticket_roles.py", "thrift_compress.py",
    "board_resources.py", "board_subscriptions.py",
    "dashboard_live.py", "onboard_server.py", "docs/assets/on-board-icon.png",
})
SDIST_FILES = PAYLOAD | {"pyproject.toml", "README.md", "LICENSE", "PKG-INFO", ".gitignore"}
PRIVATE = frozenset({
    ".agent-mem", ".onboard", ".venv", "venv", ".env", "__pycache__",
    ".pytest_cache", ".git", ".work", ".claude", ".codex", ".cursor",
    ".agent", ".agent-mem-hooks",
})


def _unsafe(name: str) -> bool:
    path = PurePosixPath(name)
    return (path.is_absolute() or ".." in path.parts or "\\" in name
            or any(part in PRIVATE for part in path.parts)
            or bool(path.parts and ":" in path.parts[0]))


def _wheel_errors(path: Path) -> list[str]:
    errors = []
    with zipfile.ZipFile(path) as archive:
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        if len(names) != len(set(names)):
            errors.append("duplicate archive members")
        paths = set(names)
        for name in sorted(paths):
            parts = PurePosixPath(name).parts
            metadata = bool(parts and parts[0].startswith("onboard_memory_mcp-")
                            and parts[0].endswith(".dist-info"))
            if _unsafe(name) or (name not in PAYLOAD and not metadata):
                errors.append(f"unexpected wheel member: {name}")
        errors.extend(f"missing wheel member: {name}" for name in sorted(PAYLOAD - paths))
        for basename in ("METADATA", "entry_points.txt"):
            hits = [name for name in names if name.endswith(".dist-info/" + basename)]
            if len(hits) != 1:
                errors.append(f"expected one {basename} for onboard-memory-mcp")
                continue
            body = archive.read(hits[0])
            if basename == "METADATA":
                if BytesParser().parsebytes(body).get("Name") != "onboard-memory-mcp":
                    errors.append("METADATA Name must be onboard-memory-mcp")
            else:
                entrypoints = configparser.ConfigParser()
                entrypoints.read_string(body.decode("utf-8"))
                if entrypoints.get("console_scripts", "onboard-memory-mcp", fallback="") != "server:main":
                    errors.append("console script onboard-memory-mcp must point to server:main")
    return errors


def _sdist_errors(path: Path) -> list[str]:
    errors = []
    sources = set()
    roots = set()
    with tarfile.open(path, "r:gz") as archive:
        seen = set()
        for entry in archive:
            name = entry.name
            parts = PurePosixPath(name).parts
            if _unsafe(name):
                errors.append(f"unsafe/private sdist member: {name}")
            if not parts:
                continue
            roots.add(parts[0])
            if entry.isdir():
                continue
            if not entry.isfile():
                errors.append(f"non-regular sdist member: {name}")
            if name in seen:
                errors.append(f"duplicate sdist member: {name}")
            seen.add(name)
            relative = "/".join(parts[1:])
            sources.add(relative)
            if relative not in SDIST_FILES:
                errors.append(f"unexpected sdist member: {name}")
        if len(roots) != 1:
            errors.append("sdist must have a single top-level directory")
        required = PAYLOAD | {"pyproject.toml"}
        errors.extend(f"missing sdist member: {name}" for name in sorted(required - sources))
    return errors


def check_distribution(dist_dir: Path) -> list[str]:
    """Return archive-specific violations; an empty list means all artifacts pass."""
    errors = []
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if not wheels:
        errors.append(f"{dist_dir}: no wheel found")
    if not sdists:
        errors.append(f"{dist_dir}: no sdist found")
    for path, inspect in [(p, _wheel_errors) for p in wheels] + [(p, _sdist_errors) for p in sdists]:
        try:
            errors.extend(f"{path.name}: {error}" for error in inspect(path))
        except (OSError, ValueError, EOFError, zipfile.BadZipFile, tarfile.TarError,
                configparser.Error, UnicodeError, KeyError) as exc:
            errors.append(f"{path.name}: cannot inspect archive: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist_dir", type=Path)
    errors = check_distribution(parser.parse_args().dist_dir)
    for error in errors:
        print(error)
    if not errors:
        print("Distribution archives passed")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
