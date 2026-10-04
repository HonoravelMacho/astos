"""CLI do ASTOS: `astos` e `astos -a/--all`."""

from __future__ import annotations

import json
import time
import webbrowser
from pathlib import Path

import click

from .generator import generate, generate_map
from .parser import SUPPORTED_LABEL, scan_repository

AGENTS_START = "<!-- ASTOS:START -->"
AGENTS_END = "<!-- ASTOS:END -->"
AGENTS_BLOCK = """<!-- ASTOS:START -->
## Mapa do repositório (ASTOS)
- Antes de explorar o código (e ao se perder no meio de um debug), leia `.astos/map.md`: arquivos, dependências, hubs, símbolos com linha e chamadas entre arquivos.
- Detalhe completo em `.astos/graph.json`; visual 3D para humanos em `.astos/index.html`.
- Mapa desatualizado? Rode `astos -a` para regenerar.
- Se existir `graphify-out/graph.json` (Graphify), prefira-o em perguntas semânticas ("como X funciona"); use o mapa ASTOS para estrutura e dependências.
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


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-a", "--all", "full", is_flag=True,
              help="Força varredura completa do zero (ignora cache incremental).")
@click.option("--no-open", is_flag=True, default=False,
              help="Gera os arquivos sem abrir o navegador.")
@click.option("--no-agents", is_flag=True, default=False,
              help="Não cria nem altera o AGENTS.md do repositório.")
@click.option("--path", "root", default=".", type=click.Path(exists=True, file_okay=False),
              help="Raiz do repositório a analisar (padrão: diretório atual).")
def main(full: bool, no_open: bool, no_agents: bool, root: str) -> None:
    """ASTOS — Abstract Syntax Tree Observer Service (3D offline)."""
    repo = Path(root).resolve()
    astos_dir = repo / ".astos"
    index = astos_dir / "index.html"
    cache = astos_dir / "graph.json"

    existed = astos_dir.exists()
    astos_dir.mkdir(parents=True, exist_ok=True)

    if full and cache.exists():
        cache.unlink()
        click.echo("ASTOS :: flag -a/--all detectada — cache descartado, varredura completa do zero.")

    if not existed:
        click.echo(f"ASTOS :: inicializando observer em {repo}")
    else:
        click.echo("ASTOS :: .astos/ encontrada — atualizando dados incrementalmente...")

    t0 = time.time()
    graph = scan_repository(repo)
    graph["meta"]["generated_in_s"] = round(time.time() - t0, 2)
    graph["meta"]["full_rescan"] = bool(full) or not existed

    cache.write_text(json.dumps(graph, ensure_ascii=False, indent=1), encoding="utf-8")
    generate(index, graph)
    mmap = generate_map(astos_dir / "map.md", graph)

    n, e = len(graph["nodes"]), len(graph["links"])
    ce = len(graph.get("call_edges", []))
    if n == 0:
        click.echo(
            f"ASTOS :: AVISO: nenhum arquivo suportado ({SUPPORTED_LABEL}) "
            f"encontrado em {repo} — o grafo foi gerado vazio."
        )
    else:
        click.echo(
            f"ASTOS :: {n} nós · {e} arestas · {ce} chamada(s) "
            f"-> {index} + {mmap.name} (100% offline, 3D imersivo)"
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
    click.echo("ASTOS :: dica: 'astos -a' força rescan completo · [⛶ FULLSCREEN] + ESC no HUD.")


if __name__ == "__main__":
    main()
