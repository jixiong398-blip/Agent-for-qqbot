# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Durable, explicit-path spool and journal for the Soyo QQ channel.

The inbound spool is the queue boundary: an authorized envelope is atomically
written before a host submission is attempted.  Receipt failures are retained
instead of disappearing.  This module has no Hermes-home fallback and no
network behavior, so a DSH sidecar cannot silently share Hermes runtime state.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from .contracts import InboundEnvelope, Receipt, qq_id

from soyo.platform import fcntl, open_private, private_fchmod, sync_directory, assert_private


Bucket = Literal["inbound", "receipts"]


class Counters:
    """Small thread-safe counter set for channel health snapshots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, int] = {}

    def inc(self, name: str, delta: int = 1) -> None:
        with self._lock:
            self._values[str(name)] = self._values.get(str(name), 0) + int(delta)

    def set(self, name: str, value: int) -> None:
        with self._lock:
            self._values[str(name)] = int(value)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._values)


def _safe_name(value: Any, limit: int = 64) -> str:
    text = str(value or "")
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in text)[:limit] or "item"


def _fsync_directory(path: Path) -> None:
    sync_directory(path)


def identity_digest(*parts: Any) -> str:
    """Filesystem key from exact structured identities, not lossy filenames."""

    raw = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SoyoQQJournal:
    """Atomic spool/journal rooted at one explicit absolute directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("SoyoQQJournal requires an absolute root")
        if self.root.is_symlink():
            raise ValueError("journal root must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.spool_root = self.root / "spool"
        self.inbound_root = self.spool_root / "inbound"
        self.receipts_root = self.spool_root / "receipts"
        self.journal_root = self.root / "journal"
        self.seen_root = self.root / "seen"
        self.attempts_root = self.root / "attempts"
        self.catchup_root = self.root / "catchup"
        for directory in (self.spool_root, self.inbound_root, self.receipts_root,
                          self.journal_root, self.seen_root, self.attempts_root, self.catchup_root):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            if directory.is_symlink():
                raise ValueError("journal directories must not be symlinks")
            directory.chmod(0o700)
        self.root.chmod(0o700)
        self._thread_lock = threading.RLock()
        self._lock_fd: int | None = None
        self._channel_attached = False
        self.started_at = time.time()

    @staticmethod
    def write_json(path: Path, value: Any) -> None:
        """Write JSON with an fsync and atomic replacement in the same directory."""

        path = Path(path)
        if path.is_symlink():
            raise ValueError("journal files must not be symlinks")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        temporary: Path | None = None
        fd: int | None = None
        try:
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
            )
            temporary = Path(temporary_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                fd = None
                private_fchmod(handle.fileno(), 0o600)
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            temporary = None
            _fsync_directory(path.parent)
        finally:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    @staticmethod
    def read_json(path: Path) -> Any:
        if Path(path).is_symlink():
            raise ValueError("journal files must not be symlinks")
        assert_private(Path(path))
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _directory_for(self, bucket: Bucket) -> Path:
        if bucket == "inbound":
            return self.inbound_root
        if bucket == "receipts":
            return self.receipts_root
        raise ValueError("unknown journal bucket")

    def append(self, name: str, value: Any) -> Path:
        """Append one durable JSONL journal record."""

        filename = _safe_name(name.removesuffix(".jsonl"), 120) + ".jsonl"
        path = self.journal_root / filename
        line = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
        with self._thread_lock:
            with path.open("a", encoding="utf-8") as handle:
                os.chmod(path, 0o600)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(path.parent)
        return path

    def spool_add(self, bucket: Bucket, value: Any, *, key: str = "") -> Path:
        """Idempotent keyed enqueue; anonymous records get collision-free names."""

        directory = self._directory_for(bucket)
        with self._thread_lock:
            name = identity_digest(key) if key else uuid.uuid4().hex
            path = directory / (name + ".json")
            if not path.exists():
                self.write_json(path, value)
        return path

    def spool_list(self, bucket: Bucket) -> list[Path]:
        directory = self._directory_for(bucket)
        paths = sorted((path for path in directory.iterdir()
                        if path.is_file() and path.suffix == ".json"),
                       key=lambda path: (path.stat().st_mtime_ns, path.name))
        if bucket == "receipts":
            pending = []
            for path in paths:
                try:
                    record = self.read_json(path)
                except (OSError, ValueError):
                    pending.append(path)
                    continue
                if not isinstance(record, dict) or record.get("report_state") not in ("reported", "rejected", "blocked"):
                    pending.append(path)
            return pending
        return paths

    @staticmethod
    def spool_remove(path: Path) -> bool:
        try:
            Path(path).unlink()
            _fsync_directory(Path(path).parent)
            return True
        except FileNotFoundError:
            return False

    def spool_move(self, path: Path, journal_name: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            item = self.read_json(path)
        except Exception as error:  # keep the queue observable even if a file is corrupt
            item = {"unreadable": type(error).__name__, "name": Path(path).name[:160]}
        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "item": item,
        }
        if extra:
            record.update(extra)
        self.append(journal_name, record)
        self.spool_remove(path)
        return record

    def quarantine(self, path: Path, reason: str) -> Path:
        """Retain unreadable bytes instead of rewriting them into empty JSON."""

        directory = self.root / "quarantine"
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / (uuid.uuid4().hex + "-" + path.name)
        self.append("quarantine", {"name": path.name, "reason": reason})
        os.replace(path, target)
        _fsync_directory(path.parent)
        _fsync_directory(directory)
        return target

    @staticmethod
    def event_key(envelope: InboundEnvelope) -> str:
        return identity_digest(envelope.account_id, envelope.route_id, envelope.scene_id,
                               envelope.event_id, envelope.occurred_at)

    def enqueue_inbound(self, envelope: InboundEnvelope, metadata: dict[str, Any]) -> bool:
        """Persist before remembering an event, including across restarts."""

        key = self.event_key(envelope)
        with self._thread_lock:
            path = self.inbound_root / (key + ".json")
            if path.exists() or (self.seen_root / path.name).exists():
                return False
            self.write_json(path, {"envelope": envelope.as_dict(), "metadata": metadata,
                                   "tries": 0, "next_try_at": 0.0})
            return True

    def finish_inbound(self, path: Path, envelope: InboundEnvelope, status: str) -> None:
        """Durable tombstone first, then remove the submitted/dead-letter item."""

        key = self.event_key(envelope)
        if path != self.inbound_root / (key + ".json"):
            raise ValueError("inbound spool identity mismatch")
        with self._thread_lock:
            self.write_json(self.seen_root / path.name,
                            {"event_id": envelope.event_id, "route_id": envelope.route_id,
                             "account_id": envelope.account_id, "status": status})
            self.spool_remove(path)

    def attempt_path(self, publication_id: str) -> Path:
        return self.attempts_root / (identity_digest(publication_id) + ".json")

    def read_attempt(self, publication_id: str) -> dict[str, Any] | None:
        path = self.attempt_path(publication_id)
        try:
            record = self.read_json(path)
        except FileNotFoundError:
            return None
        if not isinstance(record, dict) or record.get("publication_id") != publication_id:
            raise ValueError("corrupt publication fence")
        return record

    def write_attempt(self, record: dict[str, Any]) -> None:
        self.write_json(self.attempt_path(record["publication_id"]), record)

    def receipt_path(self, receipt: Receipt) -> Path:
        return self.receipts_root / (identity_digest(receipt.publication_id, receipt.attempt_id) + ".json")

    def queue_receipt(self, receipt: Receipt) -> Path:
        """Receipts stay durable even after reporting, so replay is idempotent."""

        path = self.receipt_path(receipt)
        with self._thread_lock:
            if not path.exists():
                self.write_json(path, {"publication_id": receipt.publication_id,
                                       "receipt": receipt.as_dict(), "report_state": "pending",
                                       "tries": 0, "next_try_at": 0.0})
        return path

    def bind_account(self, account_id: str) -> None:
        """Prevent a data root from silently changing accounts after restart."""

        if not qq_id(account_id):
            raise ValueError("invalid journal account")
        path = self.root / "channel.json"
        expected = {"schema_version": 1, "account_id": account_id}
        try:
            current = self.read_json(path)
        except FileNotFoundError:
            self.write_json(path, expected)
        else:
            if current != expected:
                raise ValueError("journal account/schema mismatch")

    def attach_channel(self, account_id: str) -> None:
        with self._thread_lock:
            if self._channel_attached:
                raise RuntimeError("journal is already attached to a channel")
            self.acquire_lock()
            try:
                self.bind_account(account_id)
            except Exception:
                self.release_lock()
                raise
            self._channel_attached = True

    def acquire_lock(self) -> None:
        """Hold one process lock for this sidecar data root."""

        if fcntl is None:
            raise RuntimeError("SoyoQQJournal requires a POSIX file lock")
        if self._lock_fd is not None:
            return
        path = self.root / "channel.lock"
        fd = open_private(path, os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise RuntimeError("another Soyo QQ channel process owns this data root")
        self._lock_fd = fd
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
            os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
            os.fsync(fd)
        except OSError:
            self.release_lock()
            raise

    def release_lock(self) -> None:
        fd = self._lock_fd
        self._lock_fd = None
        if fd is None:
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_UN) if fcntl is not None else None
        finally:
            os.close(fd)

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "uptime_seconds": round(max(0.0, time.time() - self.started_at), 1),
            "spool_inbound": len(self.spool_list("inbound")),
            "spool_receipts": len(self.spool_list("receipts")),
            "publication_fences": len(list(self.attempts_root.glob("*.json"))),
            "process_lock_held": self._lock_fd is not None,
        }

    def close(self) -> None:
        self._channel_attached = False
        self.release_lock()

    def __enter__(self) -> "SoyoQQJournal":
        self.acquire_lock()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
