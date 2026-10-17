# SPDX-License-Identifier: MIT
"""Private local supervisor; the user configures Bot inside native DSH."""
from __future__ import annotations

from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from soyo.platform import file_lock, protect
from .config import atomic_json, read_json, redacted, update, validate, project_root, model_profile, trusted_ui_host, trusted_ui_peer
from .manager import Manager
from .onebot import accounts, select


def serve(home, *, open_browser=True, autostart=True):
    home = Path(home)
    manager = Manager(home)
    config = manager.config
    if not trusted_ui_host(config['management_host']):
        raise ValueError('Private supervisor must bind local loopback')
    require_key = config.get('management_require_key', False)
    origin = f'http://{config["management_host"]}:{config["management_port"]}'
    key = (home / "private/control-key").read_text(encoding="ascii").strip()
    sessions, attempts = {}, []
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentQQBot"
        def setup(self):
            super().setup()
            self.connection.settimeout(15)
        def log_message(self, *_):
            pass  # Do not log credential forms, request paths or model data.

        def send(self, value, status=200, *, content_type="application/json; charset=utf-8", cookie=None):
            raw = value.encode("utf-8") if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            for name, value in {"Content-Type": content_type, "Content-Length": str(len(raw)), "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"}.items():
                self.send_header(name, value)
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers(); self.wfile.write(raw)

        def authority(self):
            return self.headers.get("Host") == origin.removeprefix("http://") and trusted_ui_peer(self.client_address[0], config['management_host'])

        def auth(self):
            if not require_key and trusted_ui_peer(self.client_address[0], config['management_host']):
                return 'trusted-network'
            supplied = self.headers.get("Authorization", "")
            if supplied.startswith("Bearer ") and hmac.compare_digest(supplied[7:], key):
                return "service"
            if supplied.startswith("Basic "):
                try:
                    if hmac.compare_digest(base64.b64decode(supplied[6:], validate=True).decode(), "admin:" + key):
                        return "service"
                except (ValueError, UnicodeError):
                    pass
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                token = cookie["agent_session"].value
                value = sessions.get(token)
                if value and value["expires"] > time.time():
                    return token
            except (KeyError, ValueError, CookieError):
                pass
            return None

        def csrf(self, identity):
            return hmac.new(key.encode(), ("csrf:" + identity).encode(), hashlib.sha256).hexdigest()

        def body(self):
            if self.headers.get_content_type() != "application/json":
                raise ValueError("JSON request required")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512 * 1024:
                raise ValueError("Request size rejected")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("JSON object required")
            return value

        def do_GET(self):
            if not self.authority():
                return self.send({"error": "invalid_host"}, 403)
            path = urlsplit(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
            if path in static:
                name, mime = static[path]
                return self.send((project_root() / "modules/dashboard/static" / name).read_text(encoding="utf-8"), content_type=mime)
            identity = self.auth()
            if not identity:
                return self.send({"error": "authentication_required"}, 401)
            try:
                if path in {"/api/csrf", "/api/session"}:
                    return self.send({"ready": True, "csrf": self.csrf(identity), "token": self.csrf(identity)})
                if path == "/api/runtime":
                    return self.send({"backend": "dsh"})
                if path == '/api/setup':
                    from .setup import view
                    return self.send(view(manager))
                if path in {"/api/status", "/api/services/status", "/api/gateway/status"}:
                    return self.send(manager.status())
                if path == "/api/config":
                    return self.send(redacted(read_json(home / "deployment.json")))
                if path == "/api/persona":
                    from .persona import view
                    return self.send(view(home))
                if path == "/api/napcat/accounts":
                    value = read_json(home / "deployment.json")
                    return self.send({"accounts": accounts(value["onebot"].get("config_directory", ""))})
                if path == "/api/logs":
                    name = parse_qs(urlsplit(self.path).query).get("service", ["manager"])[0]
                    requested = name
                    if name == "dashboard": name = "manager"
                    if name not in manager.logs:
                        raise ValueError("Unknown log stream")
                    with manager.lock:
                        lines = list(manager.logs[name])[-300:]
                        return self.send({"service": requested, "lines": lines, "log": "\n".join(lines)})
                return self.send({"error": "not_found"}, 404)
            except (ValueError, OSError) as error:
                return self.send({"error": manager._redact(str(error))}, 400)

        def do_POST(self):
            if not self.authority() or self.headers.get("Origin") != origin or self.headers.get("Sec-Fetch-Site") == "cross-site":
                return self.send({"error": "same_origin_required"}, 403)
            try:
                path = urlsplit(self.path).path
                if path == "/api/login":
                    now = time.time(); attempts[:] = [t for t in attempts if now - t < 60]
                    if len(attempts) >= 20:
                        return self.send({"error": "rate_limited"}, 429)
                    attempts.append(now)
                    supplied = str(self.body().get("key", ""))
                    if not hmac.compare_digest(supplied, key):
                        return self.send({"error": "invalid_key"}, 401)
                    token = secrets.token_urlsafe(48)
                    # Only live, bounded sessions; never a key/token URL.
                    for old in [old for old, value in sessions.items() if value["expires"] <= now]:
                        sessions.pop(old, None)
                    if len(sessions) >= 32:
                        return self.send({"error": "session_limit"}, 429)
                    sessions[token] = {"expires": now + 8 * 3600}
                    return self.send({"success": True, "csrf": self.csrf(token)}, cookie="agent_session=" + token + "; HttpOnly; SameSite=Strict; Path=/")
                identity = self.auth()
                if not identity:
                    return self.send({"error": "authentication_required"}, 401)
                supplied = self.headers.get("X-Agent-CSRF", self.headers.get("X-Dashboard-CSRF", ""))
                if not hmac.compare_digest(supplied, self.csrf(identity)):
                    return self.send({"error": "csrf_required"}, 403)
                body = self.body()
                if path == '/api/setup/save':
                    from .setup import queue
                    return self.send(queue(manager, body))
                if path == '/api/setup/napcat':
                    from .setup import napcat_operation
                    return self.send(napcat_operation(manager, body))
                if path == '/api/setup/preset':
                    from .setup import persona_preset
                    return self.send(persona_preset(manager, body))
                if path == "/api/config":
                    with manager.lock:
                        if any(row["running"] for name, row in manager.status()["services"].items() if name in {"web", "gateway"}):
                            raise ValueError("Stop native services before changing deployment configuration")
                        result = update(home, body.get("changes", {}), body.get("revision"))
                        manager.config = read_json(home / "deployment.json")
                        return self.send(result)
                if path == "/api/persona":
                    from .persona import save
                    with manager.lock:
                        if manager.status()["services"]["web"]["running"]:
                            raise ValueError("Stop native Web before replacing its private persona")
                        return self.send(save(home, text=body.get("text"), operation=body.get("operation", "save"),
                                              name=body.get("name"), digest=body.get("digest")))
                if path == "/api/model-profiles":
                    with manager.lock:
                        if manager.status()["services"]["web"]["running"]:
                            raise ValueError("Stop native services before switching model profiles")
                        value = model_profile(home, body.get("operation"), body.get("name"), body.get("revision"))
                        manager.config = read_json(home / "deployment.json")
                        return self.send(value)
                if path == "/api/models/list":
                    from .providers import list_models
                    return self.send(list_models(read_json(home / "deployment.json"), body.get("lane")))
                if path == "/api/napcat/accounts/select":
                    with manager.lock:
                        if any(manager.status()["services"][name]["running"] for name in ("web", "gateway")):
                            raise ValueError("Stop native services before changing their QQ account")
                        value = select(home, body.get("account_id"))
                        manager.config = read_json(home / "deployment.json")
                        return self.send(value)
                if path in {"/api/services/start", "/api/services/stop", "/api/services/restart"}:
                    name = body.get("service", "native")
                    if name not in {"native", "web", "gateway", "napcat", "live2d"}:
                        raise ValueError("Unknown service")
                    if path.endswith(("/stop", "/restart")):
                        manager.stop_native() if name in {"native", "web", "gateway"} else manager.stop(name)
                    if path.endswith(("/start", "/restart")):
                        manager.start_native() if name in {"native", "web", "gateway"} else manager.start_optional(name)
                    return self.send(manager.status())
                if path == "/api/shutdown":
                    manager.stop_native()
                    for name in ("live2d", "napcat"):
                        manager.stop(name)
                    self.send({"success": True})
                    stop.set(); threading.Thread(target=server.shutdown, daemon=True).start()
                    return
                return self.send({"error": "not_found"}, 404)
            except Exception as error:
                manager.log("manager", str(error))
                return self.send({"error": manager._redact(str(error))}, 400)

    with file_lock(home / "run/supervisor.lock", blocking=False), file_lock(home / "run/lifecycle.lock", blocking=False):
        from .setup import recover_interrupted
        recover_interrupted(manager)
        server = ThreadingHTTPServer((config["management_host"], config["management_port"]), Handler)
        server.daemon_threads = True
        import psutil
        atomic_json(home / "run/supervisor.json", {"pid": os.getpid(), 'created_at': psutil.Process().create_time(), "url": origin, "port": config["management_port"]})
        print("Management: " + origin)
        print("Key files: " + str(home / 'private'))
        if not require_key:
            print('Local native DSH setup: no additional Bot Key page')
        elif __import__('sys').stdout.isatty():
            print("Local access key (not written to logs): " + key)
        else:
            print("Access keys are in this instance's private directory; keys are not written to redirected output")
        def monitor():
            if autostart:
                try:
                    if manager.config["onebot"].get("enabled", False) and manager.config["napcat"].get("autostart"):
                        manager.start_optional("napcat")
                    manager.start_native()
                    if open_browser:
                        webbrowser.open(f'http://{config["native_host"]}:{config["native_port"]}/')
                except Exception as error:
                    manager.log("manager", "Startup pending: " + str(error))
            while not stop.wait(1):
                try:
                    manager.apply_saved_routes()
                    from .setup import apply_pending
                    apply_pending(manager)
                except Exception as error:
                    manager.log("manager", "Apply monitor: " + type(error).__name__)
        threading.Thread(target=monitor, daemon=True).start()
        if open_browser and not autostart:
            webbrowser.open(origin)  # Explicit maintenance-only control mode.
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            manager.stop_native()
            # Never close external QQ/NapCat. Finish only optional children
            # started by this supervisor (Windows jobs cannot outlive it).
            for name in ('live2d', 'napcat'):
                manager.stop(name)
            server.server_close()
