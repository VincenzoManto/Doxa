"""
start.py  –  NexusFish Self-Bootstrapper
Run ONCE with plain Python (no dependencies needed):

    python start.py

Does everything automatically:
  1. Installs required Python packages (pip)
  2. Downloads and installs Ollama if not present (Windows)
  3. Starts Ollama in the background if not already listening
  4. Downloads the LLM model defined in world.yaml (e.g. qwen2.5:1.5b, llama3.2…)
  5. Launches  streamlit run app.py
"""

# start.py  –  NexusFish Self-Bootstrapper (Flask version)
# -----------------------------------------
# Run ONCE with plain Python (no dependencies needed):
#
#     python start.py
#
# Does everything automatically:
#   1. Installs required Python packages (from requirements.txt)
#   2. Downloads and installs Ollama if not present (Windows)
#   3. Starts Ollama in the background if not already listening
#   4. Downloads the LLM model defined in world.yaml (e.g. qwen2.5:1.5b, llama3.2…)
#   5. Launches Flask backend server (app.py)

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

OLLAMA_WIN_URL  = "https://ollama.com/download/OllamaSetup.exe"
OLLAMA_MAC_URL  = "https://ollama.com/download/Ollama-darwin.zip"
OLLAMA_INSTALLER = Path.home() / ".nexusfish_cache" / "OllamaSetup.exe"

# Candidate paths where Ollama ends up after a Windows install
OLLAMA_WIN_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Ollama" / "ollama.exe",
    Path(r"C:\Users") / os.environ.get("USERNAME", "") / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe",
]


# Read requirements.txt for backend dependencies
REQUIREMENTS_TXT = Path(__file__).parent / "requirements.txt"
def _read_requirements():
    if REQUIREMENTS_TXT.exists():
        return [l.strip() for l in REQUIREMENTS_TXT.read_text().splitlines() if l.strip() and not l.startswith('#')]
    return []
REQUIRED_PACKAGES = _read_requirements()

WORLD_YAML = Path(__file__).parent / "world_config.yaml"
OLLAMA_API = "http://localhost:11434"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"
IS_LINUX   = platform.system() == "Linux"

_GREEN  = "\033[92m"
_YELLOW = "\033[93m"
_RED    = "\033[91m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _p(msg: str, colour: str = "") -> None:
    print(f"{colour}{msg}{_RESET}" if colour else msg, flush=True)

def _ok(msg: str)   -> None: _p(f"  ✓  {msg}", _GREEN)
def _info(msg: str) -> None: _p(f"  →  {msg}", _CYAN)
def _warn(msg: str) -> None: _p(f"  ⚠  {msg}", _YELLOW)
def _err(msg: str)  -> None: _p(f"  ✗  {msg}", _RED)
def _h(msg: str)    -> None: _p(f"\n{_BOLD}{'─'*55}\n  {msg}\n{'─'*55}{_RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Python packages
# ─────────────────────────────────────────────────────────────────────────────

def install_python_packages() -> None:
    _h("STEP 1/4 — Python packages")
    if not REQUIRED_PACKAGES:
        _warn("No requirements.txt found or empty.")
        return
    pip = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"]
    result = subprocess.run(pip + REQUIRED_PACKAGES, capture_output=True, text=True)
    if result.returncode != 0:
        _warn(f"pip output:\n{result.stderr[-800:]}")
    _ok(f"Packages installed: {', '.join(p.split('>=')[0] for p in REQUIRED_PACKAGES)}")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Find or install Ollama
# ─────────────────────────────────────────────────────────────────────────────

def _find_ollama_exe() -> Path | None:
    """Search for ollama in PATH and common Windows installation paths."""
    import shutil
    found = shutil.which("ollama")
    if found:
        return Path(found)
    if IS_WINDOWS:
        for p in OLLAMA_WIN_PATHS:
            if p.exists():
                return p
    return None


def _download_with_progress(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _info(f"Downloading from {url} …")
    last_pct = [-1]

    def _reporthook(count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        pct = min(int(count * block_size * 100 / total_size), 100)
        if pct != last_pct[0] and pct % 5 == 0:
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)
            last_pct[0] = pct

    urllib.request.urlretrieve(url, str(dest), reporthook=_reporthook)
    print()  # newline after progress bar


def install_ollama() -> Path:
    _h("STEP 2/4 — Ollama")

    exe = _find_ollama_exe()
    if exe:
        _ok(f"Ollama already installed: {exe}")
        return exe

    if not IS_WINDOWS:
        _err("Automatic installation is only supported on Windows.")
        _warn("Install manually from: https://ollama.com/download")
        _warn("Then rerun: python start.py")
        sys.exit(1)

    _info("Ollama not found – downloading installer …")
    _download_with_progress(OLLAMA_WIN_URL, OLLAMA_INSTALLER)

    _info("Running installer in background (Inno Setup, silent mode) …")
    _info("This may take 30-60 seconds …")
    result = subprocess.run(
        [str(OLLAMA_INSTALLER), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        capture_output=True, text=True
    )

    # After install, search again
    time.sleep(3)
    exe = _find_ollama_exe()
    if not exe:
        # Force the most common path
        candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        if candidate.exists():
            exe = candidate

    if not exe:
        _err("Installer completed but ollama.exe not found.")
        _warn("Try adding Ollama to PATH and rerun: python start.py")
        sys.exit(1)

    _ok(f"Ollama installed at: {exe}")
    return exe


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Start Ollama serve (if not already running)
# ─────────────────────────────────────────────────────────────────────────────

def _ollama_is_running() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{OLLAMA_API}/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_ollama_running(ollama_exe: Path) -> None:
    _h("STEP 3/4 — Ollama server")

    if _ollama_is_running():
        _ok("Ollama is already listening on localhost:11434")
        return

    _info("Starting Ollama in background …")
    subprocess.Popen(
        [str(ollama_exe), "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
    )

    # Wait up to 20s for the server to be ready
    for i in range(20):
        time.sleep(1)
        if _ollama_is_running():
            _ok(f"Ollama ready after {i+1}s")
            return
        print(f"\r  Waiting for Ollama to start … {i+1}s", end="", flush=True)

    print()
    _warn("Ollama did not respond within 20s. Continuing anyway (will use stubs).")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Download the model requested by world.yaml
# ─────────────────────────────────────────────────────────────────────────────

def _read_model_from_yaml() -> str:
    """Read world.yaml with minimal regex — without pyyaml (may not be installed yet)."""
    import re
    if not WORLD_YAML.exists():
        return "qwen2.5:1.5b"
    text = WORLD_YAML.read_text(encoding="utf-8")
    m = re.search(r"model:\s+['\"]?([^\s'\"]+)['\"]?", text)
    return m.group(1) if m else "qwen:1.5b"


def _model_is_available(model: str, ollama_exe: Path) -> bool:
    try:
        result = subprocess.run(
            [str(ollama_exe), "list"],
            capture_output=True, text=True, timeout=10
        )
        return model.split(":")[0] in result.stdout
    except Exception:
        return False


def pull_model(ollama_exe: Path) -> None:
    _h("STEP 4/4 — LLM Model")
    model = _read_model_from_yaml()
    _info(f"Model requested by world.yaml: [bold]{model}[/bold]")

    if not _ollama_is_running():
        _warn("Ollama unreachable — skipping pull. UI will use stub mode.")
        return

    if _model_is_available(model, ollama_exe):
        _ok(f"Model '{model}' already present")
        return

    _info(f"Downloading '{model}' … (may take several minutes — please wait)")
    _info("Download progress will be shown in the terminal:")
    print()

    # ollama pull prints progress to stdout — we stream it in real time
    proc = subprocess.Popen(
        [str(ollama_exe), "pull", model],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    proc.wait()

    if proc.returncode == 0:
        _ok(f"Model '{model}' downloaded successfully")
    else:
        _warn(f"Pull of '{model}' failed (exit {proc.returncode}). UI will use stub mode.")


# ─────────────────────────────────────────────────────────────────────────────
# Launch Streamlit
# ─────────────────────────────────────────────────────────────────────────────


def launch_app() -> None:
    app_path = Path(__file__).parent / "app.py"
    if not app_path.exists():
        _err(f"app.py not found in {app_path.parent}")
        sys.exit(1)

    _p(f"\n{'═'*55}", _BOLD)
    _p("  🐟  NexusFish — Launching Flask Backend", _BOLD)
    _p(f"{'═'*55}\n", _BOLD)
    _info("Flask backend running at:  http://localhost:5000")
    _info("To stop: Ctrl+C\n")

    subprocess.run([
        sys.executable, str(app_path)
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Banner
    _p(f"""
{_BOLD}{_CYAN}
  ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
  ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
  ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
  ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
  ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
  ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
  NexusFish Self-Bootstrapper
{_RESET}""")

    _p("  Automatic installation of all components …\n", _YELLOW)

    # 1. Python deps
    install_python_packages()

    # 2. Ollama binary
    ollama_exe = install_ollama()

    # 3. Server
    ensure_ollama_running(ollama_exe)

    # 4. Model
    pull_model(ollama_exe)

    # 5. Streamlit UI
    launch_app()


if __name__ == "__main__":
    main()
