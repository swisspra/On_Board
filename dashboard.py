#!/usr/bin/env python3
"""
Agent Memory Dashboard — generates a live HTML dashboard from .agent-mem/

Usage:
  python3 dashboard.py                          ← uses AGENT_PROJECT_DIR or cwd
  python3 dashboard.py /path/to/project         ← specify project path
  python3 dashboard.py --open                   ← auto-open in browser
"""

import json, sys, os, time
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else
    os.environ.get("AGENT_PROJECT_DIR", os.getcwd()))
MEMORY_DIR = PROJECT_ROOT / ".agent-mem"
AUTO_OPEN = "--open" in sys.argv

def load_json(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def time_ago(ts):
    diff = time.time() - ts
    if diff < 60: return f"{int(diff)}s ago"
    if diff < 3600: return f"{int(diff/60)}m ago"
    if diff < 86400: return f"{int(diff/3600)}h ago"
    return f"{int(diff/86400)}d ago"

# Load data
memories = load_json(MEMORY_DIR / "memories.json").get("entries", [])
agents = load_json(MEMORY_DIR / "agents.json")
state = load_json(MEMORY_DIR / "state.json")
project = load_json(MEMORY_DIR / "project.json")
tickets = load_json(MEMORY_DIR / "tickets" / "_index.json").get("tickets", [])
digests = load_json(MEMORY_DIR / "digests.json").get("digests", [])
archive = load_json(MEMORY_DIR / "archive.json").get("entries", [])

# Stats
total_tokens = sum(len(m.get("title",""))//4 + len(m.get("content",""))//4 for m in memories)
open_tickets = [t for t in tickets if t.get("status") in ("open","in_progress","in_review")]

# Memory type stats
type_counts = {}
for m in memories:
    t = m.get("memory_type", "?")
    type_counts[t] = type_counts.get(t, 0) + 1

# Agent stats
agent_list = []
for aid, a in agents.items():
    emoji = {"active":"🟢","kia":"💀","completed":"✅","handed_off":"🤝"}.get(a.get("status",""),"❓")
    agent_list.append({
        "name": a.get("agent_name","?"),
        "platform": a.get("agent_platform","?"),
        "role": a.get("agent_role","main"),
        "status": a.get("status","?"),
        "emoji": emoji,
        "writes": a.get("memories_written", 0),
        "joined": a.get("joined_at","?"),
    })

# Recent memories (last 30)
recent = sorted(memories, key=lambda m: m.get("timestamp",0), reverse=True)[:30]

# Type colors
TYPE_COLORS = {
    "decision":"#d4a017","progress":"#22c55e","blocker":"#ef4444","context":"#3b82f6",
    "handoff":"#a855f7","todo":"#f97316","file_change":"#06b6d4","discovery":"#eab308",
    "warning":"#f59e0b","checkpoint":"#8b5cf6"
}

# Build HTML
def esc(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>On Board — {esc(PROJECT_ROOT.name)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#0c0d10;--panel:#14161b;--elevated:#1b1e24;--border:#2a2d35;--text:#f0f0f2;--muted:#8b8d97;--dim:#55575f;--accent:#d4a017;--live:#22c55e;--warn:#f59e0b;--danger:#ef4444;--info:#3b82f6;--violet:#a855f7;--font:system-ui,-apple-system,sans-serif;--mono:'SF Mono',Menlo,monospace}}
body{{background:var(--bg);color:var(--text);font:13px/1.5 var(--font);-webkit-font-smoothing:antialiased}}
.app{{display:grid;grid-template-columns:220px 1fr;min-height:100vh}}
.sidebar{{background:var(--panel);border-right:1px solid var(--border);padding:16px 0;display:flex;flex-direction:column;position:sticky;top:0;height:100vh}}
.brand{{padding:12px 16px;font-weight:700;font-size:15px;letter-spacing:-.02em;border-bottom:1px solid var(--border);margin-bottom:12px}}
.brand span{{color:var(--accent)}}
.nav-item{{padding:8px 16px;font-size:12.5px;color:var(--muted);cursor:pointer;display:flex;align-items:center;gap:8px}}
.nav-item:hover{{color:var(--text);background:var(--elevated)}}
.nav-item.active{{color:var(--text);background:var(--elevated);border-left:2px solid var(--accent)}}
.badge{{font:10px var(--mono);background:var(--elevated);border:1px solid var(--border);padding:1px 6px;border-radius:8px;margin-left:auto}}
.main{{padding:20px 28px;overflow-y:auto}}
h1{{font-size:20px;font-weight:600;letter-spacing:-.02em;margin-bottom:4px}}
.sub{{color:var(--muted);font-size:12.5px;margin-bottom:20px}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}}
.kpi{{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:14px 16px}}
.kpi-label{{font:10px var(--mono);color:var(--dim);letter-spacing:.08em;text-transform:uppercase}}
.kpi-val{{font-size:28px;font-weight:600;margin-top:2px;font-variant-numeric:tabular-nums}}
.kpi-sub{{font:11px var(--mono);color:var(--muted);margin-top:2px}}
.grid2{{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;margin-bottom:24px}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:8px;overflow:hidden}}
.card-head{{padding:10px 14px;border-bottom:1px solid var(--border);font:600 11px var(--mono);color:var(--dim);letter-spacing:.06em;text-transform:uppercase}}
.card-body{{max-height:500px;overflow-y:auto}}
"""

html += """
.mem-item{padding:10px 14px;border-bottom:1px solid var(--border);display:grid;grid-template-columns:80px 1fr;gap:10px;font-size:12.5px}
.mem-item:last-child{border:0}
.mem-time{font:11px var(--mono);color:var(--dim)}
.mem-type{display:inline-block;font:10px var(--mono);padding:1px 6px;border-radius:3px;letter-spacing:.04em;text-transform:uppercase}
.mem-title{font-weight:500;margin-top:2px}
.mem-agent{font:11px var(--mono);color:var(--muted)}
.mem-content{color:var(--muted);font-size:12px;margin-top:2px;max-height:40px;overflow:hidden}
.agent-row{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;font-size:12.5px}
.agent-row:last-child{border:0}
.agent-dot{width:8px;height:8px;border-radius:50%}
.agent-name{font-weight:500;flex:1}
.agent-meta{font:11px var(--mono);color:var(--dim)}
.ticket-item{padding:10px 14px;border-bottom:1px solid var(--border);font-size:12.5px}
.ticket-item:last-child{border:0}
.ticket-id{font:11px var(--mono);color:var(--dim)}
.ticket-title{font-weight:500;margin-top:2px}
.ticket-meta{font:11px var(--mono);color:var(--muted);margin-top:2px}
.pri-low{color:#22c55e}.pri-medium{color:#f59e0b}.pri-high{color:#f97316}.pri-critical{color:#ef4444}
.st-open{color:#f59e0b}.st-in_progress{color:#3b82f6}.st-in_review{color:#a855f7}.st-closed{color:#22c55e}.st-rejected{color:#ef4444}
.type-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.type-pill{font:10px var(--mono);padding:3px 8px;border-radius:4px;border:1px solid var(--border)}
.sidebar-foot{margin-top:auto;padding:12px 16px;font:10px var(--mono);color:var(--dim)}
.tabs{display:flex;gap:2px;border-bottom:1px solid var(--border);margin-bottom:16px}
.tab{padding:8px 12px;font-size:12px;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent}
.tab:hover{color:var(--text)}.tab.active{color:var(--text);border-bottom-color:var(--accent)}
section{display:none}section.active{display:block}
</style>
</head>
"""

# Sidebar
html += f"""<body>
<div class="app">
<aside class="sidebar">
<div class="brand"><span>OB</span> On Board</div>
<div class="nav-item active" onclick="showTab('overview')">📊 Overview<span class="badge">{len(memories)}</span></div>
<div class="nav-item" onclick="showTab('timeline')">📜 Timeline<span class="badge">{len(memories)}</span></div>
<div class="nav-item" onclick="showTab('agents')">👥 Agents<span class="badge">{len(agents)}</span></div>
<div class="nav-item" onclick="showTab('tickets')">🎫 Tickets<span class="badge">{len(open_tickets)}</span></div>
<div class="nav-item" onclick="showTab('tokens')">📊 Tokens</div>
<div class="sidebar-foot">
{esc(PROJECT_ROOT.name)}<br>
v1.8.0 · 23 tools · {len(memories)} memories
</div>
</aside>
<div class="main">
"""

# ── OVERVIEW TAB ──
html += f"""<section id="tab-overview" class="active">
<h1>{esc(PROJECT_ROOT.name)}</h1>
<p class="sub">{esc(project.get('description','No description'))} · {esc(project.get('tech_stack',''))}</p>
<div class="kpis">
<div class="kpi"><div class="kpi-label">Memories</div><div class="kpi-val">{len(memories)}</div><div class="kpi-sub">+{len(archive)} archived</div></div>
<div class="kpi"><div class="kpi-label">Agents</div><div class="kpi-val">{len(agents)}</div><div class="kpi-sub">{sum(1 for a in agents.values() if a.get('status')=='active')} active</div></div>
<div class="kpi"><div class="kpi-label">Tickets</div><div class="kpi-val">{len(open_tickets)}/{len(tickets)}</div><div class="kpi-sub">open / total</div></div>
<div class="kpi"><div class="kpi-label">Tokens</div><div class="kpi-val">~{total_tokens:,}</div><div class="kpi-sub">{len(digests)} digests</div></div>
</div>
"""

# Overview: type breakdown + recent activity
html += '<div class="type-row">'
for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
    col = TYPE_COLORS.get(t, "#666")
    html += f'<span class="type-pill" style="color:{col};border-color:{col}40">{t} {c}</span>'
html += '</div>'

html += '<div class="grid2"><div class="card"><div class="card-head">Recent Activity</div><div class="card-body">'
for m in recent[:15]:
    col = TYPE_COLORS.get(m.get("memory_type",""), "#666")
    html += f"""<div class="mem-item">
<div class="mem-time">{time_ago(m.get('timestamp',0))}</div>
<div>
<span class="mem-type" style="color:{col};background:{col}18">{esc(m.get('memory_type',''))}</span>
<span class="mem-agent"> · {esc(m.get('agent_name',''))}</span>
<div class="mem-title">{esc(m.get('title',''))}</div>
<div class="mem-content">{esc(m.get('content','')[:120])}</div>
</div></div>"""
html += '</div></div>'

# Overview: agent roster sidebar
html += '<div class="card"><div class="card-head">Agent Roster</div><div class="card-body">'
for a in agent_list:
    dot_color = {"active":"#22c55e","kia":"#ef4444","completed":"#22c55e","handed_off":"#a855f7"}.get(a["status"],"#666")
    role_tag = f' <span style="color:var(--dim);font-size:10px">[{a["role"]}]</span>' if a["role"] != "main" else ""
    html += f"""<div class="agent-row">
<div class="agent-dot" style="background:{dot_color}"></div>
<div class="agent-name">{esc(a['name'])}{role_tag}</div>
<div class="agent-meta">{a['platform']} · {a['writes']}w · {a['status']}</div>
</div>"""
html += '</div></div></div></section>'

# ── TIMELINE TAB ──
html += '<section id="tab-timeline"><h1>Memory Timeline</h1><p class="sub">All entries, stamped & chronological</p>'
html += '<div class="card"><div class="card-head">All Memories</div><div class="card-body">'
for m in sorted(memories, key=lambda m: m.get("timestamp",0), reverse=True):
    col = TYPE_COLORS.get(m.get("memory_type",""), "#666")
    pin = "📌 " if m.get("pinned") else ""
    html += f"""<div class="mem-item">
<div class="mem-time">{time_ago(m.get('timestamp',0))}<br><span style="font-size:10px">{esc(m.get('created_at','')[:16])}</span></div>
<div>
<span class="mem-type" style="color:{col};background:{col}18">{esc(m.get('memory_type',''))}</span>
<span class="mem-agent"> · {esc(m.get('agent_name',''))}</span>
{f'<span style="color:var(--accent)"> · #{esc(m.get("id","")[:8])}</span>' if m.get("id") else ""}
<div class="mem-title">{pin}{esc(m.get('title',''))}</div>
<div class="mem-content">{esc(m.get('content','')[:200])}</div>
</div></div>"""
html += '</div></div></section>'

# ── AGENTS TAB ──
html += '<section id="tab-agents"><h1>Agent Roster</h1><p class="sub">Every agent that touched this project</p>'
html += '<div class="card"><div class="card-head">Agents</div><div class="card-body">'
for a in agent_list:
    dot_color = {"active":"#22c55e","kia":"#ef4444","completed":"#22c55e","handed_off":"#a855f7"}.get(a["status"],"#666")
    role_tag = f' [{a["role"]}]' if a["role"] != "main" else ""
    html += f"""<div class="agent-row">
<div class="agent-dot" style="background:{dot_color}"></div>
<div class="agent-name">{esc(a['name'])}{role_tag}</div>
<div class="agent-meta">{a['emoji']} {a['platform']} · {a['writes']} writes · joined {esc(a['joined'][:16])}</div>
</div>"""
html += '</div></div></section>'

# ── TICKETS TAB ──
html += '<section id="tab-tickets"><h1>Tickets</h1><p class="sub">Cross-agent task management</p>'
if not tickets:
    html += '<div class="card"><div class="card-body" style="padding:20px;color:var(--muted)">No tickets yet.</div></div>'
else:
    html += '<div class="card"><div class="card-head">All Tickets</div><div class="card-body">'
    for t in sorted(tickets, key=lambda x: ({"critical":0,"high":1,"medium":2,"low":3}.get(x.get("priority","medium"),9), -x.get("timestamp",0))):
        html += f"""<div class="ticket-item">
<span class="ticket-id">{esc(t.get('id',''))}</span>
<span class="pri-{t.get('priority','medium')}"> ● {esc(t.get('priority',''))}</span>
<span class="st-{t.get('status','open')}"> · {esc(t.get('status',''))}</span>
<div class="ticket-title">{esc(t.get('title',''))}</div>
<div class="ticket-meta">by {esc(t.get('created_by','?'))} → {esc(t.get('assigned_to','any'))} {f"⚡ {esc(t.get('claimed_by',''))}" if t.get('claimed_by') else ""}</div>
</div>"""
    html += '</div></div>'
html += '</section>'

# ── TOKENS TAB ──
archive_tokens = sum(len(m.get("title",""))//4 + len(m.get("content",""))//4 for m in archive)
digest_tokens = sum(len(d.get("summary",""))//4 for d in digests)
html += f"""<section id="tab-tokens"><h1>Token Usage</h1><p class="sub">Memory efficiency breakdown</p>
<div class="kpis">
<div class="kpi"><div class="kpi-label">Hot Memory</div><div class="kpi-val">~{total_tokens:,}</div><div class="kpi-sub">{len(memories)} entries</div></div>
<div class="kpi"><div class="kpi-label">Digests</div><div class="kpi-val">~{digest_tokens:,}</div><div class="kpi-sub">{len(digests)} compressed</div></div>
<div class="kpi"><div class="kpi-label">Archive</div><div class="kpi-val">~{archive_tokens:,}</div><div class="kpi-sub">{len(archive)} entries (disk only)</div></div>
<div class="kpi"><div class="kpi-label">Briefing Est.</div><div class="kpi-val">~{total_tokens + digest_tokens + 500:,}</div><div class="kpi-sub">per agent session</div></div>
</div></section>
"""

# Close HTML + JS
html += """
</div></div>
<script>
function showTab(id) {
  document.querySelectorAll('section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  event.currentTarget.classList.add('active');
}
</script>
</body></html>"""

# Write output
out_path = MEMORY_DIR / "dashboard.html"
with open(str(out_path), "w", encoding="utf-8") as f:
    f.write(html)
print(f"✅ Dashboard generated: {out_path}")
print(f"   {len(memories)} memories · {len(agents)} agents · {len(tickets)} tickets · ~{total_tokens:,} tokens")

if AUTO_OPEN:
    import webbrowser
    webbrowser.open(f"file://{out_path}")
    print("   🌐 Opened in browser")
else:
    print(f"   Open: file://{out_path}")
    print(f"   Or: python3 dashboard.py --open")
