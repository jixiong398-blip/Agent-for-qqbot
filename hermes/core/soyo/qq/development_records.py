# SPDX-License-Identifier: GPL-3.0-only
"""Stable candidate work, revision/operation audit and configured project snapshots.

Metadata lives outside the candidate sandbox. The Host supplies author bindings;
project text cannot choose a source root, deployment target, actor or grant.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import time
import uuid
import shutil
from pathlib import Path
from soyo.platform import open_private, private_fchmod, sync_directory, worker_environment


def private_json(path):
    try:
        fd = open_private(path)
    except FileNotFoundError:
        return {}
    with os.fdopen(fd, "r") as stream:
        info = os.fstat(stream.fileno())
        if info.st_size > 512 * 1024:
            raise ValueError("unsafe_development_record")
        return json.load(stream)


def durable(path, value, *, overwrite=True):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not overwrite:
        with path.open("x") as stream:
            private_fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        sync_directory(path.parent)
        return
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x") as stream:
        private_fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    sync_directory(path.parent)


class WorkLedger:
    def __init__(self, config, identifier, parent=None):
        self.root = Path(config["development_home"]).resolve().parent / "development-records"
        self.path = self.root / (identifier + ".json")
        self.history = self.root / identifier
        self.value = private_json(self.path)
        if self.value and self.value.get("parent_session") != parent:
            raise ValueError("DEVELOPMENT_AUTHOR_MISMATCH")
        if not self.value:
            self.value = {"work_id": identifier, "parent_session": parent, "revision": 1,
                          "state": "candidate", "created_at": time.time(), "project_id": None,
                          "base_revision": None, "acceptance": None, "commit": None}
            durable(self.history / "revision-1.json", self.value, overwrite=False)
            durable(self.path, self.value)

    def check(self, revision):
        if type(revision) is not int or revision != self.value["revision"]:
            raise ValueError("DEVELOPMENT_CONFLICT")

    def operation(self, args):
        identifier = args.get("_operation_id")
        if identifier is None: return None, None, None
        if not re.fullmatch(r"[a-f0-9]{64}", identifier): raise ValueError("invalid_development_operation_id")
        fingerprint = hashlib.sha256(json.dumps(args, sort_keys=True, allow_nan=False).encode()).hexdigest()
        path = self.history / ("operation-" + identifier + ".json")
        old = private_json(path)
        if old and old.get("fingerprint") != fingerprint: raise ValueError("DEVELOPMENT_OPERATION_CONFLICT")
        if old and old.get("phase") == "started":
            return path, fingerprint, {"state": "unknown", "reason": "development_operation_not_settled_no_replay",
                                       "operation_id": identifier, "revision": self.value["revision"]}
        return path, fingerprint, old.get("result")

    def begin_operation(self, operation, path, fingerprint):
        # An orphan next-revision audit means the previous publication was
        # interrupted. Keep it, refuse mutation and let the read face expose it.
        if (self.history / ("revision-" + str(self.value["revision"] + 1) + ".json")).exists():
            raise ValueError("DEVELOPMENT_RECOVERY_REQUIRED")
        if path:
            durable(path, {"phase": "started", "operation": operation, "fingerprint": fingerprint,
                           "expected_revision": self.value["revision"], "created_at": time.time()}, overwrite=False)

    def settle_operation(self, path, fingerprint, result):
        if path: durable(path, {"phase": "settled", "fingerprint": fingerprint, "result": result})

    def commit_operation(self, operation, result, operation_path=None, fingerprint=None, **changes):
        value = {**self.value, **changes, "revision": self.value["revision"] + 1, "updated_at": time.time()}
        audit = {"operation": operation, "result": result, "previous_revision": self.value["revision"], "body": value}
        durable(self.history / ("revision-" + str(value["revision"]) + ".json"), audit, overwrite=False)
        durable(self.path, value); self.value = value
        self.settle_operation(operation_path, fingerprint, result)
        return value


def project(config, project_id):
    candidates = config.get("development_projects", [])
    if not isinstance(candidates, list): raise ValueError("invalid_development_projects")
    found = [item for item in candidates if item.get("id") == project_id and item.get("enabled", True)]
    if len(found) != 1: raise ValueError("development_project_not_configured")
    value = found[0]
    if not re.fullmatch(r"[a-z][a-z0-9_-]{1,60}", str(value.get("id", ""))): raise ValueError("invalid_development_project")
    return value


def inspect_work(config, identifier, parent):
    base = Path(config["development_home"]).resolve().parent
    value = private_json(base / "development-records" / (identifier + ".json"))
    if not value: return {"state": "not-created", "work_id": identifier, "model_woken": False}
    if value.get("parent_session") != parent: raise ValueError("DEVELOPMENT_AUTHOR_MISMATCH")
    history = base / "development-records" / identifier
    orphan = history / ("revision-" + str(value["revision"] + 1) + ".json")
    pending = []
    if history.is_dir():
        for path in sorted(history.glob("operation-*.json")):
            item = private_json(path)
            if item.get("phase") == "started": pending.append({"operation_id": path.stem.removeprefix("operation-"),
                "operation": item.get("operation"), "expected_revision": item.get("expected_revision"), "phase": "unsettled-no-replay"})
    receipts = {key: private_json(base / "development-validations" / (identifier + suffix))
                for key, suffix in (("test", ".json"), ("review", ".review.json"), ("commit", ".commit.json"), ("publication", ".publication.json"))}
    return {"state": "observed", "work": value, **receipts, "unsettled_operations": pending[:40],
            "orphan_revision_audit": private_json(orphan), "recovery_required": bool(pending or orphan.exists()),
            "model_woken": False, "platform_sends": 0}


def imported_snapshot(config, project_id, candidate):
    policy = project(config, project_id)
    source = Path(policy["source_root"])
    if not source.is_absolute() or source.is_symlink() or not source.is_dir(): raise ValueError("unsafe_project_source")
    source = source.resolve()
    paths = policy.get("paths")
    if not isinstance(paths, list) or not paths or len(paths) > 100: raise ValueError("project_paths_not_configured")
    if any(candidate.iterdir()): raise ValueError("candidate_not_empty_import_refused")
    files, count, size = {}, 0, 0
    revision = None
    if (source / ".git").exists():
        git = config.get("development", {}).get("git") or shutil.which("git")
        if not git: raise ValueError("configured_git_executable_required")
        held = subprocess.run([git, "--no-replace-objects", "-C", str(source), "-c", "core.hooksPath=" + os.devnull,
                               "-c", "core.fsmonitor=false", "rev-parse", "--verify", "HEAD"],
                              env=worker_environment(home=candidate, extra={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}),
                              capture_output=True, text=True, timeout=15)
        if held.returncode or not re.fullmatch(r"[a-f0-9]{40,64}", held.stdout.strip()): raise ValueError("project_source_revision_unavailable")
        revision = held.stdout.strip()
    if policy.get("base_revision") and policy["base_revision"] != revision: raise ValueError("project_source_revision_conflict")
    for raw in paths:
        path = Path(raw)
        if not isinstance(raw, str) or path.is_absolute() or ".." in path.parts or any(part.startswith(".") for part in path.parts):
            raise ValueError("unsafe_project_import_path")
        target = source / path
        if target.is_symlink(): raise ValueError("project_symlink_import_refused")
        target.resolve().relative_to(source)
        entries = [target] if target.is_file() else sorted(target.rglob("*")) if target.is_dir() else []
        for entry in entries:
            relative = entry.relative_to(source)
            if any(part.startswith(".") or part in {"node_modules", "__pycache__", "logs", "sessions"} for part in relative.parts): continue
            if entry.is_symlink(): raise ValueError("project_symlink_import_refused")
            if not entry.is_file(): continue
            entry.resolve().relative_to(source)
            if any(parent.is_symlink() for parent in entry.parents if parent != source and source in parent.parents):
                raise ValueError("project_symlink_ancestor_import_refused")
            if entry.stat().st_nlink != 1: raise ValueError("project_hardlink_import_refused")
            payload = entry.read_bytes(); count += 1; size += len(payload)
            if count > 2000 or size > 20 * 1024 * 1024: raise ValueError("project_snapshot_budget_exceeded")
            if re.search(rb"\bsk-[A-Za-z0-9_-]{16,}", payload): raise ValueError("project_contains_credentials")
            files[str(relative)] = payload
    if not files: raise ValueError("empty_project_snapshot_refused")
    # All reads/validation finish before any candidate file is materialized.
    manifest = {name: hashlib.sha256(payload).hexdigest() for name, payload in sorted(files.items())}
    if any(hashlib.sha256((source / name).read_bytes()).hexdigest() != digest for name, digest in manifest.items()):
        raise ValueError("project_source_changed_during_snapshot")
    for name, payload in files.items():
        destination = candidate / name; destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            private_fchmod(stream.fileno(), 0o600); stream.write(payload); stream.flush(); os.fsync(stream.fileno())
    return {"state": "imported", "project_id": project_id, "files": len(files), "bytes": size,
            "source_manifest": manifest, "base_revision": revision,
            "snapshot_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "source_modified": False, "git_base_established": False}
