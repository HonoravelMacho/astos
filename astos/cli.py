"""CLI do ASTOS: `astos` e `astos -a/--all`."""

from __future__ import annotations

import json
import time
import webbrowser
from pathlib import Path

import click

from .generator import generate
from .parser import SUPPORTED_LABEL, scan_repository


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-a", "--all", "full", is_flag=True,
              help="Força varredura completa do zero (ignora cache incremental).")
@click.option("--no-open", is_flag=True, default=False,
              help="Gera os arquivos sem abrir o navegador.")
@click.option("--path", "root", default=".", type=click.Path(exists=True, file_okay=False),
              help="Raiz do repositório a analisar (padrão: diretório atual).")
def main(full: bool, no_open: bool, root: str) -> None:
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

    n, e = len(graph["nodes"]), len(graph["links"])
    if n == 0:
        click.echo(
            f"ASTOS :: AVISO: nenhum arquivo suportado ({SUPPORTED_LABEL}) "
            f"encontrado em {repo} — o grafo foi gerado vazio."
        )
    else:
        click.echo(
            f"ASTOS :: {n} nós · {e} arestas "
            f"-> {index} (100% offline, 3D imersivo)"
        )
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
