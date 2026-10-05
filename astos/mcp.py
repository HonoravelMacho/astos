"""Servidor MCP (Model Context Protocol) do ASTOS — stdio, stdlib only.

Expõe as queries (`q`, `trace`, `impact`, `caps`, `hubs`, `risks`, `slice`,
`changed`) como tools para IAs chamarem direto, sem shell. Mesma lógica da
CLI (`astos/queries.py`), então os resultados nunca divergem.

Uso pelo agente (ex. opencode/Claude):
    astos mcp --path /repo/sob/analise
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

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
    stale_note,
)

SERVER_NAME = "astos"
SERVER_VERSION = "0.3.1"
MAX_TEXT = 12000  # teto duro do texto por tool call (~3k tokens)


def _tool_defs() -> list[dict]:
    s = {"type": "string"}
    i = {"type": "integer"}
    b = {"type": "integer", "description": "Teto de tokens da resposta.", "default": 1500}
    return [
        {"name": "q",
         "description": "Busca barata no mapa: símbolos, capabilities (camera, location...) e arquivos. Use em vez de grep.",
         "inputSchema": {"type": "object", "properties": {
             "symbol": {**s, "description": "Substring de símbolo (ex: CameraController)."},
             "cap": {**s, "description": "Capability (ex: camera, location, bluetooth)."},
             "file": {**s, "description": "Substring de caminho de arquivo."}, "budget": b}}},
        {"name": "trace",
         "description": "Caminho entre dois arquivos por imports+chamadas (BFS até 6 saltos).",
         "inputSchema": {"type": "object", "required": ["from", "to"], "properties": {
             "from": {**s, "description": "Arquivo origem (substring)."},
             "to": {**s, "description": "Arquivo destino (substring)."}, "budget": b}}},
        {"name": "impact",
         "description": "Vizinhança de 1 salto de um arquivo: quem depende, quem chama, quem é chamado.",
         "inputSchema": {"type": "object", "required": ["file"], "properties": {
             "file": {**s, "description": "Arquivo (substring)."}, "budget": b}}},
        {"name": "caps",
         "description": "Hardware/plataforma detectado no repo: câmera, GPS, bluetooth... (quem fala com o quê).",
         "inputSchema": {"type": "object", "properties": {"budget": b}}},
        {"name": "hubs",
         "description": "Top arquivos por degree centrality (onde o bug provavelmente mora).",
         "inputSchema": {"type": "object", "properties": {
             "top": {**i, "description": "Quantos listar.", "default": 10}, "budget": b}}},
        {"name": "risks",
         "description": "Onde o bug mora: god files, ciclos de import, fan-in/out, TODOs, entrypoints, órfãos.",
         "inputSchema": {"type": "object", "properties": {"budget": b}}},
        {"name": "slice",
         "description": "Mapa só de uma pasta: arquivos + fronteira de 1 salto. Poupe tokens em repos grandes.",
         "inputSchema": {"type": "object", "required": ["mod"], "properties": {
             "mod": {**s, "description": "Pasta/módulo (ex: lib/camera)."}, "budget": b}}},
        {"name": "changed",
         "description": "Arquivos sujos no git (live) + contexto do grafo. Debugue aqui primeiro.",
         "inputSchema": {"type": "object", "properties": {"budget": b}}},
        {"name": "status",
         "description": "Frescor do mapa: vale confiar ou precisa rodar `astos -f`?",
         "inputSchema": {"type": "object", "properties": {"budget": b}}},
        {"name": "explain",
         "description": "Trecho exato do código (definição + corpo) + quem chama e quem é chamado. Leia isso, não o arquivo.",
         "inputSchema": {"type": "object", "properties": {
             "symbol": {**s, "description": "Nome de função/classe."},
             "file": {**s, "description": "Arquivo (substring)."},
             "line": {**i, "description": "Linha âncora (com file)."}, "budget": b}}},
        {"name": "hotspots",
         "description": "Churn recente (git log) cruzado com god files: perigoso + instável.",
         "inputSchema": {"type": "object", "properties": {
             "days": {**i, "description": "Janela em dias.", "default": 30},
             "top": {**i, "description": "Quantos listar.", "default": 10}, "budget": b}}},
        {"name": "dead",
         "description": "Provável código morto: inalcançável desde os entrypoints (confirme antes de deletar).",
         "inputSchema": {"type": "object", "properties": {"budget": b}}},
        {"name": "tests",
         "description": "Mapa teste↔fonte: quem testa o arquivo, o que o teste cobre. Sem argumento, lista todos os testes.",
         "inputSchema": {"type": "object", "properties": {
             "file": {**s, "description": "Fonte ou teste (substring)."}, "budget": b}}},
    ]


def _budget(args: dict, default: int = 1500) -> int:
    try:
        return max(200, min(8000, int(args.get("budget", default))))
    except (TypeError, ValueError):
        return default


def _cap_text(text: str, budget: int) -> str:
    limit = min(MAX_TEXT, budget * 4)
    if len(text) > limit:
        return text[:limit] + f"\n… (cortado pelo teto de ~{budget} tokens)"
    return text


def _dispatch(graph: dict, repo: Path, name: str, args: dict) -> tuple[str, dict]:
    budget = _budget(args)
    if name == "q":
        lines, payload = do_q(graph, args.get("symbol"), args.get("cap"), args.get("file"))
    elif name == "trace":
        lines, payload = do_trace(graph, args["from"], args["to"])
    elif name == "impact":
        lines, payload = do_impact(graph, args["file"])
    elif name == "caps":
        lines, payload = do_caps(graph)
    elif name == "hubs":
        lines, payload = do_hubs(graph, int(args.get("top", 10)))
    elif name == "risks":
        lines, payload = do_risks(graph)
    elif name == "slice":
        lines, payload = do_slice(graph, repo, args["mod"], write=False)
    elif name == "changed":
        lines, payload = do_changed(graph, repo)
    elif name == "status":
        lines, payload = do_status(graph, repo)
    elif name == "explain":
        lines, payload = do_explain(graph, repo, symbol=args.get("symbol"),
                                    fname=args.get("file"),
                                    line=int(args.get("line", 0) or 0))
    elif name == "hotspots":
        lines, payload = do_hotspots(graph, repo, days=int(args.get("days", 30) or 30),
                                     top=int(args.get("top", 10) or 10))
    elif name == "dead":
        lines, payload = do_dead(graph)
    elif name == "tests":
        lines, payload = do_tests(graph, args.get("file"))
    else:
        raise QueryError(f"tool desconhecida: {name!r}")
    warn = stale_note(repo, graph)
    if warn and name != "status":
        lines = [warn] + lines
    return _cap_text("\n".join(lines), budget), payload


def serve(root: str) -> int:
    """Loop JSON-RPC (NDJSON) no stdio. Retorna exit code."""
    try:
        graph, repo = load_graph(root)
    except QueryError as exc:
        sys.stderr.write(f"astos mcp: {exc}\n")
        return 1
    stdin, stdout = sys.stdin, sys.stdout
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        mid = msg.get("id")
        method = msg.get("method", "")

        def send(result=None, error=None):
            out: dict = {"jsonrpc": "2.0", "id": mid}
            if error is not None:
                out["error"] = error
            else:
                out["result"] = result if result is not None else {}
            stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            stdout.flush()

        try:
            if method == "initialize":
                send({"protocolVersion": msg.get("params", {}).get("protocolVersion", "2024-11-05"),
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
            elif method in ("notifications/initialized", "notifications/cancelled"):
                continue  # notificação: sem resposta
            elif method == "tools/list":
                send({"tools": _tool_defs()})
            elif method == "tools/call":
                params = msg.get("params", {}) or {}
                name = params.get("name", "")
                args = params.get("arguments", {}) or {}
                try:
                    text, payload = _dispatch(graph, repo, name, args)
                    send({"content": [{"type": "text", "text": text}],
                          "structuredContent": payload if isinstance(payload, dict) else {"result": payload}})
                except QueryError as exc:
                    send({"content": [{"type": "text", "text": f"ASTOS erro: {exc}"}], "isError": True})
            elif method == "ping":
                send({})
            else:
                send(error={"code": -32601, "message": f"método não suportado: {method}"})
        except BrokenPipeError:
            return 0
        except Exception as exc:  # noqa: BLE001 — servidor não pode cair
            try:
                send(error={"code": -32603, "message": str(exc)})
            except BrokenPipeError:
                return 0
    return 0
