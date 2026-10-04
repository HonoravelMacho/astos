"""Mapeamento do repositório: arquivos de código -> grafo de dependências.

Varre código-fonte a partir de uma raiz e extrai dependências:
- Python (``*.py``): imports via ``ast`` (preciso).
- C/C++ (``*.c *.h *.cpp *.hpp *.cc *.cxx``): ``#include "..."`` locais
  (resolvidos por basename/caminho) + ``#include <...>`` do sistema
  (registrados como dependências externas no HUD) e contagem de
  definições de função (heurística por regex) para dimensionar os nós.

Calcula o grau (degree centrality) de cada nó.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

IGNORE_DIRS = {
    ".astos", ".git", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", "dist", "build", "node_modules", ".tox", ".eggs",
}

LANG_OF = {
    ".py": "python",
    ".c": "c", ".h": "c",
    ".cpp": "c", ".hpp": "c", ".cc": "c", ".cxx": "c", ".hxx": "c",
}

SUPPORTED_LABEL = ".py, .c, .h, .cpp, .hpp, .cc, .cxx"

PALETTE = [
    "#22d3ee", "#f472b6", "#34d399", "#fbbf24", "#c084fc", "#818cf8",
    "#4ade80", "#f97316", "#60a5fa", "#e879f9", "#facc15", "#94a3b8",
]

RE_C_INCLUDE = re.compile(r'^\s*#\s*include\s*([<"])([^>"]+)[>"]', re.MULTILINE)
RE_C_COMMENTS = re.compile(r'//[^\n]*|/\*.*?\*/', re.DOTALL)
RE_C_FUNC = re.compile(r'([A-Za-z_]\w*)\s*\([^;(){}]*\)\s*\{')
C_KEYWORDS = {
    "if", "for", "while", "switch", "return", "sizeof", "do", "else",
    "case", "typedef", "struct", "enum", "union", "catch", "printf",
}


def _iter_code_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if Path(fn).suffix.lower() in LANG_OF:
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


def _parse_c_source(src: str) -> tuple[list[str], list[str], int]:
    """Retorna (includes locais crus, imports externos p/ HUD, nº de funções)."""
    code = RE_C_COMMENTS.sub(" ", src)
    local, external = [], []
    for delim, target in RE_C_INCLUDE.findall(code):
        target = target.strip()
        if delim == '"':
            local.append(target)
        else:
            external.append(f"<{target}>")
    funcs = 0
    for m in RE_C_FUNC.finditer(code):
        name = m.group(1)
        if name not in C_KEYWORDS:
            # exige "tipo nome(" — evita contar chamadas: olha o token anterior
            before = code[max(0, m.start(1) - 60):m.start(1)].split()
            if before and re.match(r'^[A-Za-z_][\w\*]*$', before[-1]) and before[-1] not in C_KEYWORDS:
                funcs += 1
            elif not before:
                funcs += 1
    # dedup preservando ordem
    local = list(dict.fromkeys(local))
    external = list(dict.fromkeys(external))
    return local, external, funcs


def _resolve_c_include(raw: str, by_rel: dict[str, str], by_base: dict[str, str]) -> str | None:
    raw = raw.strip().lstrip("./")
    if raw in by_rel:
        return by_rel[raw]
    base = raw.rsplit("/", 1)[-1]
    if base in by_base:
        return by_base[base]
    # sufixo: "sub/x.h" casa com "src/sub/x.h"
    for rel, mod_id in by_rel.items():
        if rel == raw or rel.endswith("/" + raw):
            return mod_id
    return None


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
    files = sorted(_iter_code_files(root))

    module_index: dict[str, str] = {}  # module_name -> relpath str
    by_rel: dict[str, str] = {}        # relpath -> module_name (p/ #include)
    by_base: dict[str, str] = {}       # basename -> module_name (p/ #include)
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
        by_rel[rel] = base
        by_base.setdefault(Path(rel).name, base)
        lang = LANG_OF.get(path.suffix.lower(), "python")
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            src = ""
        if lang == "python":
            try:
                tree = ast.parse(src)
                imports = _extract_imports(tree)
                # conta símbolos de alto nível para enriquecer o HUD
                syms = sum(
                    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    for n in tree.body
                )
            except (SyntaxError, ValueError):
                imports, syms = [], 0
            records.append({"id": base, "rel": rel, "lang": lang,
                            "imports_raw": imports, "externals": [], "symbols": syms})
        else:  # C / C++
            local_inc, externals, funcs = _parse_c_source(src)
            records.append({"id": base, "rel": rel, "lang": lang,
                            "imports_raw": local_inc, "externals": externals,
                            "symbols": funcs})

    # cor por módulo top-level (primeiro diretório ou "root")
    groups = sorted({r["rel"].split("/")[0] if "/" in r["rel"] else "root" for r in records})
    color_of = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}

    nodes: list[dict] = []
    by_id = {}
    for r in records:
        rel = r["rel"]
        mod = "root" if "/" not in rel else rel.split("/")[0]
        label = Path(rel).stem + Path(rel).suffix  # exibe extensão (main.c ≠ main.h)
        shown_imports = list(r["imports_raw"]) + list(r.get("externals", []))
        node = {
            "id": r["id"],
            "label": label,
            "file": rel,
            "lang": r.get("lang", "python"),
            "mod": mod,
            "color": color_of.get(mod, "#22d3ee"),
            "imports": shown_imports,
            "symbols": r["symbols"],
            "deg": 0,
        }
        nodes.append(node)
        by_id[r["id"]] = node

    links: list[list[str]] = []
    seen_edges = set()
    for r in records:
        src = r["id"]
        if r.get("lang") == "c":
            resolver = lambda raw: _resolve_c_include(raw, by_rel, by_base)
        else:
            resolver = lambda raw: _resolve_local(raw, module_index)
        for raw in r["imports_raw"]:
            dst = resolver(raw)
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
            "langs": sorted({r.get("lang", "python") for r in records}),
            "supported": SUPPORTED_LABEL,
        },
    }
