"""Compatibility entry point for the native Agent-for-qqbot management panel."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("AGENT_QQBOT_PROJECT", str(ROOT))
sys.path.insert(0, str(ROOT / "hermes/core"))


if __name__ == "__main__":
    from soyo.app.__main__ import main
    raise SystemExit(main(["start", *sys.argv[1:]]))
