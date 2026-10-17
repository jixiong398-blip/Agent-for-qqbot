#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
if [ -f "$ROOT/portable-manifest.json" ]; then
  exec "$ROOT/runtime/python/bin/python3" -I -B "$ROOT/extras/scripts/portable_launcher.py" start "$@"
fi
exec "${AGENT_QQBOT_PYTHON:-python3}" "$ROOT/extras/scripts/bootstrap.py" start "$@"
