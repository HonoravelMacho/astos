"""Lógica das queries do ASTOS, pura (sem click): retorna (lines, payload).

Compartilhada pela CLI (`astos q/trace/...`) e pelo servidor MCP
(`astos mcp`), para os dois nunca divergirem. Erros via `QueryError`.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from .generator import _short_defs
from .parser import _iter_code_files


class QueryError(Exception):
    """Falha de query amigável (ex.: grafo ausente, arquivo não resolvido)."""


def load_graph(root: str) -> tuple[dict, Path]:
    repo = Path(root).resolve()
    cache = repo / ".astos" / "graph.json"
    if not cache.is_file():
        raise QueryError(f"sem .astos/graph.json em {repo} — rode `astos -f` primeiro.")
    try:
        graph = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise QueryError(f"graph.json ilegível: {exc}")
    return graph, repo


def match_id(graph: dict, needle: str) -> str | None:
    """Resolve `A.dart` / substring para id do nó (melhor match por sufixo)."""
    needle = needle.strip()
    nodes = graph.get("nodes", [])
    for n in nodes:
        if n.get("id") == needle or n.get("file") == needle:
            return n["id"]
    cands = [n for n in nodes if needle in n.get("file", "") or needle in n.get("id", "")]
    if not cands:
        low = needle.lower()
        cands = [n for n in nodes if low in n.get("file", "").lower()]
    if len(cands) == 1:
        return cands[0]["id"]
    # prefere sufixo exato + maior grau
    cands.sort(key=lambda n: (n.get("file", "").endswith(needle), n.get("deg", 0)), reverse=True)
    return cands[0]["id"] if cands else None


def neighbors(graph: dict, nid: str) -> tuple[list[str], list[str], list[str]]:
    """Retorna (deps via import, chamadores via call, chamados via call)."""
    deps = sorted({t for s, t in graph.get("links", []) if s == nid})
    callers = sorted({e[0] for e in graph.get("call_edges", []) if len(e) >= 3 and e[1] == nid})
    callees = sorted({e[1] for e in graph.get("call_edges", []) if len(e) >= 3 and e[0] == nid})
    return deps, callers, callees


def do_q(graph: dict, symbol: str | None, cap: str | None,
         fname: str | None) -> tuple[list[str], dict]:
    """Busca barata: símbolos, capabilities e arquivos (use em vez de grep)."""
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    hits = []
    for n in graph.get("nodes", []):
        ok = True
        matched = ""
        if symbol:
            defs = [d for d in n.get("defs", []) if symbol.lower() in str(d.get("n", "")).lower()]
            if not defs:
                # fallback: nome do arquivo contém o símbolo
                if symbol.lower() not in n.get("file", "").lower():
                    ok = False
                else:
                    matched = "(nome do arquivo)"
            else:
                matched = ",".join(f"{d['n']}:L{d.get('l', 0)}" for d in defs[:5])
        if cap and cap not in list(n.get("caps", [])):
            ok = False
        if fname and fname.lower() not in n.get("file", "").lower():
            ok = False
        if ok:
            hits.append((n.get("deg", 0), n, matched))
    hits.sort(key=lambda t: -t[0])
    lines = [f"ASTOS q :: {len(hits)} hit(s) (ordenado por grau)"]
    payload = []
    for _, n, matched in hits:
        calls = [f"{c}()->{by_id[t]['file']}" for c, t in
                 [(e[2], e[1]) for e in graph.get("call_edges", []) if len(e) >= 3 and e[0] == n["id"]][:4]]
        line = (f"- `{n['file']}` deg={n.get('deg', 0)} lang={n.get('lang', '?')} "
                f"caps={','.join(n.get('caps', [])) or '—'} "
                f"{'match:' + matched + ' ' if matched else ''}"
                f"{'calls:' + ','.join(calls) if calls else ''}").strip()
        lines.append(line)
        payload.append({"file": n["file"], "deg": n.get("deg"), "caps": n.get("caps"),
                        "match": matched, "calls": calls})
    return lines, {"hits": payload}


def do_trace(graph: dict, src: str, dst: str) -> tuple[list[str], dict]:
    """Caminho A -> B por imports+chamadas (BFS até 6 saltos, top 5)."""
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    s, t = match_id(graph, src), match_id(graph, dst)
    if not s or not t:
        raise QueryError(f"origem/destino não resolvido: {src!r}->{s} {dst!r}->{t}")
    adj: dict[str, list[tuple[str, str]]] = {}
    for a, b in graph.get("links", []):
        adj.setdefault(a, []).append((b, "import"))
        adj.setdefault(b, []).append((a, "import⁻¹"))
    for e in graph.get("call_edges", []):
        if len(e) >= 3:
            adj.setdefault(e[0], []).append((e[1], f"call:{e[2]}"))
    paths: list[list[tuple[str, str]]] = []
    queue: deque = deque([[(s, "")]])
    seen_depth: dict[str, int] = {s: 0}
    while queue and len(paths) < 5:
        path = queue.popleft()
        cur = path[-1][0]
        if len(path) > 7:
            continue
        if cur == t and len(path) > 1:
            paths.append(path)
            continue
        for nxt, how in adj.get(cur, []):
            if any(p[0] == nxt for p in path):
                continue
            if seen_depth.get(nxt, 99) < len(path) - 2:
                continue
            seen_depth[nxt] = len(path) - 1
            queue.append(path + [(nxt, how)])
    sf, tf = by_id.get(s, {}).get("file", s), by_id.get(t, {}).get("file", t)
    if not paths:
        return ([f"ASTOS trace :: sem caminho {sf} -> {tf} (6 saltos, imports+chamadas)"],
                {"from": sf, "to": tf, "paths": []})
    lines = [f"ASTOS trace :: {len(paths)} caminho(s) `{sf}` -> `{tf}`:"]
    payload = []
    for p in paths:
        segs = [by_id.get(nid, {}).get("file", nid) for nid, _ in p]
        hops = [how for _, how in p[1:]]
        lines.append("  " + " -> ".join(f"`{x}`" for x in segs) + f"   [{', '.join(hops)}]")
        payload.append({"files": segs, "via": hops})
    return lines, {"from": sf, "to": tf, "paths": payload}


def do_impact(graph: dict, fname: str) -> tuple[list[str], dict]:
    """Vizinhança de 1 salto: quem depende, quem chama e quem é chamado."""
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    nid = match_id(graph, fname)
    if not nid:
        raise QueryError(f"arquivo não encontrado: {fname!r}")
    n = by_id[nid]
    deps, callers, callees = neighbors(graph, nid)
    rdeps = sorted({s for s, t in graph.get("links", []) if t == nid})
    f = lambda i: by_id.get(i, {}).get("file", i)
    lines = [f"ASTOS impact :: `{n['file']}` deg={n.get('deg', 0)} caps={','.join(n.get('caps', [])) or '—'}",
             f"  depende de ({len(deps)}): " + (", ".join(f"`{f(i)}`" for i in deps[:15]) or "—"),
             f"  dependentes reversos ({len(rdeps)}): " + (", ".join(f"`{f(i)}`" for i in rdeps[:15]) or "—"),
             f"  chamadores ({len(callers)}): " + (", ".join(f"`{f(i)}`" for i in callers[:15]) or "—"),
             f"  chamados ({len(callees)}): " + (", ".join(f"`{f(i)}`" for i in callees[:15]) or "—")]
    return lines, {"file": n["file"], "deps": [f(i) for i in deps],
                   "rdeps": [f(i) for i in rdeps],
                   "callers": [f(i) for i in callers],
                   "callees": [f(i) for i in callees]}


def do_caps(graph: dict) -> tuple[list[str], dict]:
    """Hardware/plataforma detectado: câmera, GPS, bluetooth..."""
    capabilities = graph.get("capabilities", {}) or {}
    if not capabilities:
        return ["ASTOS caps :: nada detectado (sem Camera/GPS/BT no código ou manifestos)"], {}
    lines = [f"ASTOS caps :: {len(capabilities)} capability(ies):"]
    for cap in sorted(capabilities):
        files = capabilities[cap][:12]
        extra = f" (+{len(capabilities[cap]) - 12})" if len(capabilities[cap]) > 12 else ""
        lines.append(f"- `{cap}`: " + ", ".join(f"`{x}`" for x in files) + extra)
    return lines, capabilities


def do_hubs(graph: dict, top: int = 10) -> tuple[list[str], list]:
    """Top arquivos por degree centrality (onde o bug provavelmente mora)."""
    nodes = sorted(graph.get("nodes", []), key=lambda n: -n.get("deg", 0))[: max(1, top)]
    lines = [f"ASTOS hubs :: top {len(nodes)} por degree:"]
    payload = []
    for n in nodes:
        lines.append(f"- `{n['file']}` deg={n.get('deg', 0)} loc={n.get('loc', 0)} "
                     f"syms={n.get('symbols', 0)} caps={','.join(n.get('caps', [])) or '—'}")
        payload.append({"file": n["file"], "deg": n.get("deg"), "loc": n.get("loc")})
    return lines, payload


def do_slice(graph: dict, repo: Path | None, mod: str,
             write: bool = False) -> tuple[list[str], dict]:
    """Mapa só de uma pasta: arquivos + fronteira de 1 salto (poupe tokens)."""
    nodes = graph.get("nodes", [])
    key = mod.strip().strip("/")
    inside = [n for n in nodes
              if n.get("file") == key or n.get("file", "").startswith(key + "/")]
    if not inside:
        inside = [n for n in nodes
                  if n.get("mod") == key or key.lower() in n.get("file", "").lower()]
    if not inside:
        avail = sorted({n.get("file", "").split("/")[0] for n in nodes if n.get("file")})
        raise QueryError(f"pasta/módulo sem match: {mod!r} — tente: {', '.join(avail[:12])}")
    in_ids = {n["id"] for n in inside}
    by_id = {n["id"]: n for n in nodes}
    adj: dict[str, list[str]] = {}
    for s, t in graph.get("links", []):
        adj.setdefault(s, []).append(t)
    calls_by_src: dict[str, list[tuple[str, str]]] = {}
    for e in graph.get("call_edges", []):
        if len(e) >= 3:
            calls_by_src.setdefault(e[0], []).append((e[2], e[1]))
    # fronteira: vizinhos fora da fatia (imports + chamadas, ida e volta)
    frontier: dict[str, str] = {}
    for n in inside:
        for d in adj.get(n["id"], []):
            if d not in in_ids:
                frontier[d] = "import"
    for e in graph.get("call_edges", []):
        if len(e) >= 3:
            if e[0] in in_ids and e[1] not in in_ids:
                frontier[e[1]] = f"call:{e[2]}"
            elif e[1] in in_ids and e[0] not in in_ids:
                frontier[e[0]] = f"chamado por:{e[2]}"
    lines = [f"ASTOS slice `{key}` :: {len(inside)} arquivo(s) + {len(frontier)} na fronteira:"]
    payload_in, payload_out = [], []
    for n in sorted(inside, key=lambda x: -x.get("deg", 0)):
        segs = [f"`{n['file']}` [{n.get('lang', '?')}] deg={n.get('deg', 0)} loc={n.get('loc', 0)}"]
        if n.get("caps"):
            segs.append("caps:" + ",".join(n["caps"][:6]))
        if n.get("entry"):
            segs.append("entry")
        if n.get("todo_n"):
            segs.append(f"todo:{n['todo_n']}")
        if n.get("defs"):
            segs.append("def:" + _short_defs(n["defs"], cap=8))
        for c, t in calls_by_src.get(n["id"], [])[:6]:
            tgt = by_id.get(t, {}).get("file", t) if t in by_id else t
            segs.append(f"{c}()>`{tgt}`" if t in in_ids else f"{c}()→fora:`{tgt}`")
        lines.append("- " + " :: ".join(segs))
        payload_in.append(n["file"])
    if frontier:
        lines.append("fronteira (1 salto, leia só se precisar):")
        for fid, how in sorted(frontier.items(), key=lambda kv: by_id.get(kv[0], {}).get("file", kv[0])):
            f = by_id.get(fid, {}).get("file", fid)
            lines.append(f"  - `{f}` [{how}]")
            payload_out.append({"file": f, "via": how})
    caps = graph.get("capabilities", {}) or {}
    touched = sorted({c for c, fs in caps.items()
                      for fl in fs if not fl.startswith("manifest:")
                      for n in inside if n["file"] == fl} |
                     {c for n in inside for c in n.get("caps", [])})
    if touched:
        lines.append("caps na fatia: " + ", ".join(f"`{c}`" for c in touched))
    risks = graph.get("risks", {}) or {}
    rr = [g["file"] for g in risks.get("gods", []) if any(g["file"] == n["file"] for n in inside)]
    rt = [t for t in risks.get("todos", []) if any(t["file"] == n["file"] for n in inside)]
    if rr:
        lines.append("gods na fatia: " + ", ".join(f"`{x}`" for x in rr))
    if rt:
        lines.append("TODOs na fatia: " + "; ".join(f"`{t['file']}`x{t['n']}" for t in rt))
    if write:
        if repo is None:
            raise QueryError("--write precisa de repo (indisponível via MCP).")
        sdir = repo / ".astos" / "slices"
        sdir.mkdir(parents=True, exist_ok=True)
        safe = key.replace("/", "_") or "root"
        out = sdir / f"{safe}.md"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        lines.append(f"(salvo em `.astos/slices/{safe}.md`)")
    return lines, {"mod": key, "inside": payload_in,
                   "frontier": payload_out, "caps": touched}


def do_risks(graph: dict) -> tuple[list[str], dict]:
    """Onde o bug mora: god files, ciclos, fan-in/out, TODOs, entrypoints."""
    r = graph.get("risks", {}) or {}
    lines = ["ASTOS risks :: comece o debug por aqui:"]
    if r.get("gods"):
        lines.append("god files: " + ", ".join(
            f"`{g['file']}`(loc={g['loc']},syms={g['symbols']},deg={g['deg']})"
            for g in r["gods"][:8]))
    if r.get("cycles"):
        for cyc in r["cycles"][:5]:
            lines.append("ciclo: " + " -> ".join(f"`{x}`" for x in cyc))
    if r.get("fan_out"):
        lines.append("fan-out: " + ", ".join(f"`{d['file']}`({d['n']})" for d in r["fan_out"][:8]))
    if r.get("fan_in"):
        lines.append("fan-in: " + ", ".join(f"`{d['file']}`({d['n']})" for d in r["fan_in"][:8]))
    if r.get("todos"):
        lines.append("TODOs: " + "; ".join(
            f"`{t['file']}`x{t['n']}" for t in r["todos"][:8]))
    if r.get("todo_total") and not r.get("todos"):
        lines.append(f"TODOs: total {r['todo_total']}")
    if r.get("entries"):
        lines.append("entrypoints: " + ", ".join(f"`{e}`" for e in r["entries"][:10]))
    if r.get("orphans"):
        lines.append("órfãos: " + ", ".join(f"`{o}`" for o in r["orphans"][:10]))
    if len(lines) == 1:
        lines.append("(nenhum risco estrutural — repo pequeno/limpo)")
    return lines, r


def _porcelain(repo: Path, timeout: int = 10) -> list[str]:
    import subprocess
    p = subprocess.run(["git", "-C", str(repo), "status", "--porcelain=v1"],
                       capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise QueryError("fora de repo git (ou git ausente).")
    return (p.stdout or "").splitlines()


def _scanned_epoch(graph: dict, repo: Path) -> float | None:
    """Quando o mapa foi gerado (epoch). Fallback: mtime do graph.json."""
    try:
        from datetime import datetime
        raw = (graph.get("meta", {}) or {}).get("scanned_at", "")
        if raw:
            return datetime.fromisoformat(raw).timestamp()
    except (ValueError, TypeError):
        pass
    try:
        return (repo / ".astos" / "graph.json").stat().st_mtime
    except OSError:
        return None


def stale_note(repo: Path, graph: dict) -> str:
    """Checagem rápida (só git, ~100ms): '' se fresco ou sem git."""
    import subprocess
    try:
        scanned = _scanned_epoch(graph, repo)
        p = subprocess.run(["git", "-C", str(repo), "status", "--porcelain=v1"],
                           capture_output=True, text=True, timeout=8)
        if p.returncode != 0:
            return ""
        dirty = [ln for ln in (p.stdout or "").splitlines() if len(ln) >= 4]
        if dirty:
            return (f"⚠ mapa pode estar desatualizado ({len(dirty)} arquivo(s) sujos no git) "
                    f"— rode `astos -f`.")
        if scanned:
            q = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct"],
                               capture_output=True, text=True, timeout=8)
            try:
                if int((q.stdout or "0").strip()) > scanned:
                    return "⚠ commits novos desde o scan — rode `astos -f`."
            except ValueError:
                pass
    except Exception:
        pass
    return ""


def do_status(graph: dict, repo: Path) -> tuple[list[str], dict]:
    """Frescor do mapa: scan vs git vs arquivos (vale o `astos -f`?)."""
    import subprocess
    meta = graph.get("meta", {}) or {}
    scanned = _scanned_epoch(graph, repo)
    lines = [f"ASTOS status :: scan em {meta.get('scanned_at', '?')} · "
             f"{meta.get('files', '?')} arquivos · {meta.get('edges', '?')} deps · "
             f"{meta.get('call_edges', '?')} chamadas"]
    reasons, payload = [], {}
    # git: sujos + HEAD novo
    try:
        porcelain = _porcelain(repo)
        dirty = []
        for ln in porcelain:
            if len(ln) < 4:
                continue
            path = ln[3:].strip().strip('"')
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip().strip('"')
            dirty.append(path)
        payload["git_dirty"] = dirty
        lines.append(f"git: {len(dirty)} sujo(s)" + (f" ({', '.join(f'`{d}`' for d in dirty[:10])})" if dirty else " — limpo"))
        if dirty:
            reasons.append(f"{len(dirty)} arquivos sujos")
        try:
            q = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %cs %s"],
                               capture_output=True, text=True, timeout=8)
            head = (q.stdout or "").strip()
            if head:
                lines.append(f"HEAD: {head}")
                payload["head"] = head
            qc = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ct"],
                                capture_output=True, text=True, timeout=8)
            if head and scanned and int((qc.stdout or "0").strip()) > scanned:
                reasons.append("commits novos desde o scan")
                payload["head_newer"] = True
        except (ValueError, Exception):
            pass
    except QueryError:
        lines.append("git: fora de repo (checagem por mtime abaixo)")
        payload["git"] = False
    # mtime: arquivos de código mais novos que o mapa
    try:
        cache_mtime = (repo / ".astos" / "graph.json").stat().st_mtime
        newer, newest, total = [], 0.0, 0
        for p in _iter_code_files(repo):
            total += 1
            try:
                mt = p.stat().st_mtime
            except OSError:
                continue
            if mt > newest:
                newest = mt
            if mt > cache_mtime:
                newer.append(p.relative_to(repo).as_posix())
        payload["files_total"] = total
        payload["files_newer"] = sorted(newer)[:50]
        if newer:
            reasons.append(f"{len(newer)} arquivo(s) de código mais novos que o mapa")
            lines.append(f"mtime: {len(newer)} código(s) pós-scan ({', '.join(f'`{x}`' for x in sorted(newer)[:8])})")
        else:
            lines.append(f"mtime: {total} código(s), nenhum mais novo que o mapa")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"mtime: checagem falhou ({exc})")
    if reasons:
        lines.insert(1, "veredito: STALE — " + "; ".join(reasons) + " → rode `astos -f`.")
        payload["verdict"] = "STALE"
    else:
        lines.insert(1, "veredito: FRESH — mapa confiável.")
        payload["verdict"] = "FRESH"
    return lines, payload


def do_changed(graph: dict, repo: Path) -> tuple[list[str], dict]:
    """Sujos no git (live) + contexto do grafo: debugue aqui primeiro."""
    import subprocess
    try:
        porcelain = _porcelain(repo)
    except QueryError:
        return ["ASTOS changed :: fora de repo git (ou git ausente) — nada a mostrar."], {"changed": []}
    except Exception:
        return ["ASTOS changed :: git falhou — nada a mostrar."], {"changed": []}
    stats: dict[str, str] = {}
    try:
        q = subprocess.run(["git", "-C", str(repo), "diff", "--numstat"],
                           capture_output=True, text=True, timeout=10)
        for line in (q.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                stats[parts[2]] = f"+{parts[0]}/-{parts[1]}"
    except Exception:
        pass
    dirty: list[tuple[str, str]] = []  # (status, path)
    for line in porcelain:
        if len(line) < 4:
            continue
        st, path = line[:2].strip() or "=", line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip().strip('"')
        if path:
            dirty.append((st, path))
    if not dirty:
        return ["ASTOS changed :: árvore limpa — nada sujo no git."], {"changed": []}
    by_file = {n["file"]: n for n in graph.get("nodes", [])}
    adj: dict[str, list[str]] = {}
    for s, t in graph.get("links", []):
        adj.setdefault(s, []).append(t)
        adj.setdefault(t, []).append(s)
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    fid_of = {n["file"]: n["id"] for n in graph.get("nodes", [])}
    lines = [f"ASTOS changed :: {len(dirty)} arquivo(s) sujos (live) — ordem de debug:"]
    payload, stale = [], []
    scored = []
    for st, path in dirty:
        n = by_file.get(path)
        deg = n.get("deg", 0) if n else -1
        scored.append((deg, st, path, n))
    scored.sort(key=lambda t: -t[0])
    for deg, st, path, n in scored:
        if n is None:
            stale.append(path)
            continue
        nb = sorted({by_id[i]["file"] for i in adj.get(fid_of[path], []) if i in by_id})[:6]
        stat = f" {stats[path]}" if path in stats else ""
        line = (f"- `{path}` [{st or '='}]{stat} deg={deg} "
                f"caps={','.join(n.get('caps', [])) or '—'}"
                f"{' entry' if n.get('entry') else ''}"
                f"{' todo:' + str(n.get('todo_n')) if n.get('todo_n') else ''}"
                f"{' viz:' + ','.join(f'`{x}`' for x in nb) if nb else ''}")
        lines.append(line)
        payload.append({"file": path, "status": st, "stat": stats.get(path, ""),
                        "deg": deg, "caps": n.get("caps", []),
                        "neighbors": nb})
    if stale:
        lines.append("fora do mapa (rode `astos -f`): " + ", ".join(f"`{x}`" for x in stale[:10]))
    return lines, {"changed": payload, "stale": stale}


def do_hotspots(graph: dict, repo: Path, days: int = 30,
                top: int = 10) -> tuple[list[str], dict]:
    """Churn recente (git log): arquivos mais mexidos × god files. Perigoso + instável."""
    import subprocess
    try:
        p = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={max(1, days)} days ago",
             "--numstat", "--pretty=format:COMMIT:%h"],
            capture_output=True, text=True, timeout=20)
        if p.returncode != 0:
            raise QueryError("fora de repo git (ou git ausente).")
        raw = (p.stdout or "").splitlines()
    except QueryError:
        return ["ASTOS hotspots :: fora de repo git (ou git ausente) — nada a mostrar."], {"hotspots": []}
    except Exception:
        return ["ASTOS hotspots :: git log falhou — nada a mostrar."], {"hotspots": []}
    commits: dict[str, set[str]] = {}
    churn: dict[str, int] = {}
    cur = ""
    for ln in raw:
        if ln.startswith("COMMIT:"):
            cur = ln[7:].strip()
        elif "\t" in ln and cur:
            parts = ln.split("\t")
            if len(parts) == 3:
                path = parts[2].strip().strip('"')
                if " => " in path:  # rename: fica com o destino
                    path = path.rsplit(" => ", 1)[1].strip().strip("{}").strip('"')
                try:
                    delta = (int(parts[0]) if parts[0] != "-" else 0) + \
                            (int(parts[1]) if parts[1] != "-" else 0)
                except ValueError:
                    delta = 0
                commits.setdefault(path, set()).add(cur)
                churn[path] = churn.get(path, 0) + delta
    if not commits:
        return [f"ASTOS hotspots :: nenhum commit nos últimos {days} dias."], {"hotspots": []}
    gods = {g["file"] for g in (graph.get("risks", {}) or {}).get("gods", [])}
    by_file = {n["file"]: n for n in graph.get("nodes", [])}
    ranked = sorted(commits, key=lambda f: (-len(commits[f]), -churn.get(f, 0)))
    lines = [f"ASTOS hotspots :: churn dos últimos {days} dias (god = ⚠):"]
    payload = []
    for f in ranked[: max(1, top)]:
        n = by_file.get(f)
        god = " ⚠god" if f in gods else ""
        extra = ""
        if n is not None:
            extra = (f" deg={n.get('deg', 0)}"
                     f"{' entry' if n.get('entry') else ''}"
                     f"{' caps:' + ','.join(n.get('caps', [])) if n.get('caps') else ''}")
        elif "." not in f.rsplit("/", 1)[-1]:
            extra = " (fora do mapa)"
        lines.append(f"- `{f}` {len(commits[f])} commits, {churn.get(f, 0)} linhas churnadas{god}{extra}")
        payload.append({"file": f, "commits": len(commits[f]),
                        "churn": churn.get(f, 0), "god": f in gods})
    return lines, {"hotspots": payload, "days": days}


def _is_test_file(rel: str) -> bool:
    low = rel.lower()
    parts = low.split("/")
    if any(p in ("test", "tests", "__tests__", "__test__", "testing") for p in parts):
        return True
    stem = parts[-1]
    return (stem.startswith("test_") or stem.startswith("tests_")
            or ".test." in stem or stem.endswith("_test.py")
            or stem.endswith(".spec.ts") or stem.endswith(".spec.js")
            or stem.endswith("test.dart") or stem.endswith("_test.dart"))


def _test_candidates(stem: str) -> set[str]:
    """Nomes-base que um teste do módulo `stem` costuma ter (e vice-versa)."""
    base = stem
    if base.endswith("Test") and len(base) > 4:  # FooTest (Java/Kotlin)
        base = base[:-4]
    for suf in (".test", ".spec", "_test", "test_", "tests_", "_spec"):
        if base.endswith(suf):
            base = base[: -len(suf)] or base
            break
    else:
        if base.startswith("test_"):
            base = base[5:]
    cands = set()
    for pat in ("test_{b}", "{b}_test", "{b}.test", "{b}.spec", "{b}Test", "Test{b}"):
        cands.add(pat.format(b=base))
    cands.add(base)
    return cands


def do_tests(graph: dict, fname: str | None = None) -> tuple[list[str], dict]:
    """Mapa teste↔fonte: quem testa X, o que Y testa, ou todos os testes.

    Sem --file: lista todos os arquivos de teste do repo.
    Com --file: testes que cobrem o arquivo (nome + dependência real) e,
    se o arquivo FOR um teste, as fontes que ele cobre.
    """
    nodes = graph.get("nodes", [])
    by_id = {n["id"]: n for n in nodes}
    tests = [n for n in nodes if _is_test_file(n.get("file", ""))]
    if not fname:
        lines = [f"ASTOS tests :: {len(tests)} arquivo(s) de teste no mapa:"]
        payload = []
        for n in sorted(tests, key=lambda x: x.get("file", "")):
            deps = sorted({t for s, t in graph.get("links", []) if s == n["id"]})
            dep_s = ",".join(f"`{by_id[d]['file']}`" for d in deps[:6] if d in by_id)
            lines.append(f"- `{n['file']}`" + (f" cobre: {dep_s}" if dep_s else ""))
            payload.append(n["file"])
        if not tests:
            lines.append("(nenhum teste detectado por convenção de nome)")
        return lines, {"tests": payload}
    nid = match_id(graph, fname)
    if not nid:
        raise QueryError(f"arquivo não encontrado: {fname!r}")
    n = by_id[nid]
    f = lambda i: by_id.get(i, {}).get("file", i)
    lines = [f"ASTOS tests :: `{n['file']}`:"]
    payload: dict = {"file": n["file"]}
    if _is_test_file(n["file"]):
        # é teste: o que ele cobre (nome + deps reais)
        stem = n["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        cands = _test_candidates(stem)
        named = [m["file"] for m in nodes
                 if m["id"] != nid and not _is_test_file(m.get("file", ""))
                 and m["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0] in cands]
        deps = sorted({t for s, t in graph.get("links", []) if s == nid and t in by_id
                       and not _is_test_file(by_id[t]["file"])})
        calls = sorted({e[1] for e in graph.get("call_edges", [])
                        if len(e) >= 3 and e[0] == nid and e[1] in by_id})
        covers = sorted(set(named) | {f(i) for i in deps} | {f(i) for i in calls})
        lines.append("cobre (rode p/ verificar mudança): " +
                     (", ".join(f"`{x}`" for x in covers[:15]) or "—"))
        payload["covers"] = covers
    else:
        # é fonte: quem a testa (nome + dependentes reais que são teste)
        stem = n["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
        cands = _test_candidates(stem)
        named = [m["file"] for m in tests
                 if m["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0] in cands]
        rdeps = sorted({s for s, t in graph.get("links", []) if t == nid
                        and s in by_id and _is_test_file(by_id[s]["file"])})
        callers = sorted({e[0] for e in graph.get("call_edges", [])
                          if len(e) >= 3 and e[1] == nid and e[0] in by_id
                          and _is_test_file(by_id[e[0]]["file"])})
        testers = sorted(set(named) | {f(i) for i in rdeps} | {f(i) for i in callers})
        lines.append("testado por (rode p/ verificar mudança): " +
                     (", ".join(f"`{x}`" for x in testers[:15]) or "— (nenhum teste achado)"))
        payload["tested_by"] = testers
    return lines, payload


def do_dead(graph: dict) -> tuple[list[str], dict]:
    """Provável código morto: inalcançável desde os entrypoints (grafo direcionado).

    Conservador: rotas por string (Flutter Navigator, lazy imports) e reflection
    podem esconder uso real — confirme antes de deletar.
    """
    nodes = graph.get("nodes", [])
    by_id = {n["id"]: n for n in nodes}
    fid_of = {n["file"]: n["id"] for n in nodes}
    entries = [f for f in (graph.get("risks", {}) or {}).get("entries", []) if f in fid_of]
    if not entries:
        entries = [n["file"] for n in nodes if n.get("entry") and n["file"] in fid_of]
    if not entries:
        return ["ASTOS dead :: sem entrypoints mapeados — rode `astos risks` e confira."], {"dead": []}
    adj: dict[str, list[str]] = {}
    for s, t in graph.get("links", []):
        adj.setdefault(s, []).append(t)
    for e in graph.get("call_edges", []):
        if len(e) >= 3:
            adj.setdefault(e[0], []).append(e[1])
    reached, stack = set(), [fid_of[f] for f in entries]
    while stack:
        cur = stack.pop()
        if cur in reached:
            continue
        reached.add(cur)
        stack.extend(x for x in adj.get(cur, []) if x not in reached)
    dead = [by_id[i] for i in by_id if i not in reached and not _is_test_file(by_id[i]["file"])]
    dead.sort(key=lambda n: (-n.get("loc", 0), n.get("file", "")))
    lines = [f"ASTOS dead :: {len(dead)} inalcançável(is) desde {len(entries)} entrypoint(s) "
             f"({', '.join(f'`{e}`' for e in entries[:5])}):"]
    payload = []
    for n in dead[:20]:
        lines.append(f"- `{n['file']}` loc={n.get('loc', 0)} deg={n.get('deg', 0)} "
                     f"syms={n.get('symbols', 0)}")
        payload.append({"file": n["file"], "loc": n.get("loc"),
                        "deg": n.get("deg"), "symbols": n.get("symbols")})
    if len(dead) > 20:
        lines.append(f"(+{len(dead) - 20} omitidos)")
    if not dead:
        lines.append("(nada inalcançável — tudo é alcançado ou é teste)")
    return lines, {"dead": payload, "entries": entries}


def _read_lines(repo: Path, rel: str) -> list[str]:
    try:
        return (repo / rel).read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def _py_body(repo: Path, rel: str, name: str) -> tuple[int, list[str], list[str]] | None:
    """Corpo da def Python (início, linhas, chamadas internas) via AST."""
    import ast
    try:
        src = (repo / rel).read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
    except (OSError, SyntaxError, ValueError):
        return None
    short = name.split(".")[-1]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == short:
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start + 40
            body = src.splitlines()[start - 1:end]
            calls: list[str] = []
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                    if sub.func.id not in calls:
                        calls.append(sub.func.id)
            return start, body, calls[:20]
    return None


def do_explain(graph: dict, repo: Path, symbol: str | None = None,
               fname: str | None = None, line: int = 0,
               window: int = 30) -> tuple[list[str], dict]:
    """Trecho exato do código: definição + corpo + quem chama + chamados.

    `symbol`: nome de função/classe (exato primeiro, substring como fallback).
    `fname` (+`line` opcional): janela do arquivo com a def que contém a linha.
    """
    if not symbol and not fname:
        raise QueryError("informe --symbol X ou --file F [--line N].")
    by_id = {n["id"]: n for n in graph.get("nodes", [])}
    targets: list[tuple[dict, dict]] = []  # (node, def)
    if symbol:
        short = symbol.split(".")[-1]
        for n in graph.get("nodes", []):
            for d in n.get("defs", []):
                dn = str(d.get("n", ""))
                if dn == symbol or dn.split(".")[-1] == short:
                    targets.append((n, d))
        targets.sort(key=lambda t: (-t[0].get("deg", 0), t[1].get("l", 0)))
        if not targets:
            # fallback: substring — só aponta, sem despejar código
            hits = []
            for n in graph.get("nodes", []):
                for d in n.get("defs", []):
                    if symbol.lower() in str(d.get("n", "")).lower():
                        hits.append((n, d))
            hits.sort(key=lambda t: (-t[0].get("deg", 0), t[1].get("l", 0)))
            if not hits:
                raise QueryError(f"símbolo sem match: {symbol!r} — tente `astos q --symbol {symbol}`.")
            lines = [f"ASTOS explain `{symbol}` :: sem match exato — {len(hits)} substring(s), refine:"]
            for n, d in hits[:10]:
                lines.append(f"  - `{n['file']}` {d.get('n')}:L{d.get('l', 0)}")
            return lines, {"symbol": symbol, "exact": [],
                           "suggest": [f"{n['file']}:{d.get('l', 0)}" for n, d in hits[:10]]}
    else:
        nid = match_id(graph, fname or "")
        if not nid:
            raise QueryError(f"arquivo não encontrado: {fname!r}")
        n = by_id[nid]
        defs = sorted(n.get("defs", []), key=lambda d: d.get("l", 0))
        at = line or (defs[0].get("l", 1) if defs else 1)
        encl = None
        for d in defs:
            if d.get("l", 0) <= at:
                encl = d
        if encl is None and defs:
            encl = defs[0]
        if encl is None:
            raise QueryError(f"`{n['file']}` sem defs mapeadas — use `astos slice` + leitura direta.")
        targets = [(n, encl)]
    lines = [f"ASTOS explain `{symbol or fname}` :: {len(targets)} definição(ões) exata(s):"]
    payload_defs = []
    for n, d in targets[:3]:
        dn, dl = str(d.get("n", "?")), int(d.get("l", 0) or 0)
        short = dn.split(".")[-1]
        src_lines = _read_lines(repo, n["file"])
        body: list[str] = []
        if n.get("lang") == "python":
            found = _py_body(repo, n["file"], dn)
            if found:
                dl, body, _ = found
        if not body and src_lines and dl:
            lo = max(1, dl - window)
            hi = min(len(src_lines), dl + (120 if n.get("lang") == "python" else window))
            body = src_lines[lo - 1:hi]
        cut = ""
        if len(body) > 120:
            cut = f"… (+{len(body) - 120} linhas cortadas)"
            body = body[:120]
        callers = sorted({e[0] for e in graph.get("call_edges", [])
                          if len(e) >= 3 and e[2] == short and e[1] == n["id"]})
        callees = sorted({e[2] for e in graph.get("call_edges", [])
                          if len(e) >= 3 and e[0] == n["id"]})[:15]
        fcall = lambda i: by_id.get(i, {}).get("file", i)
        lines.append(f"--- `{n['file']}` {dn}:L{dl} ({d.get('k', '?')})")
        lines.extend(body)
        if cut:
            lines.append(cut)
        lines.append(f"chamadores de {short}(): " +
                     (", ".join(f"`{fcall(i)}`" for i in sorted(callers)[:8]) or "—"))
        lines.append("chamados pelo arquivo: " + (", ".join(f"`{c}()`" for c in callees) or "—"))
        payload_defs.append({"file": n["file"], "def": dn, "line": dl,
                             "body": body, "callers": [fcall(i) for i in sorted(callers)],
                             "callees": callees})
    if len(targets) > 3:
        lines.append(f"(+{len(targets) - 3} definições exatas omitidas)")
    return lines, {"symbol": symbol or fname, "defs": payload_defs}
