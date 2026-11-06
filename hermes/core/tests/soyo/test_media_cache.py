# SPDX-License-Identifier: MIT
"""Inbound media is cached on arrival and verified before a later turn trusts it."""
import hashlib
from pathlib import Path

from soyo.qq import media_cache


def _config(tmp_path, **extra):
    return {"media_root": str(tmp_path / "media"), "max_media_bytes": 1024 * 1024, **extra}


def _fetch(config, args):
    root = Path(config["media_root"])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    content = b"\xff\xd8\xff\xe0" + args["ref"].encode()
    path = root / (hashlib.sha256(content).hexdigest() + ".jpg")
    path.write_bytes(content)
    path.chmod(0o600)
    return {"ok": True, "kind": args["kind"], "path": str(path), "bytes": len(content),
            "media_type": "image/jpeg", "sha256": hashlib.sha256(content).hexdigest(), "name": "inbound.jpg"}


def test_precache_stores_bytes_then_serves_the_same_object_without_refetching(tmp_path):
    config = _config(tmp_path)
    calls = []

    def fetch(cfg, args):
        calls.append(args)
        return _fetch(cfg, args)

    envelope = {"media": [{"kind": "image", "ref": "stable-file-a"}]}
    assert media_cache.precache(config, envelope, fetch) == {"cached": 1, "already": 0, "missed": []}
    hit = media_cache.lookup(config, "stable-file-a")
    assert hit["media_type"] == "image/jpeg" and Path(hit["path"]).is_file()
    assert media_cache.precache(config, envelope, fetch) == {"cached": 0, "already": 1, "missed": []}
    assert len(calls) == 1


def test_tampered_or_replaced_cache_file_becomes_a_miss(tmp_path):
    config = _config(tmp_path)
    media_cache.precache(config, {"media": [{"kind": "image", "ref": "stable-file-b"}]}, _fetch)
    hit = media_cache.lookup(config, "stable-file-b")
    Path(hit["path"]).write_bytes(b"\xff\xd8\xff\xe0different-bytes")
    assert media_cache.lookup(config, "stable-file-b") is None


def test_fetch_failures_never_raise_into_the_gateway(tmp_path):
    config = _config(tmp_path)

    def broken(cfg, args):
        raise TimeoutError("napcat timed out")

    assert media_cache.precache(config, {"media": [{"kind": "record", "ref": "voice-a"}]}, broken) == {
        "cached": 0, "already": 0, "missed": [{"kind": "record", "error": "TimeoutError"}]}


def test_non_media_and_unknown_kinds_are_ignored(tmp_path):
    config = _config(tmp_path)
    calls = []
    result = media_cache.precache(config, {"media": [
        {"kind": "face", "ref": "face-a"}, {"kind": "unknown", "ref": "x"},
        {"kind": "image", "ref": ""}, "not-a-dict"]}, lambda cfg, args: calls.append(args))
    assert result == {"cached": 0, "already": 0, "missed": []}
    assert calls == []


def test_envelope_without_media_is_a_no_op(tmp_path):
    assert media_cache.precache(_config(tmp_path), {"media": []}, _fetch) == {
        "cached": 0, "already": 0, "missed": []}


def test_purge_drops_expired_entries_and_their_bytes(tmp_path):
    config = _config(tmp_path)
    media_cache.precache(config, {"media": [{"kind": "image", "ref": "old-image"}]}, _fetch)
    hit = media_cache.lookup(config, "old-image")
    size = Path(hit["path"]).stat().st_size
    result = media_cache.purge(config, now=hit["cached_at"] + 8 * 24 * 3600, force=True)
    assert result == {"skipped": False, "deleted": 1, "freed_bytes": size}
    assert not Path(hit["path"]).exists()
    assert media_cache.lookup(config, "old-image") is None


def test_purge_keeps_recent_entries(tmp_path):
    config = _config(tmp_path)
    media_cache.precache(config, {"media": [{"kind": "image", "ref": "fresh-image"}]}, _fetch)
    hit = media_cache.lookup(config, "fresh-image")
    result = media_cache.purge(config, now=hit["cached_at"] + 3600, force=True)
    assert result["deleted"] == 0
    assert Path(hit["path"]).is_file()


def test_purge_never_deletes_outside_the_media_root(tmp_path):
    config = _config(tmp_path)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"keep me")
    index = media_cache.index_path(config, "outside-ref")
    index.write_text(media_cache.json.dumps({
        "version": 1, "kind": "image", "ref": "outside-ref", "path": str(outside),
        "bytes": outside.stat().st_size, "cached_at": 1.0,
    }), encoding="utf-8")
    result = media_cache.purge(config, now=10 * 24 * 3600, force=True)
    assert result["deleted"] == 1
    assert outside.is_file()
    assert not index.exists()
