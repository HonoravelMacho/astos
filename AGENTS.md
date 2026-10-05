# AGENTS.md

<!-- ASTOS:START -->
## Mapa do repositório (ASTOS)
- Antes de explorar o código (e ao se perder no meio de um debug), leia `.astos/map.md`: arquivos, dependências, hubs, capabilities (câmera/hardware), riscos (god files, ciclos, TODOs), símbolos com linha e chamadas entre arquivos.
- Detalhe completo em `.astos/graph.json`; visual 3D para humanos em `.astos/index.html` e palácio em `.astos/city.html` (botão [🏛 PALÁCIO]).
- Mapa desatualizado? Rode `astos -f` para regenerar sem abrir o navegador (`astos` sozinho abre o 3D).
- REGRA OBRIGATÓRIA: `astos -f` é sempre o ÚLTIMO comando de terminal de cada resposta que alterar código — sem exceção, sem abrir o navegador. O mapa nunca pode ficar desatualizado.
- Economize tokens: prefira queries a grep — `astos q --symbol X`, `astos q --cap camera`, `astos trace --from A --to B`, `astos impact --file F`, `astos caps`, `astos hubs`, `astos risks`, `astos slice <pasta>`, `astos changed`, `astos status`, `astos explain --symbol X`, `astos hotspots`, `astos dead`, `astos tests --file X`.
- Com MCP (`astos mcp --path .`), chame as mesmas queries como tools, sem shell.
- Se existir `graphify-out/graph.json` (Graphify), prefira-o em perguntas semânticas ("como X funciona"); use o mapa ASTOS para estrutura, hardware e dependências.
<!-- ASTOS:END -->
