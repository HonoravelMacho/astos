"""CLI do ASTOS: `astos` escaneia; `astos q/trace/impact/caps/hubs/risks` consulta barato."""

from __future__ import annotations

import json
import time
import webbrowser
from pathlib import Path

import click

from .generator import generate, generate_city, generate_map
from .parser import SUPPORTED_LABEL, scan_repository
from .queries import (
    QueryError,
    do_caps,
    do_changed,
    do_dead,
    do_explain,
    do_hotspots,
    do_hubs,
    do_impact,
    do_q,
    do_risks,
    do_slice,
    do_status,
    do_tests,
    do_trace,
    load_graph,
)

AGENTS_START = "<!-- ASTOS:START -->"
AGENTS_END = "<!-- ASTOS:END -->"
AGENTS_BLOCK = """<!-- ASTOS:START -->
## Mapa do repositório (ASTOS)
- Antes de explorar o código (e ao se perder no meio de um debug), leia `.astos/map.md`: arquivos, dependências, hubs, capabilities (câmera/hardware), riscos (god files, ciclos, TODOs), símbolos com linha e chamadas entre arquivos.
- Detalhe completo em `.astos/graph.json`; visual 3D para humanos em `.astos/index.html` e palácio em `.astos/city.html` (botão [🏛 PALÁCIO]).
- Mapa desatualizado? Rode `astos -f` para regenerar sem abrir o navegador (`astos` sozinho abre o 3D).
- REGRA OBRIGATÓRIA: `astos -f` é sempre o ÚLTIMO comando de terminal de cada resposta que alterar código — sem exceção, sem abrir o navegador. O mapa nunca pode ficar desatualizado.
- Economize tokens: prefira queries a grep — `astos q --symbol X`, `astos q --cap camera`, `astos trace --from A --to B`, `astos impact --file F`, `astos caps`, `astos hubs`, `astos risks`, `astos slice <pasta>`, `astos changed`, `astos status`, `astos explain --symbol X`, `astos hotspots`, `astos dead`, `astos tests --file X`.
- Com MCP (`astos mcp --path .`), chame as mesmas queries como tools, sem shell.
- Se existir `graphify-out/graph.json` (Graphify), prefira-o em perguntas semânticas ("como X funciona"); use o mapa ASTOS para estrutura, hardware e dependências.
<!-- ASTOS:END -->"""


def ensure_agents_md(repo: Path) -> str:
    """Edição cirúrgica no AGENTS.md: cria ou anexa/atualiza só o bloco ASTOS.

    Nunca remove nem altera o conteúdo original: se o bloco marcado já
    existe ele é substituído in-place; senão é anexado ao final. Retorna
    a ação executada ('criado' | 'anexado' | 'atualizado').
    """
    target = repo / "AGENTS.md"
    if not target.exists():
        target.write_text("# AGENTS.md\n\n" + AGENTS_BLOCK + "\n", encoding="utf-8")
        return "criado"
    text = target.read_text(encoding="utf-8")
    if AGENTS_START in text and AGENTS_END in text:
        import re as _re
        pattern = _re.compile(_re.escape(AGENTS_START) + r".*?" + _re.escape(AGENTS_END),
                              _re.DOTALL)
        target.write_text(pattern.sub(AGENTS_BLOCK, text, count=1), encoding="utf-8")
        return "atualizado"
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    target.write_text(text + sep + AGENTS_BLOCK + "\n", encoding="utf-8")
    return "anexado"


def _do_scan(repo: Path, full: bool, no_open: bool, no_agents: bool,
             quiet_browser: bool = False, compact: bool | None = None) -> None:
    astos_dir = repo / ".astos"
    index = astos_dir / "index.html"
    city = astos_dir / "city.html"
    cache = astos_dir / "graph.json"

    existed = astos_dir.exists()
    astos_dir.mkdir(parents=True, exist_ok=True)

    if full and cache.exists():
        cache.unlink()
        click.echo("ASTOS :: varredura completa do zero — cache descartado.")

    if not existed:
        click.echo(f"ASTOS :: inicializando observer em {repo}")
    else:
        click.echo("ASTOS :: .astos/ encontrada — atualizando dados incrementalmente...")

    t0 = time.time()
    graph = scan_repository(repo)
    graph["meta"]["generated_in_s"] = round(time.time() - t0, 2)
    graph["meta"]["full_rescan"] = bool(full) or not existed
    from datetime import datetime, timezone
    graph["meta"]["scanned_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cache.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    generate(index, graph)
    generate_city(city, graph)
    mmap = generate_map(astos_dir / "map.md", graph, compact=compact)

    n, e = len(graph["nodes"]), len(graph["links"])
    ce = len(graph.get("call_edges", []))
    caps = len(graph.get("capabilities", {}))
    mode = graph.get("meta", {}).get("map_mode", "?")
    if n == 0:
        click.echo(
            f"ASTOS :: AVISO: nenhum arquivo suportado ({SUPPORTED_LABEL}) "
            f"encontrado em {repo} — o grafo foi gerado vazio."
        )
    else:
        click.echo(
            f"ASTOS :: {n} nós · {e} arestas · {ce} chamada(s) · {caps} cap(s) · mapa:{mode} "
            f"-> {index.name} + {city.name} + {mmap.name} (100% offline)"
        )
    if not no_agents:
        try:
            action = ensure_agents_md(repo)
            click.echo(f"ASTOS :: bloco do mapa {action} em AGENTS.md (cirúrgico, original preservado).")
        except OSError as exc:
            click.echo(f"ASTOS :: AVISO: não foi possível atualizar AGENTS.md: {exc}")
    if not no_open:
        try:
            webbrowser.open(index.as_uri())
            click.echo("ASTOS :: interface aberta no navegador padrão.")
        except Exception as exc:  # noqa: BLE001
            click.echo(f"ASTOS :: não foi possível abrir o navegador: {exc}")
            click.echo(f"ASTOS :: abra manualmente: {index}")
    click.echo("ASTOS :: dica: 'astos -f' atualiza sem browser · 'astos' abre o 3D · 'astos risks' onde o bug mora.")


# ---------------------------------------------------------------------------
# Queries com teto de tokens (leem .astos/graph.json, sem re-scan).
# Lógica em `astos/queries.py` (pura, compartilhada com o MCP);
# aqui só wrappers finos de CLI.
# ---------------------------------------------------------------------------

def _load_graph(root: str) -> tuple[dict, Path]:
    global _LAST_ROOT, _LAST_GRAPH
    try:
        graph, repo = load_graph(root)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _LAST_ROOT, _LAST_GRAPH = repo, graph
    return graph, repo


_LAST_ROOT: Path | None = None
_LAST_GRAPH: dict | None = None


def _match_id(graph: dict, needle: str) -> str | None:
    from .queries import match_id
    return match_id(graph, needle)


def _print_capped(lines: list[str], budget: int, as_json: bool, payload: object = None) -> None:
    """Orçamento aproximado: 1 token ≈ 4 chars. Corta com aviso, nunca estoura."""
    if not as_json and _LAST_ROOT is not None and _LAST_GRAPH is not None:
        from .queries import stale_note
        try:
            warn = stale_note(_LAST_ROOT, _LAST_GRAPH)
        except Exception:
            warn = ""
        if warn:
            lines = [warn] + list(lines)
    if as_json:
        text = json.dumps(payload if payload is not None else lines, ensure_ascii=False, indent=1)
        click.echo(text[: budget * 4])
        return
    out, used = [], 0
    for ln in lines:
        cost = len(ln) // 4 + 1
        if used + cost > budget and out:
            out.append(f"… (+{len(lines) - len(out)} linhas cortadas pelo --budget {budget})")
            break
        out.append(ln)
        used += cost
    click.echo("\n".join(out) if out else "(vazio)")


def _neighbors(graph: dict, nid: str) -> tuple[list[str], list[str], list[str]]:
    from .queries import neighbors
    return neighbors(graph, nid)


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-a", "--all", "full", is_flag=True,
              help="Força varredura completa do zero (ignora cache incremental).")
@click.option("-f", "--force", is_flag=True, default=False,
              help="Atualiza tudo igual ao -a mas sem abrir o navegador (só arquivos).")
@click.option("--no-open", is_flag=True, default=False,
              help="Gera os arquivos sem abrir o navegador.")
@click.option("--no-agents", is_flag=True, default=False,
              help="Não cria nem altera o AGENTS.md do repositório.")
@click.option("--compact/--no-compact", default=None,
              help="Força map.md compacto (só índice) ou completo (padrão: auto).")
@click.option("--path", "root", default=".", type=click.Path(exists=True, file_okay=False),
              help="Raiz do repositório a analisar (padrão: diretório atual).")
@click.pass_context
def main(ctx: click.Context, full: bool, force: bool, no_open: bool, no_agents: bool,
         compact: bool | None, root: str) -> None:
    """ASTOS — Abstract Syntax Tree Observer Service (3D offline + queries)."""
    ctx.ensure_object(dict)
    if force:
        full, no_open = True, True
    ctx.obj["root"], ctx.obj["full"] = root, full
    if ctx.invoked_subcommand is None:
        _do_scan(Path(root).resolve(), full, no_open, no_agents,
                 quiet_browser=force, compact=compact)


@main.command("q")
@click.option("--symbol", default=None, help="Substring de símbolo (ex: CameraController).")
@click.option("--cap", default=None, help="Capability (ex: camera, location, bluetooth).")
@click.option("--file", "fname", default=None, help="Substring de caminho de arquivo.")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=2000, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def q(symbol: str | None, cap: str | None, fname: str | None,
      root: str, budget: int, as_json: bool) -> None:
    """Busca barata: símbolos, capabilities e arquivos (use em vez de grep)."""
    graph, _ = _load_graph(root)
    try:
        lines, payload = do_q(graph, symbol, cap, fname)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


@main.command("trace")
@click.option("--from", "src", required=True, help="Arquivo/origem (substring).")
@click.option("--to", "dst", required=True, help="Arquivo/destino (substring).")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1200, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def trace(src: str, dst: str, root: str, budget: int, as_json: bool) -> None:
    """Caminho A -> B por imports+chamadas (BFS até 6 saltos, top 5)."""
    graph, _ = _load_graph(root)
    try:
        lines, payload = do_trace(graph, src, dst)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


@main.command("impact")
@click.option("--file", "fname", required=True, help="Arquivo (substring).")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def impact(fname: str, root: str, budget: int, as_json: bool) -> None:
    """Vizinhança de 1 salto: quem depende, quem chama e quem é chamado."""
    graph, _ = _load_graph(root)
    try:
        lines, payload = do_impact(graph, fname)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


@main.command("caps")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def caps(root: str, budget: int, as_json: bool) -> None:
    """Lista hardware/plataforma detectado: câmera, GPS, bluetooth..."""
    graph, _ = _load_graph(root)
    lines, payload = do_caps(graph)
    _print_capped(lines, budget, as_json, payload)


@main.command("hubs")
@click.option("--top", default=10, type=int, help="Quantos hubs listar.")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1200, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def hubs(top: int, root: str, budget: int, as_json: bool) -> None:
    """Top arquivos por degree centrality (onde o bug provavelmente mora)."""
    graph, _ = _load_graph(root)
    lines, payload = do_hubs(graph, top)
    _print_capped(lines, budget, as_json, payload)


@main.command("slice")
@click.argument("mod")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=2000, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
@click.option("--write", is_flag=True, help="Salva em .astos/slices/<mod>.md.")
def slice_cmd(mod: str, root: str, budget: int, as_json: bool, write: bool) -> None:
    """Mapa só de uma pasta: arquivos + fronteira de 1 salto (poupe tokens)."""
    graph, repo = _load_graph(root)
    try:
        lines, payload = do_slice(graph, repo, mod, write=write)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


@main.command("risks")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def risks(root: str, budget: int, as_json: bool) -> None:
    """Onde o bug mora: god files, ciclos, fan-in/out, TODOs, entrypoints."""
    graph, _ = _load_graph(root)
    lines, payload = do_risks(graph)
    _print_capped(lines, budget, as_json, payload)


@main.command("changed")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def changed(root: str, budget: int, as_json: bool) -> None:
    """Sujos no git (live) + contexto do grafo: debugue aqui primeiro."""
    graph, repo = _load_graph(root)
    lines, payload = do_changed(graph, repo)
    _print_capped(lines, budget, as_json, payload)


@main.command("mcp")
@click.option("--path", "root", default=".", type=click.Path(exists=True, file_okay=False),
              help="Raiz do repositório servido (fixa nas tools).")
def mcp(root: str) -> None:
    """Servidor MCP (stdio): queries como tools para IAs (`astos mcp --path .`)."""
    from .mcp import serve
    raise SystemExit(serve(root))


@main.command("status")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1200, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def status(root: str, budget: int, as_json: bool) -> None:
    """Frescor do mapa: vale confiar ou rode `astos -f`?"""
    graph, repo = _load_graph(root)
    lines, payload = do_status(graph, repo)
    _print_capped(lines, budget, as_json, payload)


@main.command("hotspots")
@click.option("--days", default=30, type=int, help="Janela de churn em dias.")
@click.option("--top", default=10, type=int, help="Quantos listar.")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def hotspots(days: int, top: int, root: str, budget: int, as_json: bool) -> None:
    """Churn recente × god files: perigoso + instável (debugue aqui)."""
    graph, repo = _load_graph(root)
    lines, payload = do_hotspots(graph, repo, days=days, top=top)
    _print_capped(lines, budget, as_json, payload)


@main.command("dead")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def dead(root: str, budget: int, as_json: bool) -> None:
    """Provável código morto: inalcançável desde os entrypoints."""
    graph, _ = _load_graph(root)
    lines, payload = do_dead(graph)
    _print_capped(lines, budget, as_json, payload)


@main.command("tests")
@click.option("--file", "fname", default=None, help="Fonte ou teste (substring).")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=1500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def tests(fname: str | None, root: str, budget: int, as_json: bool) -> None:
    """Mapa teste↔fonte: quem testa X, o que Y cobre (rode p/ verificar)."""
    graph, _ = _load_graph(root)
    try:
        lines, payload = do_tests(graph, fname)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


@main.command("explain")
@click.option("--symbol", default=None, help="Nome de função/classe (ex: scan_repository).")
@click.option("--file", "fname", default=None, help="Arquivo (substring).")
@click.option("--line", default=0, type=int, help="Linha âncora (com --file).")
@click.option("--path", "root", default=".", help="Raiz do repositório.")
@click.option("--budget", default=2500, type=int, help="Teto de tokens da saída.")
@click.option("--json", "as_json", is_flag=True, help="Saída JSON.")
def explain(symbol: str | None, fname: str | None, line: int,
            root: str, budget: int, as_json: bool) -> None:
    """Trecho exato do código + quem chama e quem é chamado (leia isso, não o arquivo)."""
    graph, repo = _load_graph(root)
    try:
        lines, payload = do_explain(graph, repo, symbol=symbol, fname=fname, line=line)
    except QueryError as exc:
        raise click.ClickException(str(exc))
    _print_capped(lines, budget, as_json, payload)


if __name__ == "__main__":
    main()
