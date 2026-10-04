"""Mapeamento AST do repositório: módulos Python -> grafo de dependências.

Varre ``**/*.py`` a partir de uma raiz, extrai imports via ``ast``,
resolve arestas locais (módulo -> módulo) e calcula o grau
(degree centrality) de cada nó.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

IGNORE_DIRS = {
    ".astos", ".git", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", "dist", "build", "node_modules", ".tox", ".eggs",
}

PALETTE = [
    "#22d3ee", "#f472b6", "#34d399", "#fbbf24", "#c084fc", "#818cf8",
    "#4ade80", "#f97316", "#60a5fa", "#e879f9", "#facc15", "#94a3b8",
]


def _iter_py_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    name = ".".join(parts) if parts else path.stem
    return name or path.stem


def _extract_imports(tree: ast.AST) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name:
                    imports.append(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = ("." * (node.level or 0)) + node.module
                imports.append(mod)
            else:
                for a in node.names:
                    imports.append((".", node.level, a.name))
    # normaliza tuplas residuais
    out: list[str] = []
    for i in imports:
        if isinstance(i, tuple):
            out.append("." * i[1] + i[2])
        else:
            out.append(i)
    # dedup preservando ordem
    seen, uniq = set(), []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def _resolve_local(raw: str, module_index: dict[str, str]) -> str | None:
    """Tenta mapear um import bruto para um id de módulo local."""
    cand = raw.lstrip(".")
    if not cand:
        return None
    if cand in module_index:
        return cand
    # tenta prefixos progressivos (a.b.c -> a.b -> a)
    parts = cand.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in module_index:
            return prefix
    # tenta sufixo: ex. importa "pkg.mod" mas índice tem "src.pkg.mod"
    for mod_id in module_index:
        if mod_id == cand or mod_id.endswith("." + cand):
            return mod_id
    return None


def scan_repository(root: str | Path) -> dict:
    root = Path(root).resolve()
    files = sorted(_iter_py_files(root))

    module_index: dict[str, str] = {}  # module_name -> relpath str
    records: list[dict] = []
    for path in files:
        mod = _module_name(root, path)
        # evita colisão de ids
        base, k = mod, 2
        while base in module_index:
            base = f"{mod}~{k}"
            k += 1
        rel = path.relative_to(root).as_posix()
        module_index[base] = rel
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
            imports = _extract_imports(tree)
            # conta símbolos de alto nível para enriquecer o HUD
            syms = sum(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                for n in tree.body
            )
        except (SyntaxError, ValueError):
            imports, syms = [], 0
        records.append({"id": base, "rel": rel, "imports_raw": imports, "symbols": syms})

    # cor por módulo top-level (primeiro diretório ou "root")
    groups = sorted({r["rel"].split("/")[0] if "/" in r["rel"] else "root" for r in records})
    color_of = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}

    nodes: list[dict] = []
    by_id = {}
    for r in records:
        rel = r["rel"]
        mod = "root" if "/" not in rel else rel.split("/")[0]
        label = Path(rel).stem
        node = {
            "id": r["id"],
            "label": label,
            "file": rel,
            "mod": mod,
            "color": color_of.get(mod, "#22d3ee"),
            "imports": r["imports_raw"],
            "symbols": r["symbols"],
            "deg": 0,
        }
        nodes.append(node)
        by_id[r["id"]] = node

    links: list[list[str]] = []
    seen_edges = set()
    for r in records:
        src = r["id"]
        for raw in r["imports_raw"]:
            dst = _resolve_local(raw, module_index)
            if dst and dst != src and (src, dst) not in seen_edges:
                seen_edges.add((src, dst))
                links.append([src, dst])

    # degree centrality (in + out, não-direcionado para o HUD)
    deg: dict[str, int] = {n["id"]: 0 for n in nodes}
    for s, t in links:
        deg[s] = deg.get(s, 0) + 1
        deg[t] = deg.get(t, 0) + 1
    for n in nodes:
        n["deg"] = deg.get(n["id"], 0)
        n["size"] = round(6 + min(n["deg"], 30) * 0.9 + min(n["symbols"], 20) * 0.25, 2)

    # ordena por grau (hubs primeiro — bom para revelação progressiva)
    nodes.sort(key=lambda n: -n["deg"])

    return {
        "nodes": nodes,
        "links": links,
        "mods": color_of,
        "meta": {
            "root": str(root),
            "files": len(files),
            "edges": len(links),
        },
    }
