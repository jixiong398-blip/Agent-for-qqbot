# SPDX-License-Identifier: MIT
"""One explicit per-instance config; never discovers or imports a production home."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import tomllib
from urllib.parse import urlsplit

from soyo.platform import assert_private, file_lock, is_link, private_fchmod, protect, sync_directory, load_private_json

NATIVE_OPTIONS = {"max_media_bytes", "chunk_delay_seconds", "reply_part_chars", "max_reply_parts",
    "bandori_knowledge_root", "bandori_source_url", "bandori_sitemap_path", "bandori_language", "bandori_article_sections",
    "legacy_memory_db", "legacy_cron_file", "action_turn_timeout_ms", "character_turn_timeout_ms",
    "cognition_start_seq", "note_quotas", "auto_approve_admin_invites"}


def project_root():
    override = os.environ.get("AGENT_QQBOT_PROJECT")
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "application.toml").is_file():
            raise ValueError("AGENT_QQBOT_PROJECT has no application.toml")
        return root
    for root in Path(__file__).resolve().parents:
        if (root / "application.toml").is_file():
            return root
    raise ValueError("Project metadata not found; set AGENT_QQBOT_PROJECT")


def metadata():
    return tomllib.loads((project_root() / "application.toml").read_text(encoding="utf-8"))


def home_path(value=None):
    raw = value or os.environ.get("AGENT_QQBOT_HOME")
    home = Path(os.path.abspath(Path(raw).expanduser())) if raw else Path.home() / ".agent-for-qqbot"
    if is_link(home) or any(is_link(parent) for parent in home.parents):
        raise ValueError("Private instance home must not traverse links or junctions")
    root = project_root().resolve()
    if home == root or root in home.parents:
        raise ValueError("Keep private instance data outside the source checkout")
    return home


def atomic_json(path, value):
    path = Path(path)
    if is_link(path) or is_link(path.parent):
        raise ValueError("Refusing linked configuration destination")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(path.parent, directory=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            private_fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path, *, default=None):
    try:
        return load_private_json(Path(path))
    except FileNotFoundError:
        return copy.deepcopy(default)


def initialize(home):
    home = Path(home)
    if home.exists() and any(home.iterdir()) and not (home / 'deployment.json').is_file() and not (home / '.native-bootstrap').is_file():
        raise ValueError('Nonempty unfamiliar directory; select a new native instance home')
    if any((home / name).exists() for name in (".env", "config.yaml", "state.db", "memory_store.db")):
        raise ValueError("Existing legacy runtime detected; select a separate native instance home")
    if is_link(home):
        raise ValueError("Instance home cannot be a link or junction")
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    protect(home, directory=True)
    for name in ("private", "logs", "run", "backups", "persona", "workspace", "profiles", "runtimes"):
        path = home / name
        if is_link(path):
            raise ValueError("Instance directories cannot be links")
        path.mkdir(mode=0o700, exist_ok=True)
        protect(path, directory=True)
    with file_lock(home / "run" / "config.lock"):
        path = home / "deployment.json"
        if not path.exists():
            values = copy.deepcopy(metadata()["defaults"])
            values.update({"schema_version": 1, "revision": 1, "profile": "qqbot", "character_name": "Bot",
                "models": {"character": {}, "action": {}, "fallbacks": []}, "model_profiles": {}, "action_uses_character": True,
                "routes": {}, "onebot": {"enabled": False, "account_id": "", "admin_ids": [], "allowed_users": [],
                    "blocked_users": [], "owner_group_ids": [], "http_url": "", "ws_url": "",
                    "config_directory": "", "token": ""},
                "native_require_key": False, "management_require_key": False, "host_permission_mode": "workspace-write", "action_label": "行动助手",
                "napcat": {"directory": str(home / "napcat"), "command": [], "autostart": False},
                "live2d": {"enabled": False, "directory": str(project_root() / "modules/live2d"),
                    "manifest_url": metadata()['live2d_defaults']['manifest_url'], "models_directory": str(home / 'live2d/models')},
                "knowledge": {"directory": str(project_root() / "modules/knowledge"), "shared": False},
                "features": {"cognition": True, "operator_ui": True},
                "speech": {"enabled": False, "transcription_url": "", "model": "", "api_key": ""},
                "briefing_fonts": {"regular": "", "bold": ""},
                "automation_jobs": [], "development_projects": [], "development": {"backend": "disabled"},
                "agent_line": {"routes": []}, "native_options": {},
                "feishu": {"app_id": "", "app_secret": "", "chat_id": ""},
                "time_zone": "", "executables": {}, "runtime": {}, "registries": copy.deepcopy(metadata()["registries"])})
            atomic_json(path, values)
        else:
            existing = read_json(path)
            missing = {key: value for key, value in metadata()['defaults'].items() if key not in existing}
            if missing:
                atomic_json(home / 'backups' / ('before-defaults-' + secrets.token_hex(6) + '.json'), existing)
                existing.update(missing); existing['revision'] += 1; atomic_json(path, existing)
        for name in ("control-key", "web-access-key", "channel-key", "live2d-key"):
            key = home / "private" / name
            if not key.exists():
                with key.open("x", encoding="ascii") as stream:
                    private_fchmod(stream.fileno(), 0o600)
                    stream.write(secrets.token_urlsafe(48) + "\n"); stream.flush(); os.fsync(stream.fileno())
            assert_private(key, max_bytes=129)
    return read_json(home / "deployment.json")


def endpoint(value, schemes, *, loopback=False):
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n\x00"):
        raise ValueError("An explicit endpoint is required")
    url = urlsplit(value)
    if url.scheme not in schemes or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Endpoint must have a supported protocol and no credentials/query")
    if loopback and (url.hostname != "127.0.0.1" or not url.port):
        raise ValueError("OneBot endpoint must be explicit loopback with a port")
    return value.rstrip("/")


def trusted_ui_host(value):
    """Public product is local-only. Remote maintenance belongs outside the app."""
    return value == '127.0.0.1'


def trusted_ui_peer(value, host):
    # Do not trust Forwarded/X-Forwarded-For. Only the actual TCP peer can
    # establish the local boundary for a direct-entry browser.
    if value.startswith('::ffff:'): value = value[7:]
    return trusted_ui_host(host) and value == '127.0.0.1'


def model(value, *, required=False):
    if not value and not required:
        return {}
    if not isinstance(value, dict) or set(value) - {"name", "base_url", "api_key", "auth_mode", "api", "context_window", "max_tokens", "reasoning_effort", "reasoning_efforts", "vision"}:
        raise ValueError("Unsupported model fields")
    result = copy.deepcopy(value)
    if not required and not any(result.get(key) for key in ("name", "base_url", "api_key")):
        return {}
    if not all(isinstance(result.get(k), str) and result[k].strip() for k in ("name", "base_url")):
        raise ValueError("Model ID and endpoint must be explicitly configured")
    result["base_url"] = endpoint(result["base_url"], {"http", "https"})
    auth = result.setdefault("auth_mode", "bearer")
    if auth not in {"bearer", "none"}:
        raise ValueError("Choose API key authentication or explicit local no-key mode")
    if auth == "none" and urlsplit(result["base_url"]).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("No-key model access is restricted to a local loopback endpoint")
    key = result.get("api_key", "") if auth == "bearer" else ""
    if not isinstance(key, str) or (auth == "bearer" and not key.strip()):
        raise ValueError("An API key is required, or explicitly select local no-key mode")
    result["api_key"] = key
    if result.get("api") not in {"openai-completions", "openai-responses"}:
        raise ValueError("Choose Chat Completions or Responses explicitly")
    context, output = result.get("context_window"), result.get("max_tokens")
    if type(context) is not int or type(output) is not int or not 0 < output < context:
        raise ValueError("Explicit context/output ceilings required: 0 < output < context")
    if not key.isascii() or any(c in key for c in "\r\n\x00"):
        raise ValueError("Invalid credential")
    if result.get("reasoning_effort", "") not in {"", "none", "off", "minimal", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError("Unsupported reasoning effort")
    # DSH/pi-ai's semantic level is `off`; `none` is a provider wire spelling,
    # not a valid runtime level. Keep old/user-facing none as an input alias.
    if result.get('reasoning_effort') == 'none': result['reasoning_effort'] = 'off'
    efforts = result.get('reasoning_efforts', {})
    levels = {'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'}
    if not isinstance(efforts, dict) or set(efforts) - levels or (efforts and not set(efforts) - {'off'}):
        raise ValueError('Reasoning wire mapping must declare supported native levels, including at least one thinking level')
    for level, wire in efforts.items():
        if wire is None and level == 'off': continue
        if not isinstance(wire, str) or not 0 < len(wire) <= 64 or any(ord(c) < 32 for c in wire):
            raise ValueError('Invalid reasoning wire mapping')
    if efforts and result.get('reasoning_effort') and result['reasoning_effort'] not in efforts:
        raise ValueError('Selected reasoning effort is absent from the declared provider mapping')
    if type(result.get("vision", False)) is not bool:
        raise ValueError("Image support must be an explicit boolean")
    return result


def validate(config, *, ready=False):
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise ValueError("Unsupported native configuration schema")
    defaults = metadata()["defaults"]
    ports = []
    for key in defaults:
        if key.endswith("_port"):
            value = config.get(key)
            if type(value) is not int or not 1 <= value <= 65535:
                raise ValueError("Invalid configured port: " + key)
            ports.append(value)
    if len(ports) != len(set(ports)):
        raise ValueError("Instance listener ports must be distinct")
    for key in ("ready_timeout", "stop_timeout"):
        if type(config.get(key)) is not int or not 1 <= config[key] <= 600:
            raise ValueError("Invalid bounded lifecycle timeout")
    for key in ("native_require_key", "management_require_key"):
        if type(config.get(key, False)) is not bool:
            raise ValueError("Boolean setting required: " + key)
    if config.get("native_upstream_host", "127.0.0.1") != "127.0.0.1":
        raise ValueError("Native upstream must remain loopback")
    for key in ('management_host', 'native_host'):
        if not trusted_ui_host(config.get(key)):
            raise ValueError("UI listeners must bind local loopback; remote maintenance is external")
    if config.get("host_permission_mode") not in {"read-only", "workspace-write", "danger-full-access"}:
        raise ValueError("Unsupported native Host permission mode")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", config.get("profile", "")):
        raise ValueError("Invalid profile name")
    if type(config.get("action_uses_character", False)) is not bool:
        raise ValueError("Action model reuse must be an explicit boolean")
    if config.get("action_uses_character", False):
        config["models"]["action"] = copy.deepcopy(config["models"]["character"])
    for key in ("character", "action"):
        config["models"][key] = model(config["models"].get(key), required=ready)
    if not isinstance(config["models"].get("fallbacks", []), list):
        raise ValueError("Fallback routes must be a list")
    for item in config["models"].get("fallbacks", []):
        model(item, required=True)
    profiles = config.get("model_profiles", {})
    if not isinstance(profiles, dict) or len(profiles) > 32:
        raise ValueError("At most 32 named model profiles are supported")
    for name, saved in profiles.items():
        if not valid_profile_label(name) or not isinstance(saved, dict) or set(saved) != {"character", "action"}:
            raise ValueError("Invalid named model profile")
        for item in saved.values(): model(item, required=True)
    routes = config.get("routes", {})
    available = {"qqbot-character": config["models"]["character"], "qqbot-action": config["models"]["action"],
                 **{"qqbot-fallback-" + str(i): value for i, value in enumerate(config["models"].get("fallbacks", []))}}
    if not isinstance(routes, dict) or set(routes) - {"character", "action"}:
        raise ValueError("Only the configured native character/action routes are editable")
    for route in routes.values():
        if not isinstance(route, dict) or set(route) - {"provider", "model", "maxTokens", "reasoningEffort"}:
            raise ValueError("Unsupported native model route fields")
        item = available.get(route.get("provider"), {})
        if not item or route.get("model") != item["name"] or type(route.get("maxTokens")) is not int or not 0 < route["maxTokens"] <= item["max_tokens"]:
            raise ValueError("Native route exceeds the explicitly configured model/budget")
        if route.get('reasoningEffort') == 'none': route['reasoningEffort'] = 'off'
        if route.get("reasoningEffort") and route["reasoningEffort"] not in {item.get("reasoning_effort"), "off", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid native reasoning effort")
    qq = config["onebot"]
    if type(qq.get("enabled", False)) is not bool:
        raise ValueError("QQ integration must be enabled explicitly")
    if qq.get("config_directory") and not Path(qq["config_directory"]).expanduser().is_absolute():
        raise ValueError("NapCat account configuration directory must be absolute")
    for field, schemes in (("http_url", {"http"}), ("ws_url", {"ws"})):
        if qq.get(field): endpoint(qq[field], schemes, loopback=True)
    if not isinstance(qq.get("token"), str) or not qq["token"].isascii() or any(c in qq["token"] for c in "\r\n\x00"):
        raise ValueError("Invalid OneBot token")
    if ready and qq.get("enabled", False):
        if not re.fullmatch(r"[1-9][0-9]{0,19}", str(qq.get("account_id", ""))):
            raise ValueError("Select the logged-in NapCat account")
        if not qq.get("admin_ids"):
            raise ValueError("At least one explicit owner account is required")
        endpoint(qq.get("http_url"), {"http"}, loopback=True)
        endpoint(qq.get("ws_url"), {"ws"}, loopback=True)
        if not qq.get("token"):
            raise ValueError("NapCat access token is required")
    if ready and not config.get("character_name", "").strip():
        raise ValueError("Character name must be configured")
    for field in ("admin_ids", "allowed_users", "blocked_users", "owner_group_ids"):
        rows = qq.get(field, [])
        if not isinstance(rows, list) or any(not re.fullmatch(r"[1-9][0-9]{0,19}", str(x)) for x in rows):
            raise ValueError("Invalid QQ identifiers in " + field)
    for section in ("napcat", "live2d", "knowledge"):
        value = config.get(section, {}).get("directory")
        if not isinstance(value, str) or not Path(value).expanduser().is_absolute():
            raise ValueError("Explicit absolute module directory required: " + section)
    for section, field in (('napcat', 'autostart'), ('live2d','enabled'), ('knowledge','shared'), ('speech','enabled')):
        if type(config.get(section, {}).get(field, False)) is not bool:
            raise ValueError('Boolean feature flag required: ' + section + '.' + field)
    if config['live2d'].get('models_directory') and not Path(config['live2d']['models_directory']).is_absolute():
        raise ValueError('Live2D model directory must be absolute')
    if config['live2d'].get('manifest_url'): endpoint(config['live2d']['manifest_url'], {'https'})
    command = config["napcat"].get("command", [])
    if not isinstance(command, list) or any(not isinstance(x, str) or not x or '\x00' in x for x in command):
        raise ValueError("NapCat command must be an argv list, never a shell string")
    if command and not Path(command[0]).is_absolute():
        raise ValueError("NapCat command executable must be absolute")
    for value in config.get("executables", {}).values():
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("Executable overrides must be absolute paths")
    for registry in config.get("registries", {}).values(): endpoint(registry, {"https", "http"})
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(config.get("time_zone") or 'UTC')
    except (ValueError, ZoneInfoNotFoundError): raise ValueError("Configure a valid IANA time zone") from None
    jobs = config.get("automation_jobs", [])
    if not isinstance(jobs, list) or len(jobs) > 64:
        raise ValueError("Bounded automation_jobs list required")
    seen = set()
    for job in jobs:
        if not isinstance(job, dict) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", str(job.get("id", ""))) or job['id'] in seen:
            raise ValueError("Automation jobs need distinct deployment-owned IDs")
        seen.add(job['id'])
        if job.get('kind') not in {'watchdog', 'bandori', 'qzone', 'briefing', 'memory'} or not isinstance(job.get('cron'), str) or len(job['cron'].split()) != 5:
            raise ValueError("Configure automation job kind and five-field cron explicitly")
        if type(job.get('enabled', True)) is not bool or type(job.get('lookback_hours', 6)) is not int or not 1 <= job.get('lookback_hours', 6) <= 24:
            raise ValueError("Invalid automation enable/lookback setting")
    options = config.get("native_options", {})
    if not isinstance(options, dict) or set(options) - NATIVE_OPTIONS:
        raise ValueError("Unsupported native_options; runtime identity/keys cannot be overridden")
    for key in ('bandori_knowledge_root', 'legacy_memory_db', 'legacy_cron_file'):
        if options.get(key) and not Path(options[key]).is_absolute():
            raise ValueError("Native data references must be explicit absolute paths")
    backend = config.get('development', {}).get('backend')
    if backend not in {'disabled', 'docker', 'bubblewrap'} or backend == 'bubblewrap' and os.name == 'nt':
        raise ValueError("Choose disabled/Docker, or bubblewrap on Linux; never unisolated execution")
    lines = config.get('agent_line', {}).get('routes', [])
    if not isinstance(lines, list) or len(lines) > 32 or len({row.get('id') for row in lines if isinstance(row, dict)}) != len(lines):
        raise ValueError("Agent Line routes must be a bounded list with unique IDs")
    if any(not isinstance(row, dict) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', str(row.get('id', ''))) for row in lines):
        raise ValueError("Invalid Agent Line route ID")
    speech = config.get('speech', {})
    if speech.get('enabled'):
        endpoint(speech.get('transcription_url'), {'https', 'http'})
        if not speech.get('model') or not speech.get('api_key'):
            raise ValueError("Configure the transcription model and credential explicitly")
    return config


def redacted(config):
    result = copy.deepcopy(config)
    def visit(value):
        if isinstance(value, dict):
            for key in list(value):
                if key in {"api_key", "token", "app_secret"}:
                    value[key + "_configured"] = bool(value.pop(key))
                else:
                    visit(value[key])
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(result)
    return result


def valid_profile_label(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 64 and value == value.strip() and not any(ord(c) < 32 for c in value)


def merge(previous, current):
    """Shared config merge for validation and commit; blank secret fields retain values."""
    result = copy.deepcopy(previous)
    for key, value in current.items():
        if key.endswith('_configured') or key in {'api_key', 'token', 'app_secret'} and value == '':
            continue
        if key in {'routes', 'model_profiles', 'reasoning_efforts'}:
            result[key] = copy.deepcopy(value)
            continue
        if isinstance(value, dict) and not isinstance(result.get(key, {}), dict):
            raise ValueError('Configuration field type cannot change')
        result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else copy.deepcopy(value)
    return result


def model_profile(home, operation, name, revision):
    """Write-only credential library; selecting a provider never returns its key."""
    current = read_json(Path(home) / "deployment.json")
    profiles = copy.deepcopy(current.get("model_profiles", {}))
    if not valid_profile_label(name):
        raise ValueError("A short nonempty profile name is required")
    if operation == "save":
        profiles[name] = {lane: model(current["models"][lane], required=True) for lane in ("character", "action")}
        changes = {"model_profiles": profiles}
    elif operation == "use" and name in profiles:
        changes = {"models": {**profiles[name], "fallbacks": []}, "routes": {},
                   "action_uses_character": profiles[name]["character"] == profiles[name]["action"]}
    elif operation == "delete" and name in profiles:
        del profiles[name]
        changes = {"model_profiles": profiles}
    else:
        raise ValueError("Unknown model profile or operation")
    return update(home, changes, revision)


def update(home, changes, revision):
    with file_lock(Path(home) / "run/config.lock"):
        path = Path(home) / "deployment.json"
        old = read_json(path)
        if type(revision) is not int or revision != old["revision"]:
            raise ValueError("CONFIG_CONFLICT: reload before saving")
        allowed = (set(old) | {"model_profiles", "action_uses_character", "management_require_key"}) - {"schema_version", "revision", "runtime"}
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise ValueError("Unsupported configuration fields")
        new = merge(old, changes)
        if "models" in changes and "routes" not in changes:
            new["routes"] = {}  # A saved native selection must not pin the previous supplier/model.
        new = validate(new)
        new["revision"] += 1
        backup = Path(home) / "backups" / ("config-" + str(old["revision"]) + "-" + secrets.token_hex(4) + ".json")
        atomic_json(backup, old)
        atomic_json(path, new)
        return redacted(new)


def venv_python(home):
    return Path(home) / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def executable(name, config=None):
    override = (config or {}).get("executables", {}).get(name) or os.environ.get("AGENT_QQBOT_" + name.upper())
    candidate = Path(override).expanduser() if override else None
    if candidate is not None:
        if not candidate.is_absolute() or not candidate.is_file():
            raise ValueError("Explicit executable missing: " + name)
        return str(candidate)
    bundled = project_root() / "extras/node" / (name + (".exe" if name == "node" else ".cmd"))
    return shutil.which(name) or (str(bundled) if os.name == "nt" and bundled.is_file() else None)
