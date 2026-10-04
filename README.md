# ASTOS — Abstract Syntax Tree Observer Service

[![PyPI version](https://img.shields.io/pypi/v/astos?style=flat-square&color=22d3ee)](https://pypi.org/project/astos/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.9-22d3ee?style=flat-square)](https://python.org)
[![Offline](https://img.shields.io/badge/offline-100%25-f472b6?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-fbbf24?style=flat-square)](LICENSE)

> **Mapa vivo do seu código em 3D imersivo para você — e em Markdown compacto para a sua IA. Zero CDN. Puro WebGL Sci-Fi.**

O **ASTOS** escaneia qualquer repositório poliglota (Python, C/C++, Dart, Rust,
JS/TS, Java, Go, C#, Kotlin), mapeia módulos, dependências, **símbolos com
linha** (funções, classes) e **chamadas entre arquivos** (Python), e gera três
artefatos em `.astos/`:
- `index.html` — mapa **3D orbital** (Three.js vendorizado, 100% offline) para olhos humanos;
- `map.md` — resumo compacto de **uma linha por arquivo**, desenhado para agentes de IA lerem antes de explorar;
- `graph.json` — o grafo completo em dados.

Na primeira execução ele também instala um **bloco cirúrgico no `AGENTS.md`**
ensinando a IA a consultar o mapa — sem tocar em nada do conteúdo original
(use `--no-agents` para pular).

## Instalação

```bash
pip install astos
```

## Uso

Dentro de qualquer repositório:

```bash
# primeira vez: cria .astos/, analisa, gera mapa + bloco AGENTS.md e abre no navegador
astos

# força varredura completa do zero
astos -a
astos --all

# não tocar no AGENTS.md
astos --no-agents
```

Isso gera `.astos/index.html` (arquivo único, offline), `.astos/map.md` e
`.astos/graph.json`, e abre a interface no navegador padrão. Pressione `ESPAÇO`
para congelar/descongelar o movimento, `ESC` para sair do fullscreen.
Navegação por teclado: `WASD`/setas movem a câmera sem rotacionar
(`Shift` = 3x mais rápido), `Q`/`E` aproximam/afastam.

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

## O que a sua IA ganha (tokens)

Cada `astos` deixa um `AGENTS.md` (bloco marcado `ASTOS:START/END`, idempotente)
com uma instrução simples: **antes de explorar o código — e ao se perder no meio
de um debug — leia `.astos/map.md`**. Na prática:

- **Orientação barata**: o mapa de um repo médio custa poucos milhares de tokens
  de uma vez, em vez de dezenas de milhares queimados em glob/grep/leituras
  exploratórias a cada sessão.
- **Debug multi-turno**: o mapa vira referência estável entre turnos — a IA se
  re-localiza lendo o mapa em vez de re-explorar arquivos.
- **Escopo cirúrgico**: hubs (degree alto) e vizinhança direta dizem o que ler e
  o que ignorar; símbolos com linha (`helper():L1`) apontam o lugar exato.
- **Fluxo Python**: `caller.py --helper()--> callee.py` mostra quem chama quem
  entre arquivos, antes de abrir qualquer código.
- **Camadas**: se existir `graphify-out/graph.json` (Graphify), o bloco orienta
  a preferi-lo em perguntas semânticas e o mapa ASTOS na estrutura — sem briga.

Limites honestos: fora Python o parsing é heurístico (regex, sem dependências);
call edges existem só para Python; o mapa é estático (rode `astos -a` se
desconfiar que envelheceu).

## Como funciona

1. `astos/parser.py` — varre `**/*.{py,c,h,cpp,dart,rs,js,jsx,ts,tsx,java,go,cs,kt,...}`
   (Python via AST preciso, incluindo **call edges** conservadoras; demais
   linguagens via extratores regex sem dependências): `import` / `#include` /
   `mod`+`use` / `require` / `using`. Extrai **defs com linha**, resolve
   dependências locais e calcula o grau de cada módulo.
2. `astos/generator.py` — injeta o grafo + `three.min.js` + `OrbitControls.js`
   (vendorizados em `astos/vendor/`) em um HTML único, sem nenhum fetch externo;
   e gera o `map.md` compacto para agentes.
3. `astos/cli.py` — gerencia `.astos/`, cache incremental em
   `.astos/graph.json`, bloco cirúrgico no `AGENTS.md` e abertura automática
   no navegador.

## Estrutura

```
astos/
  __init__.py
  cli.py          # CLI `astos` / `astos -a` / `--no-agents` (click) + bloco AGENTS.md
  parser.py       # scan multilinguagem -> {nodes, links, call_edges}
  generator.py    # HTML 3D Sci-Fi offline (Three.js inline) + map.md p/ IAs
  vendor/
    three.min.js        # r128 UMD (offline)
    OrbitControls.js    # UMD compatível com r128 (offline)
```

## Licença

MIT — veja [LICENSE](LICENSE).
