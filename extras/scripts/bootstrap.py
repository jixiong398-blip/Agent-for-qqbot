#!/usr/bin/env python3
"""Stdlib-only dispatcher, shared by Windows and POSIX launch wrappers."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ is required; select a compatible interpreter")
import tomllib

ROOT = Path(__file__).resolve().parents[2]
os.environ["AGENT_QQBOT_PROJECT"] = str(ROOT)
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main():
    metadata = tomllib.loads((ROOT / "application.toml").read_text(encoding="utf-8"))
    minimum = tuple(map(int, metadata["runtime"]["python_minimum"].split(".")))
    if sys.version_info[:2] < minimum:
        raise SystemExit("Install Python " + metadata["runtime"]["python_minimum"] + "+ first")
    home = Path(os.path.abspath(Path(os.environ.get("AGENT_QQBOT_HOME", str(Path.home() / ".agent-for-qqbot"))).expanduser()))
    arguments = sys.argv[1:] or ["start"]
    if (ROOT / "portable-manifest.json").is_file():
        # One dispatcher for both layouts: the prebuilt bundle reuses its own Python.
        bundled = ROOT / "runtime/python" / ("python.exe" if os.name == "nt" else "bin/python3")
        launcher = Path(__file__).resolve().parent / "portable_launcher.py"
        python = bundled if bundled.is_file() else Path(sys.executable)
        return subprocess.call([str(python), "-I", "-B", str(launcher), *arguments], env=os.environ.copy())
    python = home / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # POSIX venv python is normally a symlink to the system interpreter. Compare
    # environments, not resolved executables, or installed dependencies vanish.
    if python.is_file() and Path(sys.prefix).resolve() != (home / "venv").resolve():
        return subprocess.call([str(python), "-B", str(Path(__file__).resolve()), *arguments], env=os.environ.copy())
    if not python.is_file() and arguments[0] != "install":
        raise SystemExit("This instance is not installed. Run install.bat or ./install.sh first")
    sys.path.insert(0, str(ROOT / "hermes/core"))
    from soyo.app.__main__ import main as application
    return application(["--home", str(home), *arguments])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # The same bounded error surface as `python -m soyo.app`; no giant
        # traceback or model-credential form echoed into installation consoles.
        print("Operation failed: " + type(error).__name__ + ": " + str(error)[:300], file=sys.stderr)
        raise SystemExit(1)
