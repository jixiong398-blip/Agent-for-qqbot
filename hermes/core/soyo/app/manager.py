# SPDX-License-Identifier: MIT
"""Own only processes started by this instance; never kill by port or image name."""
from __future__ import annotations

from collections import deque
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import httpx
import psutil

from soyo.platform import assert_private, worker_environment
from .config import atomic_json, executable, initialize, read_json, redacted, update, validate, project_root
from .render import render


class Manager:
    def __init__(self, home):
        self.home = Path(home)
        self.processes = {}
        self.logs = {name: deque(maxlen=800) for name in ("web", "gateway", "napcat", "live2d", "manager")}
        self.lock = threading.RLock()
        self.log_lock = threading.RLock()
        self.config = initialize(self.home)
        self.retained = read_json(self.home / "run/processes.json", default={})
        self.jobs = {}

    def _redact(self, text):
        config = self.config
        values = [config.get("onebot", {}).get("token", "")]
        values += [config.get("speech", {}).get("api_key", ""), config.get("feishu", {}).get("app_secret", "")]
        values += [v.get("api_key", "") for v in [*config["models"].values()] if isinstance(v, dict)]
        values += [v.get("api_key", "") for v in config["models"].get("fallbacks", [])]
        values.append(read_json(self.home / 'private/napcat-webui.json', default={}).get('token', ''))
        for file in (self.home / "private").glob("*-key"):
            try:
                values.append(file.read_text(encoding="utf-8").strip())
            except OSError:
                pass
        for file in (self.home / 'private').glob('*.key'):
            try: values.append(file.read_text(encoding='utf-8').strip())
            except OSError: pass
        for value in sorted((x for x in values if len(x) >= 8), key=len, reverse=True):
            text = text.replace(value, "<redacted>")
        import re
        return re.sub(r"(?i)(Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,})", "<redacted>", text)[:8000]

    def log(self, service, text):
        line = self._redact(str(text).rstrip())
        with self.log_lock:
            self.logs[service].append(line)
            # Serialize rotation and append; no raw child output is persisted.
            path = self.home / "logs" / (service + ".log")
            if path.exists() and path.stat().st_size > 4 * 1024 * 1024:
                os.replace(path, path.with_suffix(".previous.log"))
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    @staticmethod
    def _same_process(record):
        try:
            process = psutil.Process(record["pid"])
            return process if abs(process.create_time() - record["created_at"]) < 0.01 else None
        except (psutil.Error, KeyError):
            return None

    def _persist(self):
        atomic_json(self.home / "run/processes.json", self.retained)

    def spawn(self, name, argv, *, cwd, env=None):
        with self.lock:
            if self._same_process(self.retained.get(name, {})):
                raise ValueError("This instance already has an owned " + name + " process; reconcile/stop it first")
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            job, child = None, None
            if os.name == 'nt':
                import win32job
                # pywin32 requires a string; the empty name creates an unnamed
                # job. Create/configure it before spawning, not after a child
                # exists that an initialization exception could leave unowned.
                job = win32job.CreateJobObject(None, '')
                limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
                limits['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
            try:
                child = subprocess.Popen([str(x) for x in argv], cwd=str(cwd), env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=flags, start_new_session=os.name != "nt")
                if job: win32job.AssignProcessToJobObject(job, int(child._handle))
                process = psutil.Process(child.pid)
                self.processes[name] = child
                self.retained[name] = {"pid": child.pid, "created_at": process.create_time(),
                    "instance": str(self.home), "command_sha256": hashlib.sha256(json.dumps([str(x) for x in argv]).encode()).hexdigest()}
                self._persist()
            except BaseException:
                if child:
                    if child.poll() is None: child.kill()
                    child.wait()
                    if child.stdout: child.stdout.close()
                if job: job.Close()
                self.processes.pop(name, None); self.retained.pop(name, None)
                raise
            if job: self.jobs[name] = job
            threading.Thread(target=self._read_log, args=(name, child), daemon=True).start()
            return child

    def _read_log(self, name, child):
        try:
            while raw := child.stdout.readline(16 * 1024):
                self.log(name, raw.decode("utf-8", errors="replace"))
        finally:
            child.stdout.close()
            result = child.wait()
            self.log(name, "process exited: " + str(result))

    def stop(self, name):
        if name not in {"web", "gateway", "napcat", "live2d"}:
            raise ValueError("Unknown managed service")
        with self.lock:
            process = self._same_process(self.retained.get(name, {}))
            if process is None:
                job = self.jobs.pop(name, None)
                if job: job.Close()
                self.retained.pop(name, None); self._persist()
                return {"state": "stopped", "already_stopped": True}
            descendants = [(p.pid, p.create_time()) for p in process.children(recursive=True)]
            owned = [(process.pid, process.create_time()), *descendants]
            # Graceful group stop first; a bounded fallback only targets captured
            # PID/create-time identities, never unrelated port owners or QQ.exe.
            try:
                if os.name == "nt":
                    os.kill(process.pid, signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            deadline = time.monotonic() + self.config["stop_timeout"]
            while time.monotonic() < deadline and any(self._same_process({"pid": p, "created_at": t}) for p, t in owned):
                time.sleep(0.1)
            for pid, created in reversed(owned):
                current = self._same_process({"pid": pid, "created_at": created})
                if current:
                    try:
                        current.kill()
                    except psutil.NoSuchProcess:
                        pass
            psutil.wait_procs([p for pid, created in owned if (p := self._same_process({"pid": pid, "created_at": created}))], timeout=3)
            alive = [pid for pid, created in owned if self._same_process({"pid": pid, "created_at": created})]
            if alive:
                raise RuntimeError("Managed process tree has not fully stopped; record retained")
            job = self.jobs.pop(name, None)
            if job: job.Close()
            self.retained.pop(name, None); self.processes.pop(name, None); self._persist()
            return {"state": "stopped"}

    def stop_native(self):
        # NapCat stays logged in unless the operator explicitly stops NapCat.
        self.stop("gateway"); self.stop("web")

    def status(self):
        result = {}
        for name in self.logs:
            if name == "manager":
                continue
            record = self.retained.get(name, {})
            process = self._same_process(record)
            result[name] = {"running": process is not None and process.is_running(), "pid": process.pid if process else None,
                "state": "running" if process else "stopped", "owned_by_this_instance": bool(record)}
        heartbeat = read_json(self.home / "run/gateway-status.json", default={})
        result["gateway"]["backend"] = "dsh"
        result["gateway"]["enabled"] = self.config["onebot"].get("enabled", False)
        if not result["gateway"]["enabled"] and not result["gateway"]["running"]:
            result["gateway"]["state"] = "disabled"
        result["dashboard"] = {"running": True, "pid": os.getpid(), "state": "running", "owned_by_this_instance": True}
        if heartbeat:
            heartbeat = {key: value for key, value in heartbeat.items() if key in {"backend", "state", "updated_at", "mention_only", "final_only", "routes"}}
            if time.time() - heartbeat.get("updated_at", 0) > 30:
                heartbeat["state"] = "stale"
        return {"backend": "dsh", "services": result, "gateway": heartbeat, "migration": "native",
                "mode": "qq" if self.config["onebot"].get("enabled", False) else "web-only"}

    def start_native(self):
        from .install import source_fingerprint
        with self.lock:
            self.config = read_json(self.home / "deployment.json")
            validate(self.config, ready=False)
            runtime = read_json(self.home / "private/runtime.json", default={})
            if read_json(self.home / 'private/runtime-switch.json', default={}).get('phase') == 'switching':
                raise ValueError('Interrupted runtime selection; stop the supervisor and run recover-runtime')
            if not runtime or runtime.get("source_fingerprint") != source_fingerprint() and not runtime.get("allow_source_mismatch"):
                raise ValueError("Native runtime is missing or source changed; run install first (startup never installs implicitly)")
            if self._same_process(self.retained.get("web", {})) or self._same_process(self.retained.get("gateway", {})):
                raise ValueError("Native services already owned; use explicit stop/restart")
            native, profile = render(self.home, self.config, runtime["directory"])
            env = worker_environment(extra={"DSH_HOME": str(self.home), "DSH_TELEMETRY_DISABLED": "1",
                "DSH_PERMISSION_MODE": self.config["host_permission_mode"], "SOYO_HOST_PERMISSION_MODE": self.config["host_permission_mode"],
                "SOYO_PYTHON": sys.executable, "SOYO_WORKER_ROOT": str(Path(runtime["directory"]) / "worker"),
                "AGENT_QQBOT_PROJECT": str(project_root())})
            env.update(read_json(self.home / "private/model-environment.json", default={}))
            child = self.spawn("web", [runtime["node"], runtime["cli"], "--profile", self.config["profile"]], cwd=self.home / "workspace", env=env)
            from soyo.transport import private_client
            try:
                deadline = time.monotonic() + self.config["ready_timeout"]
                ready = False
                while time.monotonic() < deadline and child.poll() is None:
                    try:
                        if native.get('setup_mode'):
                            with httpx.Client(trust_env=False, timeout=2) as client:
                                response = client.get(f'http://{self.config["native_host"]}:{self.config["native_port"]}/')
                                ready = response.status_code in (200, 303)
                        else:
                            with private_client(native, timeout=2) as client:
                                response = client.post("/health", json={})
                                ready = response.status_code == 200 and response.json().get("backend") == "dsh-native"
                    except httpx.HTTPError:
                        pass
                    if ready:
                        break
                    time.sleep(0.25)
                if not ready:
                    raise RuntimeError("Native Web/Host readiness failed; see private web log")
                if self.config['onebot'].get('enabled', False):
                    try: self.connect_qq()
                    except Exception as error:
                        self.stop('gateway')
                        self.log('manager', 'QQ not connected; native setup remains available: ' + str(error))
            except BaseException:
                self.stop("gateway")
                self.stop("web")
                raise
            return self.status()

    def connect_qq(self):
        """Explicit QQ admission never prevents the operator opening native DSH."""
        self.config = read_json(self.home / 'deployment.json')
        validate(self.config, ready=True)
        if not self.config['onebot'].get('enabled', False): raise ValueError('Enable QQ in native setup first')
        from soyo.qq.runtime import other_gateway_idle, NapCat
        native = read_json(self.home / 'private/channel.json')
        qq = self.config['onebot']
        if any(native.get(key) != value for key, value in {'account_id':str(qq['account_id']), 'onebot_token':qq['token'],
                'http_url':qq['http_url'], 'ws_url':qq['ws_url'], 'qq_enabled':True}.items()):
            raise ValueError('Save and apply the new account connection before connecting QQ')
        other_gateway_idle(native)
        napcat = NapCat(native)
        try:
            account = str(napcat.read('get_login_info').get('user_id'))
            if account != native['account_id']: raise ValueError('NapCat account does not match the selected Bot account')
        finally: napcat.client.close()
        self.start_gateway(read_json(self.home / 'private/runtime.json'))

    def start_gateway(self, runtime):
        if not self.config['onebot'].get('enabled', False):
            raise ValueError('QQ is disabled; enable it explicitly before connecting')
        gateway_start = time.time()
        self.spawn('gateway', [sys.executable, '-B', '-m', 'soyo.qq.runtime', '--config', self.home / 'private/channel.json'],
            cwd=self.home / 'workspace', env=worker_environment(extra={'PYTHONPATH': str(Path(runtime['directory']) / 'worker')}))
        deadline = time.monotonic() + self.config['ready_timeout']
        while time.monotonic() < deadline and self.processes['gateway'].poll() is None:
            heartbeat = read_json(self.home / 'run/gateway-status.json', default={})
            if heartbeat.get('state') == 'connected' and heartbeat.get('updated_at', 0) >= gateway_start: return
            time.sleep(0.25)
        self.stop('gateway')
        raise RuntimeError('Native QQ transport did not become ready; no successful connection claimed')

    def start_optional(self, service):
        self.config = read_json(self.home / "deployment.json")
        if service == "napcat":
            settings = self.config["napcat"]
            directory = Path(settings["directory"]).expanduser().resolve()
            command = settings.get("command")
            if not command:
                if os.name != "nt" or not (directory / "napcat.bat").is_file():
                    raise ValueError("Configure the NapCat launch command for this platform")
                # Do not close normal QQ to make an injection succeed.
                if any(p.info["name"].lower() == "qq.exe" for p in psutil.process_iter(["name"]) if p.info["name"]):
                    raise ValueError("Normal QQ is running; exit it manually before starting NapCat")
                command = [str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe"), "/d", "/c", "napcat.bat"]
        elif service == "live2d":
            settings = self.config["live2d"]
            installed = read_json(self.home / 'private/live2d-runtime.json', default={})
            if not installed: raise ValueError('Run install-live2d before starting this optional module')
            directory = Path(installed['directory'])
            command = [installed['electron'], str(directory)]
        else:
            raise ValueError("Unknown optional service")
        if not directory.is_dir() or not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError("Configured service directory/argv missing")
        extra = {"AGENT_QQBOT_HOME": str(self.home)}
        if service == 'live2d':
            extra.update(LIVE2D_PORT=str(self.config['live2d_port']),
                LIVE2D_CONTROL_KEY=(self.home / 'private/live2d-key').read_text(encoding='ascii').strip(),
                LIVE2D_MODELS_DIR=self.config['live2d'].get('models_directory') or str(self.home / 'live2d/models'),
                LIVE2D_MANIFEST_URL=self.config['live2d'].get('manifest_url') or '',
                LIVE2D_DECRYPT_SCRIPT=str(directory / 'tools/decrypt_cvpkg.py'), SOYO_PYTHON=sys.executable)
        self.spawn(service, command, cwd=directory, env=worker_environment(extra=extra))
        return self.status()

    def apply_saved_routes(self):
        with self.lock:
            return self._apply_saved_routes()

    def _apply_saved_routes(self):
        """Reconcile a native UI request only while idle; preserve failed requests."""
        path = self.home / "private/channel.json.ui-apply.json"
        request = read_json(path, default={})
        if request.get("phase") != "queued":
            return
        from soyo.transport import private_client
        native = read_json(self.home / "private/channel.json")
        try:
            with private_client(native, timeout=3) as client:
                health = client.post("/health", json={}); health.raise_for_status(); health = health.json()
            if any(health.get(key, 0) for key in ("native_active_turns", "active_actions", "unfinished")):
                return
            current = hashlib.sha256((self.home / "private/channel.json").read_bytes()).hexdigest()
            if request.get("expected_config_digest") != current:
                raise ValueError("Native settings configuration conflict")
            previous = read_json(self.home / "deployment.json")
            request.update(phase="restarting"); atomic_json(path, request)
            self.stop('gateway')
            with private_client(native, timeout=3) as client:
                check = client.post('/health', json={}); check.raise_for_status(); check = check.json()
            if any(check.get(key, 0) for key in ('native_active_turns', 'active_actions', 'active_turns', 'unfinished')):
                if self.config['onebot'].get('enabled', False): self.start_gateway(read_json(self.home / 'private/runtime.json'))
                request.update(phase='queued'); atomic_json(path, request)
                return  # An input raced the first check. Leave its turn alone.
            self.stop('web')
            update(self.home, {"routes": request["routes"]}, previous["revision"])
            try:
                self.start_native()
            except Exception:
                held = read_json(self.home / 'deployment.json')
                if held['revision'] != previous['revision'] + 1: raise ValueError('Rollback configuration conflict')
                previous['revision'] = held['revision'] + 1
                atomic_json(self.home / "deployment.json", previous)
                self.start_native()
                raise
            request.update(phase="applied", finished_at=time.time())
        except Exception as error:
            request.update(phase="failed", error_type=type(error).__name__, finished_at=time.time())
            self.log("manager", "Native settings apply failed; rollback/operation evidence retained")
        atomic_json(path, request)
