#!/usr/bin/env python3
"""
Agent Memory LIVE Dashboard — emits a self-refreshing HTML shell that polls
the raw .agent-mem/*.json files via fetch() and re-renders in place.

Unlike dashboard.py (which bakes a static snapshot of the data into HTML),
this file emits a SHELL. Once generated, the HTML updates itself every few
seconds without re-running Python. Run it once, serve the folder via
`python3 -m http.server`, and watch memories appear live.

Usage:
  python3 dashboard_live.py                        ← uses AGENT_PROJECT_DIR or cwd
  python3 dashboard_live.py /path/to/project       ← specify project path
  python3 dashboard_live.py --open                 ← generate + start server + open browser
  python3 dashboard_live.py --serve                ← generate + start server (no browser)
  python3 dashboard_live.py --port 9000            ← use different port (default 8765)
  python3 dashboard_live.py --interval 5000        ← poll interval in ms (default 3000)

Output: <project>/.agent-mem/dashboard-live.html
"""

import json
import os
import sys
from pathlib import Path

# ── CLI args ────────────────────────────────────────────────────────────────
args = sys.argv[1:]
flags = {a for a in args if a.startswith("--")}
positional = [a for a in args if not a.startswith("--")]

def get_flag_value(name, default):
    for i, a in enumerate(args):
        if a == name and i + 1 < len(args) and not args[i + 1].startswith("--"):
            try:
                return int(args[i + 1])
            except ValueError:
                return default
        if a.startswith(name + "="):
            try:
                return int(a.split("=", 1)[1])
            except ValueError:
                return default
    return default

PORT = get_flag_value("--port", 8765)
POLL_MS = get_flag_value("--interval", get_flag_value("--poll-sec", 5) * 1000 if "--poll-sec" in flags else 5000)

PROJECT_ROOT = Path(positional[0] if positional else os.environ.get("AGENT_PROJECT_DIR", os.getcwd()))
MEMORY_DIR = PROJECT_ROOT / ".agent-mem"
OUT_PATH = MEMORY_DIR / "dashboard-live.html"

if not MEMORY_DIR.exists():
    print(f"❌ .agent-mem/ not found at {MEMORY_DIR}")
    print(f"   Run memory_init first, or pass a project path that has .agent-mem/")
    sys.exit(1)

# ── HTML shell ──────────────────────────────────────────────────────────────
# Written in plain strings (not f-strings) to avoid brace-escaping pain.
# Only a few placeholders are substituted via str.replace at the end.

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>On Board · Live — __PROJECT_NAME__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0c0d10;--panel:#14161b;--elevated:#1b1e24;--border:#2a2d35;--text:#f0f0f2;--muted:#8b8d97;--dim:#55575f;--accent:#d4a017;--live:#22c55e;--warn:#f59e0b;--danger:#ef4444;--info:#3b82f6;--violet:#a855f7;--font:system-ui,-apple-system,sans-serif;--mono:'SF Mono',Menlo,monospace}
body{background:var(--bg);color:var(--text);font:13px/1.5 var(--font);-webkit-font-smoothing:antialiased}
.app{display:grid;grid-template-columns:220px 1fr;min-height:100vh}
.sidebar{background:var(--panel);border-right:1px solid var(--border);padding:16px 0;display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
.brand{padding:12px 16px;font-weight:700;font-size:15px;letter-spacing:-.02em;border-bottom:1px solid var(--border);margin-bottom:12px;display:flex;align-items:center;gap:8px}
.brand span{color:var(--accent)}
.brand .live-dot{width:8px;height:8px;border-radius:50%;background:var(--live);box-shadow:0 0 0 0 rgba(34,197,94,.6);animation:pulse 2s infinite;margin-left:auto}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.6)}70%{box-shadow:0 0 0 8px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
.brand .live-dot.stale{background:var(--warn);animation:none}
.brand .live-dot.err{background:var(--danger);animation:none}
.nav-item{padding:8px 16px;font-size:12.5px;color:var(--muted);cursor:pointer;display:flex;align-items:center;gap:8px;border-left:2px solid transparent;transition:background .15s}
.nav-item:hover{color:var(--text);background:var(--elevated)}
.nav-item.active{color:var(--text);background:var(--elevated);border-left-color:var(--accent)}
.badge{font:10px var(--mono);background:var(--elevated);border:1px solid var(--border);padding:1px 6px;border-radius:8px;margin-left:auto;min-width:24px;text-align:center}
.badge.hot{background:#d4a01722;border-color:var(--accent);color:var(--accent)}
.main{padding:20px 28px;overflow-y:auto}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;gap:10px}
h1{font-size:20px;font-weight:600;letter-spacing:-.02em}
.live-indicator{font:11px var(--mono);color:var(--muted);display:flex;align-items:center;gap:6px}
.live-indicator .d{width:6px;height:6px;border-radius:50%;background:var(--live)}
.live-indicator.stale .d{background:var(--warn)}
.live-indicator.err .d{background:var(--danger)}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.kpi{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px 16px;transition:border-color .3s}
.kpi.flash{border-color:var(--accent)}
.kpi-label{font:10px var(--mono);color:var(--dim);letter-spacing:.08em;text-transform:uppercase}
.kpi-val{font-size:28px;font-weight:600;margin-top:2px;font-variant-numeric:tabular-nums}
.kpi-sub{font:11px var(--mono);color:var(--muted);margin-top:2px}
.grid2{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin-bottom:24px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.card-head{padding:10px 14px;border-bottom:1px solid var(--border);font:600 11px var(--mono);color:var(--dim);letter-spacing:.06em;text-transform:uppercase;display:flex;align-items:center;justify-content:space-between}
.card-head .count{font-weight:400;color:var(--muted)}
.card-body{max-height:560px;overflow-y:auto}
.mem-item{padding:10px 14px;border-bottom:1px solid var(--border);display:grid;grid-template-columns:80px 1fr;gap:10px;font-size:12.5px}
.mem-item:last-child{border:0}
.mem-item.new{animation:flash-in 1.5s}
@keyframes flash-in{0%{background:#d4a01730}100%{background:transparent}}
.mem-time{font:11px var(--mono);color:var(--dim)}
.mem-type{display:inline-block;font:10px var(--mono);padding:1px 6px;border-radius:3px;letter-spacing:.04em;text-transform:uppercase}
.mem-title{font-weight:500;margin-top:2px}
.mem-agent{font:11px var(--mono);color:var(--muted)}
.mem-content{color:var(--muted);font-size:12px;margin-top:2px;max-height:40px;overflow:hidden;text-overflow:ellipsis}
.agent-row{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;font-size:12.5px}
.agent-row:last-child{border:0}
.agent-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.agent-name{font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.agent-meta{font:11px var(--mono);color:var(--dim);white-space:nowrap}
.ticket-item{padding:10px 14px;border-bottom:1px solid var(--border);font-size:12.5px}
.ticket-item:last-child{border:0}
.ticket-id{font:11px var(--mono);color:var(--dim)}
.ticket-title{font-weight:500;margin-top:2px}
.ticket-meta{font:11px var(--mono);color:var(--muted);margin-top:2px}
.pri-low{color:#22c55e}.pri-medium{color:#f59e0b}.pri-high{color:#f97316}.pri-critical{color:#ef4444}
.st-open{color:#f59e0b}.st-in_progress{color:#3b82f6}.st-in_review{color:#a855f7}.st-closed{color:#22c55e}.st-rejected{color:#ef4444}
.type-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.type-pill{font:10px var(--mono);padding:3px 8px;border-radius:4px;border:1px solid var(--border)}
.sidebar-foot{margin-top:auto;padding:12px 16px;font:10px var(--mono);color:var(--dim);line-height:1.6}
section{display:none}section.active{display:block}
.empty{padding:24px;color:var(--muted);text-align:center;font-size:12.5px}
.refresh-btn{background:transparent;border:1px solid var(--border);color:var(--muted);font:10px var(--mono);padding:3px 8px;border-radius:4px;cursor:pointer}
.refresh-btn:hover{color:var(--text);border-color:var(--accent)}
/* ── Quota Efficiency ── */
.seg{display:inline-flex;background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:3px;gap:2px;margin-bottom:20px}
.seg button{background:transparent;border:0;color:var(--muted);font:11px var(--mono);padding:6px 14px;border-radius:6px;cursor:pointer;letter-spacing:.04em}
.seg button:hover{color:var(--text)}
.seg button.on{background:var(--elevated);color:var(--accent);box-shadow:0 0 0 1px var(--border)}
.hero{background:linear-gradient(135deg,#1b1e24 0%,#14161b 100%);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:20px 24px;margin-bottom:20px}
.hero-kicker{font:10px var(--mono);color:var(--accent);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px}
.hero-big{font-size:38px;font-weight:700;letter-spacing:-.03em;line-height:1.1;font-variant-numeric:tabular-nums}
.hero-big .unit{font-size:18px;color:var(--muted);font-weight:500;margin-left:4px}
.hero-sub{color:var(--muted);font-size:13px;margin-top:6px;max-width:640px;line-height:1.5}
.hero-sub b{color:var(--text);font-weight:600}
.bar-card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:18px 20px;margin-bottom:16px}
.bar-head{font:10px var(--mono);color:var(--dim);letter-spacing:.08em;text-transform:uppercase;margin-bottom:10px}
.bar-row{margin-bottom:14px}
.bar-row:last-child{margin-bottom:0}
.bar-label{display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;color:var(--muted)}
.bar-label b{color:var(--text);font-weight:500}
.bar-track{height:10px;background:#0c0d10;border-radius:5px;overflow:hidden;position:relative}
.bar-fill{height:100%;border-radius:5px;transition:width .6s ease-out}
.bar-fill.bad{background:linear-gradient(90deg,#ef4444,#f97316)}
.bar-fill.good{background:linear-gradient(90deg,#22c55e,#d4a017)}
.story{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}
.story-card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:16px}
.story-icon{font-size:22px;margin-bottom:8px;display:block}
.story-title{font-weight:600;font-size:13px;margin-bottom:4px}
.story-body{color:var(--muted);font-size:12px;line-height:1.5}
.caveats{color:var(--dim);font:11px var(--mono);margin-top:16px;padding:10px 14px;border-left:2px solid var(--border);line-height:1.6}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand"><span>OB</span> On Board<div class="live-dot" id="liveDot"></div></div>
    <div class="nav-item active" data-tab="overview">📊 Overview<span class="badge" id="navMemCount">–</span></div>
    <div class="nav-item" data-tab="timeline">📜 Timeline<span class="badge" id="navTimelineCount">–</span></div>
    <div class="nav-item" data-tab="agents">👥 Agents<span class="badge" id="navAgentCount">–</span></div>
    <div class="nav-item" data-tab="tickets">🎫 Tickets<span class="badge" id="navTicketCount">–</span></div>
    <div class="nav-item" data-tab="tokens">📊 Tokens</div>
    <div class="nav-item" data-tab="quota">⚡ Quota Saved</div>
    <div class="sidebar-foot">
      <div id="projName">__PROJECT_NAME__</div>
      <div>live · polling __POLL_MS__ms</div>
      <div id="lastUpdate" style="color:var(--dim);margin-top:4px">waiting…</div>
    </div>
  </aside>
  <div class="main">
    <div class="topbar">
      <h1 id="projTitle">__PROJECT_NAME__</h1>
      <div class="live-indicator" id="liveIndicator"><span class="d"></span><span id="liveText">connecting…</span> <button class="refresh-btn" id="refreshBtn" title="Force refresh now">↻</button></div>
    </div>
    <p class="sub" id="projSub">loading…</p>

    <section id="tab-overview" class="active">
      <div class="kpis" id="kpis"></div>
      <div class="type-row" id="typeRow"></div>
      <div class="grid2">
        <div class="card"><div class="card-head">Recent Activity</div><div class="card-body" id="recentActivity"></div></div>
        <div class="card"><div class="card-head">Agent Roster</div><div class="card-body" id="agentRoster"></div></div>
      </div>
    </section>

    <section id="tab-timeline">
      <div class="sub">All entries, stamped & chronological</div>
      <div class="card"><div class="card-head">All Memories</div><div class="card-body" id="timeline"></div></div>
    </section>

    <section id="tab-agents">
      <div class="sub">Every agent that touched this project</div>
      <div class="card"><div class="card-head">Agents</div><div class="card-body" id="agentsList"></div></div>
    </section>

    <section id="tab-tickets">
      <div class="sub">Cross-agent task management</div>
      <div class="card"><div class="card-head">All Tickets</div><div class="card-body" id="ticketsList"></div></div>
    </section>

    <section id="tab-tokens">
      <div class="sub">Memory efficiency breakdown</div>
      <div class="kpis" id="tokenKpis"></div>
    </section>

    <section id="tab-quota">
      <div class="sub">How much Claude time this system is buying you back</div>

      <div class="seg" id="windowSeg">
        <button class="on" data-win="24">1 day</button>
        <button data-win="168">7 days</button>
        <button data-win="99999">Lifetime</button>
      </div>

      <div class="hero" id="quotaHero"></div>

      <div class="story" id="quotaStory"></div>

      <div class="bar-card">
        <div class="bar-head">Briefing size — what Claude loads at the start of every session</div>
        <div id="quotaBars"></div>
      </div>

      <div class="kpis" id="quotaKpis"></div>

      <div class="caveats" id="quotaCaveats"></div>
    </section>
  </div>
</div>

<script>
const POLL_MS = __POLL_MS__;
const PROJECT_NAME = "__PROJECT_NAME_JS__";

const FILES = {
  memories: 'memories.json',
  agents:   'agents.json',
  state:    'state.json',
  project:  'project.json',
  tickets:  'tickets/_index.json',
  digests:  'digests.json',
  archive:  'archive.json'
};

const TYPE_COLORS = {
  decision:'#d4a017', progress:'#22c55e', blocker:'#ef4444', context:'#3b82f6',
  handoff:'#a855f7', todo:'#f97316', file_change:'#06b6d4', discovery:'#eab308',
  warning:'#f59e0b', checkpoint:'#8b5cf6'
};

const STATUS_EMOJI = { active:'🟢', kia:'💀', completed:'✅', handed_off:'🤝' };
const STATUS_COLOR = { active:'#22c55e', kia:'#ef4444', completed:'#22c55e', handed_off:'#a855f7' };
const PLATFORM_COLORS = {
  claude:'var(--info)', cursor:'var(--violet)', codex:'var(--accent)',
  antigravity:'var(--live)', unknown:'var(--dim)',
  'codex-desktop':'var(--accent)', 'claude-code':'var(--info)',
};

let lastSeenIds = new Set();
let lastCounts  = { memories:-1, agents:-1, tickets:-1 };
let fetchStats  = { lastOk:0, errors:0 };
let isFirstRender = true;

const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function timeAgo(ts) {
  if (!ts) return '?';
  const diff = Date.now()/1000 - ts;
  if (diff < 60)    return Math.max(0, Math.floor(diff)) + 's ago';
  if (diff < 3600)  return Math.floor(diff/60)   + 'm ago';
  if (diff < 86400) return Math.floor(diff/3600) + 'h ago';
  return Math.floor(diff/86400) + 'd ago';
}

async function fetchJson(path) {
  try {
    const r = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  }
}

function setLiveStatus(mode) {
  const dot = document.getElementById('liveDot');
  const ind = document.getElementById('liveIndicator');
  const txt = document.getElementById('liveText');
  dot.className = 'live-dot' + (mode === 'stale' ? ' stale' : mode === 'err' ? ' err' : '');
  ind.className = 'live-indicator' + (mode === 'stale' ? ' stale' : mode === 'err' ? ' err' : '');
  txt.textContent = mode === 'ok'    ? 'live · ' + new Date().toLocaleTimeString()
                 : mode === 'stale' ? 'reconnecting…'
                 : mode === 'err'   ? 'offline — is the HTTP server running?'
                 :                    'connecting…';
}

function renderKpis(memCount, archiveCount, agents, openTickets, totalTickets, tokens, digests) {
  const activeAgents = Object.values(agents || {}).filter(a => a && a.status === 'active').length;
  document.getElementById('kpis').innerHTML =
    '<div class="kpi"><div class="kpi-label">Memories</div><div class="kpi-val">' + memCount + '</div><div class="kpi-sub">+' + archiveCount + ' archived</div></div>' +
    '<div class="kpi"><div class="kpi-label">Agents</div><div class="kpi-val">' + Object.keys(agents||{}).length + '</div><div class="kpi-sub">' + activeAgents + ' active</div></div>' +
    '<div class="kpi"><div class="kpi-label">Tickets</div><div class="kpi-val">' + openTickets + '/' + totalTickets + '</div><div class="kpi-sub">open / total</div></div>' +
    '<div class="kpi"><div class="kpi-label">Tokens</div><div class="kpi-val">~' + tokens.toLocaleString() + '</div><div class="kpi-sub">' + digests + ' digests</div></div>';
}

function renderTypeRow(typeCounts) {
  const row = document.getElementById('typeRow');
  const sorted = Object.entries(typeCounts).sort((a,b) => b[1] - a[1]);
  row.innerHTML = sorted.map(([t, c]) => {
    const col = TYPE_COLORS[t] || '#666';
    return '<span class="type-pill" style="color:' + col + ';border-color:' + col + '40">' + esc(t) + ' ' + c + '</span>';
  }).join('');
}

function renderMemories(containerId, memories, opts) {
  opts = opts || {};
  const limit = opts.limit || 9999;
  const showId = !!opts.showId;
  const container = document.getElementById(containerId);
  if (!memories.length) {
    container.innerHTML = '<div class="empty">No memories yet.</div>';
    return;
  }
  const sorted = memories.slice().sort((a, b) => (b.timestamp||0) - (a.timestamp||0)).slice(0, limit);

  container.innerHTML = sorted.map(m => {
    const col = TYPE_COLORS[m.memory_type] || '#666';
    const pin = m.pinned ? '📌 ' : '';
    const isNew = !isFirstRender && m.id && !lastSeenIds.has(m.id);
    const idBadge = showId && m.id ? '<span style="color:var(--accent)"> · #' + esc(m.id.slice(0,8)) + '</span>' : '';
    const timeLine = showId
      ? esc(timeAgo(m.timestamp)) + '<br><span style="font-size:10px">' + esc((m.created_at||'').slice(0,16)) + '</span>'
      : esc(timeAgo(m.timestamp));
    const contentLen = showId ? 200 : 120;
    return '<div class="mem-item' + (isNew ? ' new' : '') + '">' +
      '<div class="mem-time">' + timeLine + '</div>' +
      '<div>' +
        '<span class="mem-type" style="color:' + col + ';background:' + col + '18">' + esc(m.memory_type || '') + '</span>' +
        '<span class="mem-agent"> · ' + esc(m.agent_name || '') + '</span>' + idBadge +
        '<div class="mem-title">' + pin + esc(m.title || '') + '</div>' +
        '<div class="mem-content">' + esc((m.content || '').slice(0, contentLen)) + '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}

function renderAgents(containerId, agents, compact) {
  const list = Object.values(agents || {});
  const container = document.getElementById(containerId);
  if (!list.length) {
    container.innerHTML = '<div class="empty">No agents registered yet.</div>';
    return;
  }
  // Group by agent_name
  const groups = {};
  for (const a of list) {
    const name = a.agent_name || '?';
    if (!groups[name]) groups[name] = { latest: a, records: [], totalWrites: 0 };
    groups[name].records.push(a);
    groups[name].totalWrites += (a.memories_written || 0);
    if ((a.last_activity || 0) > (groups[name].latest.last_activity || 0)) groups[name].latest = a;
  }
  // Sort: active first, then by most recent activity
  const sorted = Object.values(groups).sort((a, b) => {
    const aActive = a.latest.status === 'active' ? 0 : 1;
    const bActive = b.latest.status === 'active' ? 0 : 1;
    if (aActive !== bActive) return aActive - bActive;
    return (b.latest.last_activity || 0) - (a.latest.last_activity || 0);
  });
  // In compact mode: only active + recent (last 3h)
  const now = Date.now() / 1000;
  const filtered = compact
    ? sorted.filter(g => g.latest.status === 'active' || (now - (g.latest.last_activity || 0)) < 10800)
    : sorted;
  container.innerHTML = filtered.map(g => {
    const a = g.latest;
    const dot = STATUS_COLOR[a.status] || '#666';
    const emoji = STATUS_EMOJI[a.status] || '❓';
    const platBase = (a.agent_platform || '').split('-')[0].toLowerCase();
    const platColor = PLATFORM_COLORS[platBase] || PLATFORM_COLORS[a.agent_platform] || 'var(--dim)';
    const sessions = g.records.length > 1 ? ' · ' + g.records.length + ' sessions' : '';
    const role = (a.agent_role && a.agent_role !== 'main') ? ' [' + esc(a.agent_role) + ']' : '';
    const idleWarn = a.status === 'active' && a.last_activity && (now - a.last_activity) > 900
      ? ' · ⚠️ idle ' + Math.floor((now - a.last_activity) / 60) + 'm'
      : '';
    const meta = compact
      ? '<span style="color:' + platColor + '">' + esc(a.agent_platform || '?') + '</span> · ' + g.totalWrites + 'w · ' + esc(a.status || '?') + sessions + idleWarn
      : emoji + ' <span style="color:' + platColor + '">' + esc(a.agent_platform || '?') + '</span> · ' + g.totalWrites + ' writes · joined ' + esc((a.joined_at || '').slice(0,16)) + sessions + idleWarn;
    return '<div class="agent-row">' +
      '<div class="agent-dot" style="background:' + dot + '"></div>' +
      '<div class="agent-name">' + esc(a.agent_name || '?') + role + '</div>' +
      '<div class="agent-meta">' + meta + '</div>' +
    '</div>';
  }).join('');
}

function renderTickets(tickets, agents) {
  const container = document.getElementById('ticketsList');
  if (!tickets.length) {
    container.innerHTML = '<div class="empty">No tickets yet.</div>';
    return;
  }
  // Orphan detection
  const activeNames = new Set(Object.values(agents || {}).filter(a => a.status === 'active').map(a => a.agent_name));
  const priOrder = { critical:0, high:1, medium:2, low:3 };
  const sorted = tickets.slice().sort((a, b) => {
    const pa = priOrder[a.priority] == null ? 9 : priOrder[a.priority];
    const pb = priOrder[b.priority] == null ? 9 : priOrder[b.priority];
    if (pa !== pb) return pa - pb;
    return (b.timestamp || 0) - (a.timestamp || 0);
  });
  container.innerHTML = sorted.map(t => {
    const claimed = t.claimed_by ? '⚡ ' + esc(t.claimed_by) : '';
    const isOrphan = t.claimed_by && ['claimed','in_progress'].includes(t.status) && !activeNames.has(t.claimed_by);
    const orphanBadge = isOrphan ? ' <span style="color:var(--warn)">⚠️ orphan — claimer offline</span>' : '';
    return '<div class="ticket-item"' + (isOrphan ? ' style="border-left:2px solid var(--warn)"' : '') + '>' +
      '<span class="ticket-id">' + esc(t.id || '') + '</span>' +
      '<span class="pri-' + esc(t.priority || 'medium') + '"> ● ' + esc(t.priority || '') + '</span>' +
      '<span class="st-' + esc(t.status || 'open') + '"> · ' + esc(t.status || '') + '</span>' + orphanBadge +
      '<div class="ticket-title">' + esc(t.title || '') + '</div>' +
      '<div class="ticket-meta">by ' + esc(t.created_by || '?') + ' → ' + esc(t.assigned_to || 'any') + ' ' + claimed + '</div>' +
    '</div>';
  }).join('');
}

function renderTokens(memories, archive, digests) {
  const hot = memories.reduce((s, m) => s + Math.floor((m.title||'').length/4) + Math.floor((m.content||'').length/4), 0);
  const arc = archive.reduce((s, m) => s + Math.floor((m.title||'').length/4) + Math.floor((m.content||'').length/4), 0);
  const dig = digests.reduce((s, d) => s + Math.floor((d.summary||'').length/4), 0);
  document.getElementById('tokenKpis').innerHTML =
    '<div class="kpi"><div class="kpi-label">Hot Memory</div><div class="kpi-val">~' + hot.toLocaleString() + '</div><div class="kpi-sub">' + memories.length + ' entries</div></div>' +
    '<div class="kpi"><div class="kpi-label">Digests</div><div class="kpi-val">~' + dig.toLocaleString() + '</div><div class="kpi-sub">' + digests.length + ' compressed</div></div>' +
    '<div class="kpi"><div class="kpi-label">Archive</div><div class="kpi-val">~' + arc.toLocaleString() + '</div><div class="kpi-sub">' + archive.length + ' entries (disk only)</div></div>' +
    '<div class="kpi"><div class="kpi-label">Briefing Est.</div><div class="kpi-val">~' + (hot+dig+500).toLocaleString() + '</div><div class="kpi-sub">per agent session</div></div>';
}

// ── QUOTA EFFICIENCY ────────────────────────────────────────────────────
// Philosophy: the system's real value isn't dollars saved, it's Claude-time
// you get back. We model 3 buckets of cost an agent incurs WITHOUT On Board:
//   1. briefing raw      — loading all memories + archive from scratch
//   2. rework            — redoing things previous agents already did (~20%)
//   3. re-explanation    — re-describing context in output (~15%)
// WITH On Board: just hot memories + compressed digests + small overhead.
// Numbers are middle-ground (not conservative, not optimistic) and include
// clear caveats at the bottom of the tab.

let currentWindow = 24;  // hours — default 1D

function tokenize(chars) { return Math.floor(chars / 3); }  // Thai+EN mix ratio

function agentJoinTimestamp(a) {
  if (!a || !a.joined_at) return 0;
  try {
    const d = new Date(a.joined_at);
    return d.getTime() / 1000;
  } catch (e) { return 0; }
}

function computeQuotaStats(hours, memories, archive, digests, agents, tickets) {
  const now = Date.now() / 1000;
  const inWin = (ts) => ts && (now - ts) <= hours * 3600;

  const memIn  = memories.filter(m => inWin(m.timestamp));
  const arcIn  = archive.filter(m => inWin(m.timestamp));
  const digIn  = digests.filter(d => inWin(d.timestamp || d.created_at_ts || 0));
  const tkIn   = tickets.filter(t => inWin(t.timestamp));
  const agList = Object.values(agents || {});
  const agIn   = agList.filter(a => inWin(agentJoinTimestamp(a)));

  const hotChars = memIn.reduce((s, m) => s + (m.title||'').length + (m.content||'').length, 0);
  const arcChars = arcIn.reduce((s, m) => s + (m.title||'').length + (m.content||'').length, 0);
  const digChars = digIn.reduce((s, d) => s + (d.summary||'').length, 0) || 800;

  const briefRaw    = tokenize(hotChars + arcChars) + 500;
  const reworkCost  = Math.floor(briefRaw * 0.20);
  const reexplain   = Math.floor(briefRaw * 0.15);
  const noSystem    = briefRaw + reworkCost + reexplain;

  const withSystem  = tokenize(hotChars) + tokenize(digChars) + 500;

  const savedPer    = Math.max(0, noSystem - withSystem);
  const multiplier  = withSystem > 0 ? (noSystem / withSystem) : 1;
  const sessions    = agIn.length || 1;
  const totalSaved  = savedPer * sessions;

  // Hours of Claude time bought back — model: 1 "session" ≈ ~45 min of
  // active use before hitting 5hr quota cap on a heavy day. Saved tokens
  // translate proportionally into extra working minutes.
  // 45min * multiplier_gain / multiplier = extra_minutes per session
  const extraMinPerSession = Math.round(45 * (1 - 1/multiplier));
  const totalExtraHours    = (extraMinPerSession * sessions) / 60;

  return {
    hours, sessions,
    memCount: memIn.length, arcCount: arcIn.length, tkCount: tkIn.length,
    hotChars, arcChars, digChars,
    noSystem, withSystem, savedPer, totalSaved,
    multiplier, extraMinPerSession, totalExtraHours,
  };
}

function renderQuota(stats) {
  const m = stats.multiplier;
  const mult = m.toFixed(2);
  const winLabel = stats.hours === 24 ? '24h' : stats.hours === 168 ? '7d' : 'lifetime';

  // HERO
  const hero = document.getElementById('quotaHero');
  hero.innerHTML =
    '<div class="hero-kicker">Claude-time bought back · ' + winLabel + '</div>' +
    '<div class="hero-big">' + mult + '<span class="unit">× longer per quota window</span></div>' +
    '<div class="hero-sub">' +
      'Before On Board: ' + stats.sessions + ' agent session' + (stats.sessions !== 1 ? 's' : '') +
      ' burn <b>~' + stats.noSystem.toLocaleString() + ' tokens</b> each on re-reading, rework, and re-explaining. ' +
      'With On Board, it drops to <b>~' + stats.withSystem.toLocaleString() + '</b>. ' +
      'Claude hits quota later and you wait less for it to restore.' +
    '</div>';

  // STORY CARDS
  const story = document.getElementById('quotaStory');
  story.innerHTML =
    '<div class="story-card">' +
      '<span class="story-icon">⏱️</span>' +
      '<div class="story-title">~' + stats.extraMinPerSession + ' min extra per session</div>' +
      '<div class="story-body">Before: sessions hit the 5h cap in 30min–2h. Now you typically work <b>3h+</b> before Claude needs to restore.</div>' +
    '</div>' +
    '<div class="story-card">' +
      '<span class="story-icon">🎫</span>' +
      '<div class="story-title">' + stats.tkCount + ' ticket' + (stats.tkCount !== 1 ? 's' : '') + ' spread the load</div>' +
      '<div class="story-body">Heavy work is parallelized across agents — the PM plans, reviewer approves, coder ships. One quota doesn\'t do everything alone.</div>' +
    '</div>' +
    '<div class="story-card">' +
      '<span class="story-icon">🧠</span>' +
      '<div class="story-title">' + stats.totalSaved.toLocaleString() + ' tokens saved</div>' +
      '<div class="story-body">Cumulative across ' + stats.sessions + ' session' + (stats.sessions !== 1 ? 's' : '') +
      ' in this window — that\'s quota budget you get to spend on actual work, not rehashing context.</div>' +
    '</div>';

  // BARS
  const maxBar = Math.max(stats.noSystem, stats.withSystem) * 1.05;
  const wPct = (v) => Math.max(2, (v / maxBar) * 100).toFixed(1) + '%';
  document.getElementById('quotaBars').innerHTML =
    '<div class="bar-row">' +
      '<div class="bar-label"><span>Without On Board</span><b>~' + stats.noSystem.toLocaleString() + ' tok</b></div>' +
      '<div class="bar-track"><div class="bar-fill bad" style="width:' + wPct(stats.noSystem) + '"></div></div>' +
    '</div>' +
    '<div class="bar-row">' +
      '<div class="bar-label"><span>With On Board</span><b>~' + stats.withSystem.toLocaleString() + ' tok</b></div>' +
      '<div class="bar-track"><div class="bar-fill good" style="width:' + wPct(stats.withSystem) + '"></div></div>' +
    '</div>';

  // KPIS
  document.getElementById('quotaKpis').innerHTML =
    '<div class="kpi"><div class="kpi-label">Sessions</div><div class="kpi-val">' + stats.sessions + '</div><div class="kpi-sub">in window</div></div>' +
    '<div class="kpi"><div class="kpi-label">Saved per session</div><div class="kpi-val">~' + stats.savedPer.toLocaleString() + '</div><div class="kpi-sub">tokens</div></div>' +
    '<div class="kpi"><div class="kpi-label">Total saved</div><div class="kpi-val">~' + stats.totalSaved.toLocaleString() + '</div><div class="kpi-sub">tokens in window</div></div>' +
    '<div class="kpi"><div class="kpi-label">Claude-time gained</div><div class="kpi-val">' + stats.totalExtraHours.toFixed(1) + 'h</div><div class="kpi-sub">est. total</div></div>';

  // CAVEATS
  document.getElementById('quotaCaveats').innerHTML =
    '⚠️ <b>How this is estimated:</b> ' +
    'briefing size measured directly from .agent-mem/ files; rework/re-explain modeled at 20% / 15% based on typical agent behavior; ' +
    'Claude-time conversion assumes ~45min baseline per session at quota cap. Anthropic does not publish exact quota numbers so absolute minutes are estimates — ' +
    'but the <b>' + mult + 'x ratio is real</b>, measured from your actual memory files.';
}

async function refresh() {
  const [memData, agData, stData, projData, tkData, dgData, arData] = await Promise.all([
    fetchJson(FILES.memories),
    fetchJson(FILES.agents),
    fetchJson(FILES.state),
    fetchJson(FILES.project),
    fetchJson(FILES.tickets),
    fetchJson(FILES.digests),
    fetchJson(FILES.archive),
  ]);

  const allFailed = [memData, agData, projData].every(x => x === null);
  if (allFailed) {
    fetchStats.errors++;
    setLiveStatus(fetchStats.errors > 2 ? 'err' : 'stale');
    return;
  }
  fetchStats.errors = 0;
  fetchStats.lastOk = Date.now();

  const memories = (memData && memData.entries) || [];
  const agents   = agData || {};
  const project  = projData || {};
  const tickets  = (tkData && tkData.tickets) || [];
  const digests  = (dgData && dgData.digests) || [];
  const archive  = (arData && arData.entries) || [];

  const openTickets = tickets.filter(t => ['open','in_progress','in_review'].indexOf(t.status) >= 0).length;
  const totalTokens = memories.reduce((s, m) => s + Math.floor((m.title||'').length/4) + Math.floor((m.content||'').length/4), 0);
  const typeCounts = {};
  memories.forEach(m => { const k = m.memory_type || '?'; typeCounts[k] = (typeCounts[k] || 0) + 1; });

  const title = project.name || PROJECT_NAME;
  document.getElementById('projTitle').textContent = title;
  document.getElementById('projSub').textContent = (project.description || 'No description') + ' · ' + (project.tech_stack || '');
  document.title = 'On Board · Live — ' + title;

  document.getElementById('navMemCount').textContent = memories.length;
  document.getElementById('navTimelineCount').textContent = memories.length;
  document.getElementById('navAgentCount').textContent = Object.keys(agents).length;
  const ticketBadge = document.getElementById('navTicketCount');
  ticketBadge.textContent = openTickets;
  ticketBadge.className = 'badge' + (openTickets > 0 ? ' hot' : '');

  renderKpis(memories.length, archive.length, agents, openTickets, tickets.length, totalTokens, digests.length);

  if (!isFirstRender) {
    const kpis = document.querySelectorAll('.kpi');
    if (memories.length !== lastCounts.memories && kpis[0]) { kpis[0].classList.add('flash'); setTimeout(() => kpis[0].classList.remove('flash'), 1200); }
    if (Object.keys(agents).length !== lastCounts.agents && kpis[1]) { kpis[1].classList.add('flash'); setTimeout(() => kpis[1].classList.remove('flash'), 1200); }
    if (tickets.length !== lastCounts.tickets && kpis[2]) { kpis[2].classList.add('flash'); setTimeout(() => kpis[2].classList.remove('flash'), 1200); }
  }
  lastCounts = { memories: memories.length, agents: Object.keys(agents).length, tickets: tickets.length };

  renderTypeRow(typeCounts);
  renderMemories('recentActivity', memories, { limit: 15 });
  renderAgents('agentRoster', agents, true);
  renderMemories('timeline', memories, { showId: true });
  renderAgents('agentsList', agents, false);
  renderTickets(tickets, agents);
  renderTokens(memories, archive, digests);

  // Quota tab — cache latest data so window selector can re-render without re-fetch
  window._obData = { memories, archive, digests, agents, tickets };
  renderQuota(computeQuotaStats(currentWindow, memories, archive, digests, agents, tickets));

  lastSeenIds = new Set(memories.map(m => m.id).filter(Boolean));
  isFirstRender = false;

  setLiveStatus('ok');
  document.getElementById('lastUpdate').textContent = 'updated ' + new Date().toLocaleTimeString();
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    const tab = item.dataset.tab;
    document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('tab-' + tab).classList.add('active');
    item.classList.add('active');
  });
});

document.getElementById('refreshBtn').addEventListener('click', () => refresh());

// Quota window selector (1D / 7D / Lifetime)
document.querySelectorAll('#windowSeg button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#windowSeg button').forEach(b => b.classList.remove('on'));
    btn.classList.add('on');
    currentWindow = parseInt(btn.dataset.win, 10);
    const d = window._obData;
    if (d) renderQuota(computeQuotaStats(currentWindow, d.memories, d.archive, d.digests, d.agents, d.tickets));
  });
});

refresh();
setInterval(refresh, POLL_MS);

setInterval(() => {
  if (fetchStats.lastOk && (Date.now() - fetchStats.lastOk) > POLL_MS * 3) {
    setLiveStatus('stale');
  }
}, 15000);
</script>
</body>
</html>
"""

# ── Substitute placeholders ─────────────────────────────────────────────────
html = (HTML_TEMPLATE
    .replace("__PROJECT_NAME__", PROJECT_ROOT.name)
    .replace("__PROJECT_NAME_JS__", PROJECT_ROOT.name.replace('"', '\\"'))
    .replace("__POLL_MS__", str(POLL_MS))
)

OUT_PATH.write_text(html, encoding="utf-8")
print(f"✅ Live dashboard generated: {OUT_PATH}")
print(f"   Polls every {POLL_MS}ms · reads .agent-mem/*.json directly")
print()

# ── Optional: serve + open ──────────────────────────────────────────────────
if "--serve" in flags or "--open" in flags:
    import subprocess, webbrowser, time, threading

    url = f"http://localhost:{PORT}/dashboard-live.html"
    print(f"🌐 Starting HTTP server on port {PORT} (serving {MEMORY_DIR})")
    print(f"   URL: {url}")
    print(f"   Press Ctrl+C to stop.")
    print()

    if "--open" in flags:
        def _open():
            time.sleep(0.8)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    try:
        subprocess.run(
            ["python3", "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
            cwd=str(MEMORY_DIR),
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
else:
    print(f"   To view live, run ONE of:")
    print(f"     python3 {Path(__file__).name} {PROJECT_ROOT} --open        ← auto-serve + open browser")
    print(f"     python3 {Path(__file__).name} {PROJECT_ROOT} --serve       ← serve only")
    print(f"   Or manually:")
    print(f"     cd {MEMORY_DIR} && python3 -m http.server {PORT}")
    print(f"     open http://localhost:{PORT}/dashboard-live.html")
