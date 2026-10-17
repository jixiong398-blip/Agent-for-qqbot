# SPDX-License-Identifier: MIT
"""Explicit OS isolation for candidate code; never falls back to host execution."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

from soyo.platform import worker_environment


def sandbox_available(config):
    policy = config.get("development", {})
    backend = policy.get("backend", "disabled")
    if backend == "docker":
        return bool(shutil.which(policy.get("docker", "docker")) and re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", policy.get("image", "")))
    return backend == "bubblewrap" and os.name == "posix" and bool(shutil.which(policy.get("bubblewrap", "bwrap")))


def run_sandbox(config, root, command):
    policy = config.get("development", {})
    if not sandbox_available(config):
        return {"state": "blocked", "exit_code": None, "reason": "configured_isolated_execution_backend_required"}
    root = Path(root).resolve()
    backend = policy["backend"]
    name = "agent-qqbot-candidate-" + uuid.uuid4().hex
    env = worker_environment(home=root, extra={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    if backend == "docker":
        binary = shutil.which(policy.get("docker", "docker"))
        argv = [binary, "run", "--rm", "--pull=never", "--name", name,
            "--label", "agent-qqbot.candidate=" + name, "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=32", "--memory=256m", "--memory-swap=256m",
            "--cpus=0.5", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "--workdir=/work",
            "--mount", "type=bind,source=" + str(root) + ",target=/work", "--env=HOME=/work",
            "--env=GIT_CONFIG_NOSYSTEM=1", "--env=GIT_CONFIG_GLOBAL=/dev/null", policy["image"], *command]
        preexec = None
    else:
        binary = shutil.which(policy.get("bubblewrap", "bwrap"))
        argv = [binary, "--die-with-parent", "--new-session", "--unshare-all", "--cap-drop", "ALL",
            "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64", "--dir", "/etc", "--proc", "/proc", "--dev", "/dev",
            "--tmpfs", "/tmp", "--bind", str(root), "/work", "--chdir", "/work", "--clearenv",
            "--setenv", "HOME", "/work", "--setenv", "PATH", "/usr/bin:/bin", *command]
        def preexec():
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (4 * 1024 * 1024, 4 * 1024 * 1024))
    try:
        with tempfile.TemporaryFile(dir=root) as stdout, tempfile.TemporaryFile(dir=root) as stderr:
            result = subprocess.run(argv, cwd=root, env=env, stdout=stdout, stderr=stderr, timeout=35, preexec_fn=preexec)
            sizes = stdout.tell(), stderr.tell()
            stdout.seek(max(0, sizes[0] - 12000)); stderr.seek(max(0, sizes[1] - 4000))
            return {"state": "completed" if result.returncode == 0 else "failed", "exit_code": result.returncode,
                "stdout": stdout.read(12000).decode(errors="replace"), "stderr": stderr.read(4000).decode(errors="replace"),
                "stdout_truncated": sizes[0] > 12000, "stderr_truncated": sizes[1] > 4000, "sandbox": backend}
    except subprocess.TimeoutExpired:
        return {"state": "failed", "exit_code": None, "reason": "sandbox_timeout", "sandbox": backend}
    finally:
        if backend == "docker":
            # Only our random labelled container, never a global prune or image deletion.
            observed = subprocess.run([binary, "inspect", "--format", '{{index .Config.Labels "agent-qqbot.candidate"}}', name],
                capture_output=True, text=True, timeout=10, env=env)
            if observed.returncode == 0 and observed.stdout.strip() == name:
                subprocess.run([binary, "rm", "--force", name], capture_output=True, timeout=10, env=env)
