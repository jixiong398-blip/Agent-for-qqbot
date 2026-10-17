# SPDX-License-Identifier: GPL-3.0-only
"""Configured candidate release selectors, effect fences and explicit rollback.

No free target paths, shell, Git push, service restart or platform writer here.
Selecting a release and observing its bytes is not service activation/health.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from soyo.platform import fcntl, open_private, private_fchmod, sync_directory, WINDOWS
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .development_records import durable, private_json, project
else:
    from development_records import durable, private_json, project


def selector_target(selector, releases):
    if selector.is_symlink():
        target = selector.resolve(strict=True)
        target.relative_to(releases)
        if not target.is_dir(): raise ValueError("release_selector_target_not_directory")
        return str(target)
    if selector.is_file():
        value = private_json(selector)
        if value.get("format") != "agent-qqbot-release-v1": raise ValueError("unfamiliar_release_selector")
        target = Path(value["directory"]).resolve(strict=True)
        target.relative_to(releases)
        if not target.is_dir(): raise ValueError("release_selector_target_not_directory")
        return str(target)
    if selector.exists(): raise ValueError("unfamiliar_non_file_release_selector")
    return None


def policy_paths(config, ledger, *, create=False):
    item = project(config, ledger.value.get("project_id"))
    release = item.get("release", {})
    if not release.get("enabled"): raise ValueError("development_publication_not_configured")
    releases, selector = Path(release["root"]), Path(release["selector"])
    if not releases.is_absolute() or not selector.is_absolute() or releases.is_symlink(): raise ValueError("unsafe_release_policy_paths")
    if create: releases.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not releases.is_dir(): raise ValueError("release_root_not_created")
    releases = releases.resolve()
    if selector.parent.is_symlink() or not selector.parent.is_dir(): raise ValueError("unsafe_release_selector_parent")
    selector.parent.resolve().relative_to(Path(release.get("selector_parent", str(selector.parent))).resolve())
    return releases, selector, release


@contextmanager
def project_lock(config, ledger):
    # Per-work locks cannot serialize two authors selecting the same project's
    # release. The shared selector is fenced at the trusted project boundary.
    item = project(config, ledger.value.get("project_id"))
    parent = Path(config["development_home"]).resolve().parent / "development-locks"
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = open_private(parent / ("project-" + item["id"] + ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def publish(config, ledger, args, tree_hash):
    with project_lock(config, ledger): return _publish(config, ledger, args, tree_hash)


def _publish(config, ledger, args, tree_hash):
    ledger.check(args.get("expected_revision"))
    root = Path(config["development_home"]).resolve() / ledger.value["work_id"]
    validation = root.parent.parent / "development-validations"
    current = tree_hash()
    acceptance = ledger.value.get("acceptance") or {}
    test = private_json(validation / (root.name + ".json"))
    review = private_json(validation / (root.name + ".review.json"))
    commit = private_json(validation / (root.name + ".commit.json"))
    if (acceptance.get("decision") != "accept" or acceptance.get("tree_sha256") != current or
            acceptance.get("review_id") != review.get("review_id") or review.get("state") != "reviewed" or
            review.get("decision") != "approve" or review.get("tree_sha256") != current or
            test.get("state") != "tested" or test.get("tree_sha256") != current or test.get("exit_code") != 0 or
            commit.get("tree_sha256") != current or not commit.get("commit")):
        return {"state": "blocked", "reason": "current_test_review_author_commit_not_aligned"}
    releases, selector, policy = policy_paths(config, ledger, create=True)
    if releases == root or root in releases.parents or releases == root.parent:
        raise ValueError("release_root_overlaps_candidate_workspace")
    name = root.name + "-" + current[:16]
    target = releases / name
    previous = selector_target(selector, releases)
    if previous is None and not policy.get("allow_initial", False):
        raise ValueError("initial_release_selector_not_authorized")
    effect = validation / (root.name + ".publication.json")
    prior = private_json(effect)
    # UNKNOWN/started is reconciled by an explicit inspect, never guessed safe
    # to run again, even if the model changes its tool call or request ID.
    if prior.get("phase") in {"effect_started", "rollback_started", "unknown"}:
        return {"state": "unknown", "reason": "publication_effect_requires_inspection", "publication": prior}
    if prior.get("phase") == "release_selected" and prior.get("tree_sha256") == current and previous == prior.get("release"):
        return {"state": "release_selected", "publication": prior, "duplicate": True, "service_activated": False}
    if target.exists():
        stamp = private_json(target / "RELEASE_MANIFEST.json")
        if stamp.get("tree_sha256") != current: raise ValueError("unfamiliar_existing_candidate_release")
        for relative, digest in stamp.get("files", {}).items():
            path = target / relative
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("frozen_release_bytes_changed")
    else:
        target.mkdir(mode=0o700)
        manifest = {}
        for entry in sorted(root.rglob("*")):
            relative = entry.relative_to(root)
            if ".git" in relative.parts or "__pycache__" in relative.parts: continue
            if str(relative) == "RELEASE_MANIFEST.json": raise ValueError("candidate_reserved_release_manifest")
            if entry.is_symlink(): raise ValueError("release_candidate_symlink_refused")
            if not entry.is_file(): continue
            raw = entry.read_bytes(); destination = target / relative
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                private_fchmod(stream.fileno(), 0o400); stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            manifest[str(relative)] = hashlib.sha256(raw).hexdigest()
        if tree_hash() != current: raise ValueError("candidate_changed_during_release_freeze")
        durable(target / "RELEASE_MANIFEST.json", {"tree_sha256": current, "files": manifest,
                  "commit": commit["commit"], "review_id": review["review_id"], "author": acceptance})
    record = {"phase": "effect_started", "work_id": root.name, "tree_sha256": current,
              "release": str(target), "previous_release": previous, "selector": str(selector), "created_at": time.time(),
              "review_id": review["review_id"], "commit": commit["commit"]}
    durable(effect, record)
    temporary = selector.with_name(selector.name + "." + root.name + ".tmp")
    if temporary.exists() or temporary.is_symlink(): raise ValueError("unfamiliar_publication_temporary_path")
    if selector_target(selector, releases) != previous: raise ValueError("release_selector_conflict")
    try:
        if WINDOWS:
            durable(temporary, {"format": "agent-qqbot-release-v1", "directory": str(target)})
        else:
            temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, selector)
        sync_directory(selector.parent)
        if selector_target(selector, releases) != str(target): raise ValueError("release_selector_result_unconfirmed")
        record.update(phase="release_selected", selected_at=time.time(), service_activated=False)
    except Exception:
        record["phase"] = "unknown"; durable(effect, record); raise
    durable(effect, record)
    return {"state": "release_selected", "publication": record, "service_activated": False,
            "note": "Frozen bytes and selector installed; activation/health belongs to the native host management path, not this receipt."}


def inspect(config, ledger):
    releases, selector, _ = policy_paths(config, ledger)
    effect = Path(config["development_home"]).resolve().parent / "development-validations" / (ledger.value["work_id"] + ".publication.json")
    record = private_json(effect)
    current = selector_target(selector, releases)
    return {"state": "observed", "publication": record, "selected_release": current,
            "matches_expected_selection": bool(record.get("release")) and record.get("release") == current,
            "service_activated": None, "platform_sends": 0}


def rollback(config, ledger, args):
    with project_lock(config, ledger): return _rollback(config, ledger, args)


def _rollback(config, ledger, args):
    ledger.check(args.get("expected_revision"))
    releases, selector, _ = policy_paths(config, ledger)
    effect = Path(config["development_home"]).resolve().parent / "development-validations" / (ledger.value["work_id"] + ".publication.json")
    record = private_json(effect)
    previous = record.get("previous_release")
    if record.get("phase") != "release_selected" or not previous:
        return {"state": "blocked", "reason": "no_settled_publication_rollback_asset"}
    destination = Path(previous); destination.resolve(strict=True).relative_to(releases)
    if selector_target(selector, releases) != record.get("release"): raise ValueError("rollback_selector_conflict")
    record.update(phase="rollback_started", rollback_started_at=time.time()); durable(effect, record)
    temporary = selector.with_name(selector.name + "." + ledger.value["work_id"] + ".rollback.tmp")
    if temporary.exists() or temporary.is_symlink(): raise ValueError("unfamiliar_rollback_temporary_path")
    try:
        if WINDOWS:
            durable(temporary, {"format": "agent-qqbot-release-v1", "directory": str(destination)})
        else:
            temporary.symlink_to(destination, target_is_directory=True)
        os.replace(temporary, selector)
        sync_directory(selector.parent)
        if selector_target(selector, releases) != previous: raise ValueError("rollback_result_unconfirmed")
        record.update(phase="rollback_selected", rollback_selected_at=time.time())
    except Exception:
        record["phase"] = "unknown"; durable(effect, record); raise
    durable(effect, record)
    return {"state": "rollback_selected", "publication": record, "service_activated": False,
            "retained_new_release": True, "note": "Prior selector restored; no release files or history deleted, service restart/health is separate."}
