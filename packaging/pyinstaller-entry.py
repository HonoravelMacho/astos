"""Entry point congelado (PyInstaller): chama a CLI do ASTOS.

Separado do pacote para o binário onefile não depender de `python -m`.
Uso (CI/local): `pyinstaller packaging/astos.spec` ou via CLI (ver workflow).
"""

from astos.cli import main

if __name__ == "__main__":
    main()
