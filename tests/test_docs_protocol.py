import asyncio
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]




def test_public_source_repo_has_no_generated_project_files():
    generated_paths = [
        ".agent-mem",
        ".agent-mem-hooks",
        ".codex",
        ".cursor",
        ".claude",
        ".agent",
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
    ]
    for path in generated_paths:
        assert not (REPO_ROOT / path).exists(), path

    result = subprocess.run(
        ["bash", "doctor.sh", "--self"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "On Board Source Doctor" in result.stdout
    assert "0 failed" in result.stdout


def test_release_materials_match_current_version():
    """Version lives in pyproject; everything else must agree with it.

    Previously this pinned '4.0.0' as a literal in two places, so every release
    had to hand-edit the test that was supposed to be guarding the release. Read
    the version instead: drift between pyproject and the changelog now fails
    without anyone having to remember to update this file.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first_header = next(line for line in changelog.splitlines() if line.startswith("## v"))
    release_notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    version_match = re.search(r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$', pyproject, re.MULTILINE)
    assert version_match, "pyproject.toml has no parseable version"
    version = version_match.group(1)

    assert first_header.startswith(f"## v{version}"), (
        f"changelog leads with {first_header!r}, pyproject says {version}")
    assert f"v{version}" in release_notes, f"RELEASE_NOTES.md does not mention v{version}"



def _backticked_tool_names(text: str) -> set:
    return set(re.findall(r"`(memory_[a-z_]+)`", text))


def _registry_tool_names(tmp_path):
    """The server's real tool registry, imported away from any real board.

    AGENT_PROJECT_DIR (and the fallbacks server.py reads) are pinned to a
    throwaway project BEFORE the import, because the memory root is resolved at
    import time, and restored afterwards so this cannot touch a user's board.
    """
    keys = ("AGENT_PROJECT_DIR", "CURSOR_PROJECT_DIR", "CLAUDE_PROJECT_DIR",
            "AGENT_MEM_VECTOR_BACKEND")
    saved = {key: os.environ.get(key) for key in keys}
    os.environ["AGENT_PROJECT_DIR"] = str(tmp_path)
    os.environ.pop("CURSOR_PROJECT_DIR", None)
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    os.environ["AGENT_MEM_VECTOR_BACKEND"] = "none"
    sys.path.insert(0, str(REPO_ROOT))
    try:
        name = f"docs_protocol_server_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {tool.name for tool in asyncio.run(module.mcp.list_tools())}
    finally:
        sys.path.remove(str(REPO_ROOT))
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_documented_tool_inventory_matches_the_registry(tmp_path):
    """The public tool list is a contract: compare names, not a count.

    The README table and the docs/TOOLS headings must each cover every tool the
    server registers, and no tool the server does not have. A renamed or deleted
    tool therefore fails here instead of lingering in prose, which is how the
    docs drifted to 28/29 tools while the server exposed 30.
    """
    actual = _registry_tool_names(tmp_path)
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    tools_doc = (REPO_ROOT / "docs/TOOLS.md").read_text(encoding="utf-8")

    readme_table = readme.split("## Tools", 1)[1].split("\n---", 1)[0]
    documented_table = _backticked_tool_names(readme_table)
    documented_headings = set(
        re.findall(r"^### `(memory_[a-z_]+)`", tools_doc, re.MULTILINE))

    assert documented_table == actual, (
        f"README table missing {sorted(actual - documented_table)}; "
        f"unknown {sorted(documented_table - actual)}")
    assert documented_headings == actual, (
        f"docs/TOOLS headings missing {sorted(actual - documented_headings)}; "
        f"unknown {sorted(documented_headings - actual)}")

    # The LobeHub plugin manifest is the same public list in machine-readable
    # form; it drifted once already (it advertised a tool the server did not
    # have), so it is held to the registry too.
    manifest = json.loads((REPO_ROOT / "lhm.plugin.json").read_text(encoding="utf-8"))
    advertised = {tool["name"] for tool in manifest["tools"]}
    assert advertised == actual, (
        f"lhm.plugin.json missing {sorted(actual - advertised)}; "
        f"advertising unknown {sorted(advertised - actual)}")

    for path in ("README.md", "docs/TOOLS.md", "docs/SETUP.md", "SKILL.md",
                 "templates/agent-rules.md"):
        named = _backticked_tool_names((REPO_ROOT / path).read_text(encoding="utf-8"))
        # `kinds` documents event names, and `memory_written` matches the
        # tool-name shape without being a tool.
        unknown = named - actual - {"memory_written"}
        assert not unknown, f"{path} mentions unknown tools: {sorted(unknown)}"
