"""Disposable real Dashboard HTTP server; service/QQ side effects are fixtures.

Pass the independent Dashboard source directory as argv[1]. This is not a
production service-control test. It never imports or starts Hermes/DSH/NapCat.
"""
from __future__ import annotations

import json
import os
import socket
import secrets
import signal
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    with tempfile.TemporaryDirectory(prefix="dsh-dashboard-http-", dir="/tmp/opencode") as directory:
        home = Path(directory)
        os.environ.update(HOME=directory, HERMES_HOME=str(home / "legacy"),
                          SOYO_GATEWAY_BACKEND="dsh", SOYO_DSH_WEB_URL="")
        (home / "legacy").mkdir()
        (home / "legacy/config.yaml").write_text("model: {default: synthetic}\n", encoding="utf-8")
        (home / "legacy/.env").write_text("ONEBOT_SELF_ID=123456\n", encoding="utf-8")
        key_file = home / "test-access-key"
        key_file.write_text(secrets.token_urlsafe(48) + "\n", encoding="ascii")
        key_file.chmod(0o600)
        os.environ.update(DASHBOARD_REQUIRE_KEY="1", DASHBOARD_ACCESS_KEY_FILE=str(key_file))
        sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
        import server

        observations = {"isolation_checks": 0, "commands": [], "posts": [], "api_reads": 0, "dropped_receipts": 0}
        faults = {"drop_restart_receipt": False}

        def command(args, **kwargs):
            observations["commands"].append(args)
            if args[:3] == ["systemctl", "--user", "show"]:
                active = args[3] == "soyo-dsh-gateway.service"
                return SimpleNamespace(returncode=0, stdout=("Id=" + args[3] + "\nLoadState=loaded\nActiveState=" +
                    ("active\nSubState=running\n" if active else "inactive\nSubState=dead\n")), stderr="")
            if args[:3] == ["systemctl", "--user", "is-active"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if args[:3] == ["systemctl", "--user", "restart"] and args[3] == "nagasaki-dashboard":
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if args[:3] == ["journalctl", "--user", "-u"]:
                return SimpleNamespace(returncode=0, stdout="Synthetic Dashboard journal\n", stderr="")
            raise AssertionError("Unexpected system command; fixture refuses execution")

        def isolation(*args):
            observations["isolation_checks"] += 1
            return {"already_separate": True}

        server.subprocess.run = command
        server._napcat_running = lambda: False
        server.isolate_existing_napcat = isolation

        class FixtureHandler(server.Handler):
            def _get(self):
                self.server.guard.authenticate(self)
                if self.path == "/fixture/observations":
                    return self._json(observations)
                if self.path in ("/fixture/backend/hermes", "/fixture/backend/dsh"):
                    server.RUNTIME.backend = self.path.rsplit("/", 1)[-1]
                    return self._json({"fixture_only": True})
                if self.path == "/fixture/drop-next-receipt":
                    faults["drop_restart_receipt"] = True
                    return self._json({"fixture_only": True})
                if self.path.startswith("/api/"):
                    observations["api_reads"] += 1
                return super()._get()

            def _json(self, data, status=200):
                if (faults["drop_restart_receipt"] and self.path == "/api/services/restart" and
                        data.get("ok") is True):
                    faults["drop_restart_receipt"] = False
                    observations["dropped_receipts"] += 1
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                return super()._json(data, status)

            def _handle_service(self, action, body):
                observations["posts"].append({"action": action, "body": body})
                return super()._handle_service(action, body)

        httpd = server.DashboardServer(("127.0.0.1", 0), FixtureHandler)
        print(json.dumps({"url": f"http://127.0.0.1:{httpd.server_port}", "key_file": str(key_file)}), flush=True)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()


if __name__ == "__main__":
    main()
