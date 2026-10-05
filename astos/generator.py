"""Gerador do HTML 3D Sci-Fi 100% offline.

Injeta o grafo + three.min.js + OrbitControls.js (vendorizados) em um
arquivo HTML único. Nenhum fetch HTTP/CDN no output final.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .parser import SUPPORTED_LABEL

VENDOR_DIR = Path(__file__).parent / "vendor"


def _read_vendor() -> tuple[str, str]:
    three = (VENDOR_DIR / "three.min.js").read_text(encoding="utf-8", errors="ignore")
    orbit = (VENDOR_DIR / "OrbitControls.js").read_text(encoding="utf-8", errors="ignore")
    # protege o bloco <script> inline contra fechamento prematuro
    three = three.replace("</script", "<\\/script")
    orbit = orbit.replace("</script", "<\\/script")
    return three, orbit


def render_html(graph: dict) -> str:
    three_js, orbit_js = _read_vendor()
    nodes_json = json.dumps(graph.get("nodes", []), ensure_ascii=False)
    links_json = json.dumps(graph.get("links", []), ensure_ascii=False)
    mods_json = json.dumps(graph.get("mods", {}), ensure_ascii=False)
    exts_html = html.escape(SUPPORTED_LABEL)
    meta = graph.get("meta", {})
    n_count = len(graph.get("nodes", []))
    e_count = len(graph.get("links", []))
    root_name = html.escape(Path(str(meta.get("root", "."))).name or "repo")

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ASTOS // {root_name} — Observer 3D</title>
<style>
@font-face {{ font-family: 'SysMono'; src: local('JetBrains Mono'), local('Consolas'), local('monospace'); }}
:root {{
  --bg: #04060e; --panel: rgba(8, 12, 24, 0.90); --line: #1e293b;
  --txt: #dbeafe; --dim: #64748b; --cyan: #22d3ee; --magenta: #f472b6; --amber: #fbbf24;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--txt);
  font-family: 'SysMono', 'JetBrains Mono', Consolas, monospace; overflow: hidden; }}
#bg-grid {{ position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background-image: radial-gradient(circle at 50% 38%, rgba(34,211,238,0.09), transparent 62%),
    radial-gradient(circle at 80% 90%, rgba(244,114,182,0.05), transparent 55%),
    linear-gradient(rgba(34,211,238,0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34,211,238,0.05) 1px, transparent 1px);
  background-size: auto, auto, 44px 44px, 44px 44px; }}
#scanlines {{ position: fixed; inset: 0; z-index: 60; pointer-events: none; opacity: .55;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,0.02) 0 1px, transparent 1px 3px); }}
#vignette {{ position: fixed; inset: 0; z-index: 59; pointer-events: none;
  box-shadow: inset 0 0 190px rgba(0,0,0,0.88); }}
#stage {{ position: fixed; inset: 0; z-index: 1; }}
#net3d {{ position: absolute; inset: 0; }}
#topbar {{ position: fixed; top: 0; left: 0; right: 0; z-index: 100; display: flex; align-items: center;
  gap: 12px; padding: 10px 16px; flex-wrap: wrap;
  background: linear-gradient(180deg, rgba(4,6,14,0.96), rgba(4,6,14,0.55) 80%, transparent);
  border-bottom: 1px solid rgba(34,211,238,0.28); }}
#topbar .logo {{ color: var(--cyan); font-weight: bold; letter-spacing: 2px; font-size: 15px;
  text-shadow: 0 0 14px rgba(34,211,238,0.85); }}
#topbar .sub {{ color: var(--dim); font-size: 11px; letter-spacing: 1px; }}
.hbtn {{ cursor: pointer; border: 1px solid var(--cyan); background: rgba(15,23,42,0.85); color: var(--cyan);
  font-family: inherit; font-size: 11px; letter-spacing: 1px; padding: 7px 12px; border-radius: 4px; }}
.hbtn:hover {{ background: rgba(34,211,238,0.16); }}
.hbtn.on {{ background: var(--cyan); color: #03131a; font-weight: bold; box-shadow: 0 0 14px rgba(34,211,238,0.7); }}
.hbtn.mag {{ border-color: var(--magenta); color: var(--magenta); }}
.hbtn.mag.on {{ background: var(--magenta); color: #1a0313; box-shadow: 0 0 14px rgba(244,114,182,0.7); }}
#stats {{ margin-left: auto; font-size: 11px; color: var(--dim); text-align: right; line-height: 1.5; }}
#stats b {{ color: var(--cyan); }}
#panel-toggle {{ position: fixed; top: 66px; right: 12px; z-index: 101; cursor: pointer;
  border: 1px solid var(--cyan); background: var(--panel); color: var(--cyan);
  font-family: inherit; font-size: 12px; padding: 6px 10px; border-radius: 4px; }}
#panel {{ position: fixed; top: 102px; right: 12px; bottom: 12px; width: 302px; z-index: 100;
  background: var(--panel); border: 1px solid rgba(34,211,238,0.35); border-radius: 8px;
  padding: 14px; overflow-y: auto; backdrop-filter: blur(4px);
  box-shadow: 0 0 24px rgba(34,211,238,0.12); }}
#panel.hidden {{ display: none; }}
#panel h3 {{ margin: 14px 0 8px; font-size: 11px; letter-spacing: 2px; color: var(--cyan);
  border-bottom: 1px solid var(--line); padding-bottom: 5px; }}
#panel h3:first-child {{ margin-top: 0; }}
#panel label {{ font-size: 11px; color: var(--dim); display: block; margin: 6px 0 2px; }}
#panel input[type="range"] {{ width: 100%; accent-color: var(--cyan); }}
#panel input[type="text"] {{ width: 100%; background: #0b1120; border: 1px solid var(--line);
  color: var(--txt); font-family: inherit; font-size: 12px; padding: 7px 9px; border-radius: 4px; }}
.row {{ display: flex; gap: 6px; align-items: center; }}
.btn {{ cursor: pointer; flex: 1; border: 1px solid var(--cyan); background: transparent; color: var(--cyan);
  font-family: inherit; font-size: 12px; letter-spacing: 1px; padding: 8px 6px; border-radius: 4px; }}
.btn:hover {{ background: rgba(34,211,238,0.15); }}
.btn.on {{ background: var(--cyan); color: #03131a; font-weight: bold; }}
.btn.warn {{ border-color: var(--amber); color: var(--amber); }}
.mod {{ display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; cursor: pointer; }}
.mod .dot {{ width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 8px currentColor; }}
.mod .n {{ margin-left: auto; color: var(--dim); font-size: 11px; }}
.mod.off {{ opacity: 0.35; }}
#search-results {{ max-height: 150px; overflow-y: auto; margin-top: 6px; }}
.sr {{ font-size: 12px; padding: 5px 7px; cursor: pointer; border-radius: 3px; }}
.sr:hover {{ background: rgba(34,211,238,0.15); }}
.sr small {{ color: var(--dim); }}
#info {{ position: fixed; left: 12px; bottom: 12px; z-index: 100; width: 400px; max-width: calc(100vw - 24px);
  max-height: 46vh; overflow-y: auto;
  background: rgba(8,12,24,0.94); border: 1px solid rgba(244,114,182,0.55); border-radius: 8px;
  padding: 12px 14px; font-size: 12px; display: none;
  box-shadow: 0 0 26px rgba(244,114,182,0.18), 0 0 26px rgba(34,211,238,0.10); }}
#info.show {{ display: block; }}
#info .t {{ color: var(--magenta); font-weight: bold; font-size: 13px; margin-bottom: 4px;
  text-shadow: 0 0 10px rgba(244,114,182,0.7); word-break: break-word; }}
#info .r {{ color: var(--dim); line-height: 1.7; word-break: break-word; }}
#info .r b {{ color: var(--txt); font-weight: normal; }}
#info .imp {{ color: var(--cyan); }}
#info .x {{ float: right; cursor: pointer; color: var(--dim); border: 1px solid var(--line);
  border-radius: 4px; padding: 0 7px; }}
#info .x:hover {{ color: var(--magenta); border-color: var(--magenta); }}
#legend {{ position: fixed; left: 12px; top: 66px; z-index: 100; background: var(--panel);
  border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; font-size: 11px; max-width: 240px;
  max-height: 40vh; overflow-y: auto; }}
#legend .mod {{ cursor: default; }}
#legend b.tt {{ color: var(--cyan); font-size: 10px; letter-spacing: 2px; }}
#empty {{ position: fixed; inset: 0; z-index: 90; display: none; align-items: center; justify-content: center;
  text-align: center; pointer-events: none; }}
#empty.show {{ display: flex; }}
#empty .card {{ background: var(--panel); border: 1px solid rgba(251,191,36,0.5); border-radius: 10px;
  padding: 26px 34px; max-width: 560px; box-shadow: 0 0 30px rgba(251,191,36,0.15); pointer-events: auto; }}
#empty .big2 {{ color: var(--amber); letter-spacing: 3px; font-size: 15px; margin-bottom: 10px; }}
#empty .small2 {{ color: var(--dim); font-size: 12px; line-height: 1.8; }}
#boot {{ position: fixed; inset: 0; z-index: 200; background: var(--bg); display: flex;
  align-items: center; justify-content: center; flex-direction: column; gap: 10px;
  transition: opacity 0.5s; }}
#boot.gone {{ opacity: 0; pointer-events: none; }}
#boot .big {{ color: var(--cyan); font-size: 24px; letter-spacing: 5px; text-shadow: 0 0 22px rgba(34,211,238,0.9); }}
#boot .small {{ color: var(--dim); font-size: 12px; letter-spacing: 2px; }}
#boot .bar {{ width: 260px; height: 4px; background: #0b1120; border: 1px solid var(--line); }}
#boot .bar i {{ display: block; height: 100%; width: 40%; background: var(--cyan);
  box-shadow: 0 0 12px var(--cyan); animation: scan 1s linear infinite; }}
@keyframes scan {{ from {{ margin-left: 0; }} to {{ margin-left: 60%; }} }}
.val {{ color: var(--cyan); font-size: 11px; }}
#hint {{ position: fixed; bottom: 12px; left: 50%; transform: translateX(-50%); z-index: 99;
  font-size: 11px; color: var(--dim); letter-spacing: 1px; background: rgba(8,12,24,0.7);
  border: 1px solid var(--line); padding: 5px 12px; border-radius: 20px; }}
</style>
</head>
<body>
<div id="bg-grid"></div>
<div id="stage"><div id="net3d"></div></div>
<div id="scanlines"></div>
<div id="vignette"></div>

<div id="topbar">
  <span class="logo">ASTOS // OBSERVER</span>
  <span class="sub">3D IMERSIVO · {n_count} NÓS · {e_count} ARESTAS · 100% OFFLINE</span>
  <a class="hbtn" id="btn-city" href="city.html" title="Palácio do código (metáfora Makepad: blocos por tamanho)" style="text-decoration:none">[ 🏛 PALÁCIO ]</a>
  <button class="hbtn on" id="btn-rgb" title="Fita RGB animada percorrendo as arestas">[ FLUXO RGB ]</button>
  <button class="hbtn on" id="btn-orbit" title="Rotação orbital contínua">[ ÓRBITA ]</button>
  <button class="hbtn" id="btn-freeze" title="Congela tudo: física + órbita (atalho: espaço)">[ ❄ CONGELAR ]</button>
  <button class="hbtn" id="btn-full" title="Tela cheia (ESC para sair)">[ ⛶ FULLSCREEN ]</button>
  <div id="stats">nós <b id="st-nodes">—</b> · arestas <b id="st-edges">—</b><br><span id="st-sel">nenhum nó selecionado</span></div>
</div>

<button id="panel-toggle">[ PAINEL ]</button>
<div id="panel">
  <h3>// NAVEGAÇÃO 3D</h3>
  <div class="row">
    <button class="btn on" id="btn-phys">FÍSICA ON</button>
    <button class="btn warn" id="btn-cam">RECENTRAR</button>
  </div>
  <label>velocidade orbital: <span class="val" id="orb-val">1.0</span>x</label>
  <input type="range" id="orb" min="0" max="50" value="10">
  <label>repulsão / espalhamento: <span class="val" id="rep-val">1.0</span>x</label>
  <input type="range" id="rep" min="0" max="30" value="10">
  <div class="row" style="margin-top:6px">
    <button class="btn on" id="btn-roty">GIRO Y</button>
    <button class="btn" id="btn-rotx">GIRO X</button>
  </div>

  <h3>// FLUXO RGB (fita de luz)</h3>
  <div class="row">
    <button class="btn on" id="btn-rgb2">RGB GLOBAL</button>
    <button class="btn on" id="btn-selrgb">RGB SELEÇÃO</button>
  </div>
  <label>densidade do fluxo: <span class="val" id="flux-val">1.0</span>x</label>
  <input type="range" id="flux" min="1" max="30" value="12">

  <h3>// FILTROS</h3>
  <label>busca de nó</label>
  <input type="text" id="search" placeholder="ex: parser, generator, cli..." autocomplete="off">
  <div id="search-results"></div>
  <label>grau mínimo: <span class="val" id="deg-val">0</span></label>
  <input type="range" id="deg" min="0" max="20" value="0">
  <div id="mods"></div>
  <div class="row" style="margin-top:6px">
    <button class="btn" id="btn-all">TODOS</button>
    <button class="btn warn" id="btn-none">NENHUM</button>
  </div>
</div>

<div id="legend"></div>
<div id="empty"><div class="card"><div class="big2">⚠ NENHUM CÓDIGO SUPORTADO ENCONTRADO</div><div class="small2" id="empty-msg"></div></div></div>
<div id="info"><span class="x" id="info-x">[x]</span><div class="t" id="info-t"></div><div class="r" id="info-r"></div></div>
<div id="hint">arraste: orbitar · scroll: zoom · botão direito: pan · WASD/setas: mover · Q/E: aprox./afastar · clique num nó: HUD · espaço: congelar · ESC: sair do fullscreen</div>

<div id="boot">
  <div class="big">ASTOS</div>
  <div class="small" id="boot-msg">INICIALIZANDO OBSERVER 3D // 100% OFFLINE...</div>
  <div class="bar"><i></i></div>
</div>

<script>{three_js}</script>
<script>{orbit_js}</script>
<script>
"use strict";
const NODES = {nodes_json};
const LINKS = {links_json};
const MOD_COLORS = {mods_json};
const $ = (id) => document.getElementById(id);

/* ================= estado ================= */
if (!NODES.length) {{
  $('empty-msg').innerHTML = 'Nenhum arquivo <b style="color:var(--txt)">{exts_html}</b> ' +
    'foi encontrado neste repositório.<br>Rode <b style="color:var(--cyan)">astos</b> dentro da pasta do código-fonte.';
  $('empty').classList.add('show');
  $('st-nodes').textContent = '0'; $('st-edges').textContent = '0';
}}
const state = {{
  phys: true, rotY: true, rotX: false, orbSpeed: 1.0, repulsion: 1.0,
  rgbGlobal: true, rgbSelect: true, flux: 1.0, frozen: false,
  minDeg: 0, hiddenMods: new Set(), selected: null,
}};
const byId = {{}}; NODES.forEach(n => byId[n.id] = n);
const adj = {{}};
LINKS.forEach(([s, t]) => {{ (adj[s] = adj[s] || []).push(t); (adj[t] = adj[t] || []).push(s); }});
const inSet = (n) => !state.hiddenMods.has(n.mod) && n.deg >= state.minDeg;
function visibleNodes() {{ return NODES.filter(inSet); }}

/* ================= HUD estático ================= */
$('st-nodes').textContent = NODES.length;
$('st-edges').textContent = LINKS.length;
$('legend').innerHTML = '<b class="tt">// MÓDULOS</b>' +
  Object.keys(MOD_COLORS).map(m => {{
    const c = NODES.filter(n => n.mod === m).length;
    return c ? `<div class="mod"><span class="dot" style="background:${{MOD_COLORS[m]}};color:${{MOD_COLORS[m]}}"></span>${{m}}<span class="n">${{c}}</span></div>` : '';
  }}).join('');
$('mods').innerHTML = Object.keys(MOD_COLORS).map(m => {{
  const c = NODES.filter(n => n.mod === m).length;
  return c ? `<div class="mod" data-mod="${{m}}"><span class="dot" style="background:${{MOD_COLORS[m]}};color:${{MOD_COLORS[m]}}"></span>${{m}}<span class="n">${{c}}</span></div>` : '';
}}).join('');
document.querySelectorAll('#mods .mod').forEach(el => {{
  el.onclick = () => {{
    const m = el.dataset.mod;
    if (state.hiddenMods.has(m)) {{ state.hiddenMods.delete(m); el.classList.remove('off'); }}
    else {{ state.hiddenMods.add(m); el.classList.add('off'); }}
    rebuildVisibility();
  }};
}});

/* ================= three.js ================= */
const container = $('net3d');
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x04060e, 0.0016);
const camera = new THREE.PerspectiveCamera(60, innerWidth / innerHeight, 0.1, 8000);
camera.position.set(0, 120, 320);
const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
container.appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.06;
controls.autoRotate = true; controls.autoRotateSpeed = 1.0;
scene.add(new THREE.AmbientLight(0x8899bb, 0.7));
const key = new THREE.PointLight(0x22d3ee, 1.2, 0); key.position.set(200, 300, 200); scene.add(key);
const rim = new THREE.PointLight(0xf472b6, 0.9, 0); rim.position.set(-220, -140, -180); scene.add(rim);

/* fundo estelar */
(function stars() {{
  const N = 1400, pos = new Float32Array(N * 3), col = new Float32Array(N * 3);
  const c = new THREE.Color();
  for (let i = 0; i < N; i++) {{
    const r = 900 + Math.random() * 1600, th = Math.random() * Math.PI * 2, ph = Math.acos(2 * Math.random() - 1);
    pos[i*3] = r * Math.sin(ph) * Math.cos(th); pos[i*3+1] = r * Math.cos(ph); pos[i*3+2] = r * Math.sin(ph) * Math.sin(th);
    c.set(Math.random() < 0.12 ? 0xf472b6 : (Math.random() < 0.3 ? 0x22d3ee : 0x8ea2c8)).multiplyScalar(0.35 + Math.random() * 0.5);
    col[i*3] = c.r; col[i*3+1] = c.g; col[i*3+2] = c.b;
  }}
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({{ size: 2.4, vertexColors: true, transparent: true, opacity: 0.9, depthWrite: false }})));
}})();

/* textura de brilho */
function glowTexture() {{
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(32,32,0,32,32,32);
  g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(0.35, 'rgba(255,255,255,0.45)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.fillRect(0,0,64,64);
  return new THREE.CanvasTexture(c);
}}
const GLOW = glowTexture();

/* nós */
const R = 160; // raio inicial da esfera
const P = {{}}; // id -> {{x,y,z,vx,vy,vz,mesh,glow,data,vis}}
const sphereGeo = new THREE.SphereGeometry(1, 20, 20);
NODES.forEach((n, i) => {{
  const th = Math.acos(1 - 2 * (i + 0.5) / NODES.length), ph = i * 2.399963;
  const rad = R * (0.55 + Math.random() * 0.7);
  const s = 2.2 + Math.min(n.deg, 30) * 0.45;
  const mat = new THREE.MeshBasicMaterial({{ color: new THREE.Color(n.color), transparent: true, opacity: 1 }});
  const mesh = new THREE.Mesh(sphereGeo, mat);
  mesh.scale.setScalar(s);
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({{
    map: GLOW, color: new THREE.Color(n.color), transparent: true, opacity: 0.55,
    blending: THREE.AdditiveBlending, depthWrite: false }}));
  glow.scale.setScalar(s * 5.2);
  mesh.add(glow);
  mesh.position.set(rad*Math.sin(th)*Math.cos(ph), rad*Math.cos(th)*0.8, rad*Math.sin(th)*Math.sin(ph));
  mesh.userData.id = n.id;
  scene.add(mesh);
  P[n.id] = {{ x: mesh.position.x, y: mesh.position.y, z: mesh.position.z, vx: 0, vy: 0, vz: 0, mesh, glow, data: n, vis: true }};
}});

/* arestas — TEIA DUPLA (base fosca + feixe luminoso) p/ visibilidade de longe */
const E = LINKS.map(([s, t]) => ({{ s, t }}));
const edgePos = new Float32Array(E.length * 6);
const edgeCol = new Float32Array(E.length * 6);
const edgeGeo = new THREE.BufferGeometry();
edgeGeo.setAttribute('position', new THREE.BufferAttribute(edgePos, 3));
edgeGeo.setAttribute('color', new THREE.BufferAttribute(edgeCol, 3));
const baseLines = new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({{
  vertexColors: true, transparent: true, opacity: 0.5,
  blending: THREE.AdditiveBlending, depthWrite: false }}));
scene.add(baseLines);
// feixe: mesma geometria, material mais quente/brilhante por cima
const beamLines = new THREE.LineSegments(edgeGeo, new THREE.LineBasicMaterial({{
  vertexColors: true, transparent: true, opacity: 0.85,
  blending: THREE.AdditiveBlending, depthWrite: false }}));
beamLines.scale.setScalar(1.001);
scene.add(beamLines);
const _cb = new THREE.Color();
function paintEdges() {{
  for (let i = 0; i < E.length; i++) {{
    const a = P[E[i].s], b = P[E[i].t];
    const on = a && b && a.vis && b.vis;
    const sel = state.selected && (E[i].s === state.selected || E[i].t === state.selected);
    if (!on) {{ for (let k = 0; k < 6; k++) edgeCol[i*6+k] = 0; continue; }}
    if (sel) _cb.set(state.rgbSelect || state.rgbGlobal ? 0xffffff : 0xfbbf24);
    else _cb.set(0x38e0f8).multiplyScalar(0.75);
    if (!sel) _cb.lerp(new THREE.Color(0xf472b6), 0.25);
    edgeCol[i*6]=_cb.r; edgeCol[i*6+1]=_cb.g; edgeCol[i*6+2]=_cb.b;
    edgeCol[i*6+3]=_cb.r; edgeCol[i*6+4]=_cb.g; edgeCol[i*6+5]=_cb.b;
  }}
  edgeGeo.attributes.color.needsUpdate = true;
  const visE = E.filter(e => P[e.s].vis && P[e.t].vis).length;
  $('st-edges').textContent = visE + ' / ' + E.length;
}}

/* ===== FITA RGB: fótons animados percorrendo as arestas ===== */
const MAXP = Math.min(3200, Math.max(600, E.length * 2));
const pPos = new Float32Array(MAXP * 3);
const pCol = new Float32Array(MAXP * 3);
const pGeo = new THREE.BufferGeometry();
pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
pGeo.setAttribute('color', new THREE.BufferAttribute(pCol, 3));
const photons = new THREE.Points(pGeo, new THREE.PointsMaterial({{
  size: 3.4, vertexColors: true, transparent: true, opacity: 0.95,
  blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true }}));
scene.add(photons);
const runners = [];
for (let i = 0; i < MAXP; i++) runners.push({{ e: (Math.random() * E.length) | 0, t: Math.random(), sp: 0.004 + Math.random() * 0.014 }});
const _pa = new THREE.Vector3(), _pb = new THREE.Vector3(), _hc = new THREE.Color();
function edgeAllowed(e) {{
  const a = P[e.s], b = P[e.t];
  if (!a || !b || !a.vis || !b.vis) return false;
  const sel = (e.s === state.selected || e.t === state.selected);
  if (state.selected && state.rgbSelect && !state.rgbGlobal) return sel;
  if (!state.rgbGlobal && !(state.selected && sel && state.rgbSelect)) return false;
  if (state.selected && sel) return true; // seleção sempre tem fita
  return state.rgbGlobal;
}}
let hueT = 0;
function tickPhotons() {{
  if (!state.frozen) hueT = (hueT + 0.0035 * state.flux) % 1;
  let w = 0;
  const target = Math.floor(MAXP * Math.min(1, 0.35 + state.flux / 2.2));
  for (let i = 0; i < runners.length && w < target; i++) {{
    const r = runners[i];
    let e = E[r.e];
    let guard = 0;
    while (e && !edgeAllowed(e) && guard++ < 6) {{ r.e = (Math.random() * E.length) | 0; e = E[r.e]; }}
    if (!e || !edgeAllowed(e)) continue;
    if (!state.frozen) {{
      r.t += r.sp * state.flux;
      if (r.t > 1) {{ r.t = 0; r.e = (Math.random() * E.length) | 0; continue; }}
    }}
    const a = P[e.s], b = P[e.t];
    _pa.set(a.x, a.y, a.z); _pb.set(b.x, b.y, b.z);
    const sel = (e.s === state.selected || e.t === state.selected);
    const off = sel ? 0 : ((r.e * 0.618) % 1);
    _hc.setHSL((hueT + r.t * 0.25 + off) % 1, 1.0, sel ? 0.65 : 0.55);
    pPos[w*3] = _pa.x + (_pb.x - _pa.x) * r.t;
    pPos[w*3+1] = _pa.y + (_pb.y - _pa.y) * r.t;
    pPos[w*3+2] = _pa.z + (_pb.z - _pa.z) * r.t;
    pCol[w*3] = _hc.r; pCol[w*3+1] = _hc.g; pCol[w*3+2] = _hc.b;
    w++;
  }}
  pGeo.setDrawRange(0, w);
  pGeo.attributes.position.needsUpdate = true;
  pGeo.attributes.color.needsUpdate = true;
}}

/* labels dos hubs */
const labelGroup = new THREE.Group(); scene.add(labelGroup);
function makeLabel(text, color) {{
  const c = document.createElement('canvas'); const x = c.getContext('2d');
  x.font = 'bold 26px monospace'; const w = Math.ceil(x.measureText(text).width) + 26;
  c.width = w; c.height = 40;
  const g = x.createLinearGradient(0,0,w,0); g.addColorStop(0,'rgba(4,8,18,0.85)'); g.addColorStop(1,'rgba(4,8,18,0.55)');
  x.fillStyle = g; x.fillRect(0,0,w,40);
  x.strokeStyle = color; x.lineWidth = 2; x.strokeRect(1,1,w-2,38);
  x.font = 'bold 26px monospace'; x.fillStyle = '#eaf6ff'; x.fillText(text, 13, 28);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({{ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }}));
  sp.scale.set(w * 0.28, 40 * 0.28, 1);
  return sp;
}}
[...NODES].sort((a,b) => b.deg - a.deg).slice(0, Math.min(70, NODES.length)).forEach(n => {{
  const sp = makeLabel(n.label, n.color);
  sp.userData.nodeId = n.id;
  labelGroup.add(sp);
}});

/* ================= física ================= */
function physics() {{
  if (!state.phys) return;
  const ids = Object.keys(P).filter(id => P[id].vis);
  const R2 = state.repulsion;
  // molas
  for (const e of E) {{
    const a = P[e.s], b = P[e.t];
    if (!a || !b || !a.vis || !b.vis) continue;
    const dx = b.x-a.x, dy = b.y-a.y, dz = b.z-a.z;
    const d = Math.hypot(dx,dy,dz) || 0.01, rest = 34;
    const f = (d - rest) * 0.012;
    const ux = dx/d, uy = dy/d, uz = dz/d;
    a.vx += ux*f; a.vy += uy*f; a.vz += uz*f;
    b.vx -= ux*f; b.vy -= uy*f; b.vz -= uz*f;
  }}
  // repulsão amostrada
  for (let i = 0; i < ids.length; i++) {{
    const a = P[ids[i]];
    for (let k = 0; k < 10; k++) {{
      const b = P[ids[(Math.random()*ids.length)|0]];
      if (!b || b === a) continue;
      const dx = a.x-b.x, dy = a.y-b.y, dz = a.z-b.z;
      const d2 = dx*dx+dy*dy+dz*dz + 40;
      const d = Math.sqrt(d2);
      const f = Math.min(6, (9000 * R2) / d2) / (d || 1);
      a.vx += dx*f*0.12; a.vy += dy*f*0.12; a.vz += dz*f*0.12;
    }}
    // gravidade central suave
    a.vx -= a.x * 0.0016; a.vy -= a.y * 0.0016; a.vz -= a.z * 0.0016;
  }}
  for (const id of ids) {{
    const p = P[id];
    p.vx *= 0.86; p.vy *= 0.86; p.vz *= 0.86;
    const sp = Math.hypot(p.vx,p.vy,p.vz);
    if (sp > 6) {{ p.vx *= 6/sp; p.vy *= 6/sp; p.vz *= 6/sp; }}
    else if (sp < 0.06) {{ p.vx = p.vy = p.vz = 0; }} // sleep: para de tremer ao estabilizar
    p.x += p.vx; p.y += p.vy; p.z += p.vz;
  }}
}}
function syncMeshes() {{
  for (const id in P) {{
    const p = P[id];
    p.mesh.position.set(p.x, p.y, p.z);
    p.mesh.visible = p.vis;
  }}
  for (let i = 0; i < E.length; i++) {{
    const a = P[E[i].s], b = P[E[i].t];
    edgePos[i*6]   = a ? a.x : 0; edgePos[i*6+1] = a ? a.y : 0; edgePos[i*6+2] = a ? a.z : 0;
    edgePos[i*6+3] = b ? b.x : 0; edgePos[i*6+4] = b ? b.y : 0; edgePos[i*6+5] = b ? b.z : 0;
  }}
  edgeGeo.attributes.position.needsUpdate = true;
  labelGroup.children.forEach(sp => {{
    const p = P[sp.userData.nodeId];
    if (!p || !p.vis) {{ sp.visible = false; return; }}
    sp.visible = true;
    sp.position.set(p.x, p.y + 6.5, p.z);
  }});
}}

/* ================= seleção / HUD card ================= */
const ray = new THREE.Raycaster(); const mouse = new THREE.Vector2();
let downAt = 0;
renderer.domElement.addEventListener('pointerdown', () => {{ downAt = performance.now(); }});
renderer.domElement.addEventListener('pointerup', (ev) => {{
  if (performance.now() - downAt > 260) return; // foi arraste
  const r = renderer.domElement.getBoundingClientRect();
  mouse.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
  mouse.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
  ray.setFromCamera(mouse, camera);
  const hits = ray.intersectObjects(Object.values(P).filter(p => p.vis).map(p => p.mesh));
  if (hits.length) selectNode(hits[0].object.userData.id, true);
  else clearSelect();
}});
function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}
function selectNode(id, focus) {{
  state.selected = id;
  const n = byId[id];
  const viz = (adj[id] || []);
  $('info-t').textContent = '◈ ' + n.label;
  const imps = (n.imports && n.imports.length)
    ? n.imports.slice(0, 24).map(i => `<span class="imp">▸ ${{esc(i)}}</span>`).join('<br>') +
      (n.imports.length > 24 ? `<br>… +${{n.imports.length - 24}} importações` : '')
    : '<i style="color:var(--dim)">— sem imports detectados —</i>';
  const vizList = viz.slice(0, 12).map(v => esc(byId[v] ? byId[v].label : v)).join(', ') || '—';
  $('info-r').innerHTML =
    `arquivo/módulo: <b>${{esc(n.label)}}</b><br>` +
    `caminho relativo: <b>${{esc(n.file)}}</b><br>` +
    `comunidade: <b>${{esc(n.mod)}}</b> · símbolos: <b>${{n.symbols || 0}}</b><br>` +
    `degree centrality: <b style="color:var(--cyan)">${{n.deg}}</b> con. (${{viz.length}} vizinhos)<br>` +
    `vizinhos: <b>${{vizList}}</b>${{viz.length > 12 ? ` <i>+${{viz.length-12}}</i>` : ''}}<br>` +
    `<br><span style="color:var(--cyan);letter-spacing:2px;font-size:10px">// IMPORTAÇÕES E DEPENDÊNCIAS DIRETAS</span><br>${{imps}}`;
  $('info').classList.add('show');
  $('st-sel').innerHTML = 'selecionado: <b>' + esc(n.label) + '</b> · ' + n.deg + ' conexões';
  for (const pid in P) {{
    const keep = pid === id || (adj[id] || []).includes(pid);
    P[pid].mesh.material.opacity = keep ? 1 : 0.12;
    P[pid].glow.material.opacity = keep ? 0.75 : 0.06;
  }}
  paintEdges();
  if (focus) {{
    const p = P[id];
    const tgt = new THREE.Vector3(p.x, p.y, p.z);
    const dir = camera.position.clone().sub(controls.target);
    controls.target.copy(tgt);
  }}
}}
function clearSelect() {{
  state.selected = null;
  $('info').classList.remove('show');
  $('st-sel').textContent = 'nenhum nó selecionado';
  for (const pid in P) {{ P[pid].mesh.material.opacity = 1; P[pid].glow.material.opacity = 0.55; }}
  paintEdges();
}}
$('info-x').onclick = clearSelect;

function rebuildVisibility() {{
  let nv = 0;
  for (const n of NODES) {{
    const v = inSet(n);
    P[n.id].vis = v;
    if (v) nv++;
  }}
  if (state.selected && !P[state.selected].vis) clearSelect();
  else paintEdges();
  $('st-nodes').textContent = nv + ' / ' + NODES.length;
}}

/* ================= controles ================= */
$('btn-phys').onclick = (e) => {{ if (state.frozen) doUnfreeze(); state.phys = !state.phys; e.target.textContent = state.phys ? 'FÍSICA ON' : 'FÍSICA OFF'; e.target.classList.toggle('on', state.phys); }};
$('btn-cam').onclick = () => {{
  controls.target.set(0,0,0); camera.position.set(0, 120, 320);
}};
$('orb').oninput = (e) => {{ state.orbSpeed = +e.target.value / 10; $('orb-val').textContent = state.orbSpeed.toFixed(1); }};
$('rep').oninput = (e) => {{ state.repulsion = +e.target.value / 10; $('rep-val').textContent = state.repulsion.toFixed(1); }};
$('btn-roty').onclick = (e) => {{ if (state.frozen) doUnfreeze(); state.rotY = !state.rotY; e.target.classList.toggle('on', state.rotY); }};
$('btn-rotx').onclick = (e) => {{ if (state.frozen) doUnfreeze(); state.rotX = !state.rotX; e.target.classList.toggle('on', state.rotX); }};
$('flux').oninput = (e) => {{ state.flux = +e.target.value / 12; $('flux-val').textContent = state.flux.toFixed(1); }};
function syncRgbBtns() {{
  $('btn-rgb').classList.toggle('on', state.rgbGlobal);
  $('btn-rgb2').classList.toggle('on', state.rgbGlobal);
  $('btn-selrgb').classList.toggle('on', state.rgbSelect);
  $('btn-rgb').textContent = state.rgbGlobal ? '[ FLUXO RGB ]' : '[ RGB OFF ]';
}}
$('btn-rgb').onclick = () => {{ state.rgbGlobal = !state.rgbGlobal; syncRgbBtns(); }};
$('btn-rgb2').onclick = (e) => {{ state.rgbGlobal = !state.rgbGlobal; syncRgbBtns(); }};
$('btn-selrgb').onclick = () => {{ state.rgbSelect = !state.rgbSelect; syncRgbBtns(); }};
$('btn-orbit').onclick = (e) => {{ if (state.frozen) doUnfreeze(); controls.autoRotate = !controls.autoRotate; e.target.classList.toggle('on', controls.autoRotate); }};
/* ---- CONGELAR: para física + órbita + fluxo de uma vez ---- */
let _saved = null;
function syncMotionUI() {{
  $('btn-phys').textContent = state.phys ? 'FÍSICA ON' : 'FÍSICA OFF';
  $('btn-phys').classList.toggle('on', state.phys);
  $('btn-roty').classList.toggle('on', state.rotY);
  $('btn-rotx').classList.toggle('on', state.rotX);
  $('btn-orbit').classList.toggle('on', controls.autoRotate);
}}
function doFreeze() {{
  if (state.frozen) return;
  _saved = {{ phys: state.phys, rotY: state.rotY, rotX: state.rotX, auto: controls.autoRotate }};
  state.frozen = true;
  state.phys = false; state.rotY = false; state.rotX = false; controls.autoRotate = false;
  for (const id in P) {{ P[id].vx = P[id].vy = P[id].vz = 0; }}
  $('btn-freeze').textContent = '[ ▶ DESCONGELAR ]';
  $('btn-freeze').classList.add('on');
  syncMotionUI();
}}
function doUnfreeze() {{
  if (!state.frozen) return;
  state.frozen = false;
  state.phys = _saved.phys; state.rotY = _saved.rotY; state.rotX = _saved.rotX;
  controls.autoRotate = _saved.auto;
  $('btn-freeze').textContent = '[ ❄ CONGELAR ]';
  $('btn-freeze').classList.remove('on');
  syncMotionUI();
}}
$('btn-freeze').onclick = () => {{ state.frozen ? doUnfreeze() : doFreeze(); }};
$('btn-full').onclick = () => {{
  if (!document.fullscreenElement) document.documentElement.requestFullscreen().catch(() => {{}});
  else document.exitFullscreen().catch(() => {{}});
}};
document.addEventListener('fullscreenchange', () => {{
  $('btn-full').textContent = document.fullscreenElement ? '[ ⛶ SAIR FULL ]' : '[ ⛶ FULLSCREEN ]';
  $('btn-full').classList.toggle('on', !!document.fullscreenElement);
}});
$('deg').oninput = (e) => {{ state.minDeg = +e.target.value; $('deg-val').textContent = state.minDeg; rebuildVisibility(); }};
$('btn-all').onclick = () => {{ state.hiddenMods.clear();
  document.querySelectorAll('#mods .mod').forEach(el => el.classList.remove('off')); rebuildVisibility(); }};
$('btn-none').onclick = () => {{ state.hiddenMods = new Set(Object.keys(MOD_COLORS));
  document.querySelectorAll('#mods .mod').forEach(el => el.classList.add('off')); rebuildVisibility(); }};
$('panel-toggle').onclick = () => $('panel').classList.toggle('hidden');
$('search').oninput = (e) => {{
  const q = e.target.value.trim().toLowerCase();
  const box = $('search-results');
  if (q.length < 2) {{ box.innerHTML = ''; return; }}
  const hits = NODES.filter(n => n.label.toLowerCase().includes(q) && P[n.id].vis).slice(0, 12);
  box.innerHTML = hits.map(n => `<div class="sr" data-id="${{n.id}}">${{esc(n.label)}} <small>${{esc(n.mod)}} · grau ${{n.deg}}</small></div>`).join('') || '<div class="sr">— nada —</div>';
  box.querySelectorAll('.sr[data-id]').forEach(el => {{
    el.onclick = () => selectNode(el.dataset.id, true);
  }});
}};
addEventListener('resize', () => {{
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}});
/* pan pelo teclado: move câmera + alvo no plano da tela, sem rotacionar */
const keysDown = new Set();
document.addEventListener('keydown', (e) => {{
  const tag = document.activeElement ? document.activeElement.tagName : '';
  const k = e.key.toLowerCase();
  if ((tag === 'INPUT' || tag === 'TEXTAREA')) return;
  if (['w','a','s','d','q','e','arrowup','arrowdown','arrowleft','arrowright','shift'].includes(k)) {{
    keysDown.add(k); e.preventDefault();
  }}
  if (e.key === 'Escape' && state.selected) clearSelect();
  if (k === 'f') $('btn-full').click();
  if (e.key === ' ') {{ e.preventDefault(); $('btn-freeze').click(); }}
}});
document.addEventListener('keyup', (e) => keysDown.delete(e.key.toLowerCase()));
window.addEventListener('blur', () => keysDown.clear());

const _fwd = new THREE.Vector3(), _rgt = new THREE.Vector3(), _up = new THREE.Vector3(), _mv = new THREE.Vector3();
function keyboardPan() {{
  if (!keysDown.size) return;
  camera.getWorldDirection(_fwd);
  _rgt.crossVectors(_fwd, camera.up).normalize();
  _up.crossVectors(_rgt, _fwd).normalize();
  const dist = camera.position.distanceTo(controls.target);
  const step = dist * 0.07 * (keysDown.has('shift') ? 3 : 1);
  _mv.set(0, 0, 0);
  if (keysDown.has('w') || keysDown.has('arrowup')) _mv.add(_up);
  if (keysDown.has('s') || keysDown.has('arrowdown')) _mv.sub(_up);
  if (keysDown.has('a') || keysDown.has('arrowleft')) _mv.sub(_rgt);
  if (keysDown.has('d') || keysDown.has('arrowright')) _mv.add(_rgt);
  if (keysDown.has('q')) _mv.add(_fwd);
  if (keysDown.has('e')) _mv.sub(_fwd);
  if (_mv.lengthSq() === 0) return;
  _mv.normalize().multiplyScalar(step);
  camera.position.add(_mv); controls.target.add(_mv);
}}

/* ================= loop ================= */
paintEdges();
rebuildVisibility();
syncRgbBtns();
function loop() {{
  requestAnimationFrame(loop);
  physics();
  syncMeshes();
  tickPhotons();
  keyboardPan();
  if (state.rotY) controls.autoRotateSpeed = state.orbSpeed * 2.0;
  else if (!controls.autoRotate) {{}}
  if (!state.rotY && $('btn-orbit').classList.contains('on')) {{ /* mantém autoRotate do toggle */ }}
  if (state.rotX) {{
    const a = 0.0022 * state.orbSpeed;
    const y = camera.position.y * Math.cos(a) - camera.position.z * Math.sin(a);
    const z = camera.position.y * Math.sin(a) + camera.position.z * Math.cos(a);
    camera.position.y = y; camera.position.z = z;
  }}
  if (!state.rotY) controls.autoRotateSpeed = 0;
  controls.update();
  renderer.render(scene, camera);
}}
loop();
setTimeout(() => {{
  $('boot').classList.add('gone');
  $('boot-msg').textContent = 'SISTEMA ONLINE';
  setTimeout(() => {{ $('boot').style.display = 'none'; }}, 700);
}}, 900);
</script>
</body>
</html>"""


def generate(output_path: str | Path, graph: dict) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(graph), encoding="utf-8")
    return output_path


def _short_defs(defs: list[dict], cap: int = 12) -> str:
    parts = []
    for d in defs[:cap]:
        name = d.get("n", "?")
        kind = d.get("k", "")
        line = d.get("l", 0)
        parts.append(f"{name}{'()' if kind == 'func' else ''}:L{line}")
    s = ", ".join(parts)
    if len(defs) > cap:
        s += f" (+{len(defs) - cap})"
    return s


COMPACT_LIM = 300  # acima disso o map.md sai compacto sozinho (use --no-compact p/ forçar cheio)


def render_map_md(graph: dict, compact: bool | None = None) -> str:
    """Resumo compacto do repositório, desenhado para consumo por agentes de IA.

    Índice tiny (hubs + capabilities + como consultar) + uma linha por arquivo
    (caminho, linguagem, grau, dependências, símbolos com linha, caps de
    hardware e chamadas resolvidas) + ranking de hubs + fluxo de chamadas.

    Modo compacto (auto acima de COMPACT_LIM arquivos, ou --compact): só o
    índice + risks + fatias — sem as linhas por arquivo. Queries cobrem o resto.
    """
    meta = graph.get("meta", {})
    nodes = graph.get("nodes", [])
    links = graph.get("links", [])
    calls = graph.get("call_edges", [])
    capabilities = graph.get("capabilities", {}) or {}
    if compact is None:
        compact = len(nodes) > COMPACT_LIM
    root = Path(str(meta.get("root", "."))).name or "repo"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    langs = ", ".join(meta.get("langs", [])) or "—"

    adj: dict[str, list[str]] = {}
    for s, t in links:
        adj.setdefault(s, []).append(t)
    by_id = {n["id"]: n for n in nodes}
    calls_by_src: dict[str, list[tuple[str, str]]] = {}
    for edge in calls:
        if len(edge) >= 3:
            calls_by_src.setdefault(edge[0], []).append((edge[2], edge[1]))

    L = [f"# ASTOS MAP — {root}",
         f"> Gerado por `astos` em {now}. {len(nodes)} arquivos · "
         f"{len(links)} dependências · {len(calls)} chamadas inter-arquivo · langs: {langs}.",
         "> Se desatualizado: `astos -f` (atualiza sem abrir o navegador). Detalhe: `.astos/graph.json`. Visual humano: `.astos/index.html` + `.astos/city.html` (palácio).",
         "> Queries baratas (use em vez de grep): `astos q --symbol X` · `astos q --cap camera` · `astos trace --from A --to B` · `astos impact --file F` · `astos caps` · `astos hubs` · `astos risks` · `astos slice <pasta>` · `astos changed` · `astos status` · `astos explain --symbol X` · `astos hotspots` · `astos dead` · `astos tests --file X`.",
         "",
         "## HUBS (maior degree centrality)"]
    for n in nodes[:15]:
        deps = adj.get(n["id"], [])
        dep_s = ", ".join(f"`{by_id[d]['file']}`" for d in deps[:8] if d in by_id)
        extra = f" — dep: {dep_s}" if dep_s else ""
        if len(deps) > 8:
            extra += f" (+{len(deps) - 8})"
        L.append(f"- `{n['file']}` [{n.get('lang', '?')}] deg={n.get('deg', 0)}{extra}")
    if capabilities:
        L += ["", "## CAPABILITIES (hardware/plataforma — quem fala com o quê)"]
        for cap in sorted(capabilities):
            files = [f for f in capabilities[cap] if not f.startswith("manifest:")][:12]
            manifs = [f[len("manifest:"):] for f in capabilities[cap] if f.startswith("manifest:")][:6]
            line = f"- `{cap}`: " + ", ".join(f"`{f}`" for f in files) if files else f"- `{cap}`:"
            if manifs:
                line += (" · " if files else "") + "manifest: " + ", ".join(f"`{m}`" for m in manifs)
            extra_n = len(capabilities[cap]) - len(files) - len(manifs)
            if extra_n > 0:
                line += f" (+{extra_n})"
            L.append(line)
    L.append("")
    if compact:
        mods = sorted({n.get("file", "").split("/")[0] for n in nodes if n.get("file")})
        L.append(f"## MODO COMPACTO ({len(nodes)} arquivos — detalhe por arquivo em `.astos/graph.json`)")
        L.append("fatias (leia só o que precisa): " +
                 ", ".join(f"`astos slice {m}`" for m in mods[:20]))
        L.append("")
    else:
        L.append("## ARQUIVOS")
    for n in nodes:
        if compact:
            break
        segs = [f"`{n['file']}` [{n.get('lang', '?')}] deg={n.get('deg', 0)}"]
        deps = [by_id[d]["file"] for d in adj.get(n["id"], []) if d in by_id]
        if deps:
            shown = ", ".join(f"`{d}`" for d in deps[:10])
            if len(deps) > 10:
                shown += f" (+{len(deps) - 10})"
            segs.append(f"dep: {shown}")
        exts = list(n.get("externals", []))[:6]
        if exts:
            segs.append("ext: " + ", ".join(f"`{e}`" for e in exts))
        if n.get("caps"):
            segs.append("caps: " + ",".join(n["caps"][:6]))
        if n.get("changed"):
            segs.append("●changed")
        if n.get("entry"):
            segs.append("entry")
        if n.get("todo_n"):
            ex = (n.get("todo_ex", []) or [""])[0][:60]
            segs.append(f"todo:{n['todo_n']}" + (f"({ex})" if ex else ""))
        if n.get("defs"):
            segs.append("def: " + _short_defs(n["defs"]))
        src_calls = calls_by_src.get(n["id"], [])[:8]
        if src_calls:
            segs.append("calls: " + ", ".join(
                f"{c}()>`{by_id[t]['file']}`" if t in by_id else f"{c}()"
                for c, t in src_calls))
        L.append("- " + " :: ".join(segs))
    risks = graph.get("risks", {}) or {}
    if any(risks.get(k) for k in ("gods", "cycles", "todos", "fan_in", "fan_out", "entries", "orphans")):
        L += ["", "## RISKS (onde o bug provavelmente mora — comece por aqui)"]
        if risks.get("gods"):
            L.append("god files (grande/conectado demais): " + ", ".join(
                f"`{g['file']}`(loc={g['loc']},syms={g['symbols']},deg={g['deg']})"
                for g in risks["gods"][:8]))
        if risks.get("cycles"):
            for cyc in risks["cycles"][:5]:
                L.append("ciclo: " + " -> ".join(f"`{x}`" for x in cyc))
        if risks.get("fan_out"):
            L.append("fan-out alto (depende de muitos): " + ", ".join(
                f"`{d['file']}`({d['n']})" for d in risks["fan_out"][:8]))
        if risks.get("fan_in"):
            L.append("fan-in alto (muitos dependem): " + ", ".join(
                f"`{d['file']}`({d['n']})" for d in risks["fan_in"][:8]))
        if risks.get("todos"):
            L.append("TODOs: " + "; ".join(
                f"`{t['file']}`x{t['n']}({(t.get('ex') or [''])[0][:50]})"
                for t in risks["todos"][:8]))
        if risks.get("entries"):
            L.append("entrypoints: " + ", ".join(f"`{e}`" for e in risks["entries"][:10]))
        if risks.get("orphans"):
            L.append("órfãos (deg=0, possível morto): " + ", ".join(
                f"`{o}`" for o in risks["orphans"][:10]))
    dirty = [n["file"] for n in nodes if n.get("changed")]
    if dirty:
        L += ["", "## CHANGED (sujos no git — debugue aqui primeiro)"]
        for f in dirty[:20]:
            L.append(f"- `{f}`")
        if len(dirty) > 20:
            L.append(f"- (+{len(dirty) - 20} outros — `astos changed` lista tudo)")
    if calls and not compact:
        L += ["", "## FLUXO (chamadas entre arquivos, top 30)"]
        for s, t, name in calls[:30]:
            sf = by_id.get(s, {}).get("file", s)
            tf = by_id.get(t, {}).get("file", t)
            L.append(f"- `{sf}` --{name}()--> `{tf}`")
    L.append("")
    return "\n".join(L)


def generate_map(output_path: str | Path, graph: dict,
                 compact: bool | None = None) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_map_md(graph, compact=compact), encoding="utf-8")
    if compact is None:
        compact = len(graph.get("nodes", [])) > COMPACT_LIM
    graph.setdefault("meta", {})["map_mode"] = "compact" if compact else "full"
    return output_path


def _city_height(n: dict) -> float:
    loc = int(n.get("loc", 0) or 0)
    syms = int(n.get("symbols", 0) or 0)
    deg = int(n.get("deg", 0) or 0)
    return round(4 + min(loc, 3000) / 55 + min(syms, 60) * 0.7 + min(deg, 25) * 0.5, 2)


def render_city_html(graph: dict) -> str:
    """Palácio do código (metáfora Makepad, gerada em Python).

    Placa de circuito: pastas são quadras coladas lado a lado numa placa
    única, arquivos são blocos (altura ~ loc + símbolos + grau, maiores no
    centro da quadra), trilhas cyan = dependências entre blocos.
    Nomes só nos 12 maiores (botão NOMES liga/desliga); clique no bloco abre
    a ficha do arquivo. Não altera o grafo 3D — visão irmã, mesmo Three.js.
    """
    three_js, orbit_js = _read_vendor()
    nodes = graph.get("nodes", []) or []
    links = graph.get("links", []) or []
    mods = graph.get("mods", {}) or {}
    meta = graph.get("meta", {})
    root_name = html.escape(Path(str(meta.get("root", "."))).name or "repo")

    city = []
    for n in nodes:
        city.append({
            "id": n.get("id"), "label": n.get("label"), "file": n.get("file"),
            "lang": n.get("lang"), "mod": n.get("mod"), "color": n.get("color"),
            "deg": n.get("deg", 0), "symbols": n.get("symbols", 0),
            "loc": int(n.get("loc", 0) or 0), "caps": list(n.get("caps", []))[:8],
            "h": _city_height(n),
            "todo_n": int(n.get("todo_n", 0) or 0),
            "entry": bool(n.get("entry", False)),
            "defs": (n.get("defs", []) or [])[:10],
        })
    city.sort(key=lambda d: -d["h"])
    city_json = json.dumps(city, ensure_ascii=False)
    links_json = json.dumps(links, ensure_ascii=False)
    mods_json = json.dumps(mods, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ASTOS // {root_name} — Palácio do Código</title>
<style>
:root {{ --bg:#04060e; --panel:rgba(8,12,24,.92); --line:#1e293b; --txt:#dbeafe; --dim:#64748b; --cyan:#22d3ee; --mag:#f472b6; }}
* {{ box-sizing:border-box; }} html,body {{ margin:0; height:100%; background:var(--bg); color:var(--txt);
font-family:Consolas,monospace; overflow:hidden; }}
#stage {{ position:fixed; inset:0; }} #net3d {{ position:absolute; inset:0; }}
#topbar {{ position:fixed; top:0; left:0; right:0; z-index:100; display:flex; gap:12px; align-items:center; padding:10px 16px; flex-wrap:wrap;
background:linear-gradient(180deg,rgba(4,6,14,.96),rgba(4,6,14,.55) 80%,transparent); border-bottom:1px solid rgba(34,211,238,.28); }}
.logo {{ color:var(--cyan); font-weight:bold; letter-spacing:2px; }} .sub {{ color:var(--dim); font-size:11px; }}
.hbtn {{ border:1px solid var(--cyan); background:rgba(15,23,42,.85); color:var(--cyan); font-family:inherit; font-size:11px; padding:7px 12px; border-radius:4px; cursor:pointer; text-decoration:none; }}
#panel {{ position:fixed; top:64px; right:12px; width:300px; z-index:100; background:var(--panel); border:1px solid rgba(34,211,238,.35); border-radius:8px; padding:12px; }}
#panel input,select {{ width:100%; background:#0b1120; border:1px solid var(--line); color:var(--txt); font-family:inherit; font-size:12px; padding:7px 9px; border-radius:4px; margin-top:4px; }}
#panel label {{ font-size:11px; color:var(--dim); display:block; margin-top:8px; }}
#info {{ position:fixed; left:12px; bottom:12px; z-index:100; width:420px; max-width:calc(100vw - 24px); max-height:46vh; overflow:auto;
background:rgba(8,12,24,.94); border:1px solid rgba(244,114,182,.55); border-radius:8px; padding:12px 14px; font-size:12px; display:none; }}
#info.show {{ display:block; }} #info .t {{ color:var(--mag); font-weight:bold; }} #info .r {{ color:var(--dim); line-height:1.7; word-break:break-word; }}
#hint {{ position:fixed; bottom:12px; left:50%; transform:translateX(-50%); z-index:99; font-size:11px; color:var(--dim); background:rgba(8,12,24,.7); border:1px solid var(--line); padding:5px 12px; border-radius:20px; }}
</style>
</head>
<body>
<div id="stage"><div id="net3d"></div></div>
<div id="topbar"><span class="logo">ASTOS // PALÁCIO</span><span class="sub">{len(city)} BLOCOS · PLACA DE CIRCUITO · ALTURA=LINHAS · 100% OFFLINE</span>
<a class="hbtn" href="index.html">[ ◀ GRAFO ]</a><button class="hbtn on" id="btn-names">[ NOMES ]</button><button class="hbtn on" id="btn-traces">[ TRILHAS ]</button></div>
<div id="panel"><label>busca de bloco</label><input id="search" placeholder="ex: camera, service..." autocomplete="off">
<label>capability (hardware)</label><select id="cap"><option value="">todas</option></select>
<label style="margin-top:8px">placa única: quadras coladas por pasta · altura = loc + símbolos + grau · trilhas = dependências · clique no bloco = ficha</label></div>
<div id="info"><div class="t" id="info-t"></div><div class="r" id="info-r"></div></div>
<div id="hint">arraste: orbitar · scroll: zoom · botão direito: pan · clique num bloco: HUD</div>
<script>{three_js}</script>
<script>{orbit_js}</script>
<script>
"use strict";
const CITY = {city_json}; const LINKS = {links_json}; const MODS = {mods_json};
const $ = (id) => document.getElementById(id);
const byId = {{}}; CITY.forEach(b => byId[b.id] = b);
const adj = {{}}; LINKS.forEach(([s,t]) => {{ (adj[s]=adj[s]||[]).push(t); (adj[t]=adj[t]||[]).push(s); }});
const caps = [...new Set(CITY.flatMap(b => b.caps || []))].sort();
caps.forEach(c => {{ const o=document.createElement('option'); o.value=c; o.textContent=c; $('cap').appendChild(o); }});
let filterCap = "", query = "";
const scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x04060e, 0.0011);
const camera = new THREE.PerspectiveCamera(60, innerWidth/innerHeight, 0.1, 9000);
camera.position.set(0, 260, 420);
const renderer = new THREE.WebGLRenderer({{antialias:true, alpha:true}});
renderer.setSize(innerWidth, innerHeight); $('net3d').appendChild(renderer.domElement);
const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = 0.06; controls.autoRotate = true; controls.autoRotateSpeed = 0.8;
scene.add(new THREE.AmbientLight(0x8899bb, 0.85));
const key = new THREE.PointLight(0x22d3ee, 1.1, 0); key.position.set(300,500,300); scene.add(key);
// ---- CIDADE: cada pasta (mod) é uma quadra, arquivos são blocos ----
// (corrige bug antigo: espiral punha os primeiros blocos todos no centro)
const P = {{}}; const labelSprites = {{}}; const STEP = 30;
function makeLabel(t, color) {{
  const c = document.createElement('canvas'); const x = c.getContext('2d');
  x.font = 'bold 24px monospace'; const w = Math.ceil(x.measureText(t).width) + 24;
  c.width = w; c.height = 38; x.fillStyle = 'rgba(4,8,18,.85)'; x.fillRect(0,0,w,38);
  x.strokeStyle = color; x.strokeRect(1,1,w-2,36); x.font = 'bold 24px monospace'; x.fillStyle = '#eaf6ff'; x.fillText(t, 12, 26);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({{ map:new THREE.CanvasTexture(c), transparent:true, depthWrite:false }}));
  sp.scale.set(w*0.26, 38*0.26, 1); return sp;
}}
const districts = {{}};
CITY.forEach(b => {{ (districts[b.mod] = districts[b.mod] || []).push(b); }});
Object.values(districts).forEach(arr => arr.sort((a, b) => b.h - a.h));
const dnames = Object.keys(districts).sort((a, b) => districts[b].length - districts[a].length);
const GAP = 5; // quadras coladas: só a junta de solda entre as placas
const rect = {{}}; // m -> {{wdt, dep, cols, rows}}
dnames.forEach(m => {{
  const n = districts[m].length, cols = Math.ceil(Math.sqrt(n)), rows = Math.ceil(n / cols);
  rect[m] = {{ wdt: cols * STEP + 26, dep: rows * STEP + 26, cols, rows }};
}});
// empacota as quadras em linhas: a cidade inteira vira UMA placa de circuito
const DCOLS = Math.ceil(Math.sqrt(dnames.length));
let bx = 0, bz = 0, rowH = 0, bcol = 0, boardW = 0;
const dpos = {{}};
dnames.forEach(m => {{
  if (bcol >= DCOLS) {{ bcol = 0; bx = 0; bz += rowH + GAP; rowH = 0; }}
  dpos[m] = {{ x: bx + rect[m].wdt / 2, z: bz + rect[m].dep / 2 }};
  bx += rect[m].wdt + GAP;
  if (rect[m].dep > rowH) rowH = rect[m].dep;
  if (bx > boardW) boardW = bx;
  bcol++;
}});
const boardH = bz + rowH;
const ox = boardW / 2, oz = boardH / 2; // centraliza a placa na origem
const half = Math.max(boardW, boardH) / 2;
camera.position.set(0, half * 0.9 + 140, half * 1.2 + 200);
const gridSize = Math.ceil(Math.max(boardW, boardH) + 500);
const grid = new THREE.GridHelper(gridSize, Math.ceil(gridSize / 20), 0x164e63, 0x0f172a);
grid.position.y = -2.5; scene.add(grid);
dnames.forEach((m) => {{
  const cx = dpos[m].x - ox, cz = dpos[m].z - oz;
  const arr = districts[m];
  const cols = rect[m].cols, rows = rect[m].rows;
  const cells = [];
  for (let rr = 0; rr < rows; rr++) for (let cc2 = 0; cc2 < cols; cc2++) cells.push([cc2, rr]);
  const cc = (cols - 1) / 2, rc = (rows - 1) / 2;
  cells.sort((p1, p2) => Math.hypot(p1[0]-cc, p1[1]-rc) - Math.hypot(p2[0]-cc, p2[1]-rc));
  const wdt = rect[m].wdt, dep = rect[m].dep;
  const plate = new THREE.Mesh(new THREE.BoxGeometry(wdt, 2, dep),
    new THREE.MeshLambertMaterial({{ color: 0x0b1226 }}));
  plate.position.set(cx, -1, cz); scene.add(plate);
  plate.add(new THREE.LineSegments(new THREE.EdgesGeometry(plate.geometry),
    new THREE.LineBasicMaterial({{ color: new THREE.Color(arr[0].color) }})));
  const mlab = makeLabel('▤ ' + m + ' (' + arr.length + ')', arr[0].color);
  mlab.position.set(cx, 16, cz - dep/2 - 8); mlab.scale.multiplyScalar(1.3); scene.add(mlab);
  labelSprites['mod:' + m] = mlab;
  arr.forEach((b, i) => {{
    const cell = cells[i] || [0, 0];
    const x = cx + (cell[0] - cc) * STEP, z = cz + (cell[1] - rc) * STEP;
    const w = 9 + Math.min(b.symbols, 40) * 0.12, d = 9 + Math.min(b.symbols, 40) * 0.12;
    const geo = new THREE.BoxGeometry(w, b.h, d);
    const mat = new THREE.MeshLambertMaterial({{ color: new THREE.Color(b.color), emissive: new THREE.Color(b.color).multiplyScalar(0.18) }});
    const mesh = new THREE.Mesh(geo, mat); mesh.position.set(x, b.h/2, z); mesh.userData.id = b.id;
    mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({{ color: 0xffffff, transparent:true, opacity:0.18 }})));
    scene.add(mesh); P[b.id] = {{ x, z, w, d, h: b.h, mesh, data: b }};
  }});
}});
// trilhas do circuito: dependências entre blocos (top 400, somem no filtro)
const traces = [];
LINKS.slice(0, 400).forEach(([s, t]) => {{
  if (s === t || !P[s] || !P[t]) return;
  const g = new THREE.BufferGeometry().setFromPoints(
    [new THREE.Vector3(P[s].x, 1.2, P[s].z), new THREE.Vector3(P[t].x, 1.2, P[t].z)]);
  const ln = new THREE.Line(g, new THREE.LineBasicMaterial({{ color: 0x22d3ee, transparent: true, opacity: 0.3 }}));
  scene.add(ln); traces.push({{ s, t, ln }});
}});
// nomes: só os 12 maiores + quadras (botão NOMES liga/desliga)
let namesOn = true, trailsOn = true;
CITY.slice(0, 12).forEach(b => {{
  const sp = makeLabel(b.label, b.color); const p = P[b.id];
  if (!p) return;
  sp.position.set(p.x, p.h + 8, p.z); sp.userData.nodeId = b.id; scene.add(sp);
  labelSprites[b.id] = sp;
}});
$('btn-names').onclick = (e) => {{
  namesOn = !namesOn;
  e.target.textContent = namesOn ? '[ NOMES ]' : '[ SEM NOMES ]';
  e.target.classList.toggle('on', namesOn);
  refresh();
}};
$('btn-traces').onclick = (e) => {{
  trailsOn = !trailsOn;
  e.target.textContent = trailsOn ? '[ TRILHAS ]' : '[ SEM TRILHAS ]';
  e.target.classList.toggle('on', trailsOn);
  refresh();
}};
function visible(b) {{
  if (filterCap && !(b.caps||[]).includes(filterCap)) return false;
  if (query && !(b.label.toLowerCase().includes(query) || b.file.toLowerCase().includes(query))) return false;
  return true;
}}
function refresh() {{
  CITY.forEach(b => {{ if (P[b.id]) P[b.id].mesh.visible = visible(b); }});
  Object.keys(labelSprites).forEach(k => {{
    if (k.indexOf('mod:') === 0) return; // quadras sempre nomeadas
    const b = byId[k];
    labelSprites[k].visible = namesOn && !!b && visible(b);
  }});
  traces.forEach(tr => {{
    tr.ln.visible = trailsOn && !!byId[tr.s] && !!byId[tr.t] && visible(byId[tr.s]) && visible(byId[tr.t]);
  }});
}}
$('search').oninput = (e) => {{ query = e.target.value.trim().toLowerCase(); refresh(); }};
$('cap').onchange = (e) => {{ filterCap = e.target.value; refresh(); }};
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2(); let downAt = 0;
renderer.domElement.addEventListener('pointerdown', () => downAt = performance.now());
renderer.domElement.addEventListener('pointerup', (ev) => {{
  if (performance.now() - downAt > 260) return;
  const r = renderer.domElement.getBoundingClientRect();
  mouse.x = ((ev.clientX - r.left)/r.width)*2-1; mouse.y = -((ev.clientY-r.top)/r.height)*2+1;
  ray.setFromCamera(mouse, camera);
  const hits = ray.intersectObjects(Object.values(P).filter(p=>p.mesh.visible).map(p=>p.mesh));
  if (!hits.length) {{ $('info').classList.remove('show'); return; }}
  const b = byId[hits[0].object.userData.id]; if (!b) return;
  $('info-t').textContent = '▣ ' + b.label + (b.entry ? ' · ⚑ entry' : '');
  const viz = (adj[b.id]||[]).slice(0,10).map(v => byId[v] ? byId[v].label : v).join(', ') || '—';
  const defs = (b.defs||[]).slice(0,6).map(d => d.n + ':L' + d.l).join(', ') || '—';
  $('info-r').innerHTML = 'arquivo: <b style="color:#fff">'+b.file+'</b><br>quadra: <b style="color:#fff">'+b.mod+'</b> · loc: <b style="color:#fff">'+b.loc+'</b> · símbolos: <b style="color:#fff">'+b.symbols+'</b> · grau: <b style="color:#fff">'+b.deg+'</b>' +
    (b.todo_n ? ' · todo:<b style="color:#fbbf24">'+b.todo_n+'</b>' : '') + '<br>'
    + 'caps: <b style="color:#22d3ee">'+((b.caps||[]).join(', ')||'—')+'</b><br>defs: '+defs+'<br>vizinhos: '+viz;
  $('info').classList.add('show');
}});
addEventListener('resize', () => {{ camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); }});
(function loop() {{ requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); }})();
</script>
</body>
</html>"""


def generate_city(output_path: str | Path, graph: dict) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_city_html(graph), encoding="utf-8")
    return output_path
