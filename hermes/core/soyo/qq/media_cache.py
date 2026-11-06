# SPDX-License-Identifier: MIT
"""Cache inbound QQ media on arrival; understanding stays on demand.

The gateway persists image/voice bytes as soon as an authorized event is
spooled, before any @ mention, model turn or action delegation decides to use
them. Video attachments are recorded as skipped policy outcomes and are not
downloaded. Caching never calls a model or a transcriber: a later turn either reads
the original bytes or ignores them. Records are content-addressed sidecars in
the deployment-owned media root; a tampered or missing file is a cache miss,
never a trusted hit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Mapping

from soyo.platform import assert_private, load_private_json, private_fchmod, sync_directory

CACHEABLE = frozenset({"image", "mface", "record", "video"})
PURGE_INTERVAL_SECONDS = 3600
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
DEFAULT_MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_ITEMS = 200
MAX_INDEX_BYTES = 8 * 1024
# Hashing every byte on each lookup would make a cached voice/video read costly.
# Small media (all images) are always verified; large media verify size only.
FULL_VERIFY_BYTES = 8 * 1024 * 1024

# Cache lifecycle states.  These are vocabulary only; existing cache behavior
# remains unchanged until later migration steps attach them to records.
STATUS_PENDING = "pending"
STATUS_CACHED_READABLE = "cached_readable"
STATUS_NOT_PROVIDED = "not_provided"
STATUS_DOWNLOAD_FAILED = "download_failed"
STATUS_REF_EXPIRED = "ref_expired"
STATUS_UNSUPPORTED_FORMAT = "unsupported_format"
STATUS_SKIPPED_BY_POLICY = "skipped_by_policy"

MEDIA_CACHE_STATUSES = frozenset({
    STATUS_PENDING,
    STATUS_CACHED_READABLE,
    STATUS_NOT_PROVIDED,
    STATUS_DOWNLOAD_FAILED,
    STATUS_REF_EXPIRED,
    STATUS_UNSUPPORTED_FORMAT,
    STATUS_SKIPPED_BY_POLICY,
})

REASON_QUEUE_FULL = "queue_full"
REASON_TIMEOUT = "timeout"
REASON_NAPCAT_UNAVAILABLE = "napcat_unavailable"
REASON_HTTP_ERROR = "http_error"
REASON_SIZE_LIMIT = "size_limit"
REASON_DISK_ERROR = "disk_error"
REASON_DISK_QUOTA = "disk_quota"
REASON_INVALID_CONTENT_TYPE = "invalid_content_type"
REASON_CACHE_INTEGRITY_ERROR = "cache_integrity_error"
REASON_LEGACY_CACHE_MISSING = "legacy_cache_missing"
REASON_MESSAGE_ATTACHMENT_LIMIT = "message_attachment_limit"
REASON_UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
REASON_SKIPPED_BY_POLICY = "skipped_by_policy"

MEDIA_CACHE_REASONS = frozenset({
    REASON_QUEUE_FULL,
    REASON_TIMEOUT,
    REASON_NAPCAT_UNAVAILABLE,
    REASON_HTTP_ERROR,
    REASON_SIZE_LIMIT,
    REASON_DISK_ERROR,
    REASON_DISK_QUOTA,
    REASON_INVALID_CONTENT_TYPE,
    REASON_CACHE_INTEGRITY_ERROR,
    REASON_LEGACY_CACHE_MISSING,
    REASON_MESSAGE_ATTACHMENT_LIMIT,
    REASON_UNSUPPORTED_MEDIA_TYPE,
    REASON_SKIPPED_BY_POLICY,
})

_FAILED_MEDIA_CACHE_STATUSES = frozenset({
    STATUS_DOWNLOAD_FAILED,
    STATUS_REF_EXPIRED,
    STATUS_UNSUPPORTED_FORMAT,
})


def is_failure_status(status: str) -> bool:
    """Return whether a media-cache status represents a failed outcome."""
    return status in _FAILED_MEDIA_CACHE_STATUSES


def media_root(config: Mapping[str, Any]) -> Path:
    root = Path(str(config.get("media_root") or ""))
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("media root unavailable")
    return root


def cache_dir(config: Mapping[str, Any]) -> Path:
    root = media_root(config) / "inbound-cache"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise ValueError("media cache directory must not be a symlink")
    return root


def reference_key(ref: str) -> str:
    return hashlib.sha256(ref.encode("utf-8")).hexdigest()


def index_path(config: Mapping[str, Any], ref: str) -> Path:
    return cache_dir(config) / (reference_key(ref) + ".json")


def normalize_kind(kind: str) -> str:
    """One cached kind per stored object; unknown media is not cached."""
    value = str(kind or "").strip().lower()
    if value in {"image", "mface"}:
        return "image"
    if value in {"record", "audio"}:
        return "record"
    return "video" if value == "video" else ""


def is_sticker(item: Mapping[str, Any]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    return str(metadata.get("sticker") or "").lower() in {"custom", "market"}


def fingerprint(item: Mapping[str, Any], cached: Mapping[str, Any] | None = None) -> str:
    """Return a stable sticker identity without treating photos as stickers."""
    if not is_sticker(item):
        return ""
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    if str(metadata.get("sticker")) == "market" and metadata.get("emoji_id"):
        return "market:" + str(metadata["emoji_id"])[:64]
    file_name = str(item.get("ref") or "").rsplit("/", 1)[-1]
    stem = file_name.rsplit(".", 1)[0]
    if len(stem) == 32 and all(char in "0123456789abcdefABCDEF" for char in stem):
        return "md5:" + stem.lower()
    value = (cached or {}).get("sha256") if isinstance(cached, Mapping) else ""
    return "sha256:" + str(value)[:64] if value else ""


def _write_index(path: Path, value: Mapping[str, Any]) -> None:
    text = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = None
            private_fchmod(stream.fileno(), 0o600)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        sync_directory(path.parent)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            try:
                Path(temporary).unlink()
            except FileNotFoundError:
                pass


def record(config: Mapping[str, Any], ref: str, kind: str, fetched: Mapping[str, Any]) -> dict[str, Any]:
    """Record one successful fetch. The bytes already live under the media root."""
    if not ref or len(ref) > 2048:
        raise ValueError("bounded media reference required")
    normalized = normalize_kind(kind)
    if not normalized:
        raise ValueError("unsupported media kind")
    media = Path(str(fetched.get("path") or ""))
    info = assert_private(media, max_bytes=int(config.get("max_media_bytes", 20 * 1024 * 1024)))
    value = {"version": 1, "kind": normalized, "ref": ref, "path": str(media),
             "bytes": info.st_size, "media_type": str(fetched.get("media_type") or "")[:80],
             "sha256": str(fetched.get("sha256") or ""), "name": str(fetched.get("name") or "")[:120],
             "cached_at": time.time()}
    if not value["sha256"]:
        value["sha256"] = hashlib.sha256(media.read_bytes()).hexdigest()
    _write_index(index_path(config, ref), value)
    return value


def lookup(config: Mapping[str, Any], ref: str) -> dict[str, Any] | None:
    """Return one verified cached object, or None. Never trusts a stale path."""
    if not isinstance(ref, str) or not ref or len(ref) > 2048:
        return None
    try:
        path = index_path(config, ref)
        if not path.is_file() or path.is_symlink():
            return None
        value = load_private_json(path, max_bytes=MAX_INDEX_BYTES)
        if not isinstance(value, dict) or value.get("version") != 1 or value.get("ref") != ref:
            return None
        normalized = normalize_kind(value.get("kind"))
        if not normalized:
            return None
        media = Path(str(value.get("path") or ""))
        limit = int(config.get("max_media_bytes", 20 * 1024 * 1024))
        info = assert_private(media, max_bytes=limit)
        if info.st_size != value.get("bytes"):
            return None
        if info.st_size <= FULL_VERIFY_BYTES:
            if hashlib.sha256(media.read_bytes()).hexdigest() != value.get("sha256"):
                return None
        return {"kind": normalized, "path": str(media), "bytes": info.st_size,
                "media_type": str(value.get("media_type") or ""), "sha256": str(value.get("sha256") or ""),
                "name": str(value.get("name") or ""), "cached_at": value.get("cached_at")}
    except (OSError, ValueError, TypeError):
        return None


def _max_items(config: Mapping[str, Any]) -> int:
    """Read the bounded per-envelope cache capacity, defaulting to 200."""
    value = config.get("media_cache_max_items", MAX_ITEMS)
    if type(value) is not int:
        return MAX_ITEMS
    return max(1, min(1000, value))


def _failure_detail(value: Any, fallback: str = "fetch_failed") -> str:
    if isinstance(value, BaseException):
        text = f"{type(value).__name__}: {value}"
    else:
        text = str(value or fallback)
    return " ".join(text.split())[:200] or fallback


def _failure_reason(value: Any) -> str:
    text = _failure_detail(value).lower().replace("_", " ").replace("-", " ")
    error_type = type(value).__name__.lower()
    if isinstance(value, TimeoutError) or "timeout" in error_type or "timed out" in text:
        return REASON_TIMEOUT
    if any(marker in text for marker in (
        "too large", "oversized", "exceeds", "size limit", "bounded size", "max bytes",
        "maximum size", "size exceeded",
    )):
        return REASON_SIZE_LIMIT
    if any(marker in text for marker in (
        "content type", "mime", "base64", "type rejected", "invalid content",
        "unsupported format", "invalid format", "wrong format",
    )):
        return REASON_INVALID_CONTENT_TYPE
    return REASON_HTTP_ERROR


def precache(config: Mapping[str, Any], envelope: Mapping[str, Any],
             fetch: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]]) -> dict[str, Any]:
    """Best-effort caching for one inbound envelope; never raises into the gateway."""
    media = envelope.get("media") if isinstance(envelope, Mapping) else None
    if not isinstance(media, list) or not media:
        return {"cached": 0, "already": 0, "missed": []}
    cached, already, missed = 0, 0, []
    for item in media[:_max_items(config)]:
        if not isinstance(item, Mapping):
            continue
        normalized = normalize_kind(item.get("kind"))
        ref = item.get("ref")
        if not normalized or not isinstance(ref, str) or not ref:
            continue
        if normalized == "video":
            try:
                record_failure(config, ref, normalized, STATUS_SKIPPED_BY_POLICY,
                               REASON_SKIPPED_BY_POLICY,
                               "video caching disabled by policy")
            except Exception as error:
                missed.append({"kind": normalized, "error": type(error).__name__})
            continue
        try:
            if lookup(config, ref) is not None:
                already += 1
                continue
        except (OSError, ValueError):
            pass
        try:
            fetched = fetch(config, {"kind": normalized, "ref": ref, "op": "media"})
        except Exception as error:
            try:
                record_failure(config, ref, normalized, STATUS_DOWNLOAD_FAILED,
                               _failure_reason(error), _failure_detail(error))
            except Exception as record_error:
                missed.append({"kind": normalized, "error": type(record_error).__name__})
            else:
                missed.append({"kind": normalized, "error": type(error).__name__})
            continue
        fetch_error = None if isinstance(fetched, Mapping) and fetched.get("ok") else (
            fetched.get("error") if isinstance(fetched, Mapping) else fetched)
        if fetch_error is None and not (isinstance(fetched, Mapping) and fetched.get("ok")):
            fetch_error = "fetch_failed"
        if fetch_error is not None:
            try:
                record_failure(config, ref, normalized, STATUS_DOWNLOAD_FAILED,
                               _failure_reason(fetch_error), _failure_detail(fetch_error))
            except Exception as record_error:
                missed.append({"kind": normalized, "error": type(record_error).__name__})
            else:
                missed.append({"kind": normalized, "error": _failure_detail(fetch_error, "fetch_failed")[:80]})
            continue
        try:
            record(config, ref, normalized, fetched)
            cached += 1
        except (OSError, ValueError) as error:
            missed.append({"kind": normalized, "error": type(error).__name__})
    try:
        purge(config)
    except Exception:
        pass
    return {"cached": cached, "already": already, "missed": missed[:4]}


def record_failure(config: Mapping[str, Any], ref: str, kind: str, status: str,
                   reason: str, detail: Any = None) -> dict[str, Any]:
    """Record a bounded failed cache outcome using the index's atomic writer."""
    if not isinstance(ref, str) or not ref or len(ref) > 2048:
        raise ValueError("bounded media reference required")
    normalized = normalize_kind(kind)
    if not normalized:
        raise ValueError("unsupported media kind")
    if status not in MEDIA_CACHE_STATUSES:
        raise ValueError("unsupported media cache status")
    if reason not in MEDIA_CACHE_REASONS:
        raise ValueError("unsupported media cache reason")
    value = {"version": 1, "ref": ref, "kind": normalized, "status": status,
             "reason": reason, "detail": detail, "recorded_at": time.time()}
    _write_index(index_path(config, ref), value)
    return value


def _bounded(config: Mapping[str, Any], key: str, default: float, low: float, high: float) -> float:
    value = config.get(key, default)
    if type(value) not in (int, float) or isinstance(value, bool):
        return default
    return max(low, min(high, float(value)))


def purge(config: Mapping[str, Any], now: float | None = None, force: bool = False) -> dict[str, Any]:
    """Drop expired cache entries and their bytes; never touches non-cache files.

    Runs at most once an hour unless forced.  Only sidecars under
    ``media/inbound-cache`` and files that live inside the media root are
    removed; anything resolving outside the root is left alone.
    """
    now = time.time() if now is None else now
    ttl = _bounded(config, "media_cache_ttl_seconds", DEFAULT_TTL_SECONDS, 3600, 90 * 24 * 3600)
    max_bytes = int(_bounded(config, "media_cache_max_bytes", DEFAULT_MAX_BYTES,
                             64 * 1024 * 1024, 20 * 1024 * 1024 * 1024))
    root = cache_dir(config)
    stamp = root / ".purge-stamp"
    if not force:
        try:
            last = float(stamp.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            last = 0.0
        if now - last < PURGE_INTERVAL_SECONDS:
            return {"skipped": True, "deleted": 0, "freed_bytes": 0}

    entries = []
    for path in sorted(root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        try:
            recorded = float(value.get("cached_at") or value.get("recorded_at") or 0)
        except (TypeError, ValueError):
            recorded = 0.0
        media = Path(str(value.get("path") or ""))
        size = 0
        try:
            size = media.stat().st_size if media.is_file() else 0
        except OSError:
            size = 0
        entries.append({"index": path, "media": media, "recorded": recorded,
                        "bytes": size, "remove": False})

    for entry in entries:
        if ttl and entry["recorded"] and now - entry["recorded"] > ttl:
            entry["remove"] = True

    total = sum(entry["bytes"] for entry in entries if not entry["remove"])
    if total > max_bytes:
        for entry in sorted((item for item in entries if not item["remove"]),
                            key=lambda item: item["recorded"]):
            if total <= max_bytes * 0.8:
                break
            entry["remove"] = True
            total -= entry["bytes"]

    kept = {str(entry["media"]) for entry in entries if not entry["remove"] and entry["media"]}
    base = media_root(config).resolve()
    deleted = freed = 0
    for entry in entries:
        if not entry["remove"]:
            continue
        try:
            entry["index"].unlink(missing_ok=True)
            deleted += 1
        except OSError:
            continue
        media = entry["media"]
        if not str(media) or str(media) in kept:
            continue
        try:
            resolved = media.resolve()
            if resolved == base or base not in resolved.parents or not resolved.is_file():
                continue
            size = resolved.stat().st_size
            resolved.unlink()
            freed += size
        except (OSError, RuntimeError):
            pass
    try:
        stamp.write_text(str(now) + "\n", encoding="utf-8")
        os.chmod(stamp, 0o600)
    except OSError:
        pass
    return {"skipped": False, "deleted": deleted, "freed_bytes": freed}
