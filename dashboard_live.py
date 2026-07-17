#!/usr/bin/env python3
"""
Agent Memory LIVE Dashboard — emits a self-refreshing HTML shell that polls
the raw .agent-mem/*.json files via fetch() and re-renders in place.

Run it once, serve the folder via python3 -m http.server, and watch the
dashboard update itself every few seconds without re-running Python.

Usage:
  python3 dashboard_live.py                        <- uses AGENT_PROJECT_DIR or cwd
  python3 dashboard_live.py /path/to/project       <- specify project path
  python3 dashboard_live.py --open                 <- generate + start server + open browser
  python3 dashboard_live.py --serve                <- generate + start server (no browser)
  python3 dashboard_live.py --port 9000            <- use different port (default 8765)
  python3 dashboard_live.py --interval 5000        <- poll interval in ms (default 5000)

Output: <project>/.agent-mem/dashboard-live.html
"""

import json
import os
import sys
from html import escape as html_escape
from pathlib import Path

# -- CLI args ----------------------------------------------------------------
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
    print(f"ERROR: .agent-mem/ not found at {MEMORY_DIR}")
    print(f"       Run memory_init first, or pass a project path that has .agent-mem/")
    sys.exit(1)

# -- HTML shell --------------------------------------------------------------
# Placeholders __PROJECT_NAME__, __PROJECT_NAME_JS__, __POLL_MS__ are
# substituted via str.replace at the end.
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>On Board · Live — __PROJECT_NAME__</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d0e11;--panel:#15171b;--panel2:#1c1f25;--raised:#23272e;
  --border:#282c34;--border-soft:#20242b;
  --text:#e9eaed;--muted:#969aa3;--dim:#5c606a;
  --accent:#e0a92e;--accent-deep:#c8931f;--accent-soft:rgba(224,169,46,.13);
  --live:#3fb950;--track:#0a0b0d;--shadow:rgba(0,0,0,.35);
  --rpad:0px;
}
:root[data-theme="light"]{
  --bg:#f3f2ee;--panel:#ffffff;--panel2:#faf9f6;--raised:#f0efea;
  --border:#e3e2db;--border-soft:#edece6;
  --text:#1a1b1e;--muted:#6a6d75;--dim:#a2a5ac;
  --accent:#a9791a;--accent-deep:#8f6512;--accent-soft:rgba(169,121,26,.1);
  --live:#2ea043;--track:#eceae4;--shadow:rgba(30,28,22,.08);
}
html,body{background:var(--bg)}
body{color:var(--text);font-family:Avenir Next,Helvetica Neue,system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased;font-size:13px;line-height:1.5}
.mono{font-family:SFMono-Regular,Menlo,Consolas,ui-monospace,monospace}
a{color:var(--accent);text-decoration:none}
a:hover{color:var(--accent-deep)}
button{font:inherit;cursor:pointer}
input{font:inherit}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:6px}
::-webkit-scrollbar-track{background:transparent}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(63,185,80,.5)}70%{box-shadow:0 0 0 7px rgba(63,185,80,0)}100%{box-shadow:0 0 0 0 rgba(63,185,80,0)}}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}

#root{display:grid;grid-template-columns:236px 1fr;min-height:100vh;background:var(--bg);color:var(--text)}
aside{background:var(--panel);border-right:1px solid var(--border);display:flex;flex-direction:column;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:10px;padding:18px 18px 16px;border-bottom:1px solid var(--border)}
.logo{width:30px;height:30px;border-radius:8px;background:var(--accent);color:#141414;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;letter-spacing:-.02em}
nav{padding:12px 10px;display:flex;flex-direction:column;gap:2px}
.navbtn{display:flex;align-items:center;gap:11px;padding:9px 13px;width:100%;border:0;border-radius:8px;font-size:12.5px;text-align:left;transition:background .15s,color .15s;background:transparent;color:var(--muted);font-weight:400}
.navbtn:hover{background:var(--panel2)}
.navbtn.on{background:var(--accent-soft);color:var(--text);font-weight:600}
.navbtn .lbl{flex:1}
.badge{font-size:10px;color:var(--dim);background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:1px 7px;min-width:22px;text-align:center}
.badge.hot{color:var(--accent);background:var(--accent-soft);border-color:var(--accent)}
.side-foot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:12px}
.side-cap{font-size:9px;letter-spacing:.09em;text-transform:uppercase;color:var(--dim);margin-bottom:6px}
.seg{display:flex;background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:3px;gap:3px}
.seg button{flex:1;border:0;border-radius:6px;padding:6px 0;font-size:11.5px;font-weight:500;background:transparent;color:var(--muted)}
.seg button.on{background:var(--raised);color:var(--accent);box-shadow:0 0 0 1px var(--border)}
.foot-meta{font-size:9.5px;color:var(--dim);line-height:1.7}

main{padding:22px 30px 60px;overflow-y:auto;height:100vh}
.head{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:3px}
h1{font-size:22px;font-weight:600;letter-spacing:-.02em}
.head-right{display:flex;align-items:center;gap:10px}
.search{position:relative;display:flex;align-items:center}
.search svg{position:absolute;left:11px;pointer-events:none}
.search input{width:190px;padding:7px 12px 7px 30px;background:var(--panel2);border:1px solid var(--border);border-radius:20px;color:var(--text);font-size:12px;outline:none}
.kbtn{display:flex;align-items:center;gap:5px;padding:6px 10px;background:var(--panel2);border:1px solid var(--border);border-radius:20px;color:var(--muted);font-size:11px}
.chip{display:flex;align-items:center;gap:7px;font-size:11px;padding:5px 11px;border:1px solid var(--border);border-radius:20px;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%}
.sub{color:var(--muted);font-size:12.5px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:12px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.kpi{padding:15px 16px}
.kpi .k-lbl{font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.kpi .k-val{font-size:29px;font-weight:600;letter-spacing:-.02em;margin-top:3px;font-variant-numeric:tabular-nums}
.kpi .k-sub{font-size:11px;color:var(--muted);margin-top:2px}
.kpi .k-trend{font-size:10px;margin-top:6px}
.cap{padding:12px 16px;border-bottom:1px solid var(--border);font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim)}
.row{border-bottom:1px solid var(--border-soft)}
[data-density="compact"] [data-row]{padding-top:7px!important;padding-bottom:7px!important}
.hact{opacity:0;transition:opacity .12s ease}
[data-row]:hover .hact{opacity:1}
.copybtn{padding:2px 8px;font-size:9.5px;background:var(--panel2);border:1px solid var(--border);border-radius:6px;color:var(--muted)}
.pill{font-size:9.5px;padding:1.5px 7px;border-radius:4px;letter-spacing:.03em;text-transform:uppercase}
.empty{padding:44px 24px;text-align:center}
.empty .e-t{font-weight:600;font-size:13px}
.empty .e-s{color:var(--muted);font-size:12px;margin-top:4px}
.spinner{width:34px;height:34px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;margin:0 auto 16px}
section{animation:fade .3s ease}
@keyframes flowdash{to{background-position-x:16px}}
@keyframes flowpulse{0%{left:-4px;opacity:0}12%{opacity:1}88%{opacity:1}100%{left:100%;opacity:0}}
@keyframes cardin{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.flow-rail{display:flex;align-items:center;gap:8px;padding:20px 12px 12px}
.flow-node{display:flex;flex-direction:column;align-items:center;gap:5px;min-width:82px}
.flow-ring{width:15px;height:15px;border-radius:50%;border:2px solid currentColor;position:relative}
.flow-ring::after{content:'';position:absolute;inset:3px;border-radius:50%;background:currentColor}
.flow-count{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1}
.flow-nlbl{font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.flow-conn{flex:1;height:3px;border-radius:3px;position:relative;overflow:hidden;background:var(--border-soft);min-width:26px}
.flow-conn::before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(90deg,var(--accent) 0 6px,transparent 6px 16px);background-size:16px 100%;opacity:.4;animation:flowdash 1.1s linear infinite}
.flow-pulse{position:absolute;top:50%;width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);transform:translateY(-50%);animation:flowpulse 2.6s ease-in-out infinite}
.flow-cols{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.flow-col{background:var(--panel2);border:1px solid var(--border);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.flow-col-h{padding:9px 12px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border);font-size:11px}
.flow-col-b{padding:8px;display:flex;flex-direction:column;gap:7px;min-height:44px}
.flow-card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:9px 10px;animation:cardin .45s both}
.flow-card.orphan{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent-soft)}
.flow-empty{color:var(--dim);font-size:11px;text-align:center;padding:10px}
.flow-branch{display:flex;gap:12px;margin-top:14px}

#palette{position:fixed;inset:0;z-index:60;display:none;align-items:flex-start;justify-content:center;padding-top:11vh;background:rgba(0,0,0,.5);backdrop-filter:blur(2px)}
#palette.open{display:flex;animation:fade .15s ease}
.pal{width:560px;max-width:92vw;background:var(--panel);border:1px solid var(--border);border-radius:14px;box-shadow:0 24px 70px var(--shadow);overflow:hidden}
.pal-head{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--border)}
.pal-head input{flex:1;border:0;background:transparent;color:var(--text);font-size:14px;outline:none}
.pal-esc{font-size:9.5px;color:var(--dim);border:1px solid var(--border);border-radius:5px;padding:2px 6px}
.pal-list{max-height:52vh;overflow-y:auto;padding:6px}
.pal-row{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:8px}
.pal-row.on{background:var(--accent-soft)}
.pal-foot{display:flex;gap:16px;padding:9px 16px;border-top:1px solid var(--border);font-size:9.5px;color:var(--dim)}

@media (max-width: 860px) {
  #root{display:block;min-height:100vh}
  aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--border)}
  .brand{padding:14px 16px}
  nav{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));padding:10px}
  .side-foot{display:none}
  main{height:auto;min-height:100vh;padding:16px 14px 40px}
  .head{align-items:flex-start;flex-direction:column}
  .head-right{width:100%;flex-wrap:wrap}
  .search{width:100%}
  .search input{width:100%}
  .grid4,.grid3,.flow-cols{grid-template-columns:1fr}
  .flow-rail{overflow-x:auto;align-items:flex-start}
  .flow-node{min-width:72px}
  .flow-branch{flex-direction:column}
  .pal{width:94vw}
}
</style>
</head>
<body>
<div id="root" data-theme="dark" data-density="comfortable">
  <aside>
    <div class="brand">
      <div class="logo mono">OB</div>
      <div style="line-height:1.15">
        <div style="font-weight:600;font-size:14.5px;letter-spacing:-.01em">On Board</div>
        <div class="mono" style="font-size:9.5px;color:var(--dim);letter-spacing:.04em">agent memory · v2</div>
      </div>
      <span class="dot" id="brand-dot" title="live" style="margin-left:auto;background:var(--live);animation:pulse 2.4s infinite"></span>
    </div>
    <nav id="nav"></nav>
    <div class="side-foot">
      <div>
        <div class="side-cap mono">Theme</div>
        <div class="seg" id="seg-theme">
          <button data-action="theme" data-arg="dark">Dark</button>
          <button data-action="theme" data-arg="light">Light</button>
        </div>
      </div>
      <div>
        <div class="side-cap mono">Charts</div>
        <div class="seg" id="seg-chart">
          <button data-action="chart" data-arg="rich">Rich</button>
          <button data-action="chart" data-arg="bars">Bars</button>
        </div>
      </div>
      <div>
        <div class="side-cap mono">Density</div>
        <div class="seg" id="seg-dens">
          <button data-action="dens" data-arg="comfortable">Cozy</button>
          <button data-action="dens" data-arg="compact">Compact</button>
        </div>
      </div>
      <div class="foot-meta mono" id="foot-meta"></div>
    </div>
  </aside>
  <main>
    <div class="head">
      <h1 id="proj-name">Loading…</h1>
      <div class="head-right">
        <div class="search">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--dim)" stroke-width="1.5"><circle cx="7" cy="7" r="4.5"></circle><line x1="10.5" y1="10.5" x2="14" y2="14"></line></svg>
          <input id="filter" placeholder="Filter this view" autocomplete="off">
        </div>
        <button class="kbtn mono" data-action="palopen" title="Command palette"><span style="font-size:12px">⌘</span>K</button>
        <div class="chip mono" id="health" title="Overall memory health"></div>
        <div class="chip mono" id="live-chip"><span class="dot" style="width:6px;height:6px;background:var(--live);animation:pulse 2.4s infinite"></span>live · <span id="clock"></span></div>
      </div>
    </div>
    <p class="sub" id="proj-sub"></p>
    <div id="main-content"></div>
  </main>
</div>

<div id="palette">
  <div class="pal" data-action="palstop">
    <div class="pal-head">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="var(--dim)" stroke-width="1.5"><circle cx="7" cy="7" r="4.5"></circle><line x1="10.5" y1="10.5" x2="14" y2="14"></line></svg>
      <input id="palq" placeholder="Search memories, tickets, agents, or jump to a tab" autocomplete="off">
      <span class="pal-esc mono">ESC</span>
    </div>
    <div class="pal-list" id="pal-list"></div>
    <div class="pal-foot mono"><span>↑ ↓ navigate</span><span>↵ open</span><span>⌘K toggle</span></div>
  </div>
</div>

<script>
"use strict";
/* ---------- config: where the .agent-mem data lives ---------- */
const params = new URLSearchParams(location.search);
const OVERRIDE = params.get('data');
const BASE_CANDIDATES = OVERRIDE ? [OVERRIDE] : ['.', '.agent-mem', './.agent-mem', '../.agent-mem'];
const POLL_MS = __POLL_MS__;

const join = (b, f) => (b === '.' || b === '') ? f : b.replace(/\/+$/, '') + '/' + f;
async function getJSON(url) { const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw new Error(r.status + ' ' + url); return r.json(); }

/* ---------- state ---------- */
const LS = { get: k => { try { return localStorage.getItem('onboard.' + k); } catch (e) { return null; } }, set: (k, v) => { try { localStorage.setItem('onboard.' + k, v); } catch (e) {} } };
const state = {
  theme: LS.get('theme') || 'dark',
  chartMode: LS.get('chart') || 'rich',
  density: LS.get('density') || 'comfortable',
  tab: 'overview', win: 24, tlGroup: 'day', ticketView: 'list',
  query: '', palOpen: false, palQuery: '', palIdx: 0,
  loading: true, error: null, base: null, data: null, palResults: []
};

let liveErr = 0;
/* ---------- colour maps ---------- */
const TYPE = { decision:'#e0a92e', progress:'#3fb950', blocker:'#e5484d', context:'#4c8dff', handoff:'#a06cf0', todo:'#f0883e', file_change:'#33b3c4', discovery:'#d1b429', warning:'#e0a92e', checkpoint:'#8b6cf0', note:'#7f8794' };
const PRI = { critical:'#e5484d', high:'#f0883e', medium:'#e0a92e', low:'#3fb950' };
const ST = { open:'#f0883e', in_progress:'#4c8dff', in_review:'#a06cf0', closed:'#3fb950', rejected:'#e5484d', canceled:'#6a6d75', cancelled:'#6a6d75' };
const AST = { active:'#3fb950', kia:'#e5484d', completed:'#4c8dff', handed_off:'#a06cf0', idle:'#e0a92e' };
const typeColor = t => TYPE[t] || '#7f8794';
const soft = h => (h && h[0] === '#') ? h + '22' : 'var(--accent-soft)';
const halo = h => (h && h[0] === '#') ? h + '26' : 'transparent';

/* ---------- helpers ---------- */
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
const fmt = n => Math.round(n).toLocaleString();
const nowSec = () => Date.now() / 1000;
function ago(ts) { const d = nowSec() - ts; if (d < 60) return Math.max(0, Math.floor(d)) + 's ago'; if (d < 3600) return Math.floor(d/60)+'m ago'; if (d < 86400) return Math.floor(d/3600)+'h ago'; return Math.floor(d/86400)+'d ago'; }
const basename = p => (p || '').replace(/\/+$/, '').split('/').pop() || '';
const clockStr = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
function inferPlat(name){ const n=(name||'').toLowerCase(); if(/claude|fable|opus|sonnet|haiku/.test(n)) return 'claude'; if(/codex|terra|gpt|openai|o[0-9]|luna|soul/.test(n)) return 'codex'; if(/cursor/.test(n)) return 'cursor'; if(/antigravity|gemini/.test(n)) return 'antigravity'; return 'unknown'; }
function platOf(a){ let p=(a.agent_platform||'').toLowerCase().replace(/_/g,'-'); if(!p||p==='unknown') return {p:inferPlat(a.agent_name), guessed:true}; return {p, guessed:false}; }
function platLabel(a){ const r=platOf(a); return r.p+(r.guessed?'?':''); }
let lastSig = null;
function dataSig(d){ if(!d) return ''; try { return d.memories.length+'|'+d.tickets.length+'|'+Object.keys(d.agents).length+'|'+d.archive.length+'|'+d.digests.length+'|'+(d.memories.reduce((m,x)=>Math.max(m,x.timestamp||0),0))+'|'+d.tickets.map(t=>t.status+(t.updated_at||'')).join(',')+'|'+Object.values(d.agents).map(a=>a.status+'@'+a.last_activity).join(','); } catch(e){ return String(Math.random()); } }
function donut(items, C) { const total = items.reduce((s,i)=>s+i.value,0)||1; let cum=0; return items.map(i=>{ const frac=i.value/total, len=frac*C; const seg={...i, dash:len.toFixed(2)+' '+(C-len).toFixed(2), offset:(-cum).toFixed(2), pct:Math.round(frac*100)+'%'}; cum+=len; return seg; }); }

/* ---------- data loading ---------- */
async function resolveBase() {
  for (const b of BASE_CANDIDATES) { try { const r = await fetch(join(b, 'project.json'), { cache: 'no-store' }); if (r.ok) return b; } catch (e) {} }
  return null;
}
async function loadData(base) {
  const safe = async (f, d) => { try { return await getJSON(join(base, f)); } catch (e) { return d; } };
  const [project, mem, agents, digests, archive, tickets, stateKv] = await Promise.all([
    safe('project.json', {}), safe('memories.json', { entries: [] }), safe('agents.json', {}),
    safe('digests.json', { digests: [] }), safe('archive.json', { entries: [] }),
    safe('tickets/_index.json', { tickets: [] }), safe('state.json', {})
  ]);
  const ticketList = Array.isArray(tickets) ? tickets : (tickets.tickets || []);
  const memories = (mem.entries || []).map(m => ({ ...m, related_tickets: m.related_tickets || [], tags: m.tags || [], related_files: m.related_files || [] }));
  return {
    project: {
      name: basename(project.project_root) || project.name || "__PROJECT_NAME_JS__",
      description: project.description || '',
      tech: project.tech_stack || ''
    },
    memories,
    agents: agents || {},
    digests: (digests.digests || []),
    archive: (archive.entries || []),
    tickets: ticketList.map(t => ({ ...t, tags: t.tags || [], related_files: t.related_files || [] })),
    stateKv: stateKv || {}
  };
}
async function boot() {
  state.base = await resolveBase();
  if (!state.base) { state.loading = false; state.error = 'nodata'; render(); return; }
  try { state.data = await loadData(state.base); state.loading = false; state.error = null; }
  catch (e) { state.loading = false; state.error = 'load'; }
  lastSig = dataSig(state.data);
  render();
  if (state.data) setLive('ok');
  setInterval(refresh, POLL_MS);
}
function setLive(mode) {
  const chip = document.getElementById('live-chip'), bd = document.getElementById('brand-dot');
  const color = mode==='ok'?'var(--live)':mode==='stale'?'var(--accent)':'#e5484d';
  const anim = mode==='ok'?'animation:pulse 2.4s infinite':'';
  const body = mode==='ok'?'live · <span id="clock">'+clockStr()+'</span>':mode==='stale'?'reconnecting\u2026':'offline \u00b7 start the server';
  if (chip) chip.innerHTML = '<span class="dot" style="width:6px;height:6px;background:'+color+';'+anim+'"></span>'+body;
  if (bd) { bd.style.background = color; bd.style.animation = mode==='ok'?'pulse 2.4s infinite':'none'; }
}
async function refresh() {
  if (!state.base) { state.base = await resolveBase(); if (!state.base) { setLive('offline'); return; } }
  let ok = false;
  try { const r = await fetch(join(state.base, 'project.json'), { cache: 'no-store' }); ok = r.ok; } catch (e) {}
  if (!ok) { liveErr++; setLive(liveErr > 2 ? 'offline' : 'stale'); return; }
  liveErr = 0;
  let data = null;
  try { data = await loadData(state.base); } catch (e) { setLive('stale'); return; }
  const sig = dataSig(data);
  state.data = data; state.error = null; state.loading = false;
  if (sig !== lastSig) { lastSig = sig; updateMain(); updateHeader(); }
  setLive('ok');
}

/* ---------- derive view model ---------- */
function derive() {
  const d = state.data, isRich = state.chartMode === 'rich', C = 2 * Math.PI * 54;
  const memSorted = d.memories.slice().sort((a, b) => b.timestamp - a.timestamp);
  const openStatuses = ['open', 'in_progress', 'in_review'];
  const openTickets = d.tickets.filter(t => openStatuses.includes(t.status)).length;
  const agentList = Object.values(d.agents);
  const activeAgents = agentList.filter(a => a.status === 'active').length;
  const activeNames = new Set(agentList.filter(a => a.status === 'active').map(a => a.agent_name));
  const totalTok = d.memories.reduce((a, m) => a + Math.floor((m.title||'').length/4) + Math.floor((m.content||'').length/4), 0);

  const typeCounts = {};
  d.memories.forEach(m => typeCounts[m.memory_type] = (typeCounts[m.memory_type]||0)+1);
  const typeItems = Object.entries(typeCounts).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({label:k,value:v,color:typeColor(k)}));
  const typeSegs = donut(typeItems, C);

  const buckets = new Array(24).fill(0);
  d.memories.forEach(m => { const h = Math.floor((nowSec()-m.timestamp)/3600); if (h>=0 && h<24) buckets[23-h]++; });
  const maxB = Math.max(1, ...buckets), W = 320, H = 62;
  const pts = buckets.map((v,i)=>[(i/23)*W, H-(v/maxB)*(H-6)+3]);
  const line = 'M' + pts.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' L');
  const area = line + ' L'+W+','+H+' L0,'+H+' Z';

  const query = state.query.trim().toLowerCase();
  const hitMem = m => !query || ((m.title||'')+' '+(m.content||'')+' '+m.memory_type+' '+m.agent_name+' '+m.tags.join(' ')).toLowerCase().includes(query);
  const fmtMem = m => ({ id:'#'+m.id, rawId:m.id, ago:ago(m.timestamp), stamp:(m.created_at||'').slice(0,16).replace('T',' '), type:m.memory_type, color:typeColor(m.memory_type), agent:m.agent_name, title:m.title||'(untitled)', content:m.content||'', pin:m.pinned, ts:m.timestamp });
  const recent = memSorted.filter(hitMem).map(fmtMem);

  // agents
  const rank = a => (a.status==='active'?0:1);
  const roster = agentList.slice().sort((a,b)=>rank(a)-rank(b) || b.last_activity-a.last_activity).map(a=>({
    name:a.agent_name, role:a.agent_role && a.agent_role!=='main'?' · '+a.agent_role:'', color:AST[a.status]||'#888',
    meta:platLabel(a)+' · '+a.memories_written+'w · '+a.status.replace('_',' ')+' · '+ago(a.last_activity)
  }));
  const agentsFull = agentList.slice().sort((a,b)=>rank(a)-rank(b) || b.last_activity-a.last_activity).map(a=>({
    name:a.agent_name, role:a.agent_role && a.agent_role!=='main'?' · '+a.agent_role:'', color:AST[a.status]||'#888', writes:a.memories_written,
    meta:platLabel(a)+' · '+a.status.replace('_',' ')+' · joined '+(a.joined_at||'').slice(0,10)+' · last '+ago(a.last_activity),
    q:(a.agent_name+' '+a.agent_platform+' '+a.status+' '+(a.agent_role||'')).toLowerCase()
  }));
  const agentRows = agentsFull.filter(a => !query || a.q.includes(query));

  // agents by platform
  const PLAT = { 'claude':'#4c8dff', 'claude-desktop':'#4c8dff', 'claude-code':'#4c8dff', 'codex':'#e0a92e', 'cursor':'#a06cf0', 'antigravity':'#3fb950', 'unknown':'#6a6d75' };
  const platColor = k => PLAT[k] || '#33b3c4';
  const platMap = {}; agentList.forEach(a => { const k=platOf(a).p; platMap[k]=(platMap[k]||0)+1; });
  const platItems = Object.entries(platMap).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({label:k, value:v, color:platColor(k)}));
  const platforms = donut(platItems, C);
  const platTop = platItems[0] || { label:'—', value:0 };

  // tickets
  const priOrder = { critical:0, high:1, medium:2, low:3 };
  const tickets = d.tickets.slice().sort((a,b)=>(priOrder[a.priority]??9)-(priOrder[b.priority]??9) || b.timestamp-a.timestamp).map(t=>{
    const orphan = t.claimed_by && ['in_progress','in_review'].includes(t.status) && !activeNames.has(t.claimed_by);
    return { id:t.id, priority:t.priority, priColor:PRI[t.priority]||'#888', status:(t.status||'').replace('_',' '), rawStatus:t.status, statusColor:ST[t.status]||'#888',
      edge:orphan?'#e0a92e':'transparent', isOrphan:orphan,
      orphanReason: orphan ? esc(t.claimed_by)+' claimed this ticket but is no longer active, so nobody is working it.' : '',
      orphanAction: orphan ? 'Release the claim or reassign it to an active agent.' : '',
      title:t.title||'', meta:'by '+(t.created_by||'?')+' → '+(t.assigned_to||'any')+(t.claimed_by?' · claimed by '+t.claimed_by:'')+(t.related_files.length?' · '+t.related_files.join(', '):''),
      q:((t.id||'')+' '+(t.title||'')+' '+(t.status||'')+' '+(t.created_by||'')).toLowerCase() };
  });
  const ticketRows = tickets.filter(t => !query || t.q.includes(query));

  // ticket flow
  const FLOWDEF = [{key:'open',label:'Open'},{key:'in_progress',label:'In progress'},{key:'in_review',label:'In review'},{key:'closed',label:'Closed'}];
  const fbucket = {open:[],in_progress:[],in_review:[],closed:[],canceled:[],rejected:[]};
  ticketRows.forEach(t=>{ const k=t.rawStatus==='cancelled'?'canceled':t.rawStatus; if(fbucket[k]) fbucket[k].push(t); else fbucket.open.push(t); });
  const flowStages = FLOWDEF.map(s=>({key:s.key, label:s.label, color:ST[s.key]||'#888', items:fbucket[s.key], count:fbucket[s.key].length}));
  const flowBranch = [{key:'canceled',label:'Canceled',color:ST.canceled,items:fbucket.canceled},{key:'rejected',label:'Rejected',color:ST.rejected,items:fbucket.rejected}];
  const flowBranchTotal = fbucket.canceled.length + fbucket.rejected.length;

  // links
  const hasShared = (a,b) => { const bs = new Set((b||[]).map(x=>x.toLowerCase())); return (a||[]).some(x=>bs.has(x.toLowerCase())); };
  const linkTickets = d.tickets.map(t=>{
    const related = d.memories.map(m=>{
      let sc=0; const text = ((m.title||'')+' '+(m.content||'')+' '+m.tags.join(' ')+' '+m.related_files.join(' ')+' '+(m.related_tickets||[]).join(' ')).toLowerCase();
      if (text.includes((t.id||'').toLowerCase())) sc+=50;
      if ((m.related_tickets||[]).includes(t.id)) sc+=80;
      if (hasShared(m.related_files, t.related_files)) sc+=25;
      if (hasShared(m.tags, t.tags)) sc+=12;
      if (m.pinned) sc+=5;
      return { m, sc };
    }).filter(x=>x.sc>0).sort((a,b)=>b.sc-a.sc).slice(0,4);
    return { t, related };
  }).filter(x=>x.related.length).sort((a,b)=>b.related.length-a.related.length).map(x=>({
    id:x.t.id, title:x.t.title, meta:(x.t.status||'').replace('_',' ')+' · '+x.t.priority+' · '+(x.t.related_files.join(', ')||'no files'),
    related:x.related.map(r=>({type:'['+r.m.memory_type+']', color:typeColor(r.m.memory_type), title:r.m.title, agent:r.m.agent_name, score:'score '+r.sc}))
  }));
  const fileMap = {};
  d.memories.forEach(m => m.related_files.forEach(f=>{ fileMap[f]=fileMap[f]||{m:0,t:0}; fileMap[f].m++; }));
  d.tickets.forEach(t => t.related_files.forEach(f=>{ fileMap[f]=fileMap[f]||{m:0,t:0}; fileMap[f].t++; }));
  const fileLinks = Object.entries(fileMap).sort((a,b)=>(b[1].m+b[1].t)-(a[1].m+a[1].t)).map(([f,c])=>({path:f, meta:c.m+' mem · '+c.t+' tkt'}));
  const tagMap = {};
  d.memories.forEach(m => m.tags.forEach(t=>tagMap[t]=(tagMap[t]||0)+1));
  const tags = Object.entries(tagMap).sort((a,b)=>b[1]-a[1]).map(([t,c])=>({label:t,count:c}));

  const health = [];
  d.tickets.forEach(t=>{ if (t.claimed_by && ['in_progress','in_review'].includes(t.status) && !activeNames.has(t.claimed_by)) health.push({color:'#e0a92e', msg:'Ticket '+t.id+' is claimed by '+t.claimed_by+', who is offline. Reassign or release it.'}); });
  if (!health.length) health.push({ color:'#3fb950', msg:'No linkage or data-health warnings.' });

  // health score
  const orphanCount = d.tickets.filter(t => t.claimed_by && ['in_progress','in_review'].includes(t.status) && !activeNames.has(t.claimed_by)).length;
  const openCrit = d.tickets.filter(t => t.priority==='critical' && ['open','in_progress'].includes(t.status)).length;
  const blockers = d.memories.filter(m => m.memory_type==='blocker').length;
  const hscore = Math.max(0, Math.min(100, 100 - orphanCount*8 - openCrit*6 - blockers*4));
  const hcolor = hscore>=85?'var(--live)':hscore>=60?'var(--accent)':'#e5484d';
  const hlabel = hscore>=85?'Healthy':hscore>=60?'Attention':'At risk';

  // trends
  const w0 = d.memories.filter(m=>nowSec()-m.timestamp<=86400).length;
  const w1 = d.memories.filter(m=>{const a=nowSec()-m.timestamp;return a>86400&&a<=172800;}).length;
  const dm = w0-w1;
  const kpis = [
    { label:'Memories', val:d.memories.length+'', sub:'+'+d.archive.length+' archived', trend:{dir:dm>=0?'▲':'▼', text:(dm>=0?'+'+dm:dm)+' writes vs prev day', color:dm>=0?'var(--live)':'#e5484d'} },
    { label:'Agents', val:agentList.length+'', sub:activeAgents+' active' },
    { label:'Tickets', val:openTickets+'/'+d.tickets.length, sub:'open / total', trend:openCrit>0?{dir:'!', text:openCrit+' critical open', color:'#e5484d'}:null },
    { label:'Tokens', val:'~'+fmt(totalTok), sub:d.digests.length+' digests' }
  ];

  // timeline groups
  const groupKey = ts => {
    const ageDays = Math.floor((nowSec()-ts)/86400);
    if (state.tlGroup==='hour') { const h=Math.floor((nowSec()-ts)/3600); return h<=0?'Past hour':h+'h ago'; }
    if (state.tlGroup==='week') { const w=Math.floor(ageDays/7); return w<=0?'This week':w===1?'Last week':w+' weeks ago'; }
    return ageDays<=0?'Today':ageDays===1?'Yesterday':ageDays+' days ago';
  };
  const seen={}, tg=[]; recent.forEach(m=>{ const k=groupKey(m.ts); if(!seen[k]){seen[k]={label:k,items:[]};tg.push(seen[k]);} seen[k].items.push(m); });
  const timelineGroups = tg.map(g=>({label:g.label, count:g.items.length+(g.items.length===1?' memory':' memories'), items:g.items}));

  // tokens tab
  const tk = c => Math.floor(c/3);
  const hot = tk(d.memories.reduce((a,m)=>a+(m.title||'').length+(m.content||'').length,0));
  const dig = tk(d.digests.reduce((a,x)=>a+(x.summary||'').length,0));
  const arc = tk(d.archive.reduce((a,m)=>a+(m.title||'').length+(m.content||'').length,0));
  const tokenItems = [{label:'Hot memory',value:hot,color:'#e0a92e'},{label:'Digests',value:dig,color:'#4c8dff'},{label:'Archive (disk only)',value:arc,color:'#8b6cf0'}];
  const tokenSegs = donut(tokenItems, C).map(x=>({...x, valStr:fmt(x.value)}));
  const tokenKpis = [
    { label:'Hot memory', val:'~'+fmt(hot), sub:d.memories.length+' entries' },
    { label:'Digests', val:'~'+fmt(dig), sub:d.digests.length+' compressed' },
    { label:'Archive', val:'~'+fmt(arc), sub:d.archive.length+' on disk' },
    { label:'Per session', val:'~'+fmt(hot+dig+500), sub:'loaded at start' }
  ];

  // changes / diff since last checkpoint
  const chk = memSorted.find(m=>m.memory_type==='checkpoint');
  const refTs = chk ? chk.timestamp : nowSec()-86400;
  const chgAdded = memSorted.filter(m=>m.timestamp>refTs && m.memory_type!=='checkpoint').map(fmtMem);
  const chgTickets = d.tickets.filter(t=>t.timestamp>refTs).sort((a,b)=>b.timestamp-a.timestamp).map(t=>({id:t.id, title:t.title, status:(t.status||'').replace('_',' '), statusColor:ST[t.status]||'#888', ago:ago(t.timestamp)}));
  const chgAgents = agentList.filter(a=>a.status!=='active' && a.last_activity>refTs).map(a=>({name:a.agent_name, to:a.status.replace('_',' '), color:AST[a.status]||'#888', ago:ago(a.last_activity)}));
  const changes = { ref: chk?chk.title:'the last 24 hours', refAgo: ago(refTs), added:chgAdded, tickets:chgTickets, agents:chgAgents, empty:!chgAdded.length && !chgTickets.length && !chgAgents.length };
  const changeKpis = [
    { label:'New memories', val:chgAdded.length+'', sub:'since checkpoint' },
    { label:'Ticket updates', val:chgTickets.length+'', sub:'created / moved' },
    { label:'Agent changes', val:chgAgents.length+'', sub:'status shifts' }
  ];

  // quota tab
  const q = quota(state.win, activeNames);

  return { isRich, C, memSorted, openTickets, activeAgents, totalTok, typeSegs, spark:{line,area,total:buckets.reduce((a,b)=>a+b,0)},
    recent, roster, agentsFull, agentRows, platforms, platCount:platItems.length, platTop, totalAgents:agentList.length, tickets, ticketRows, flowStages, flowBranch, flowBranchTotal, linkTickets, fileLinks, tags, health,
    hscore, hcolor, hlabel, kpis, timelineGroups, tokenKpis, tokenSegs, tokenTotal:fmt(hot+dig+arc),
    changes, changeKpis, q,
    counts:{ memories:d.memories.length, agents:agentList.length, openTickets } };
}

function quota(hours, activeNames) {
  const d = state.data, now = nowSec();
  const win = ts => ts && (now-ts) <= hours*3600;
  const memIn = d.memories.filter(m=>win(m.timestamp));
  const arcIn = d.archive.filter(m=>win(m.timestamp));
  const digIn = d.digests.filter(x=>win(Date.parse(x.compressed_at)/1000));
  const tkIn = d.tickets.filter(t=>win(t.timestamp));
  const agIn = Object.values(d.agents).filter(a=>win(Date.parse(a.joined_at)/1000));
  const tok = c => Math.floor(c/3);
  const hotChars = memIn.reduce((s,m)=>s+(m.title||'').length+(m.content||'').length,0);
  const arcChars = arcIn.reduce((s,m)=>s+(m.title||'').length+(m.content||'').length,0);
  const digChars = digIn.reduce((s,x)=>s+(x.summary||'').length,0) || 800;
  const briefRaw = tok(hotChars+arcChars)+500;
  const noSystem = briefRaw + Math.floor(briefRaw*0.2) + Math.floor(briefRaw*0.15);
  const withSystem = tok(hotChars) + tok(digChars) + 500;
  const savedPer = Math.max(0, noSystem-withSystem);
  const mult = withSystem>0 ? noSystem/withSystem : 1;
  const sessions = agIn.length || 1;
  const extraMin = Math.round(45*(1 - 1/mult));
  const totalHours = (extraMin*sessions)/60;
  const winLabel = hours===24?'24h':hours===168?'7 days':'lifetime';
  const maxBar = Math.max(noSystem, withSystem)*1.05 || 1;
  return {
    winLabel, mult:mult.toFixed(2), sessions, sessionWord:sessions===1?'session':'sessions',
    noSystem:fmt(noSystem), withSystem:fmt(withSystem), savedPer:fmt(savedPer), totalSaved:fmt(savedPer*sessions),
    tkCount:tkIn.length, extraMin, totalHours:totalHours.toFixed(1),
    gaugeDash:((Math.min(1, mult/4))*(2*Math.PI*54)).toFixed(2)+' '+(2*Math.PI*54).toFixed(2),
    story:[
      { stat:'+'+extraMin+' min', title:'more work per session', body:'Before, sessions hit the cap quickly. Now they usually run much longer before Claude has to reset.' },
      { stat:tkIn.length+'', title:tkIn.length===1?'ticket splits the load':'tickets split the load', body:'Heavy work runs across agents instead of one. A planner scopes it, a coder ships it, a reviewer signs off.' },
      { stat:fmt(savedPer*sessions), title:'tokens saved in window', body:'That budget goes to real work rather than rebuilding context every time an agent starts.' }
    ],
    bars:[
      { label:'Without On Board', valStr:fmt(noSystem), pct:Math.max(3, noSystem/maxBar*100).toFixed(0)+'%', color:'#e5484d' },
      { label:'With On Board', valStr:fmt(withSystem), pct:Math.max(3, withSystem/maxBar*100).toFixed(0)+'%', color:'var(--live)' }
    ],
    kpis:[
      { label:'Sessions', val:sessions+'', sub:'in window' },
      { label:'Saved / session', val:'~'+fmt(savedPer), sub:'tokens' },
      { label:'Total saved', val:'~'+fmt(savedPer*sessions), sub:'tokens' },
      { label:'Time gained', val:totalHours.toFixed(1)+'h', sub:'estimated' }
    ]
  };
}

/* ---------- templates ---------- */
const NAV = [
  ['overview','Overview','memories','<rect x="2" y="2" width="5" height="5" rx="1.2"/><rect x="9" y="2" width="5" height="5" rx="1.2"/><rect x="2" y="9" width="5" height="5" rx="1.2"/><rect x="9" y="9" width="5" height="5" rx="1.2"/>'],
  ['timeline','Timeline','memories','<line x1="4" y1="2" x2="4" y2="14"/><circle cx="4" cy="5" r="1.7" fill="currentColor" stroke="none"/><circle cx="4" cy="11" r="1.7" fill="currentColor" stroke="none"/><line x1="8" y1="5" x2="14" y2="5"/><line x1="8" y1="11" x2="12.5" y2="11"/>'],
  ['changes','Changes',null,'<path d="M2.5 4.5h7"/><path d="M6.5 2l3 2.5-3 2.5"/><path d="M13.5 11.5h-7"/><path d="M9.5 9l-3 2.5 3 2.5"/>'],
  ['agents','Agents','agents','<circle cx="6" cy="6" r="2.4"/><circle cx="11.4" cy="7" r="1.9"/><path d="M2 13.4c0-2.1 1.8-3.3 4-3.3s4 1.2 4 3.3"/>'],
  ['tickets','Tickets','openTickets','<rect x="2" y="4" width="12" height="8" rx="1.6"/><line x1="2" y1="8" x2="14" y2="8" stroke-dasharray="1.4 1.4"/>'],
  ['links','Links',null,'<circle cx="4" cy="4.5" r="2"/><circle cx="12" cy="6" r="2"/><circle cx="7" cy="12" r="2"/><line x1="5.7" y1="5" x2="10.3" y2="5.6"/><line x1="5" y1="6" x2="6.4" y2="10.3"/>'],
  ['tokens','Tokens',null,'<line x1="3.5" y1="13" x2="3.5" y2="8.5" stroke-width="2" stroke-linecap="round"/><line x1="8" y1="13" x2="8" y2="4" stroke-width="2" stroke-linecap="round"/><line x1="12.5" y1="13" x2="12.5" y2="10" stroke-width="2" stroke-linecap="round"/>'],
  ['quota','Quota saved',null,'<polygon points="9,1.5 3.5,9 7,9 6.5,14.5 12.5,7 8.5,7" fill="currentColor" stroke="none"/>']
];
function buildNav(v) {
  document.getElementById('nav').innerHTML = NAV.map(([tab,label,countKey,svg])=>{
    const on = state.tab===tab;
    let badge = '';
    if (v && countKey) { const n = v.counts[countKey]; const hot = countKey==='openTickets' && n>0; badge = `<span class="badge mono${hot?' hot':''}">${n}</span>`; }
    return `<button class="navbtn${on?' on':''}" data-action="tab" data-arg="${tab}"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4">${svg}</svg><span class="lbl">${label}</span>${badge}</button>`;
  }).join('');
}
const kpiCard = k => `<div class="card kpi"><div class="k-lbl mono">${esc(k.label)}</div><div class="k-val">${esc(k.val)}</div><div class="k-sub mono">${esc(k.sub)}</div>${k.trend?`<div class="k-trend mono" style="color:${k.trend.color}">${k.trend.dir} ${esc(k.trend.text)}</div>`:''}</div>`;
const donutSVG = (segs, total, unit, size) => `<div style="position:relative;width:${size}px;height:${size}px;flex-shrink:0"><svg width="${size}" height="${size}" viewBox="0 0 120 120"><circle cx="60" cy="60" r="54" fill="none" stroke="var(--track)" stroke-width="12"/><g transform="rotate(-90 60 60)">${segs.map(s=>`<circle cx="60" cy="60" r="54" fill="none" stroke="${s.color}" stroke-width="12" stroke-dasharray="${s.dash}" stroke-dashoffset="${s.offset}"/>`).join('')}</g></svg><div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center"><div style="font-size:${size>120?20:22}px;font-weight:600;font-variant-numeric:tabular-nums">${total}</div><div class="mono" style="font-size:8.5px;color:var(--dim);letter-spacing:.06em">${unit}</div></div></div>`;
const memRow = (m, cols) => `<div data-row class="row" style="position:relative;padding:13px 16px;display:grid;grid-template-columns:${cols};gap:14px">
  <button class="hact copybtn mono" data-action="copy" data-arg="${esc(m.id)}" title="Copy id" style="position:absolute;top:12px;right:12px">copy id</button>
  <div class="mono" style="font-size:10.5px;color:var(--dim);line-height:1.5"><div style="color:var(--muted)">${esc(m.ago)}</div><div style="font-size:9.5px">${esc(m.stamp)}</div></div>
  <div style="min-width:0">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><span class="pill mono" style="color:${m.color};background:${soft(m.color)}">${esc(m.type)}</span><span class="mono" style="font-size:10.5px;color:var(--muted)">${esc(m.agent)}</span><span class="mono" style="font-size:10px;color:var(--accent)">${esc(m.id)}</span></div>
    <div style="font-weight:500;margin-top:4px;font-size:12.5px">${m.pin?'★ ':''}${esc(m.title)}</div>
    <div style="color:var(--muted);font-size:12px;margin-top:2px;white-space:pre-wrap;overflow:hidden;max-height:3em">${esc(m.content)}</div>
  </div></div>`;

function tabHTML(v) {
  const t = state.tab;
  if (t==='overview') return `<section>
    <div class="grid4" style="margin-bottom:16px">${v.kpis.map(kpiCard).join('')}</div>
    <div style="display:grid;grid-template-columns:1.7fr 1fr;gap:16px;margin-bottom:16px">
      <div class="card" style="padding:16px 18px">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px"><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim)">Memory activity · last 24h</div><div class="mono" style="font-size:11px;color:var(--muted)">${v.spark.total} writes</div></div>
        <svg viewBox="0 0 320 68" preserveAspectRatio="none" style="width:100%;height:70px;display:block"><path d="${v.spark.area}" fill="var(--accent-soft)"/><path d="${v.spark.line}" fill="none" stroke="var(--accent)" stroke-width="1.6" stroke-linejoin="round"/></svg>
      </div>
      <div class="card" style="padding:16px 18px;display:flex;flex-direction:column">
        <div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin-bottom:8px">Memory types</div>
        ${v.isRich ? `<div style="display:flex;align-items:center;gap:16px;flex:1">${donutSVG(v.typeSegs, v.counts.memories, 'TOTAL', 104)}<div style="flex:1;display:flex;flex-direction:column;gap:5px">${v.typeSegs.map(s=>`<div style="display:flex;align-items:center;gap:7px;font-size:11.5px"><span style="width:8px;height:8px;border-radius:2px;background:${s.color};flex-shrink:0"></span><span style="color:var(--muted);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.label)}</span><span class="mono" style="color:var(--text)">${s.value}</span></div>`).join('')}</div></div>`
        : `<div style="display:flex;flex-direction:column;gap:9px;flex:1;justify-content:center">${v.typeSegs.map(s=>`<div><div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span style="color:var(--muted)">${esc(s.label)}</span><span class="mono" style="color:var(--text)">${s.value}</span></div><div style="height:6px;background:var(--track);border-radius:4px;overflow:hidden"><div style="height:100%;border-radius:4px;background:${s.color};width:${s.pct}"></div></div></div>`).join('')}</div>`}
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1.7fr 1fr;gap:16px">
      <div class="card" style="overflow:hidden">
        <div class="cap mono">Recent activity</div>
        <div style="max-height:440px;overflow-y:auto">${v.recent.length?v.recent.slice(0,40).map(m=>memRowCompact(m)).join(''):emptyBox('No memories yet','Once agents start writing, activity shows here.')}</div>
      </div>
      <div class="card" style="overflow:hidden">
        <div class="cap mono">Agent roster</div>
        <div style="max-height:440px;overflow-y:auto">${v.roster.map(a=>`<div data-row class="row" style="padding:12px 16px;display:flex;align-items:center;gap:10px"><span style="width:9px;height:9px;border-radius:50%;background:${a.color};flex-shrink:0;box-shadow:0 0 0 3px ${halo(a.color)}"></span><div style="min-width:0;flex:1"><div style="font-weight:500;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.name)}${esc(a.role)}</div><div class="mono" style="font-size:10px;color:var(--muted);margin-top:1px">${esc(a.meta)}</div></div></div>`).join('')}</div>
      </div>
    </div>
  </section>`;

  if (t==='timeline') return `<section>
    <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px"><div class="mono" style="font-size:11px;color:var(--muted)">Group by</div>
      <div class="seg" style="width:auto">${['hour','day','week'].map(g=>`<button class="${state.tlGroup===g?'on':''}" data-action="tl" data-arg="${g}" style="padding:6px 16px">${g[0].toUpperCase()+g.slice(1)}</button>`).join('')}</div></div>
    ${v.timelineGroups.length ? v.timelineGroups.map(g=>`<div style="margin-bottom:18px"><div style="display:flex;align-items:baseline;gap:10px;margin-bottom:8px;padding-left:2px"><div style="font-weight:600;font-size:13px">${esc(g.label)}</div><div class="mono" style="font-size:10px;color:var(--dim)">${esc(g.count)}</div><div style="flex:1;height:1px;background:var(--border-soft)"></div></div><div class="card" style="overflow:hidden">${g.items.map(m=>memRow(m,'100px 1fr')).join('')}</div></div>`).join('')
      : emptyBox('No memories match your filter','Clear the filter box in the header to see the full timeline.',true)}
  </section>`;

  if (t==='changes') return `<section>
    <div style="border-left:3px solid var(--accent);padding:2px 0 2px 14px;margin-bottom:18px"><div class="mono" style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent)">Since last checkpoint</div><div style="font-weight:600;font-size:14.5px;margin-top:4px">${esc(v.changes.ref)}</div><div class="mono" style="font-size:11px;color:var(--muted);margin-top:2px">recorded ${esc(v.changes.refAgo)}</div></div>
    <div class="grid3" style="margin-bottom:16px">${v.changeKpis.map(k=>`<div class="card kpi"><div class="k-lbl mono">${esc(k.label)}</div><div class="k-val" style="font-size:26px">${esc(k.val)}</div><div class="k-sub mono">${esc(k.sub)}</div></div>`).join('')}</div>
    ${v.changes.empty ? emptyBox('Nothing has changed since the checkpoint','New memories, ticket moves, and agent status shifts will appear here.',true) : `<div style="display:grid;grid-template-columns:1.6fr 1fr;gap:16px">
      <div class="card" style="overflow:hidden;align-self:start"><div class="cap mono">Memories added</div>${v.changes.added.length?v.changes.added.map(m=>`<div class="row" style="padding:12px 16px;display:grid;grid-template-columns:22px 1fr;gap:10px"><span style="color:var(--live);font-weight:700;font-size:14px">+</span><div style="min-width:0"><div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><span class="pill mono" style="color:${m.color};background:${soft(m.color)}">${esc(m.type)}</span><span class="mono" style="font-size:10.5px;color:var(--muted);white-space:nowrap">${esc(m.agent)} · ${esc(m.ago)}</span></div><div style="font-weight:500;margin-top:4px;font-size:12.5px">${m.pin?'★ ':''}${esc(m.title)}</div></div></div>`).join(''):'<div style="padding:20px;color:var(--muted);font-size:12px">No new memories.</div>'}</div>
      <div style="display:flex;flex-direction:column;gap:16px">
        <div class="card" style="overflow:hidden"><div class="cap mono">Ticket updates</div>${v.changes.tickets.length?v.changes.tickets.map(t=>`<div class="row" style="padding:11px 16px"><div style="display:flex;align-items:center;gap:8px"><span class="mono" style="font-size:10.5px;color:var(--dim)">${esc(t.id)}</span><span class="pill mono" style="color:${t.statusColor};background:${soft(t.statusColor)}">${esc(t.status)}</span><span class="mono" style="font-size:10px;color:var(--muted);margin-left:auto">${esc(t.ago)}</span></div><div style="font-size:12px;margin-top:4px">${esc(t.title)}</div></div>`).join(''):'<div style="padding:16px;color:var(--muted);font-size:12px">No ticket updates.</div>'}</div>
        <div class="card" style="overflow:hidden"><div class="cap mono">Agent changes</div>${v.changes.agents.length?v.changes.agents.map(a=>`<div class="row" style="padding:11px 16px;display:flex;align-items:center;gap:9px"><span style="width:8px;height:8px;border-radius:50%;background:${a.color};flex-shrink:0"></span><span style="font-size:12px;font-weight:500">${esc(a.name)}</span><span class="mono" style="font-size:10.5px;color:var(--muted)">now ${esc(a.to)}</span><span class="mono" style="font-size:10px;color:var(--dim);margin-left:auto">${esc(a.ago)}</span></div>`).join(''):'<div style="padding:16px;color:var(--muted);font-size:12px">No agent changes.</div>'}</div>
      </div></div>`}
  </section>`;

  if (t==='agents') return `<section>
    <div class="card" style="margin-bottom:16px;padding:16px 18px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px"><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim)">Agents by platform</div><div class="mono" style="font-size:11px;color:var(--muted)">${v.platCount} platform${v.platCount===1?'':'s'} · most used <b style="color:var(--text)">${esc(v.platTop.label)}</b> (${v.platTop.value})</div></div>
      ${v.isRich ? `<div style="display:flex;align-items:center;gap:24px">${donutSVG(v.platforms, v.totalAgents, 'AGENTS', 120)}<div style="flex:1;display:flex;flex-direction:column;gap:7px">${v.platforms.map(s=>`<div style="display:flex;align-items:center;gap:9px;font-size:12px"><span style="width:9px;height:9px;border-radius:2px;background:${s.color};flex-shrink:0"></span><span style="flex:1;color:var(--muted)">${esc(s.label)}</span><span class="mono" style="color:var(--text)">${s.value}</span><span class="mono" style="color:var(--dim);width:42px;text-align:right">${s.pct}</span></div>`).join('')}</div></div>`
      : `<div style="display:flex;flex-direction:column;gap:11px">${v.platforms.map(s=>`<div><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px"><span style="color:var(--muted)">${esc(s.label)}</span><span class="mono" style="color:var(--text)">${s.value} · ${s.pct}</span></div><div style="height:8px;background:var(--track);border-radius:5px;overflow:hidden"><div style="height:100%;border-radius:5px;background:${s.color};width:${s.pct}"></div></div></div>`).join('')}</div>`}
    </div>
    <div class="card" style="overflow:hidden"><div class="cap mono">Every agent on this project</div>
    ${v.agentRows.length ? v.agentRows.map(a=>`<div data-row class="row" style="padding:14px 16px;display:flex;align-items:center;gap:12px"><span style="width:10px;height:10px;border-radius:50%;background:${a.color};flex-shrink:0;box-shadow:0 0 0 3px ${halo(a.color)}"></span><div style="min-width:0;flex:1"><div style="font-weight:500;font-size:13px">${esc(a.name)}${esc(a.role)}</div><div class="mono" style="font-size:10.5px;color:var(--muted);margin-top:2px">${esc(a.meta)}</div></div><div class="mono" style="text-align:right;flex-shrink:0"><div style="font-size:16px;font-weight:600">${a.writes}</div><div style="font-size:9px;color:var(--dim);letter-spacing:.05em;text-transform:uppercase">writes</div></div></div>`).join('')
      : '<div class="empty"><div class="e-s">No agents match your filter.</div></div>'}
  </div></section>`;

  if (t==='tickets') {
    const listBody = v.ticketRows.length ? v.ticketRows.map(t=>`<div data-row class="row" style="padding:14px 16px;border-left:2px solid ${t.edge}"><div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span class="mono" style="font-size:10.5px;color:var(--dim)">${esc(t.id)}</span><span style="width:7px;height:7px;border-radius:50%;background:${t.priColor}"></span><span class="mono" style="font-size:10px;text-transform:uppercase;color:${t.priColor}">${esc(t.priority)}</span><span class="pill mono" style="color:${t.statusColor};background:${soft(t.statusColor)}">${esc(t.status)}</span>${t.isOrphan?'<span class="mono" style="font-size:10px;color:var(--accent)">⚠ orphan</span>':''}</div><div style="font-weight:500;font-size:13px;margin-top:6px">${esc(t.title)}</div><div class="mono" style="font-size:10.5px;color:var(--muted);margin-top:3px">${esc(t.meta)}</div>${t.isOrphan?`<div style="margin-top:9px;padding:9px 11px;background:var(--accent-soft);border-radius:8px;font-size:11.5px;line-height:1.5"><div><b style="color:var(--accent)">Why flagged:</b> ${t.orphanReason}</div><div style="color:var(--muted);margin-top:3px"><b style="color:var(--text)">Suggested:</b> ${t.orphanAction}</div></div>`:''}</div>`).join('') : '<div class="empty"><div class="e-s">No tickets match your filter.</div></div>';
    const list = `<div class="card" style="overflow:hidden"><div class="cap mono">All tickets</div>${listBody}</div>`;
    const fcard = (t,ci)=>`<div class="flow-card${t.isOrphan?' orphan':''}" style="animation-delay:${(ci*0.06).toFixed(2)}s"><div style="display:flex;align-items:center;gap:7px"><span style="width:6px;height:6px;border-radius:50%;background:${t.priColor};flex-shrink:0"></span><span class="mono" style="font-size:10px;color:var(--dim)">${esc(t.id)}</span>${t.isOrphan?'<span class="mono" style="margin-left:auto;font-size:9px;color:var(--accent)">\u26a0</span>':''}</div><div style="font-size:11.5px;margin-top:4px;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${esc(t.title)}</div></div>`;
    const rail = v.flowStages.map((s,i)=>`<div class="flow-node" style="color:${s.color}"><div class="flow-ring"></div><div class="flow-count" style="color:var(--text)">${s.count}</div><div class="flow-nlbl">${esc(s.label)}</div></div>${i<v.flowStages.length-1?`<div class="flow-conn"><span class="flow-pulse" style="animation-delay:${(i*0.6).toFixed(2)}s"></span></div>`:''}`).join('');
    const cols = v.flowStages.map(s=>`<div class="flow-col"><div class="flow-col-h"><span style="width:8px;height:8px;border-radius:50%;background:${s.color}"></span><span style="font-weight:600">${esc(s.label)}</span><span class="mono" style="margin-left:auto;color:var(--muted)">${s.count}</span></div><div class="flow-col-b">${s.items.length?s.items.map((t,ci)=>fcard(t,ci)).join(''):'<div class="flow-empty">\u2014</div>'}</div></div>`).join('');
    const branch = v.flowBranchTotal ? `<div class="flow-branch">${v.flowBranch.map(b=>`<div class="flow-col" style="flex:1"><div class="flow-col-h"><span style="width:8px;height:8px;border-radius:50%;background:${b.color}"></span><span style="font-weight:600">${esc(b.label)}</span><span class="mono" style="margin-left:auto;color:var(--muted)">${b.items.length}</span></div><div class="flow-col-b" style="flex-direction:row;flex-wrap:wrap;gap:6px">${b.items.length?b.items.map((t,ci)=>`<span class="flow-card mono" style="animation-delay:${(ci*0.05).toFixed(2)}s;font-size:10px;padding:4px 8px;color:var(--muted)">${esc(t.id)}</span>`).join(''):'<div class="flow-empty">\u2014</div>'}</div></div>`).join('')}</div>` : '';
    const flow = `<div class="card" style="padding:4px 10px 12px;margin-bottom:14px"><div class="flow-rail">${rail}</div></div><div class="flow-cols">${cols}</div>${branch}`;
    const toggle = `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px"><div class="mono" style="font-size:11px;color:var(--muted)">${v.ticketRows.length} ticket${v.ticketRows.length===1?'':'s'}</div><div class="seg" style="width:auto"><button class="${state.ticketView==='list'?'on':''}" data-action="tview" data-arg="list" style="padding:6px 16px">List</button><button class="${state.ticketView==='flow'?'on':''}" data-action="tview" data-arg="flow" style="padding:6px 16px">Flow</button></div></div>`;
    return `<section>${toggle}${state.ticketView==='flow'?flow:list}</section>`;
  }

  if (t==='links') return `<section style="display:grid;grid-template-columns:1.6fr 1fr;gap:16px">
    <div class="card" style="overflow:hidden"><div class="cap mono">Ticket ↔ memory links</div><div style="max-height:520px;overflow-y:auto">
      ${v.linkTickets.map(t=>`<div class="row" style="padding:13px 16px"><div style="font-weight:600;font-size:12.5px">${esc(t.id)} · ${esc(t.title)}</div><div class="mono" style="font-size:10px;color:var(--muted);margin:3px 0 6px">${esc(t.meta)}</div>${t.related.map(r=>`<div class="mono" style="font-size:10.5px;color:var(--muted);padding:2px 0"><span style="color:${r.color}">↳ ${esc(r.type)}</span> ${esc(r.title)} <span style="color:var(--dim)">· ${esc(r.agent)} · ${esc(r.score)}</span></div>`).join('')}</div>`).join('') || '<div style="padding:20px;color:var(--muted);font-size:12px">No ticket↔memory links found.</div>'}
      <div class="cap mono" style="border-top:1px solid var(--border)">File links</div>
      ${v.fileLinks.map(f=>`<div data-row class="row" style="padding:10px 16px;display:flex;align-items:center;justify-content:space-between;gap:10px"><span class="mono" style="font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(f.path)}</span><div style="display:flex;align-items:center;gap:8px;flex-shrink:0"><button class="hact copybtn mono" data-action="copy" data-arg="${esc(f.path)}" title="Copy path">copy</button><span class="mono" style="font-size:10.5px;color:var(--muted);white-space:nowrap">${esc(f.meta)}</span></div></div>`).join('') || '<div style="padding:16px;color:var(--muted);font-size:12px">No file references.</div>'}
    </div></div>
    <div class="card" style="overflow:hidden"><div class="cap mono">Data health</div>
      ${v.health.map(h=>`<div class="row" style="padding:12px 16px;display:flex;gap:9px;align-items:flex-start"><span style="width:7px;height:7px;border-radius:50%;background:${h.color};margin-top:4px;flex-shrink:0"></span><span style="font-size:12px;color:var(--muted)">${esc(h.msg)}</span></div>`).join('')}
      <div style="padding:16px;border-top:1px solid var(--border)"><div class="cap mono" style="border:0;padding:0 0 9px">Tags</div><div style="display:flex;flex-wrap:wrap;gap:6px">${v.tags.map(tag=>`<span class="mono" style="font-size:10.5px;padding:2px 8px;border:1px solid var(--border);border-radius:12px;color:var(--muted)">${esc(tag.label)} ${tag.count}</span>`).join('') || '<span style="color:var(--muted);font-size:12px">No tags.</span>'}</div></div>
    </div>
  </section>`;

  if (t==='tokens') return `<section>
    <div class="grid4" style="margin-bottom:16px">${v.tokenKpis.map(k=>`<div class="card kpi"><div class="k-lbl mono">${esc(k.label)}</div><div class="k-val" style="font-size:26px">${esc(k.val)}</div><div class="k-sub mono">${esc(k.sub)}</div></div>`).join('')}</div>
    <div class="card" style="padding:18px 20px"><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin-bottom:14px">Where the token budget goes</div>
      ${v.isRich ? `<div style="display:flex;align-items:center;gap:28px">${donutSVG(v.tokenSegs, v.tokenTotal, 'TOKENS', 150)}<div style="flex:1;display:flex;flex-direction:column;gap:10px">${v.tokenSegs.map(s=>`<div style="display:flex;align-items:center;gap:10px"><span style="width:10px;height:10px;border-radius:3px;background:${s.color};flex-shrink:0"></span><span style="flex:1;font-size:12.5px">${esc(s.label)}</span><span class="mono" style="font-size:12px;color:var(--text)">${s.valStr}</span><span class="mono" style="font-size:11px;color:var(--dim);width:40px;text-align:right">${s.pct}</span></div>`).join('')}</div></div>`
      : `<div style="display:flex;flex-direction:column;gap:14px">${v.tokenSegs.map(s=>`<div><div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px"><span style="color:var(--muted)">${esc(s.label)}</span><span class="mono" style="color:var(--text)">${s.valStr} · ${s.pct}</span></div><div style="height:11px;background:var(--track);border-radius:6px;overflow:hidden"><div style="height:100%;border-radius:6px;background:${s.color};width:${s.pct}"></div></div></div>`).join('')}</div>`}
    </div>
  </section>`;

  if (t==='quota') { const q=v.q; return `<section>
    <div class="seg" style="width:fit-content;border-radius:9px;margin-bottom:18px">${[[24,'1 day'],[168,'7 days'],[99999,'Lifetime']].map(([w,l])=>`<button class="mono ${state.win===w?'on':''}" data-action="win" data-arg="${w}" style="padding:7px 16px">${l}</button>`).join('')}</div>
    <div style="display:grid;grid-template-columns:${v.isRich?'1.9fr 1fr':'1fr'};gap:16px;margin-bottom:16px">
      <div class="card" style="border-left:3px solid var(--accent);padding:22px 24px"><div class="mono" style="font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);margin-bottom:8px">Claude time bought back · ${esc(q.winLabel)}</div><div style="font-size:44px;font-weight:700;letter-spacing:-.03em;font-variant-numeric:tabular-nums">${q.mult}<span style="font-size:19px;color:var(--muted);font-weight:500;margin-left:6px">× longer per quota window</span></div><div style="color:var(--muted);font-size:13px;margin-top:10px;max-width:600px;line-height:1.55">Without On Board, ${q.sessions} agent ${q.sessionWord} each spend about <b style="color:var(--text)">${q.noSystem} tokens</b> re-reading history, redoing finished work, and re-explaining context. With On Board that drops to about <b style="color:var(--text)">${q.withSystem}</b>. Claude reaches its quota later, so you wait less for it to reset.</div></div>
      ${v.isRich ? `<div class="card" style="padding:18px;display:flex;align-items:center;justify-content:center"><div style="position:relative;width:150px;height:150px"><svg width="150" height="150" viewBox="0 0 120 120"><circle cx="60" cy="60" r="54" fill="none" stroke="var(--track)" stroke-width="12"/><circle cx="60" cy="60" r="54" fill="none" stroke="var(--accent)" stroke-width="12" stroke-linecap="round" stroke-dasharray="${q.gaugeDash}" transform="rotate(-90 60 60)"/></svg><div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center"><div style="font-size:26px;font-weight:700">${q.mult}×</div><div class="mono" style="font-size:8.5px;color:var(--dim);letter-spacing:.06em">EFFICIENCY</div></div></div></div>`:''}
    </div>
    <div class="grid3" style="margin-bottom:16px">${q.story.map(s=>`<div class="card" style="padding:16px 18px"><div style="font-size:22px;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums">${esc(s.stat)}</div><div style="font-weight:600;font-size:12.5px;margin:5px 0 4px">${esc(s.title)}</div><div style="color:var(--muted);font-size:12px;line-height:1.5">${esc(s.body)}</div></div>`).join('')}</div>
    <div class="card" style="padding:18px 20px;margin-bottom:16px"><div class="mono" style="font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--dim);margin-bottom:14px">Session cost: what Claude loads before doing any work</div>${q.bars.map(b=>`<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:5px"><span style="color:var(--muted)">${esc(b.label)}</span><b style="font-variant-numeric:tabular-nums">${b.valStr} tok</b></div><div style="height:12px;background:var(--track);border-radius:6px;overflow:hidden"><div style="height:100%;border-radius:6px;background:${b.color};width:${b.pct};transition:width .5s ease"></div></div></div>`).join('')}</div>
    <div class="grid4" style="margin-bottom:16px">${q.kpis.map(k=>`<div class="card kpi"><div class="k-lbl mono">${esc(k.label)}</div><div class="k-val" style="font-size:24px">${esc(k.val)}</div><div class="k-sub mono">${esc(k.sub)}</div></div>`).join('')}</div>
    <div style="border-left:2px solid var(--border);padding:12px 16px;color:var(--dim);font-size:11.5px;line-height:1.6">How this is estimated: briefing size is measured from the memory files. Rework and re-explanation are modeled at 20% and 15%. Time assumes about 45 minutes of active use per session at the quota cap. Minute figures are estimates; the ${q.mult}× ratio comes from actual file sizes.</div>
  </section>`; }
  return '';
}
function memRowCompact(m) {
  return `<div data-row class="row" style="position:relative;padding:12px 16px;display:grid;grid-template-columns:70px 1fr;gap:12px">
    <button class="hact copybtn mono" data-action="copy" data-arg="${esc(m.id)}" title="Copy id" style="position:absolute;top:10px;right:12px">copy id</button>
    <div class="mono" style="font-size:10.5px;color:var(--dim);padding-top:2px">${esc(m.ago)}</div>
    <div style="min-width:0"><div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap"><span class="pill mono" style="color:${m.color};background:${soft(m.color)}">${esc(m.type)}</span><span class="mono" style="font-size:10.5px;color:var(--muted)">${esc(m.agent)}</span></div><div style="font-weight:500;margin-top:4px;font-size:12.5px">${m.pin?'★ ':''}${esc(m.title)}</div><div style="color:var(--muted);font-size:12px;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.content)}</div></div></div>`;
}
const emptyBox = (title, sub, dashed) => `<div class="empty" ${dashed?'style="border:1px dashed var(--border);border-radius:12px"':''}><div class="e-t">${esc(title)}</div><div class="e-s">${esc(sub)}</div></div>`;

/* ---------- palette ---------- */
function palResults() {
  const d = state.data; const pq = state.palQuery.trim().toLowerCase(); const all = [];
  const goTab = tab => () => { state.tab=tab; closePalette(); updateMain(); syncNavActive(); };
  NAV.forEach(([tab,label]) => all.push({ kind:'Go to', label, sub:'tab', icon:'▸', color:'var(--muted)', go:goTab(tab) }));
  all.push({ kind:'Toggle', label:state.theme==='dark'?'Switch to light theme':'Switch to dark theme', sub:'appearance', icon:'◐', color:'var(--muted)', go:()=>{ setTheme(state.theme==='dark'?'light':'dark'); closePalette(); } });
  all.push({ kind:'Toggle', label:state.chartMode==='rich'?'Use simple bar charts':'Use rich charts', sub:'appearance', icon:'▤', color:'var(--muted)', go:()=>{ setChart(state.chartMode==='rich'?'bars':'rich'); closePalette(); } });
  if (d) {
    d.memories.forEach(m => all.push({ kind:'Memory', label:m.title||'(untitled)', sub:'#'+m.id+' · '+m.memory_type+' · '+m.agent_name, icon:'◆', color:typeColor(m.memory_type), go:goTab('timeline') }));
    d.tickets.forEach(t => all.push({ kind:'Ticket', label:t.id+' · '+t.title, sub:(t.status||'').replace('_',' ')+' · '+t.priority, icon:'●', color:PRI[t.priority]||'var(--muted)', go:goTab('tickets') }));
    Object.values(d.agents).forEach(a => all.push({ kind:'Agent', label:a.agent_name, sub:platLabel(a)+' · '+a.status, icon:'◉', color:AST[a.status]||'var(--muted)', go:goTab('agents') }));
  }
  return (pq ? all.filter(r=>(r.label+' '+r.sub+' '+r.kind).toLowerCase().includes(pq)) : all).slice(0,9);
}
function renderPalette() {
  const res = palResults(); state.palResults = res;
  if (state.palIdx >= res.length) state.palIdx = Math.max(0, res.length-1);
  document.getElementById('pal-list').innerHTML = res.length ? res.map((r,i)=>`<div class="pal-row${i===state.palIdx?' on':''}" data-action="palgo" data-arg="${i}"><span style="width:18px;flex-shrink:0;text-align:center;color:${r.color}">${r.icon}</span><div style="min-width:0;flex:1"><div style="font-size:12.5px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.label)}</div><div class="mono" style="font-size:10px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(r.sub)}</div></div><span class="mono" style="font-size:9px;flex-shrink:0;color:var(--dim);text-transform:uppercase;letter-spacing:.05em">${esc(r.kind)}</span></div>`).join('') : '<div style="padding:24px;text-align:center;color:var(--muted);font-size:12px">No matches</div>';
}
function openPalette() { state.palOpen=true; state.palQuery=''; state.palIdx=0; const p=document.getElementById('palette'); p.classList.add('open'); const q=document.getElementById('palq'); q.value=''; renderPalette(); setTimeout(()=>q.focus(),20); }
function closePalette() { state.palOpen=false; document.getElementById('palette').classList.remove('open'); }

/* ---------- render orchestration ---------- */
function setTheme(t){ state.theme=t; LS.set('theme',t); document.documentElement.setAttribute('data-theme',t); syncSegs(); renderPalette(); }
function setChart(c){ state.chartMode=c; LS.set('chart',c); syncSegs(); updateMain(); }
function setDensity(dd){ state.density=dd; LS.set('density',dd); document.documentElement.setAttribute('data-density',dd); syncSegs(); }
function syncSegs(){ [['seg-theme',state.theme],['seg-chart',state.chartMode],['seg-dens',state.density]].forEach(([id,val])=>{ document.querySelectorAll('#'+id+' button').forEach(b=>b.classList.toggle('on', b.dataset.arg===val)); }); }
function syncNavActive(){ document.querySelectorAll('#nav .navbtn').forEach(b=>b.classList.toggle('on', b.dataset.arg===state.tab)); }

function updateHeader() {
  const d = state.data; if (!d) return;
  document.getElementById('proj-name').textContent = d.project.name;
  document.getElementById('proj-sub').innerHTML = esc(d.project.description) + (d.project.tech?` <span style="color:var(--dim)">· ${esc(d.project.tech)}</span>`:'');
  const v = window.__v || derive();
  document.getElementById('health').innerHTML = `<span class="dot" style="width:7px;height:7px;background:${v.hcolor}"></span><span style="color:${v.hcolor}">${v.hlabel}</span><span style="color:var(--dim)">·</span><span style="color:var(--muted)">${v.hscore}</span>`;
  document.getElementById('foot-meta').innerHTML = `<div>${esc(d.project.name)}</div><div>polling every ${Math.round(POLL_MS/1000)}s</div><div>updated ${clockStr()}</div>`;
  buildNav(v);
}
function updateMain() {
  if (state.loading) { document.getElementById('main-content').innerHTML = `<div class="empty" style="padding-top:80px"><div class="spinner"></div><div class="e-t">Reading memory files…</div><div class="e-s">Loading .agent-mem</div></div>`; return; }
  if (state.error) { document.getElementById('main-content').innerHTML = errorHTML(); return; }
  const v = derive(); window.__v = v;
  document.getElementById('main-content').innerHTML = tabHTML(v);
  syncNavActive(); updateHeader();
}
function errorHTML() {
  if (state.error==='nodata') return `<div class="empty" style="padding-top:70px"><div class="e-t">No .agent-mem data found</div><div class="e-s" style="max-width:460px;margin:6px auto 0">Place this dashboard next to an <b>.agent-mem</b> folder, or open it with <span class="mono">?data=PATH</span> pointing at one. Tried: ${BASE_CANDIDATES.map(esc).join(', ')}.</div></div>`;
  return `<div class="empty" style="padding-top:70px"><div class="e-t">Couldn't read the memory files</div><div class="e-s" style="max-width:460px;margin:6px auto 0">If you opened this file directly, the browser blocks local reads. Serve the folder over HTTP instead — e.g. <span class="mono">python3 -m http.server</span> — then reload.</div></div>`;
}
function render() {
  document.documentElement.setAttribute('data-theme', state.theme);
  document.documentElement.setAttribute('data-density', state.density);
  syncSegs();
  buildNav(window.__v);
  document.getElementById('clock').textContent = clockStr();
  if (state.data) updateHeader();
  updateMain();
}

/* ---------- events ---------- */
document.addEventListener('click', e => {
  const el = e.target.closest('[data-action]'); if (!el) return;
  const a = el.dataset.action, arg = el.dataset.arg;
  if (a==='tab') { state.tab=arg; state.query=''; document.getElementById('filter').value=''; updateMain(); syncNavActive(); }
  else if (a==='theme') setTheme(arg);
  else if (a==='chart') setChart(arg);
  else if (a==='dens') setDensity(arg);
  else if (a==='win') { state.win=+arg; updateMain(); }
  else if (a==='tl') { state.tlGroup=arg; updateMain(); }
  else if (a==='tview') { state.ticketView=arg; updateMain(); }
  else if (a==='palopen') openPalette();
  else if (a==='palgo') { const r=state.palResults[+arg]; if(r) r.go(); }
  else if (a==='palstop') e.stopPropagation();
  else if (a==='copy') { navigator.clipboard && navigator.clipboard.writeText(arg); const o=el.textContent; el.textContent='copied'; setTimeout(()=>{el.textContent=o;},900); }
});
document.getElementById('palette').addEventListener('click', e => { if (e.target.id==='palette') closePalette(); });
document.addEventListener('input', e => {
  if (e.target.id==='filter') { state.query=e.target.value; updateMain(); }
  else if (e.target.id==='palq') { state.palQuery=e.target.value; state.palIdx=0; renderPalette(); }
});
document.addEventListener('keydown', e => {
  const k = (e.key||'').toLowerCase();
  if ((e.metaKey||e.ctrlKey) && k==='k') { e.preventDefault(); state.palOpen?closePalette():openPalette(); return; }
  if (!state.palOpen) return;
  if (e.key==='Escape') closePalette();
  else if (e.key==='ArrowDown') { e.preventDefault(); state.palIdx=Math.min(state.palResults.length-1, state.palIdx+1); renderPalette(); }
  else if (e.key==='ArrowUp') { e.preventDefault(); state.palIdx=Math.max(0, state.palIdx-1); renderPalette(); }
  else if (e.key==='Enter') { e.preventDefault(); const r=state.palResults[state.palIdx]; if(r) r.go(); }
});
setInterval(()=>{ const c=document.getElementById('clock'); if(c) c.textContent=clockStr(); }, 1000);

/* ---------- go ---------- */
render();
boot();
</script>
</body>
</html>
"""

# -- Substitute placeholders -------------------------------------------------
html = (HTML_TEMPLATE
    .replace("__PROJECT_NAME_JS__", json.dumps(PROJECT_ROOT.name)[1:-1])
    .replace("__PROJECT_NAME__", html_escape(PROJECT_ROOT.name, quote=True))
    .replace("__POLL_MS__", str(POLL_MS))
)

OUT_PATH.write_text(html, encoding="utf-8")
print(f"OK  Live dashboard generated: {OUT_PATH}")
print(f"    Polls every {POLL_MS}ms - reads .agent-mem/*.json directly")
print()

# -- Optional: serve + open --------------------------------------------------
if "--serve" in flags or "--open" in flags:
    import subprocess, webbrowser, time, threading

    url = f"http://localhost:{PORT}/dashboard-live.html"
    print(f"Serving {MEMORY_DIR} on port {PORT}")
    print(f"    URL: {url}")
    print(f"    Press Ctrl+C to stop.")
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
        print("\nServer stopped.")
else:
    print(f"    To view live, run ONE of:")
    print(f"      python3 {Path(__file__).name} {PROJECT_ROOT} --open        <- auto-serve + open browser")
    print(f"      python3 {Path(__file__).name} {PROJECT_ROOT} --serve       <- serve only")
    print(f"    Or manually:")
    print(f"      cd {MEMORY_DIR} && python3 -m http.server {PORT}")
    print(f"      open http://localhost:{PORT}/dashboard-live.html")
