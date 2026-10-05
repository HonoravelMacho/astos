# ASTOS — Abstract Syntax Tree Observer Service

[![PyPI version](https://img.shields.io/pypi/v/astos?style=flat-square&color=22d3ee)](https://pypi.org/project/astos/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.9-22d3ee?style=flat-square)](https://python.org)
[![Offline](https://img.shields.io/badge/offline-100%25-f472b6?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-fbbf24?style=flat-square)](LICENSE)

> **Mapa vivo do seu código em 3D imersivo para você — e em Markdown compacto para a sua IA. Zero CDN. Puro WebGL Sci-Fi.**

O **ASTOS** escaneia qualquer repositório poliglota (Python, C/C++, Dart, Rust,
JS/TS, Java, Go, C#, Kotlin), mapeia módulos, dependências, **símbolos com
linha** (funções, classes, métodos) e **chamadas entre arquivos** (todas as
linguagens, regra conservadora), detecta **capabilities de hardware**
(câmera, GPS, bluetooth...) e **riscos** (god files, ciclos, TODOs), e gera os
artefatos em `.astos/`:
- `index.html` — mapa **3D orbital** (Three.js vendorizado, 100% offline) para olhos humanos;
- `city.html` — **palácio do código** 🏗️ *(em desenvolvimento)*: cada pasta é uma
  quadra colada numa placa de circuito, cada arquivo é um bloco com altura = tamanho;
- `map.md` — resumo compacto (uma linha por arquivo, modo compacto automático
  em repos grandes), desenhado para agentes de IA lerem antes de explorar;
- `graph.json` — o grafo completo em dados.

Na primeira execução ele também instala um **bloco cirúrgico no `AGENTS.md`**
ensinando a IA a consultar o mapa — sem tocar em nada do conteúdo original
(use `--no-agents` para pular).

## Instalação

```bash
pip install astos
```

Sem Python? Baixe o binário pronto na [Release](../../releases) (`astos-linux`,
`astos.exe`, `astos-macos`) ou o pacote da sua distro (`*.deb`, `*.rpm`):

```bash
# exemplo Debian/Ubuntu
sudo dpkg -i astos_*.deb
```

## Uso

Dentro de qualquer repositório:

```bash
# primeira vez: cria .astos/, analisa, gera mapa + bloco AGENTS.md e abre no navegador
astos

# atualiza tudo sem abrir o navegador (ideal p/ agentes e CI; última linha de cada resposta da IA)
astos -f

# força varredura completa do zero (o -f já faz isso em silêncio)
astos -a

# map.md compacto (só índice; automático acima de 300 arquivos) ou completo
astos --compact | astos --no-compact

# não tocar no AGENTS.md
astos --no-agents
```

Isso gera `.astos/index.html` (arquivo único, offline), `.astos/map.md` e
`.astos/graph.json`, e abre a interface no navegador padrão. Pressione `ESPAÇO`
para congelar/descongelar o movimento, `ESC` para sair do fullscreen.
Navegação por teclado: `WASD`/setas movem a câmera sem rotacionar
(`Shift` = 3x mais rápido), `Q`/`E` aproximam/afastam.

```bash
# queries baratas com teto de tokens (use em vez de grep)
astos q --symbol CameraController   # quem define/usa um símbolo
astos q --cap camera                # quem fala com a câmera
astos trace --from preview.dart --to service.dart  # caminho A -> B
astos impact --file service.dart    # vizinhança de 1 salto
astos explain --symbol scan_repository  # trecho exato + chamadores
astos caps | astos hubs | astos risks   # hardware, hubs, god files/ciclos
astos slice lib/camera [--write]    # só uma pasta + fronteira
astos changed | astos status | astos hotspots | astos dead | astos tests
# sujos no git, frescor do mapa, churn, mortos, teste↔fonte

# servidor MCP (stdio): as mesmas 13 queries como tools, sem shell
astos mcp --path .
```

## O que você vê (3D)

- **Somente 3D imersivo** — esferas de neon, órbita contínua, zoom/pan/orbit.
- **Teia de aranha visível de longe** — links com feixe luminoso aditivo + opacidade alta.
- **Fita RGB animada** — fótons coloridos percorrem as arestas do nó selecionado
  (toggle global `FLUXO RGB` disponível no HUD).
- **Card HUD por clique** — nome do arquivo/módulo, caminho relativo,
  importações/dependências diretas e degree centrality.
- **`❄ CONGELAR`** — para física + órbita + fluxo de uma vez (atalho: espaço).
- **Tema Sci-Fi/Chronos** — HUD cyberpunk dark, neon cyan/magenta, painéis foscos,
  fonte monospace, scanlines + vinheta.
- **`[ 🏛 PALÁCIO ]`** 🏗️ *(em desenvolvimento)* — botão no topo abre o `city.html`:
  placa de circuito com trilhas de dependência, filtro por capability,
  `[ NOMES ]` e `[ TRILHAS ]` ligam/desligam, clique no bloco mostra a ficha
  do arquivo.

## O que a sua IA ganha (tokens)

Cada `astos` deixa um `AGENTS.md` (bloco marcado `ASTOS:START/END`, idempotente)
ensinando a IA a consultar o mapa — e a rodar `astos -f` como último comando
de cada resposta que alterar código, para o mapa nunca envelhecer. Na prática:

- **Orientação barata**: o mapa de um repo médio custa poucos milhares de tokens
  de uma vez, em vez de dezenas de milhares queimados em glob/grep/leituras
  exploratórias a cada sessão. Em repo grande, o modo compacto corta as linhas
  por arquivo e as fatias (`astos slice`) entregam só o pedaço.
- **Confiança**: `astos status` diz se o mapa vale ou precisa de `-f`, e toda
  query avisa sozinha quando o git andou — a IA nunca confia num mapa velho
  sem saber.
- **Debug multi-turno**: o mapa vira referência estável entre turnos — a IA se
  re-localiza lendo o mapa em vez de re-explorar arquivos.
- **Escopo cirúrgico**: hubs, `impact`, `trace` e `risks` dizem o que ler e
  o que ignorar; `explain` entrega o trecho exato do código (sem abrir o arquivo).
- **Hardware sem grep**: `q --cap camera` responde "o que fala com a câmera?"
  em milissegundos, incluindo permissões de manifesto.
- **Git no loop**: `changed` (sujos), `hotspots` (churn × god files), `dead`
  (inalcançáveis) e `tests` (quem testa o quê) apontam onde debugar e verificar.
- **MCP nativo**: `astos mcp --path .` expõe as 13 queries como tools —
  a IA chama direto, sem shell, com o mesmo teto de tokens.

Limites honestos: fora Python o parsing é heurístico (regex, sem dependências —
tree-sitter ficaria mais preciso ao custo do "zero dependências"); call edges
seguem regra conservadora (só liga quando o nome é definido num arquivo);
semântica profunda ("por que esse design?") não é o trabalho dele.

## ASTOS × Graphify — comparação honesta

O **ASTOS não é melhor que o Graphify**. São ferramentas diferentes, e esta
seção existe para ninguém comprar gato por lebre:

- **Graphify** é a ferramenta mais forte em **profundidade semântica**: grafo
  via LLM, comunidades, god nodes, memória persistente entre sessões. Brilha em
  "como X funciona de ponta a ponta" e perguntas fundas e repetidas sobre a
  mesma base. Custa setup, tokens para construir e curva de aprendizado.
- **ASTOS** é a ferramenta mais forte em **velocidade e simplicidade**: um
  comando, segundos, zero dependências, zero tokens para construir, visual 3D
  + palácio que qualquer humano entende de cara. E cobre o que o Graphify nem
  tenta: hardware/plataforma, git (sujos, churn, frescor) e trecho exato de
  código com teto de tokens.

Regra prática: use o ASTOS sempre (custo zero, benefício imediato); some o
Graphify quando as perguntas ficarem semânticas e recorrentes. O bloco que o
`astos` instala no `AGENTS.md` já orquestra os dois: mapa ASTOS para estrutura,
hardware e dependências; `graphify-out/` para significado.

## Como funciona

1. `astos/parser.py` — varre `**/*.{py,c,h,cpp,dart,rs,js,jsx,ts,tsx,java,go,cs,kt,...}`
   (Python via AST preciso; demais linguagens via extratores regex sem
   dependências, incluindo métodos e **call edges** conservadoras): `import` /
   `#include` / `mod`+`use` / `require` / `using`. Extrai **defs com linha**,
   resolve dependências locais, detecta **capabilities de hardware**,
   **TODOs/entrypoints** e calcula grau, god files, ciclos e órfãos.
2. `astos/queries.py` — as 13 queries puras (`q`, `trace`, `impact`, `caps`,
   `hubs`, `risks`, `slice`, `changed`, `status`, `explain`, `hotspots`,
   `dead`, `tests`), todas com teto de tokens; compartilhadas pela CLI e MCP.
3. `astos/generator.py` — injeta o grafo + `three.min.js` + `OrbitControls.js`
   (vendorizados em `astos/vendor/`) em dois HTMLs únicos (grafo 3D + palácio),
   sem nenhum fetch externo; e gera o `map.md` (cheio ou compacto) para agentes.
4. `astos/cli.py` — gerencia `.astos/`, `graph.json`, bloco cirúrgico no
   `AGENTS.md`, abertura automática no navegador e o servidor `astos mcp`.
5. `astos/mcp.py` — servidor MCP stdio (só stdlib) com as queries como tools.

## Estrutura

```
astos/
  __init__.py
  cli.py          # CLI `astos` / `-a` / `-f` / `--compact` / queries / `mcp` (click) + bloco AGENTS.md
  parser.py       # scan multilinguagem -> {nodes, links, call_edges, capabilities, risks}
  queries.py      # 13 queries puras com teto de tokens (CLI + MCP)
  mcp.py          # servidor MCP stdio (stdlib only)
  generator.py    # HTMLs 3D Sci-Fi offline (Three.js inline) + map.md p/ IAs
  vendor/
    three.min.js        # r128 UMD (offline)
    OrbitControls.js    # UMD compatível com r128 (offline)
packaging/        # entry PyInstaller + receita nFPM (.deb/.rpm)
.github/workflows/release.yml  # binários Linux/Win/macOS + Release
```

## Licença

MIT — veja [LICENSE](LICENSE).
