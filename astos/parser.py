"""Mapeamento do repositório: arquivos de código -> grafo de dependências.

Estratégia por linguagem (zero dependência extra, 100% offline):
- Python (``*.py``): imports via ``ast`` (preciso).
- C/C++ (``*.c *.h *.cpp *.hpp *.cc *.cxx``): ``#include`` (regex).
- Dart (``*.dart``): ``import`` / ``export`` / ``part`` (``dart:`` = externo,
  ``package:`` e relativos resolvidos por sufixo/caminho).
- Rust (``*.rs``): ``mod foo;`` (``foo.rs`` / ``foo/mod.rs``) e ``use``
  com ``crate::`` / ``self::`` / ``super::`` ou nome do pacote (lido do
  ``Cargo.toml``); demais crates = externos.
- JS/TS (``*.js *.jsx *.mjs *.cjs *.ts *.tsx``): ``import`` / ``require`` /
  ``import()`` relativos (com sondagem de extensão e ``index``); bare
  specifiers = externos.
- Java (``*.java``), C# (``*.cs``), Kotlin (``*.kt *.kts``): imports
  pontuados resolvidos por sufixo de caminho.
- Go (``*.go``): módulo lido do ``go.mod``; imports do próprio módulo viram
  arestas entre arquivos de pacotes diferentes; stdlib/terceiros = externos.

Calcula o grau (degree centrality) de cada nó.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path, PurePosixPath

IGNORE_DIRS = {
    ".astos", ".git", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", "dist", "build", "node_modules", ".tox", ".eggs",
    ".dart_tool", "target", "vendor", ".gradle", "Pods", ".next", "out",
    "ephemeral", "generated", "cmake-build-debug", ".idea", ".vscode",
}

LANG_OF = {
    ".py": "python",
    ".c": "c", ".h": "c",
    ".cpp": "c", ".hpp": "c", ".cc": "c", ".cxx": "c", ".hxx": "c",
    ".dart": "dart",
    ".rs": "rust",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "js", ".tsx": "js", ".mts": "js", ".cts": "js",
    ".java": "java",
    ".go": "go",
    ".cs": "csharp",
    ".kt": "kotlin", ".kts": "kotlin",
}

SUPPORTED_LABEL = ".py, .c, .h, .cpp, .hpp, .cc, .cxx, .dart, .rs, .js, .jsx, .ts, .tsx, .java, .go, .cs, .kt"

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

RE_DART_IO = re.compile(r'''(?:import|export)\s+['"]([^'"]+)['"]|part\s+['"]([^'"]+)['"]''')
RE_DART_SYM = re.compile(r'^\s*(?:abstract\s+|sealed\s+|base\s+|final\s+)?(?:class|mixin|enum)\s+(\w+)|^\s*(?:[\w<>?,\s]+\s+)?(\w+)\s*\([^;{}=]*\)\s*(?:async\s*)?(?:=>|\{)', re.MULTILINE)

RE_RUST_MOD = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_]\w*)\s*;', re.MULTILINE)
RE_RUST_USE = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]+);', re.MULTILINE)
RE_RUST_SYM = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?(?P<kind>fn|struct|enum|trait|impl)\s+(?P<name>\w+)', re.MULTILINE)
RE_CARGO_NAME = re.compile(r'^\s*name\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)

RE_JS_IMP = re.compile(r'''(?:import\s+(?:[^'"]*?\s+from\s+)?|export\s+[^'"]*?\s+from\s+|require\s*\(|import\s*\()\s*['"]([^'"]+)['"]''')
RE_JS_SYM = re.compile(r'^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)|^\s*(?:export\s+(?:default\s+)?)?class\s+(\w+)', re.MULTILINE)
RE_JS_ARROW = re.compile(r'^\s*(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^;{}=]*\)\s*=>', re.MULTILINE)
RE_JS_METHOD = re.compile(r'^\s*(?:async\s+|static\s+|get\s+|set\s+)?(\w+)\s*\([^;{}=]*\)\s*\{', re.MULTILINE)
JS_METHOD_SKIP = {
    "if", "for", "while", "switch", "catch", "return", "sizeof", "do",
    "else", "case", "new", "const", "let", "var", "function", "extends",
    "import", "export", "try", "await", "yield", "throw", "super", "this",
}

RE_JAVA_IMP = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)(?:\.\*)?\s*;', re.MULTILINE)
RE_JAVA_SYM = re.compile(r'^\s*(?:public\s+|protected\s+|private\s+|abstract\s+|final\s+|sealed\s+)*(?P<kind>class|interface|enum)\s+(?P<name>\w+)', re.MULTILINE)
RE_JAVA_METHOD = re.compile(r'^\s*(?:(?:public|protected|private|static|final|synchronized|abstract|native|transient|volatile)\s+)*(?:[\w<>\[\].,\s]+\s+)?(\w+)\s*\([^;{}=]*\)\s*(?:throws\s+[\w.,\s]+)?\{', re.MULTILINE)
JAVA_METHOD_SKIP = {
    "if", "for", "while", "switch", "catch", "return", "sizeof", "do",
    "else", "case", "new", "super", "this", "assert", "record",
}

RE_DART_INLINE = re.compile(r'(?<![\w$.])([A-Za-z_]\w*)\s*\([^;{}=()]*\)\s*(?:async\s*)?\{')

RE_GO_IMP = re.compile(r'"([^"]+)"')
RE_GO_FUNC = re.compile(r'^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>\w+)', re.MULTILINE)
RE_GO_MOD = re.compile(r'^\s*module\s+(\S+)', re.MULTILINE)
RE_GO_PKG = re.compile(r'^\s*package\s+(\w+)', re.MULTILINE)

RE_CS_USING = re.compile(r'^\s*using\s+(?:static\s+|global\s+)?([\w.]+)\s*;', re.MULTILINE)
RE_CS_SYM = re.compile(r'^\s*(?:namespace\s+[\w.]+\s*\{\s*)?(?:public\s+|internal\s+|private\s+|protected\s+|abstract\s+|sealed\s+|static\s+|partial\s+)*(?P<kind>class|interface|enum|struct)\s+(?P<name>\w+)', re.MULTILINE)

RE_KT_IMP = re.compile(r'^\s*import\s+([\w.]+)(?:\.\*)?\s*$', re.MULTILINE)
RE_KT_SYM = re.compile(r'^\s*(?:public\s+|private\s+|internal\s+|open\s+|abstract\s+|data\s+|sealed\s+)*(?:class|interface|object|enum)\s+(\w+)|^\s*(?:public\s+|private\s+|internal\s+|suspend\s+)?fun\s+(?:<[^>]*>\s*)?(\w+)', re.MULTILINE)

# ---------------------------------------------------------------------------
# Capabilities (hardware / plataforma): mapeia trechos de código e manifestos
# para recursos como câmera, GPS, bluetooth... 100% offline, regex simples.
# Usado pela IA para responder "o que fala com a câmera?" sem grep.
# ---------------------------------------------------------------------------

DART_CTRL_EARLY = {
    "if", "for", "while", "do", "switch", "catch", "assert", "return",
    "else", "case", "new", "const", "final", "var", "late", "await",
    "yield", "throw", "import", "export", "library", "part", "try", "on",
}

CAPABILITY_RULES: dict[str, list[str]] = {
    "camera": [
        r"CameraController", r"ImagePicker", r"camera2", r"CameraX",
        r"AVCapture", r"UIImagePicker", r"android\.hardware\.camera",
        r"Manifest\.permission\.CAMERA", r"NSCameraUsageDescription",
        r"mediaDevices\.getUserMedia", r"getUserMedia",
        r"uses-permission[^>]*CAMERA", r"\bcamera\b",
    ],
    "location": [
        r"FusedLocationProvider", r"CLLocationManager", r"Geolocator",
        r"ACCESS_FINE_LOCATION", r"ACCESS_COARSE_LOCATION",
        r"NSLocationWhenInUse", r"NSLocationAlways",
        r"navigator\.geolocation", r"\bgeolocator\b",
    ],
    "bluetooth": [
        r"BluetoothAdapter", r"BluetoothLeScanner", r"CBCentralManager",
        r"CBPeripheralManager", r"BLUETOOTH_SCAN", r"BLUETOOTH_CONNECT",
        r"CoreBluetooth", r"\bbluetooth\b",
    ],
    "microphone": [
        r"AudioRecord", r"MediaRecorder", r"AVAudioRecorder",
        r"RECORD_AUDIO", r"NSMicrophoneUsageDescription",
        r"SpeechRecognizer", r"\bmicrophone\b",
    ],
    "sensors": [
        r"SensorManager", r"CMMotionManager", r"accelerometer",
        r"gyroscope", r"magnetometer", r"proximity",
    ],
    "storage": [
        r"READ_EXTERNAL_STORAGE", r"WRITE_EXTERNAL_STORAGE",
        r"MANAGE_EXTERNAL_STORAGE", r"NSPhotoLibrary",
        r"FilePicker", r"READ_MEDIA_IMAGES", r"READ_MEDIA_VIDEO",
    ],
    "notifications": [
        r"NotificationManager", r"UNUserNotificationCenter",
        r"POST_NOTIFICATIONS", r"FirebaseMessaging",
        r"pushNotification", r"\bnotifications?\b",
    ],
    "network": [
        r"\bokhttp\b", r"\bretrofit\b", r"\bdio\b", r"HttpClient",
        r"NSAppTransportSecurity", r"android\.permission\.INTERNET",
        r"ACCESS_NETWORK_STATE",
    ],
    "nfc": [
        r"NfcAdapter", r"CoreNFC", r"NFCReader", r"android\.permission\.NFC",
    ],
    "biometrics": [
        r"BiometricPrompt", r"LocalAuthentication", r"USE_BIOMETRIC",
        r"NSFaceIDUsageDescription", r"\bfaceid\b", r"\btouchid\b",
    ],
    "telephony": [
        r"TelephonyManager", r"READ_PHONE_STATE", r"CALL_PHONE",
        r"SMS_RECEIVED", r"CTTelephonyNetworkInfo",
    ],
    "media": [
        r"ExoPlayer", r"AVPlayer", r"VideoPlayer", r"MediaPlayer",
        r"AVAudioPlayer", r"TextureView", r"SurfaceView",
    ],
}

_CAP_COMPILED: list[tuple[str, re.Pattern]] = [
    (cap, re.compile("|".join(f"(?:{p})" for p in pats)))
    for cap, pats in CAPABILITY_RULES.items()
]

# Arquivo que casa com domains demais provavelmente É o dicionário (ex: o
# próprio parser do astos) e não um usuário das APIs — reportar tudo seria
# ruído no `q --cap`. Acima disso, zera as caps (o RISKS já sinaliza o file).
CAPS_DENSITY_LIM = 6

PERMISSION_TO_CAP = {
    "CAMERA": "camera",
    "ACCESS_FINE_LOCATION": "location", "ACCESS_COARSE_LOCATION": "location",
    "ACCESS_BACKGROUND_LOCATION": "location",
    "BLUETOOTH_SCAN": "bluetooth", "BLUETOOTH_CONNECT": "bluetooth",
    "BLUETOOTH_ADVERTISE": "bluetooth",
    "RECORD_AUDIO": "microphone", "MODIFY_AUDIO_SETTINGS": "microphone",
    "READ_EXTERNAL_STORAGE": "storage", "WRITE_EXTERNAL_STORAGE": "storage",
    "MANAGE_EXTERNAL_STORAGE": "storage", "READ_MEDIA_IMAGES": "storage",
    "READ_MEDIA_VIDEO": "storage", "READ_MEDIA_AUDIO": "storage",
    "POST_NOTIFICATIONS": "notifications",
    "INTERNET": "network", "ACCESS_NETWORK_STATE": "network",
    "NFC": "nfc",
    "USE_BIOMETRIC": "biometrics", "USE_FINGERPRINT": "biometrics",
    "READ_PHONE_STATE": "telephony", "CALL_PHONE": "telephony",
    "RECEIVE_SMS": "telephony", "SEND_SMS": "telephony",
}

PLIST_TO_CAP = {
    "NSCameraUsageDescription": "camera",
    "NSLocationWhenInUseUsageDescription": "location",
    "NSLocationAlwaysUsageDescription": "location",
    "NSBluetoothAlwaysUsageDescription": "bluetooth",
    "NSMicrophoneUsageDescription": "microphone",
    "NSMotionUsageDescription": "sensors",
    "NSPhotoLibraryUsageDescription": "storage",
    "NSFaceIDUsageDescription": "biometrics",
}

RE_ANDROID_PERM = re.compile(r'uses-permission[^>]*android:name="android\.permission\.([A-Z_]+)"')
RE_PLIST_KEY = re.compile(r"<key>(NS\w+)</key>")
RE_DEP_TOKEN = re.compile(r'["\']([A-Za-z0-9_.\-@/]+)["\']|^\s*(?:name|implementation|api)\s*\(?["\']([^"\']+)', re.MULTILINE)

# ---------------------------------------------------------------------------
# Riscos (debug rápido): TODOs, entrypoints e arquivos propensos a bug.
# ---------------------------------------------------------------------------

RE_TODO = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b\s*:?\s*(.{0,80})", re.IGNORECASE)
RE_ENTRY_DEF = re.compile(r"\b(?:void\s+main\s*\(|fun\s+main\s*\(|func\s+main\s*\(|def\s+main\b|runApp\s*\(|UIApplicationMain|@main\b)")
ENTRY_BASENAMES = {
    "main.dart", "main.py", "__main__.py", "main.kt", "MainActivity.kt",
    "MainActivity.java", "AppDelegate.swift", "App.kt", "index.js",
    "index.ts", "main.go", "Main.java", "Program.cs", "app.py",
}

GOD_LOC = 800
GOD_SYMS = 60
GOD_DEG = 10
FAN_LIM = 8


def _file_todos(src: str, cap: int = 8) -> list[dict]:
    out: list[dict] = []
    for m in RE_TODO.finditer(src):
        tag = m.group(1).upper()
        txt = (m.group(2) or "").strip()[:80]
        out.append({"t": tag, "l": _line_of(src, m.start()), "x": txt})
        if len(out) >= cap:
            break
    return out


def _is_entry(rel: str, src: str, defs: list[dict]) -> bool:
    base = rel.rsplit("/", 1)[-1]
    if base in ENTRY_BASENAMES:
        return True
    names = {str(d.get("n", "")).split(".")[-1] for d in defs}
    if names & {"main", "Main", "runApp", "MyApp", "App"}:
        return True
    if "__name__" in src and "__main__" in src:
        return True
    if RE_ENTRY_DEF.search(src):
        return True
    return False

# chamadas genéricas `nome(` para linguagens sem AST (heurística conservadora)
RE_GENERIC_CALL = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
CALL_SKIP = {
    "if", "for", "while", "switch", "catch", "return", "sizeof", "do",
    "else", "case", "new", "const", "final", "var", "late", "await",
    "yield", "throw", "import", "export", "assert", "try", "on",
    "fun", "func", "function", "class", "struct", "enum", "impl",
    "print", "printf", "println", "super", "this", "self",
} | C_KEYWORDS | DART_CTRL_EARLY


def _file_caps(src: str) -> list[str]:
    """Tags de hardware/plataforma detectadas no texto do arquivo."""
    found = []
    for cap, rx in _CAP_COMPILED:
        if rx.search(src):
            found.append(cap)
    if len(found) > CAPS_DENSITY_LIM:
        return []  # dicionário/meta, não uso real de hardware
    return found


def _scan_manifest_caps(root: Path) -> tuple[dict[str, list[str]], list[str]]:
    """Lê manifestos conhecidos e retorna (cap -> evidências, arquivos lidos)."""
    caps: dict[str, list[str]] = {}
    read: list[str] = []

    def add(cap: str, ev: str):
        caps.setdefault(cap, [])
        if ev not in caps[cap]:
            caps[cap].append(ev)

    manifest_names = {
        "AndroidManifest.xml", "Info.plist", "pubspec.yaml", "package.json",
        "build.gradle", "build.gradle.kts", "Podfile", "Cargo.toml",
        "go.mod", "app.json", "AndroidManifest.xml",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if fn not in manifest_names:
                continue
            p = Path(dirpath) / fn
            try:
                rel = p.relative_to(root).as_posix()
                src = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            read.append(rel)
            if fn == "AndroidManifest.xml":
                for perm in RE_ANDROID_PERM.findall(src):
                    cap = PERMISSION_TO_CAP.get(perm)
                    if cap:
                        add(cap, f"{rel}[{perm}]")
            elif fn == "Info.plist":
                for key in RE_PLIST_KEY.findall(src):
                    cap = PLIST_TO_CAP.get(key)
                    if cap:
                        add(cap, f"{rel}[{key}]")
            else:
                low = src.lower()
                for cap in CAPABILITY_RULES:
                    if cap in low or (cap == "camera" and "image_picker" in low):
                        # evidência curta: arquivo + dependência relevante
                        add(cap, rel)
    return caps, read


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
    out: list[str] = []
    for i in imports:
        if isinstance(i, tuple):
            out.append("." * i[1] + i[2])
        else:
            out.append(i)
    seen, uniq = set(), []
    for i in out:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq


def _parse_c_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    """Retorna (includes locais, imports externos, defs [{n,k,l}])."""
    code = _strip_c_keep_lines(src)
    local, external, defs = [], [], []
    for delim, target in RE_C_INCLUDE.findall(code):
        target = target.strip()
        if delim == '"':
            local.append(target)
        else:
            external.append(f"<{target}>")
    for m in RE_C_FUNC.finditer(code):
        name = m.group(1)
        if name not in C_KEYWORDS:
            before = code[max(0, m.start(1) - 60):m.start(1)].split()
            if before and re.match(r'^[A-Za-z_][\w\*]*$', before[-1]) and before[-1] not in C_KEYWORDS:
                defs.append({"n": name, "k": "func", "l": _line_of(code, m.start())})
            elif not before:
                defs.append({"n": name, "k": "func", "l": _line_of(code, m.start())})
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), defs


def _same_line_prefix(src: str, pos: int) -> str:
    start = src.rfind("\n", 0, pos) + 1
    return src[start:pos]


def _is_new_expr(prefix: str) -> bool:
    return bool(re.search(r'\bnew\s*$', prefix))


def _collect_inline(src: str, pattern: re.Pattern, skip: set[str],
                    defs: list[dict], kind: str = "func", cap: int = 150) -> list[dict]:
    """Métodos fora do início da linha (`class A { void f() {...} }`, JS shorthand...).

    Exige `{` após os parênteses (chamadas terminam em `;`), ignora keywords
    de controle e `new X()`. Heurística com recall maior, precisão menor.
    """
    seen = {str(d.get("n", "")).split(".")[-1] for d in defs}
    for m in pattern.finditer(src):
        name = m.group(1)
        if not name or name in seen or name in skip:
            continue
        if _is_new_expr(_same_line_prefix(src, m.start(1))):
            continue
        seen.add(name)
        defs.append({"n": name, "k": kind, "l": _line_of(src, m.start())})
        if len(defs) >= cap:
            break
    return defs


def _parse_dart_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    local, external = [], []
    for uri, part in RE_DART_IO.findall(src):
        target = (uri or part).strip()
        if not target:
            continue
        if target.startswith("dart:"):
            external.append(target)
        else:
            local.append(target)
    defs = []
    for m in RE_DART_SYM.finditer(src):
        cls, fn = m.group(1), m.group(2)
        if cls:
            defs.append({"n": cls, "k": "class", "l": _line_of(src, m.start())})
        elif fn and fn not in DART_CTRL:
            defs.append({"n": fn, "k": "func", "l": _line_of(src, m.start())})
    _collect_inline(src, RE_DART_INLINE, DART_CTRL | C_KEYWORDS, defs)
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), defs


def _parse_rust_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    mods = [f"mod:{m}" for m in RE_RUST_MOD.findall(src)]
    uses = []
    for stmt in RE_RUST_USE.findall(src):
        for chunk in stmt.split(","):
            uses.append("use:" + chunk.strip().split(" as ")[0].strip().strip("{} "))
    defs = _named(src, RE_RUST_SYM)
    return list(dict.fromkeys(mods + uses)), [], defs


def _parse_js_source(src: str) -> tuple[list[str], list[str], int]:
    local, external = [], []
    for spec in RE_JS_IMP.findall(src):
        spec = spec.strip()
        if not spec:
            continue
        if spec.startswith((".", "/")):
            local.append(spec)
        else:
            external.append(spec)
    defs = _named(src, RE_JS_SYM, kinds={1: "func", 2: "class"})
    for m in RE_JS_ARROW.finditer(src):
        name = m.group(1)
        if name and all(d.get("n") != name for d in defs) and len(defs) < 150:
            defs.append({"n": name, "k": "func", "l": _line_of(src, m.start())})
    _collect_inline(src, RE_JS_METHOD, JS_METHOD_SKIP, defs)
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), defs


def _parse_java_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    imports = [i for i in RE_JAVA_IMP.findall(src) if not i.startswith(("java.", "javax."))]
    external = [i for i in RE_JAVA_IMP.findall(src) if i.startswith(("java.", "javax."))]
    defs = _named(src, RE_JAVA_SYM)
    _collect_inline(src, RE_JAVA_METHOD, JAVA_METHOD_SKIP, defs)
    return list(dict.fromkeys(imports)), list(dict.fromkeys(external)), defs


def _parse_go_source(src: str) -> tuple[list[str], list[str], list[dict], str]:
    quoted = RE_GO_IMP.findall(src)
    local, external = [], []
    for q in quoted:
        if "/" not in q and "." not in q:
            external.append(q)  # stdlib raiz: fmt, os, ...
        else:
            local.append("go:" + q)  # resolvido contra o nome do módulo
            external.append(q)
    m = RE_GO_PKG.search(src)
    pkg = m.group(1) if m else ""
    defs = _named(src, RE_GO_FUNC, kinds={1: "func"})
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), defs, pkg


def _parse_cs_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    usings = RE_CS_USING.findall(src)
    local = [u for u in usings if not u.startswith("System")]
    external = [u for u in usings if u.startswith("System")]
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), _named(src, RE_CS_SYM)


def _parse_kt_source(src: str) -> tuple[list[str], list[str], list[dict]]:
    imports = RE_KT_IMP.findall(src)
    local = [i for i in imports if not i.startswith(("kotlin.", "java.", "javax."))]
    external = [i for i in imports if i.startswith(("kotlin.", "java.", "javax."))]
    defs = _named(src, RE_KT_SYM, kinds={1: "class", 2: "func"})
    return list(dict.fromkeys(local)), list(dict.fromkeys(external)), defs


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def _named(src: str, pattern: re.Pattern, kinds: dict[int, str] | None = None,
           skip: set[str] | None = None, cap: int = 150) -> list[dict]:
    """Extrai [{n, k, l}] (nome, kind, linha) de matches com grupos name/kind."""
    out: list[dict] = []
    for m in pattern.finditer(src):
        gd = m.groupdict()
        name = gd.get("name") or ""
        kind = (gd.get("kind") or "").lower() if kinds is None else kinds.get(0, "")
        if kinds is not None:
            # padrão multi-grupo sem nomes: usa kinds por índice do grupo
            for idx, k in kinds.items():
                try:
                    if m.group(idx):
                        name, kind = m.group(idx), k
                        break
                except IndexError:
                    pass
        if not name or (skip and name in skip):
            continue
        out.append({"n": name, "k": kind or "def", "l": _line_of(src, m.start())})
        if len(out) >= cap:
            break
    return out


def _strip_c_keep_lines(src: str) -> str:
    return RE_C_COMMENTS.sub(lambda m: "\n" * m.group(0).count("\n"), src)


DART_CTRL = {
    "if", "for", "while", "do", "switch", "catch", "assert", "return",
    "else", "case", "new", "const", "final", "var", "late", "await",
    "yield", "throw", "import", "export", "library", "part", "try", "on",
}


class _PyVisitor(ast.NodeVisitor):
    """Coleta defs (com linha e aninhamento) e nomes chamados (Python)."""

    def __init__(self) -> None:
        self.defs: list[dict] = []
        self.calls: list[str] = []
        self._stack: list[str] = []

    def _visit_def(self, node: ast.AST, kind: str, name: str):
        qual = ".".join(self._stack + [name])
        self.defs.append({"n": qual, "k": kind,
                          "l": getattr(node, "lineno", 0),
                          "top": not self._stack})
        self._stack.append(name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_def(node, "func", node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_def(node, "func", node.name)

    def visit_ClassDef(self, node: ast.ClassDef):
        self._visit_def(node, "class", node.name)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        self.generic_visit(node)


def _resolve_local(raw: str, module_index: dict[str, str]) -> str | None:
    """Mapeia import pontuado para id de módulo local (python/java/csharp/kotlin)."""
    cand = raw.lstrip(".")
    if not cand:
        return None
    if cand in module_index:
        return cand
    parts = cand.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in module_index:
            return prefix
    for mod_id in module_index:
        if mod_id == cand or mod_id.endswith("." + cand):
            return mod_id
    return None


def _resolve_c_include(raw: str, by_rel: dict[str, str], by_base: dict[str, str]) -> str | None:
    raw = raw.strip().lstrip("./")
    if raw in by_rel:
        return by_rel[raw]
    base = raw.rsplit("/", 1)[-1]
    if base in by_base:
        return by_base[base]
    for rel, mod_id in by_rel.items():
        if rel == raw or rel.endswith("/" + raw):
            return mod_id
    return None


def _normposix(base_dir: str, spec: str) -> str | None:
    try:
        return str(PurePosixPath(base_dir or ".").joinpath(spec)).replace("\\", "/")
    except Exception:
        return None


def _resolve_dart(raw: str, importer_rel: str, by_rel: dict[str, str]) -> str | None:
    raw = raw.strip()
    if raw.startswith("package:"):
        rest = raw[len("package:"):]
        segs = rest.split("/")
        tails = [rest] + (["/".join(segs[1:])] if len(segs) > 1 else [])
        for tail in tails:
            for rel, mod_id in by_rel.items():
                if rel == tail or rel.endswith("/" + tail):
                    return mod_id
        return None
    base_dir = str(PurePosixPath(importer_rel).parent)
    cand = _normposix(base_dir, raw)
    if cand and cand in by_rel:
        return by_rel[cand]
    if cand:
        base = cand.rsplit("/", 1)[-1]
        for rel, mod_id in by_rel.items():
            if rel == cand or (rel.rsplit("/", 1)[-1] == base and rel.endswith("/" + cand)):
                return mod_id
    # fallback: import por basename ("service.dart" -> lib/camera/service.dart)
    # só quando é único no repo, para não inventar aresta.
    tail = raw.strip().rsplit("/", 1)[-1]
    if tail and "." in tail:
        hits = [mod_id for rel, mod_id in by_rel.items() if rel.rsplit("/", 1)[-1] == tail]
        if len(hits) == 1:
            return hits[0]
    return None


def _resolve_rust(raw: str, importer_rel: str, by_rel: dict[str, str],
                  package: str) -> list[str]:
    """Rust pode mapear 1 import para N arquivos (mod + dir). Retorna lista."""
    out: list[str] = []
    base_dir = str(PurePosixPath(importer_rel).parent)
    if raw.startswith("mod:"):
        name = raw[4:]
        for cand in (f"{base_dir}/{name}.rs", f"{base_dir}/{name}/mod.rs"):
            cand = candCov(cand)
            if cand in by_rel:
                out.append(by_rel[cand])
        return out
    # use:path::...
    path = raw[4:].strip().strip(":")
    segs = [s for s in path.split("::") if s not in ("", "*") and not s.startswith("{")]
    if not segs:
        return out
    first = segs[0]
    if first in ("crate", "self", "super"):
        segs = segs[1:] if first in ("crate", "self") else segs  # super:: resolve relativo
        rel_segs = segs[:-1] if len(segs) > 1 else segs
        cands = []
        if rel_segs:
            cands.append(f"{base_dir}/{'/'.join(rel_segs)}.rs")
            cands.append(f"{base_dir}/{'/'.join(rel_segs)}/mod.rs")
        for cand in cands:
            cand = candCov(cand)
            if cand in by_rel and by_rel[cand] not in out:
                out.append(by_rel[cand])
        return out
    if package and first == package:
        rest = segs[1:]
        if rest:
            for rel, mod_id in by_rel.items():
                dotted = rel[:-3].replace("/", "::") if rel.endswith(".rs") else None
                if dotted and (dotted.endswith("::" + "::".join(rest)) or dotted == "::".join(rest)):
                    if mod_id not in out:
                        out.append(mod_id)
    return out


def candCov(p: str) -> str:
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


JS_PROBE_EXTS = ("", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")


def _resolve_js(raw: str, importer_rel: str, by_rel: dict[str, str]) -> str | None:
    base_dir = str(PurePosixPath(importer_rel).parent)
    joined = _normposix(base_dir, raw) or ""
    cands = [candCov(joined + ext) for ext in JS_PROBE_EXTS]
    cands += [candCov(f"{joined}/index{ext}") for ext in JS_PROBE_EXTS[1:]]
    for cand in cands:
        if cand in by_rel:
            return by_rel[cand]
    return None


def _resolve_go(raw: str, importer_rel: str, by_rel: dict[str, str],
                dir_files: dict[str, list[str]], module: str) -> list[str]:
    """Import do próprio módulo -> arquivos do pacote-alvo (outro dir)."""
    out: list[str] = []
    if not raw.startswith("go:"):
        return out
    path = raw[3:]
    if module and path.startswith(module):
        rest = path[len(module):].strip("/")
        if rest in dir_files:
            own_dir = str(PurePosixPath(importer_rel).parent)
            if rest != own_dir:
                out.extend(i for i in dir_files[rest])
    return out


def _generic_calls(src: str, cap: int = 200) -> list[str]:
    """Heurística `nome(` para linguagens sem AST. Conservadora por design."""
    # remove strings longas para reduzir falsos positivos (mantém linhas)
    out: list[str] = []
    for m in RE_GENERIC_CALL.finditer(src):
        name = m.group(1)
        if name in CALL_SKIP or name.startswith("_"):
            continue
        if len(name) <= 1:
            continue
        if name not in out:
            out.append(name)
        if len(out) >= cap:
            break
    return out


def _git_changed(root: Path, timeout: int = 10) -> set[str]:
    """Arquivos sujos no git (staged + unstaged + untracked). Fail-soft: fora
    de repo git ou git ausente, retorna vazio sem quebrar o scan."""
    try:
        import subprocess
        p = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1"],
            capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return set()
    except Exception:
        return set()
    out: set[str] = set()
    for line in (p.stdout or "").splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:  # rename: fica com o destino
            path = path.split(" -> ", 1)[1].strip().strip('"')
        if path:
            out.add(path)
    return out


def _find_cycles(links: list[list[str]], max_len: int = 5, max_cycles: int = 8) -> list[list[str]]:
    """Ciclos de import direcionados (DFS limitada, sem explodir em repo grande)."""
    adj: dict[str, list[str]] = {}
    for s, t in links:
        adj.setdefault(s, [])
        if t not in adj[s]:
            adj[s].append(t)
    cycles: list[list[str]] = []
    seen: set[tuple] = set()

    def dfs(start: str, cur: str, path: list[str], depth: int):
        if len(cycles) >= max_cycles or depth > max_len:
            return
        for nxt in adj.get(cur, [])[:20]:
            if nxt == start and len(path) >= 1:
                cyc = path + [start]
                key = tuple(sorted(set(cyc)))
                if key not in seen:
                    seen.add(key)
                    cycles.append(cyc)
            elif nxt not in path and depth < max_len:
                dfs(start, nxt, path + [nxt], depth + 1)

    for s in list(adj)[:400]:
        dfs(s, s, [s], 1)
        if len(cycles) >= max_cycles:
            break
    return cycles


def scan_repository(root: str | Path) -> dict:
    root = Path(root).resolve()
    files = sorted(_iter_code_files(root))

    # nome do pacote rust / módulo go (para resolver `use` / imports locais)
    rust_pkg, go_mod = "", ""
    cargo = root / "Cargo.toml"
    if cargo.is_file():
        m = RE_CARGO_NAME.search(cargo.read_text(encoding="utf-8", errors="ignore"))
        if m:
            rust_pkg = m.group(1).replace("-", "_")
    gomod = root / "go.mod"
    if gomod.is_file():
        m = RE_GO_MOD.search(gomod.read_text(encoding="utf-8", errors="ignore"))
        if m:
            go_mod = m.group(1)

    module_index: dict[str, str] = {}
    by_rel: dict[str, str] = {}
    by_base: dict[str, str] = {}
    dir_files: dict[str, list[str]] = {}
    records: list[dict] = []
    for path in files:
        mod = _module_name(root, path)
        base, k = mod, 2
        while base in module_index:
            base = f"{mod}~{k}"
            k += 1
        rel = path.relative_to(root).as_posix()
        module_index[base] = rel
        by_rel[rel] = base
        by_base.setdefault(Path(rel).name, base)
        dir_files.setdefault(str(PurePosixPath(rel).parent), []).append(base)
        lang = LANG_OF.get(path.suffix.lower(), "python")
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            src = ""
        rec: dict = {"id": base, "rel": rel, "lang": lang,
                     "imports_raw": [], "externals": [], "defs": [],
                     "calls": [], "tops": set(), "caps": [], "loc": 0}
        if lang == "python":
            try:
                tree = ast.parse(src)
                rec["imports_raw"] = _extract_imports(tree)
                vis = _PyVisitor()
                vis.visit(tree)
                rec["defs"] = vis.defs[:150]
                rec["calls"] = list(dict.fromkeys(vis.calls))[:200]
                rec["tops"] = {d["n"].split(".")[0] for d in vis.defs if d.get("top")}
            except (SyntaxError, ValueError):
                pass
        elif lang == "c":
            local, ext, defs = _parse_c_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "dart":
            local, ext, defs = _parse_dart_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "rust":
            local, ext, defs = _parse_rust_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "js":
            local, ext, defs = _parse_js_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "java":
            local, ext, defs = _parse_java_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "go":
            local, ext, defs, pkg = _parse_go_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150], pkg=pkg)
        elif lang == "csharp":
            local, ext, defs = _parse_cs_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        elif lang == "kotlin":
            local, ext, defs = _parse_kt_source(src)
            rec.update(imports_raw=local, externals=ext, defs=defs[:150])
        # genéricos (todas as linguagens): caps de hardware + loc + calls
        try:
            rec["caps"] = _file_caps(src)
        except Exception:
            rec["caps"] = []
        rec["loc"] = src.count("\n") + 1 if src else 0
        try:
            rec["todos"] = _file_todos(src)
        except Exception:
            rec["todos"] = []
        try:
            rec["entry"] = bool(_is_entry(rel, src, rec.get("defs", [])))
        except Exception:
            rec["entry"] = False
        if lang != "python" and rec.get("defs"):
            rec["tops"] = {str(d.get("n", "")).split(".")[-1] for d in rec["defs"] if d.get("n")}
            if not rec.get("calls"):
                try:
                    own_tops = rec["tops"]
                    calls = [c for c in _generic_calls(src) if c not in own_tops]
                    rec["calls"] = calls[:200]
                except Exception:
                    rec["calls"] = []
        records.append(rec)

    # manifestos (AndroidManifest, Info.plist, pubspec, package.json...)
    try:
        manifest_caps, manifest_files = _scan_manifest_caps(root)
    except Exception:
        manifest_caps, manifest_files = {}, []

    # índice global de definições (todas as linguagens): nome curto -> arquivos
    def_index: dict[str, set[str]] = {}
    for r in records:
        for t in r.get("tops", set()):
            if t:
                def_index.setdefault(t, set()).add(r["id"])

    # sujos no git (para "debugue aqui primeiro"); vazio fora de repo git
    try:
        git_changed = _git_changed(root)
    except Exception:
        git_changed = set()

    groups = sorted({r["rel"].split("/")[0] if "/" in r["rel"] else "root" for r in records})
    color_of = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}

    nodes: list[dict] = []
    by_id = {}
    for r in records:
        rel = r["rel"]
        mod = "root" if "/" not in rel else rel.split("/")[0]
        label = Path(rel).stem + Path(rel).suffix
        shown = []
        for _i in list(r["imports_raw"]) + list(r.get("externals", [])):
            if _i.startswith("mod:"):
                shown.append("mod " + _i[4:])
            elif _i.startswith("use:"):
                shown.append(_i[4:] or "use")
            elif _i.startswith("go:"):
                shown.append(_i[3:])
            else:
                shown.append(_i)
        node = {
            "id": r["id"],
            "label": label,
            "file": rel,
            "lang": r.get("lang", "python"),
            "mod": mod,
            "color": color_of.get(mod, "#22d3ee"),
            "imports": shown,
            "externals": list(r.get("externals", []))[:30],
            "symbols": len(r.get("defs", [])),
            "defs": r.get("defs", []),
            "caps": list(r.get("caps", [])),
            "loc": int(r.get("loc", 0)),
            "todo_n": len(r.get("todos", [])),
            "todo_ex": [f"{t['t']}:L{t.get('l', 0)} {t.get('x', '')}".strip()[:100]
                        for t in r.get("todos", [])[:5]],
            "entry": bool(r.get("entry", False)),
            "changed": rel in git_changed,
            "deg": 0,
        }
        nodes.append(node)
        by_id[r["id"]] = node

    links: list[list[str]] = []
    seen_edges = set()

    def add_edge(s: str, t: str | None):
        if t and t != s and (s, t) not in seen_edges:
            seen_edges.add((s, t))
            links.append([s, t])

    for r in records:
        src_id, lang = r["id"], r.get("lang", "python")
        for raw in r["imports_raw"]:
            if lang in ("python", "java", "csharp", "kotlin"):
                add_edge(src_id, _resolve_local(raw, module_index))
            elif lang == "c":
                add_edge(src_id, _resolve_c_include(raw, by_rel, by_base))
            elif lang == "dart":
                add_edge(src_id, _resolve_dart(raw, r["rel"], by_rel))
            elif lang == "rust":
                for dst in _resolve_rust(raw, r["rel"], by_rel, rust_pkg):
                    add_edge(src_id, dst)
            elif lang == "js":
                add_edge(src_id, _resolve_js(raw, r["rel"], by_rel))
            elif lang == "go":
                for dst in _resolve_go(raw, r["rel"], by_rel, dir_files, go_mod):
                    add_edge(src_id, dst)

    # call edges (todas as linguagens): chamador -> arquivo que define o nome.
    # Regra conservadora: ignora chamadas a nomes locais e nomes ambíguos
    # (definidos em 2+ arquivos) para não inventar aresta.
    call_edges: list[list[str]] = []
    seen_calls = set()
    for r in records:
        own = set(r.get("tops", set())) | {r["id"].split(".")[-1].split("~")[0]}
        for name in r.get("calls", []):
            if not name or name in own:
                continue
            definers = (def_index.get(name, set()) - {r["id"]}) or set()
            if len(definers) == 1:
                dst = next(iter(definers))
                key = (r["id"], dst, name)
                if key not in seen_calls:
                    seen_calls.add(key)
                    call_edges.append([r["id"], dst, name])

    deg: dict[str, int] = {n["id"]: 0 for n in nodes}
    for s, t in links:
        deg[s] = deg.get(s, 0) + 1
        deg[t] = deg.get(t, 0) + 1
    for n in nodes:
        n["deg"] = deg.get(n["id"], 0)
        n["size"] = round(6 + min(n["deg"], 30) * 0.9 + min(n["symbols"], 20) * 0.25, 2)

    nodes.sort(key=lambda n: -n["deg"])

    # capabilities agregadas: cap -> arquivos (código) + evidências de manifesto
    capabilities: dict[str, list[str]] = {}
    for n in nodes:
        for cap in n.get("caps", []):
            capabilities.setdefault(cap, [])
            if n["file"] not in capabilities[cap]:
                capabilities[cap].append(n["file"])
    for cap, evs in manifest_caps.items():
        capabilities.setdefault(cap, [])
        for ev in evs:
            tag = f"manifest:{ev}"
            if tag not in capabilities[cap]:
                capabilities[cap].append(tag)
    for cap in capabilities:
        capabilities[cap] = sorted(capabilities[cap])[:50]

    # riscos: god files, fan-in/out alto, ciclos, TODOs, entrypoints, órfãos
    by_id2 = {n["id"]: n for n in nodes}
    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    for s, t in links:
        out_deg[s] = out_deg.get(s, 0) + 1
        in_deg[t] = in_deg.get(t, 0) + 1
    gods = []
    for n in nodes:
        score = n.get("loc", 0) / 400 + n.get("symbols", 0) / 20 + n.get("deg", 0) / 5
        if n.get("loc", 0) >= GOD_LOC or n.get("symbols", 0) >= GOD_SYMS or n.get("deg", 0) >= GOD_DEG:
            gods.append({"file": n["file"], "loc": n.get("loc", 0),
                         "symbols": n.get("symbols", 0), "deg": n.get("deg", 0),
                         "score": round(score, 2)})
    gods.sort(key=lambda g: -g["score"])
    fan_out = [{"file": by_id2[s]["file"], "n": v} for s, v in out_deg.items()
               if v >= FAN_LIM and s in by_id2]
    fan_out.sort(key=lambda d: -d["n"])
    fan_in = [{"file": by_id2[t]["file"], "n": v} for t, v in in_deg.items()
              if v >= FAN_LIM and t in by_id2]
    fan_in.sort(key=lambda d: -d["n"])
    try:
        raw_cycles = _find_cycles(links)
    except Exception:
        raw_cycles = []
    cycles = []
    for cyc in raw_cycles[:8]:
        files = [by_id2[i]["file"] if i in by_id2 else i for i in cyc]
        cycles.append(files)
    todo_files = [{"file": n["file"], "n": n.get("todo_n", 0),
                   "ex": n.get("todo_ex", [])[:3]}
                  for n in nodes if n.get("todo_n", 0) > 0]
    todo_files.sort(key=lambda d: -d["n"])
    entries = [n["file"] for n in nodes if n.get("entry")]
    orphans = [n["file"] for n in nodes if n.get("deg", 0) == 0 and not n.get("entry")][:20]
    risks = {
        "gods": gods[:10],
        "fan_out": fan_out[:10],
        "fan_in": fan_in[:10],
        "cycles": cycles,
        "todos": todo_files[:10],
        "todo_total": sum(n.get("todo_n", 0) for n in nodes),
        "entries": entries[:20],
        "orphans": orphans,
    }

    return {
        "nodes": nodes,
        "links": links,
        "call_edges": call_edges,
        "mods": color_of,
        "capabilities": capabilities,
        "manifest_files": manifest_files,
        "risks": risks,
        "changed": sorted(git_changed)[:100],
        "meta": {
            "root": str(root),
            "files": len(files),
            "edges": len(links),
            "call_edges": len(call_edges),
            "git_changed": len(git_changed),
            "langs": sorted({r.get("lang", "python") for r in records}),
            "supported": SUPPORTED_LABEL,
        },
    }
