"""Executable tests for the inline JS emitted by ``dashboard_live.py``.

The generator module is never imported: ``HTML_TEMPLATE`` is lifted straight
out of the source with :mod:`ast`, its three placeholders are substituted the
way the generator does, the single inline ``<script>`` block is evaluated under
a minimal DOM/timer/fetch stub, and the *real* ``derive()`` is called on
purpose-built fixtures. Assertions are on the derived view model (memberships,
totals, colours), never on source text or on a mocked return value.

A JS runtime (node, else bun) is required; tests skip with a reason if neither
is on PATH.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = REPO_ROOT / "dashboard_live.py"

PROJECT_NAME = "fixture-project"
POLL_MS = 5000

NOW = time.time()
ISO_NOW = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(NOW))

RUNTIME = next((exe for exe in ("node", "bun") if shutil.which(exe)), None)
requires_js = pytest.mark.skipif(
    RUNTIME is None,
    reason="no JS runtime (node or bun) on PATH; the emitted inline JS cannot be exercised",
)


# --------------------------------------------------------------------------- #
# template extraction (no generator execution)
# --------------------------------------------------------------------------- #
def read_html_template() -> str:
    """Return the HTML_TEMPLATE literal from the source, without running it."""
    tree = ast.parse(DASHBOARD.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HTML_TEMPLATE":
                    value = ast.literal_eval(node.value)
                    assert isinstance(value, str) and value.strip()
                    return value
    raise AssertionError("HTML_TEMPLATE assignment not found in dashboard_live.py")


def render_template() -> str:
    """Apply the generator's placeholder substitutions to the raw template."""
    html = read_html_template()
    html = html.replace("__PROJECT_NAME_JS__", json.dumps(PROJECT_NAME)[1:-1])
    html = html.replace("__PROJECT_NAME__", PROJECT_NAME)
    html = html.replace("__POLL_MS__", str(POLL_MS))
    return html


def extract_inline_js(html: str) -> str:
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match, "inline <script> block not found in rendered dashboard"
    return match.group(1)


# --------------------------------------------------------------------------- #
# JS harness
# --------------------------------------------------------------------------- #
# Minimal browser surface: just enough for the module body + render()/boot() to
# run. fetch always fails so resolveBase() bails out; the tests then install
# their own fixture and call derive() directly.
PRELUDE = r"""
const __noop = function () {};
function __el() {
  return {
    innerHTML: "", textContent: "", value: "",
    style: {}, dataset: {},
    classList: { add: __noop, remove: __noop, toggle: __noop, contains: function () { return false; } },
    addEventListener: __noop, removeEventListener: __noop,
    setAttribute: __noop, removeAttribute: __noop,
    querySelector: function () { return __el(); }, querySelectorAll: function () { return []; },
    appendChild: __noop, focus: __noop, closest: function () { return null; }
  };
}
function __def(name, value) {
  try { Object.defineProperty(globalThis, name, { value: value, configurable: true, writable: true }); }
  catch (e) { try { globalThis[name] = value; } catch (e2) {} }
}
__def("window", globalThis);
__def("document", {
  documentElement: __el(), body: __el(),
  getElementById: function () { return __el(); },
  querySelector: function () { return __el(); }, querySelectorAll: function () { return []; },
  createElement: function () { return __el(); },
  addEventListener: __noop, removeEventListener: __noop
});
__def("location", { search: "" });
__def("localStorage", { getItem: function () { return null; }, setItem: __noop, removeItem: __noop });
__def("navigator", { clipboard: { writeText: function () { return Promise.resolve(); } } });
__def("fetch", function () { return Promise.resolve({ ok: false, status: 404, json: function () { return Promise.resolve({}); } }); });
__def("setInterval", function () { return 0; });
__def("clearInterval", __noop);
__def("setTimeout", function () { return 0; });
__def("clearTimeout", __noop);
"""

DRIVER = r"""
state.data = __FIXTURE__;
state.loading = false;
state.error = null;
const __v = derive();
const TH3 = '\u0e01\u0e02\u0e04';
const EM3 = '\u{1F600}\u{1F601}\u{1F602}';
const EM4 = '\u{1F600}\u{1F600}\u{1F600}\u{1F600}';
const out = {
  active: __v.counts.activeTickets,
  unknown: __v.counts.unknownTickets,
  stages: __v.flowStages.map(function (s) { return [s.key, s.count, s.items.map(function (t) { return t.id; })]; }),
  branches: __v.flowBranch.map(function (b) { return [b.key, b.items.map(function (t) { return t.id; })]; }),
  branchTotal: __v.flowBranchTotal,
  orphans: __v.tickets.filter(function (t) { return t.isOrphan; }).map(function (t) { return t.id; }),
  health: __v.health.map(function (h) { return h.msg; }),
  hscore: __v.hscore,
  statusColors: __v.tickets.map(function (t) { return [t.id, t.statusColor]; }),
  totalTok: __v.totalTok,
  tokenKpis: __v.tokenKpis.map(function (k) { return [k.label, k.val]; }),
  tokenValues: __v.tokenSegs.map(function (s) { return [s.label, s.value]; }),
  quotaNoSystem: __v.q.noSystem,
  quotaWithSystem: __v.q.withSystem,
  quotaSavedPer: __v.q.savedPer,
  estimates: {
    ascii4: estimateTokens('abcd'),
    ascii5: estimateTokens('abcde'),
    ascii8: estimateTokens('abcdefgh'),
    empty: estimateTokens(''),
    thai3: estimateTokens(TH3),
    emoji4: estimateTokens(EM4),
    perEntry: memoryTokens([{ title: TH3, content: EM3 }]),
    aggregated: estimateTokens(TH3 + EM3)
  }
};
console.log('__RESULT__' + JSON.stringify(out));
"""


def build_harness(fixture: dict) -> str:
    inline = extract_inline_js(render_template())
    driver = DRIVER.replace("__FIXTURE__", json.dumps(fixture))
    return PRELUDE + "\n;(function () {\n\"use strict\";\n" + inline + "\n" + driver + "\n})();\n"


def run_fixture(fixture: dict) -> dict:
    """Evaluate the emitted inline JS against ``fixture`` and return derive()."""
    assert RUNTIME, "run_fixture called without a JS runtime"
    with tempfile.TemporaryDirectory() as td:
        harness = Path(td) / "harness.js"
        harness.write_text(build_harness(fixture), encoding="utf-8")
        proc = subprocess.run([RUNTIME, str(harness)], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"JS harness failed ({proc.returncode}):\n{proc.stderr}\n{proc.stdout}"
    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])
    raise AssertionError(f"no __RESULT__ line; stdout={proc.stdout!r} stderr={proc.stderr!r}")


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
ACTIVE_CLAIM_STATUSES = ("claimed", "in_progress", "creating_report", "submitted", "reviewing", "in_review")

AGENTS = {
    "a-alpha": {
        "agent_name": "alpha", "agent_role": "main", "status": "active",
        "agent_platform": "claude", "memories_written": 4,
        "last_activity": NOW, "joined_at": ISO_NOW,
    },
    "a-ghost": {
        "agent_name": "ghost", "agent_role": "coder", "status": "completed",
        "agent_platform": "codex", "memories_written": 2,
        "last_activity": NOW - 7200, "joined_at": ISO_NOW,
    },
}


def _memory(mid, title, content, **kw):
    base = {
        "id": mid, "title": title, "content": content,
        "memory_type": "note", "agent_name": "alpha",
        "timestamp": NOW, "created_at": ISO_NOW,
        "tags": [], "related_files": [], "related_tickets": [], "pinned": False,
    }
    base.update(kw)
    return base


def _ticket(tid, status, **kw):
    base = {
        "id": tid, "title": f"ticket {tid}", "status": status, "priority": "medium",
        "created_by": "alpha", "assigned_to": "alpha",
        "timestamp": NOW, "created_at": ISO_NOW,
        "tags": [], "related_files": [],
    }
    base.update(kw)
    return base


def _data(memories=(), tickets=(), digests=(), archive=()):
    return {
        "project": {"name": PROJECT_NAME, "description": "", "tech": ""},
        "memories": list(memories),
        "agents": dict(AGENTS),
        "digests": list(digests),
        "archive": list(archive),
        "tickets": list(tickets),
        "stateKv": {},
    }


def status_fixture() -> dict:
    """One ticket per canonical state, with a stale claimer on the six claims."""
    specs = [
        ("t-open", "open", {}),
        ("t-claimed", "claimed", {"claimed_by": "ghost"}),
        ("t-progress", "in_progress", {"claimed_by": "ghost"}),
        ("t-report", "creating_report", {"claimed_by": "ghost"}),
        ("t-submitted", "submitted", {"claimed_by": "ghost"}),
        ("t-reviewing", "reviewing", {"claimed_by": "ghost"}),
        ("t-in-review", "in_review", {"claimed_by": "ghost"}),
        ("t-rejected", "rejected", {}),
        ("t-closed", "closed", {}),
        ("t-canceled", "canceled", {}),
        ("t-terminated", "terminated", {}),
    ]
    return _data(tickets=[_ticket(tid, status, **kw) for tid, status, kw in specs])


def alias_fixture() -> dict:
    """Legacy 'cancelled', distinct 'terminated', and an unrecognised state."""
    specs = [
        ("t-open", "open", {}),
        ("t-cancelled", "cancelled", {}),
        ("t-canceled", "canceled", {}),
        ("t-terminated", "terminated", {}),
        ("t-archived", "archived", {}),
    ]
    return _data(tickets=[_ticket(tid, status, **kw) for tid, status, kw in specs])


def token_fixture() -> dict:
    """Short ASCII entries plus 3-code-point Thai/emoji title and content."""
    memories = [
        _memory("m-ascii", "abcdefgh", "ijklmnop"),                       # 2 + 2
        _memory("m-unicode", "\u0e01\u0e02\u0e04", "\U0001F600\U0001F601\U0001F602"),  # 0 + 0
    ]
    digests = [{"summary": "abcdefghijkl", "compressed_at": ISO_NOW, "method": "local"}]  # 3
    return _data(memories=memories, digests=digests)


# --------------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------------- #
@requires_js
def test_active_kpis_flow_and_orphans_cover_every_canonical_state():
    result = run_fixture(status_fixture())

    # Active = live work + awaiting adjudication, never closed/canceled/terminated.
    assert result["active"] == 8
    assert result["unknown"] == 0

    stages = {key: (count, ids) for key, count, ids in result["stages"]}
    assert stages["open"] == (1, ["t-open"])
    assert stages["in_progress"][0] == 3
    assert sorted(stages["in_progress"][1]) == ["t-claimed", "t-progress", "t-report"]
    assert stages["in_review"][0] == 3
    assert sorted(stages["in_review"][1]) == ["t-in-review", "t-reviewing", "t-submitted"]
    assert stages["closed"] == (1, ["t-closed"])

    branches = {key: ids for key, ids in result["branches"]}
    assert branches["canceled"] == ["t-canceled"]
    assert branches["rejected"] == ["t-rejected"]
    assert branches["terminated"] == ["t-terminated"]
    assert result["branchTotal"] == 3

    # One stale-claim set: the six claim statuses whose claimer is inactive.
    assert sorted(result["orphans"]) == [
        "t-claimed", "t-in-review", "t-progress", "t-report", "t-reviewing", "t-submitted",
    ]
    assert len(result["health"]) == 6

    # Score uses the same predicate and the same set as the rows above.
    assert result["hscore"] == 100 - 6 * 8


@requires_js
def test_active_claimer_is_not_an_orphan_in_any_claim_stage():
    fixture = _data(tickets=[
        _ticket(f"active-{status}", status, claimed_by="alpha")
        for status in ACTIVE_CLAIM_STATUSES
    ])
    result = run_fixture(fixture)
    assert result["orphans"] == []
    assert result["hscore"] == 100


@requires_js
def test_cancelled_alias_terminated_branch_and_unknown_state():
    result = run_fixture(alias_fixture())

    stages = {key: ids for key, _count, ids in result["stages"]}
    assert stages["open"] == ["t-open"]
    assert result["active"] == 1
    # An unrecognised state is never quietly relabelled as Open.
    assert result["unknown"] == 1
    for ids in stages.values():
        assert "t-archived" not in ids

    branches = {key: sorted(ids) for key, ids in result["branches"]}
    assert branches["canceled"] == ["t-canceled", "t-cancelled"]
    assert branches["rejected"] == []
    assert branches["terminated"] == ["t-terminated"]
    assert result["branchTotal"] == 3

    colors = dict(result["statusColors"])
    assert colors["t-cancelled"] == colors["t-canceled"]     # legacy spelling folds onto canceled
    assert colors["t-terminated"] != colors["t-canceled"]    # terminated is its own state


@requires_js
def test_token_estimates_match_server_per_entry_model():
    result = run_fixture(token_fixture())
    est = result["estimates"]

    # floor(code points / 4), code points counted with for..of
    assert est["ascii4"] == 1
    assert est["ascii5"] == 1
    assert est["ascii8"] == 2
    assert est["empty"] == 0
    assert est["thai3"] == 0            # 3 code points
    assert est["emoji4"] == 1           # 4 astral emoji = 4 code points
    assert est["perEntry"] == 0         # 3 + 3 code points, floored per entry (title, content)
    assert est["aggregated"] == 1       # the same 6 code points floored once would be 1

    # Overview, Tokens tab and Quota all read the same per-entry sums.
    assert result["totalTok"] == 4       # m-ascii 2+2, m-unicode 0+0
    values = dict(result["tokenValues"])
    assert values["Hot memory"] == 4
    assert values["Digests"] == 3
    assert values["Archive (disk only)"] == 0

    kpis = dict(result["tokenKpis"])
    assert kpis["Hot memory"] == "~4"
    assert kpis["Digests"] == "~3"
    assert kpis["Archive"] == "~0"
    assert kpis["Per session"] == "~507"

    # Quota keeps the 20%/15% rework model but on top of the shared estimate:
    # brief = 4 + 0 + 500, noSystem = 504 + floor(100.8) + floor(75.6).
    assert result["quotaNoSystem"] == "679"
    assert result["quotaWithSystem"] == "507"
    assert result["quotaSavedPer"] == "172"
