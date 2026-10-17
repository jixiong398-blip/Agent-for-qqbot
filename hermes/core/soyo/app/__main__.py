# SPDX-License-Identifier: MIT
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import sys

from .config import home_path, initialize, read_json, redacted, update, validate


def control(home, path, body=None):
    import httpx
    import psutil
    from .config import endpoint, trusted_ui_host
    config = read_json(Path(home) / "deployment.json")
    if not config: raise ValueError('Instance is not installed')
    supervisor = read_json(Path(home) / 'run/supervisor.json', default={})
    try:
        process = psutil.Process(supervisor.get('pid', -1))
        if abs(process.create_time() - supervisor.get('created_at', -1)) >= 0.01:
            raise ValueError('Supervisor identity changed; no request sent to an unknown port')
    except psutil.Error:
        raise ValueError('This instance supervisor is not running; no unrelated process was stopped') from None
    key = (Path(home) / "private/control-key").read_text(encoding="ascii").strip()
    # The saved next-start port may differ from the current listener.
    origin = endpoint(supervisor.get('url'), {'http'})
    from urllib.parse import urlsplit
    address = urlsplit(origin)
    if not trusted_ui_host(address.hostname) or not address.port or address.path not in ('', '/'):
        raise ValueError('Supervisor endpoint must be an explicit loopback root URL')
    with httpx.Client(base_url=origin, trust_env=False, timeout=max(config["ready_timeout"], config["stop_timeout"] * 5) + 10,
                      headers={"Authorization": "Bearer " + key, "Origin": origin}) as client:
        if body is None:
            response = client.get(path)
        else:
            csrf = client.get("/api/csrf"); csrf.raise_for_status()
            response = client.post(path, json=body, headers={"X-Agent-CSRF": csrf.json()["csrf"]})
        response.raise_for_status()
        return response.json()


def _configure(home):
    current = initialize(home)
    def prompt(label, old="", *, secret=False):
        value = (getpass.getpass if secret else input)(label + (" [keep existing]" if old else "") + ": ")
        return value.strip() or old
    name = prompt("Character name", current["character_name"])
    models = {}
    same = prompt("Reuse character provider/model for action brain? yes/no", "yes" if current.get("action_uses_character", not bool(current['models']['action'])) else "no").lower() == "yes"
    for lane in ("character", "action"):
        if lane == "action" and same:
            import copy
            models[lane] = copy.deepcopy(models["character"])
            continue
        old = current["models"].get(lane, {})
        print("\nConfigure " + lane + " route (no provider/model is inferred)")
        auth = prompt("Authentication: bearer or none (no-key local loopback only)", old.get("auth_mode", "bearer"))
        models[lane] = {"name": prompt("Model ID", old.get("name", "")),
            "base_url": prompt("OpenAI-compatible API base URL", old.get("base_url", "")),
            "api_key": prompt("API key", old.get("api_key", ""), secret=True) if auth == "bearer" else "", "auth_mode": auth,
            "api": prompt("Protocol: openai-completions or openai-responses", old.get("api", "openai-completions")),
            "context_window": int(prompt("Documented context ceiling", str(old.get("context_window", "")))),
            "max_tokens": int(prompt("Output token ceiling", str(old.get("max_tokens", "")))),
            "reasoning_effort": prompt("Reasoning effort (blank = provider default)", old.get("reasoning_effort", "")),
            "vision": prompt("Image support explicitly available? yes/no", "yes" if old.get("vision") else "no").lower() == "yes"}
    qq = current["onebot"]
    enable_qq = prompt("Enable QQ now? yes/no (no = Web only)", "yes" if qq.get("enabled", False) else "no").lower() == "yes"
    onebot = {"enabled": enable_qq}
    if enable_qq: onebot.update({"account_id": prompt("Bot QQ", qq["account_id"]),
        "admin_ids": [x.strip() for x in prompt("Owner QQ IDs, comma-separated", ",".join(qq["admin_ids"])).split(",") if x.strip()],
        "http_url": prompt("NapCat loopback HTTP URL including port", qq["http_url"]),
        "ws_url": prompt("NapCat loopback WS URL including port/path", qq["ws_url"]),
        "token": prompt("NapCat access token", qq["token"], secret=True),
        "config_directory": prompt("NapCat account config directory (optional)", qq.get("config_directory", ""))})
    permission = prompt("Host tool mode: read-only/workspace-write/danger-full-access", current["host_permission_mode"])
    result = update(home, {"character_name": name, "models": models, "onebot": onebot, "action_uses_character": same,
                           "host_permission_mode": permission}, current["revision"])
    persona = Path(home) / "persona/SOUL.md"
    if not persona.exists():
        filename = prompt("Path to your SOUL/persona file (blank = editable basic draft)")
        if filename:
            source = Path(filename).expanduser().resolve()
            if not source.is_file() or source.stat().st_size > 256 * 1024:
                raise ValueError("Persona source missing or too large")
            text = source.read_text(encoding="utf-8-sig")
        else:
            text = "# " + name + "\n\nYou are " + name + ". Keep your identity consistent. Be honest about what you know and what you have actually done.\n"
        from .persona import save
        save(home, text=text)
    validate(read_json(Path(home) / "deployment.json"), ready=True)
    print("Configuration saved privately; existing databases/history were not imported or changed")
    return 0


def configure(home):
    from soyo.platform import file_lock
    initialize(home)
    with file_lock(Path(home) / 'run/lifecycle.lock', blocking=False):
        return _configure(home)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agent-qqbot")
    parser.add_argument("--home", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install")
    install.add_argument("--inside-venv", action="store_true", help=argparse.SUPPRESS)
    commands.add_parser("update", help="Rebuild the current checkout into a new immutable runtime; never git-pull over local work")
    config = commands.add_parser("configure"); config.add_argument("--web", action="store_true")
    start = commands.add_parser("start"); start.add_argument("--no-browser", action="store_true"); start.add_argument("--no-autostart", action="store_true")
    commands.add_parser("stop")
    commands.add_parser("status")
    commands.add_parser('rollback', help='Select the previous built runtime, without starting it or changing databases')
    commands.add_parser('install-live2d', help='Explicitly install optional Electron dependencies, without launching them')
    commands.add_parser('recover-runtime', help='Restore known profile links/manifest after an interrupted installation, without starting services')
    commands.add_parser("doctor", help="Read-only local inventory, not tests or network probes")
    args = parser.parse_args(argv)
    home = home_path(args.home)
    if args.command == 'recover-runtime':
        from .install import recover_runtime
        print(json.dumps(recover_runtime(home)))
        return 0
    if args.command == 'install-live2d':
        from .install import install_live2d
        install_live2d(home)
        return 0
    if args.command == 'rollback':
        from .install import rollback
        rollback(home)
        print('Previous built runtime selected; not started. Session/database formats were not downgraded.')
        return 0
    if args.command in {"install", "update"}:
        from .install import install
        install(home, install_python=not getattr(args, "inside_venv", False))
        return 0
    if args.command == "configure" and not args.web:
        return configure(home)
    if args.command in {"start", "configure"}:
        from .web import serve
        serve(home, open_browser=not getattr(args, "no_browser", False),
              autostart=args.command == "configure" or not args.no_autostart)
        return 0
    if args.command in {"stop", "status"}:
        value = control(home, "/api/shutdown", {}) if args.command == "stop" else control(home, "/api/status")
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    config = read_json(home / 'deployment.json')
    if not config: raise ValueError('Instance is not installed; inventory does not create it')
    from .install import node_and_npm, source_fingerprint
    checks = {"home": str(home), "python": sys.version.split()[0], "tests_run": False,
              "services_started": False, "network_probes": False}
    try:
        node, _npm = node_and_npm(config); checks["node"] = node
    except (ValueError, OSError) as error:
        checks["node_error"] = str(error)
    try:
        validate(config, ready=True); checks["configuration_ready"] = True
    except ValueError as error:
        checks.update(configuration_ready=False, configuration_error=str(error))
    runtime = read_json(home / "private/runtime.json", default={})
    checks["source_matches_runtime"] = runtime.get("source_fingerprint") == source_fingerprint()
    checks["persona_exists"] = (home / "persona/SOUL.md").is_file()
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # API/server error bodies and credentials are deliberately not printed.
        print("Operation failed: " + type(error).__name__ + ": " + str(error)[:300], file=sys.stderr)
        raise SystemExit(1)
