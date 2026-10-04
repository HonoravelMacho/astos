# ASTOS — Abstract Syntax Tree Observer Service

[![PyPI version](https://img.shields.io/pypi/v/astos?style=flat-square&color=22d3ee)](https://pypi.org/project/astos/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.9-22d3ee?style=flat-square)](https://python.org)
[![Offline](https://img.shields.io/badge/offline-100%25-f472b6?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-fbbf24?style=flat-square)](LICENSE)

> **Observe a estrutura viva do seu código em 3D imersivo. Zero CDN. Puro WebGL Sci-Fi.**

O **ASTOS** escaneia qualquer repositório **Python ou C/C++**, mapeia módulos,
importações/`#include`s e dependências diretas, e gera um mapa **3D orbital** (Three.js
vendorizado, 100% offline) com física de partículas, teia de aranha luminosa,
**fita RGB animada** nos links selecionados, card HUD Sci-Fi por nó e botão de
tela cheia.

## Instalação

```bash
pip install astos
```

## Uso

Dentro de qualquer repositório:

```bash
# primeira vez: cria .astos/, analisa, gera e abre no navegador
astos

# força varredura completa do zero
astos -a
astos --all
```

Isso gera `.astos/index.html` (arquivo único, offline) e abre automaticamente
no navegador padrão. Pressione `ESC` para sair do fullscreen.

## O que você vê

- **Somente 3D imersivo** — esferas de neon, órbita contínua, zoom/pan/orbit.
- **Teia de aranha visível de longe** — links com feixe luminoso aditivo + opacidade alta.
- **Fita RGB animada** — fótons coloridos percorrem as arestas do nó selecionado
  (toggle global `FLUXO RGB` disponível no HUD).
- **Card HUD por clique** — nome do arquivo/módulo, caminho relativo,
  importações/dependências diretas e degree centrality.
- **Tema Sci-Fi/Chronos** — HUD cyberpunk dark, neon cyan/magenta, painéis foscos,
  fonte monospace, scanlines + vinheta.

## Como funciona

1. `astos/parser.py` — varre `**/*.{py,c,h,cpp,hpp,cc,cxx}`, parseia `ast.Import` /
   `ast.ImportFrom` (Python) e `#include "..."` / `<...>` (C/C++, via regex),
   resolve dependências locais e calcula o grau de cada módulo.
2. `astos/generator.py` — injeta o grafo + `three.min.js` + `OrbitControls.js`
   (vendorizados em `astos/vendor/`) em um HTML único, sem nenhum fetch externo.
3. `astos/cli.py` — gerencia `.astos/`, cache incremental em
   `.astos/graph.json` e abertura automática no navegador.

## Estrutura

```
astos/
  __init__.py
  cli.py          # CLI `astos` / `astos -a` (click)
  parser.py       # AST scan -> {nodes, links}
  generator.py    # HTML 3D Sci-Fi offline (Three.js inline)
  vendor/
    three.min.js        # r128 UMD (offline)
    OrbitControls.js    # UMD compatível com r128 (offline)
```

## Licença

MIT — veja [LICENSE](LICENSE).
