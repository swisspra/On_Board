#!/usr/bin/env python3
"""measure_compaction.py — how much does thrift compression actually save on digests?

Answers one question honestly: run `compress_digest` over real board text and
report the token delta, with a gate that fails any unit which lost a fact.

    uv run --with tiktoken python tools/measure_compaction.py --corpus <file.json>
    uv run --with tiktoken python tools/measure_compaction.py --board <project-dir>
    uv run --with tiktoken python tools/measure_compaction.py --archive <project-dir>

Design notes (why it looks like this):
  * tiktoken is NOT a repo dependency. Run through `uv run --with tiktoken`.
    Without it the harness still runs and reports character deltas, clearly
    labelled as a proxy — it never silently substitutes one metric for another.
  * The tokenizer is o200k_base, a GPT-family encoder. It is NOT Claude's.
    Every report says so. Use it for relative comparison, not billing math.
  * A unit that drops a protected literal scores FAIL. The headline number
    counts gate-passing units only, because a "saving" bought by deleting an
    ID is not a saving.
  * Never mutates the board. Read-only, always.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thrift_compress import compress_digest  # noqa: E402

# --- fidelity gate --------------------------------------------------------
# Same protected classes the v4 board-style measurement used, so numbers from
# the two runs stay comparable.
_PROTECTED = {
    "ticket": re.compile(r"TK-[0-9a-f]{12}"),
    "mem_id": re.compile(r"(?<!TK-)\b[0-9a-f]{12}\b"),
    "number": re.compile(r"\d+(?:[.,]\d+)+|\d+"),
    "path":   re.compile(r"[\w~${}./-]*/[\w${}.*/-]+|\b[\w-]+\.(?:md|py|json|sh|toml|jpg)\b"),
    "code":   re.compile(r"`([^`\n]+)`"),
}

# Titles are a separate class because the literal classes above cannot see
# them. compress_digest once rewrote plain entry titles while every protected
# literal survived, and the old fidelity() scored that 1.0 -- a gate blind to
# the very requirement it exists to enforce. These patterns make that failure
# expressible. `--self-test` proves they still can.
_TITLE_SPANS = (
    ("heading", re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+\S.*$", re.M)),
    ("bold_title", re.compile(r"^[ \t]*[-*][ \t]+(\*\*.+?\*\*)", re.M)),
    ("plain_title", re.compile(r"^[ \t]*[-*][ \t]+(.+?)[ \t]+\(`[^`\n]+`\)[ \t]*$", re.M)),
)


def gate(original: str, compressed: str) -> list[str]:
    """Literals and titles from `original` that did not survive into `compressed`."""
    misses = []
    for label, pattern in _PROTECTED.items():
        for item in set(pattern.findall(original)):
            if item and item not in compressed:
                misses.append(f"{label}:{item[:60]}")
    for label, pattern in _TITLE_SPANS:
        for m in pattern.finditer(original):
            span = (m.group(1) if m.groups() else m.group(0)).strip()
            if span and span not in compressed:
                misses.append(f"{label}:{span[:60]}")
    return misses


def self_test() -> int:
    """Prove the gate can go red. A gate that only ever passes proves nothing."""
    cases = [
        ("plain title rewritten",
         "- Refactored the database configuration in the deployment environment (`bob`)",
         "- Refactored DB config in deployment env (`bob`)"),
        ("heading rewritten", "# The database configuration", "# DB config"),
        ("ticket id dropped", "see TK-000000000000 for detail", "see the ticket for detail"),
        ("number changed", "saved 17.8% overall", "saved a lot overall"),
    ]
    ok = True
    for name, before, after in cases:
        misses = gate(before, after)
        print(f"  {'RED ' if misses else 'GREEN'}  {name}"
              + (f" -> {misses[0]}" if misses else "  <-- GATE IS BLIND HERE"))
        ok = ok and bool(misses)
    clean = gate("- Title kept (`bob`)\n# Heading kept", "- Title kept (`bob`)\n# Heading kept")
    print(f"  {'GREEN' if not clean else 'RED  '}  unchanged text passes"
          + (f" -> {clean}" if clean else ""))
    ok = ok and not clean
    print("\nself-test", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


# --- corpus loading -------------------------------------------------------
def from_corpus(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()}


def _entries_to_units(entries: list, tag: str) -> dict:
    units = {}
    for e in entries:
        body = (e.get("content") or "").strip()
        if body:
            units[f"{tag}:{e.get('id', len(units))}"] = body
    return units


def from_board(project: Path) -> dict:
    """Exactly the entries `memory_compact` would compact -- no more, no less.

    Delegates to server._split_hot_cold so this cannot drift from the server's
    own rule (HOT_WINDOW_HOURS, MAX_HOT_ENTRIES, pinning). An earlier version
    approximated cold as priority<3, which ignored the 24h hot window and so
    measured a corpus larger than compaction actually touches.

    A pinned or high-priority entry is exempt from compaction forever, so it
    can never appear in a compaction measurement. Boards whose owner pins
    everything therefore have no measurable corpus -- a property of the board,
    not a bug here, and the caller is told so plainly.
    """
    os.environ["AGENT_PROJECT_DIR"] = str(project)  # server reads this at import
    try:
        import server as S
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(f"--board needs the server module importable: {exc}")
    _hot, cold = S._split_hot_cold(S._load_mem())
    return _entries_to_units(cold, "board")


def from_archive(project: Path) -> dict:
    p = project / ".agent-mem" / "archive.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return _entries_to_units(data if isinstance(data, list) else data.get("entries", []), "archive")


# --- measurement ----------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--corpus", type=Path, help="JSON object of {name: text}")
    src.add_argument("--board", type=Path, help="project dir; measures COLD entries only")
    src.add_argument("--archive", type=Path, help="project dir; measures archived entries")
    src.add_argument("--self-test", action="store_true",
                     help="prove the fidelity gate can fail, then exit")
    ap.add_argument("--budget", default="medium",
                    help="lossless | verbatim | light | medium | aggressive")
    ap.add_argument("--dump", type=Path, help="write a side-by-side audit file")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.corpus:
        units, origin = from_corpus(args.corpus), f"corpus {args.corpus}"
    elif args.board:
        units, origin = from_board(args.board), f"live board {args.board} (cold entries)"
    else:
        units, origin = from_archive(args.archive), f"archive {args.archive}"

    if not units:
        print(f"EMPTY COLD SET: {origin} has nothing compaction would touch.")
        print("  This is a property of the source, not missing coverage here.")
        if args.board:
            print("  Every entry is currently exempt — pinned, inside the hot window")
            print("  (AGENT_MEM_HOT_HOURS), or within the AGENT_MEM_MAX_HOT budget.")
            print("  Measure --archive or --corpus instead; do NOT unpin the board to")
            print("  manufacture a corpus.")
        return 2

    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        size, unit_name, exact = (lambda s: len(enc.encode(s))), "tok", True
    except ImportError:
        size, unit_name, exact = len, "char", False
        print("tiktoken absent — reporting CHARACTER deltas as a proxy.")
        print("Re-run via `uv run --with tiktoken ...` for real token counts.\n")

    rows, dump = [], []
    for name, original in sorted(units.items()):
        compressed = compress_digest(original, budget=args.budget)
        misses = gate(original, compressed)
        before, after = size(original), size(compressed)
        saving = (1 - after / before) * 100 if before else 0.0
        rows.append((name, before, after, saving, not misses, misses))
        dump.append(
            f"\n\n{'=' * 78}\n## {name}  ({before} -> {after} {unit_name}, {saving:.1f}%)  "
            f"gate={'PASS' if not misses else 'FAIL ' + ', '.join(misses[:6])}"
            f"\n\n--- ORIGINAL ---\n{original}\n\n--- COMPRESSED ---\n{compressed}")

    print(f"source: {origin}")
    print(f"budget: {args.budget}\n")
    print(f"{'unit':46} {'before':>8} {'after':>8} {'save':>7}  gate")
    for name, before, after, saving, ok, _m in rows:
        print(f"{name[:46]:46} {before:8} {after:8} {saving:6.1f}%  {'PASS' if ok else 'FAIL'}")

    passed = [r for r in rows if r[4]]
    tb, ta = sum(r[1] for r in rows), sum(r[2] for r in rows)
    print("-" * 82)
    print(f"{'ALL UNITS':46} {tb:8} {ta:8} {(1 - ta / tb) * 100:6.1f}%   n={len(rows)}")
    if passed:
        pb, pa = sum(r[1] for r in passed), sum(r[2] for r in passed)
        print(f"{'GATE-PASSED ONLY (the honest number)':46} {pb:8} {pa:8} "
              f"{(1 - pa / pb) * 100:6.1f}%   n={len(passed)}/{len(rows)}")

    failures = [r for r in rows if not r[4]]
    if failures:
        print("\nGATE FAILURES — fix the compressor, never the gate:")
        for name, *_rest, misses in failures:
            print(f"  {name}")
            for m in misses[:6]:
                print(f"    - lost {m}")

    if args.dump:
        args.dump.write_text("# compaction audit dump\n" + "".join(dump), encoding="utf-8")
        print(f"\naudit dump: {args.dump}")

    print(f"\nunits are {unit_name}; "
          + ("tokenizer o200k_base (GPT family) — NOT Claude's tokenizer, so treat "
             "this as relative, not billing-accurate."
             if exact else "character proxy, not tokens."))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
