# SPDX-License-Identifier: GPL-3.0-only
"""Action-brain project broker: no arbitrary shell, paths or production writes.

Each work lives beneath its own DSH development directory. The broker never
imports Hermes or receives model/provider credentials. Commands are fixed
project-local Python/git operations, with bounded time and output.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from soyo.platform import fcntl, open_private, private_fchmod, sync_directory
from soyo.sandbox import run_sandbox, sandbox_available
from pathlib import Path

if __package__:
    from .development_records import WorkLedger, imported_snapshot, inspect_work, private_json as read_private, durable as save_private
    from . import development_release
else:
    from development_records import WorkLedger, imported_snapshot, inspect_work, private_json as read_private, durable as save_private
    import development_release


def _call(config, args):
    identifier = args.get("work_id", "")
    if not re.fullmatch(r"action-[0-9a-f-]{36}", identifier):
        raise ValueError("invalid_work_identity")
    base = Path(config["development_home"]).resolve()
    root = base / identifier
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    def path(raw):
        if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
            raise ValueError("relative_project_path_required")
        if any(part.startswith(".") or part in {"..", "node_modules"} for part in Path(raw).parts):
            raise ValueError("protected_project_path")
        result = (root / raw).resolve()
        result.relative_to(root)
        return result
    operation = args.get("operation")
    validations = base.parent / "development-validations"
    validations.mkdir(mode=0o700, exist_ok=True)
    if operation == "import":
        return imported_snapshot(config, args.get("project_id"), root)
    def private_json(file):
        try:
            fd = open_private(file)
        except FileNotFoundError:
            return {}
        with os.fdopen(fd, "r") as stream:
            info = os.fstat(stream.fileno())
            if info.st_size > 256 * 1024:
                raise ValueError("unsafe_development_receipt")
            return json.load(stream)
    def durable(file, value):
        temporary = file.with_name(file.name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("x") as stream:
            private_fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, file)
        sync_directory(file.parent)
    def tree_hash():
        digest, count, size = hashlib.sha256(), 0, 0
        for item in sorted(root.glob("**/*")):
            if ".git" in item.relative_to(root).parts or "__pycache__" in item.parts:
                continue
            if item.is_symlink():
                raise ValueError("candidate_symlink_not_allowed")
            if not item.is_file():
                continue
            count += 1; size += item.stat().st_size
            if count > 2000 or size > 20 * 1024 * 1024:
                raise ValueError("candidate_tree_budget_exceeded")
            digest.update(str(item.relative_to(root)).encode()); digest.update(b"\0"); digest.update(item.read_bytes())
        return digest.hexdigest()
    if operation == "list":
        return {"state": "observed", "files": [str(item.relative_to(root)) for item in root.glob("**/*")
                                                if item.is_file() and ".git" not in item.parts][:200]}
    if operation == "read":
        target = path(args.get("path"))
        if target.stat().st_size > 64 * 1024:
            raise ValueError("file_too_large")
        return {"state": "observed", "text": target.read_text(encoding='utf-8')}
    if operation == "write":
        target = path(args.get("path"))
        text = args.get("text")
        if not isinstance(text, str) or len(text.encode()) > 64 * 1024:
            raise ValueError("bounded_utf8_text_required")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8'); target.chmod(0o600)
        return {"state": "written", "path": str(target.relative_to(root)), "sha256": hashlib.sha256(text.encode()).hexdigest()}
    def sandboxed(command):
        return run_sandbox(config, root, command)
    def git(*args):
        # Tests can write repo config/hooks even though broker writes reject
        # dotfiles. Git must also remain in the same no-network OS sandbox.
        return sandboxed(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "commit.gpgsign=false", *args])
    if operation == "baseline":
        if not (root / ".git").is_dir():
            value = git("init", "-q")
            if value["exit_code"] != 0: return value
        if git("rev-parse", "--verify", "HEAD")["exit_code"] == 0:
            return {"state": "blocked", "reason": "candidate_baseline_already_exists"}
        added = git("add", "--", ".")
        if added["exit_code"] != 0: return added
        value = git("-c", "user.name=Candidate snapshot", "-c", "user.email=snapshot@example.invalid", "commit", "-qm", "Imported source baseline")
        if value["exit_code"] == 0:
            value.update(baseline_commit=git("rev-parse", "HEAD")["stdout"].strip(),
                         note="Source baseline only; no test, review, author acceptance or release.")
        return value
    if operation == "check":
        target = path(args.get("path"))
        if target.suffix != ".py":
            raise ValueError("python_path_required")
        import ast
        ast.parse(target.read_text(encoding='utf-8'), filename=str(target.relative_to(root)))
        return {"state": "syntax_valid", "path": str(target.relative_to(root))}
    if operation == "test":
        if not sandbox_available(config):
            return {"state": "blocked", "reason": "isolated_execution_backend_required"}
        receipt = validations / (identifier + ".json")
        durable(receipt, {"state": "test_started", "created_at": time.time()})
        before = tree_hash()
        # No inherited home, credentials or network. Project Python is allowed
        # only after crossing this kernel-enforced namespace/filesystem boundary.
        result = sandboxed(["python3", "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"])
        result["note"] = "A sandbox setup failure is not a passing test."
        if result["exit_code"] == 0 and "Ran 0 tests" not in result["stderr"] and "\nOK" in result["stderr"]:
            after = tree_hash()
            if before != after:
                return {**result, "state": "unverified", "reason": "candidate_changed_during_test"}
            proof = {"state": "tested", "tree_sha256": after, "exit_code": 0, "created_at": time.time(),
                     "command": ["python3", "-B", "-m", "unittest", "discover", "-s", ".", "-p", "test_*.py"],
                     "stdout": result["stdout"], "stderr": result["stderr"], "sandbox": result["sandbox"]}
            # This receipt is outside /work, hence candidate test code cannot
            # forge it. A later file change invalidates commit eligibility.
            durable(receipt, proof)
        else:
            durable(receipt, {"state": "failed", "exit_code": result["exit_code"], "tree_sha256": before,
                              "stdout": result["stdout"], "stderr": result["stderr"], "created_at": time.time()})
        return result
    if operation == "fingerprint":
        return {"state": "observed", "tree_sha256": tree_hash(),
                "note": "Candidate fingerprint only; no test or review approval."}
    if operation == "review_package":
        before = tree_hash()
        test = private_json(validations / (identifier + ".json"))
        meta = read_private(base.parent / "development-records" / (identifier + ".json"))
        baseline = meta.get("source_manifest", {})
        files, remaining, omitted = [], 128000, 0
        for item in sorted(root.glob("**/*")):
            relative = item.relative_to(root)
            if ".git" in relative.parts or "__pycache__" in relative.parts or not item.is_file(): continue
            raw = item.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if baseline.get(str(relative)) == digest: continue
            if re.search(rb"\bsk-[A-Za-z0-9_-]{16,}", raw): raise ValueError("candidate_review_contains_credentials")
            try: text = raw.decode("utf-8")
            except UnicodeDecodeError: text = None
            excerpt = raw[:min(64000, remaining)].decode("utf-8", errors="ignore") if text is not None else None
            if len(files) >= 100 or remaining <= 0:
                omitted += 1; continue
            if excerpt is not None: remaining -= len(excerpt.encode("utf-8"))
            files.append({"path": str(relative), "sha256": digest, "bytes": len(raw),
                          "text": excerpt, "truncated": text is None or len(excerpt) < len(text)})
        # A model cannot invent the diff, passing test result or tree identity.
        diff = git("diff", "--no-ext-diff", "--no-textconv", "HEAD", "--") if (root / ".git").is_dir() else {
            "exit_code": None, "stdout": "New candidate: no Git base; inspect actual file snapshot.", "stderr": ""}
        if before != tree_hash(): raise ValueError("candidate_changed_during_review_snapshot")
        package = {"state": "observed", "work_id": identifier, "tree_sha256": before, "files": files,
                    "omitted_files": omitted, "contents_truncated": bool(omitted or any(row["truncated"] for row in files) or diff.get("stdout_truncated")),
                    "baseline_commit": meta.get("baseline_commit"), "source_snapshot_sha256": meta.get("source_snapshot_sha256"),
                   "diff": diff, "test": test,
                    "current_tree_test_passed": test.get("state") == "tested" and test.get("exit_code") == 0 and test.get("tree_sha256") == before,
                   "evidence_source": "host-read-candidate-and-private-sandbox-receipt"}
        durable(validations / (identifier + ".snapshot.json"), package)
        return package
    if operation == "review_started":
        snapshot = private_json(validations / (identifier + ".snapshot.json"))
        if (not re.fullmatch(r"review-[0-9a-f-]{36}", str(args.get("review_id", ""))) or
                args.get("tree_sha256") != snapshot.get("tree_sha256") or args.get("tree_sha256") != tree_hash()):
            raise ValueError("review_snapshot_conflict")
        durable(validations / (identifier + ".review.json"), {"state": "pending", "review_id": args["review_id"],
                  "tree_sha256": args["tree_sha256"], "work_id": identifier, "created_at": time.time()})
        return {"state": "recorded", "review_id": args["review_id"]}
    if operation == "review_receipt":
        value = args.get("receipt")
        if (not isinstance(value, dict) or value.get("work_id") != identifier or
                not re.fullmatch(r"review-[0-9a-f-]{36}", value.get("review_id", "")) or
                value.get("decision") not in {"approve", "changes", "block", "unstructured"}):
            raise ValueError("invalid_review_receipt")
        snapshot = private_json(validations / (identifier + ".snapshot.json"))
        prior = private_json(validations / (identifier + ".review.json"))
        if prior.get("review_id") != value["review_id"]:
            return {"state": "superseded", "reason": "newer_review_preserved", "review_id": value["review_id"]}
        current = tree_hash()
        matching = value.get("tree_sha256") == current == snapshot.get("tree_sha256")
        complete = snapshot.get("current_tree_test_passed") and not snapshot.get("contents_truncated")
        receipt = {**value, "state": "reviewed" if matching and complete else "stale" if not matching else "incomplete",
                   "created_at": time.time(), "snapshot_matches_current_tree": matching, "evidence_complete": bool(complete)}
        # Later changes/block/failed-completeness invalidates old approval too.
        durable(validations / (identifier + ".review.json"), receipt)
        return {"state": "recorded", "review_state": receipt["state"], "review_id": receipt["review_id"],
                "decision": receipt["decision"], "tree_sha256": current, "test_and_review_only": True}
    if operation in {"diff", "commit"}:
        if operation == "commit":
            receipt = validations / (identifier + ".json")
            proof = private_json(receipt)
            if proof.get("state") != "tested" or proof.get("exit_code") != 0 or proof.get("tree_sha256") != tree_hash():
                return {"state": "blocked", "reason": "current_tree_has_no_successful_sandbox_test"}
            review_path = validations / (identifier + ".review.json")
            try:
                review = private_json(review_path)
            except (OSError, ValueError):
                review = {}
            if (review.get("state") != "reviewed" or review.get("decision") != "approve"
                    or review.get("tree_sha256") != tree_hash()):
                return {"state": "blocked", "reason": "current_tree_has_no_matching_gpt_review"}
            metadata = read_private(base.parent / "development-records" / (identifier + ".json"))
            acceptance = metadata.get("acceptance") or {}
            if (acceptance.get("decision") != "accept" or acceptance.get("tree_sha256") != tree_hash()
                    or acceptance.get("review_id") != review.get("review_id")):
                return {"state": "blocked", "reason": "current_tree_has_no_soyo_author_acceptance"}
        if not (root / ".git").is_dir():
            initialized = git("init", "-q")
            if initialized["exit_code"] != 0:
                return initialized
        if operation == "diff":
            return git("diff", "--no-ext-diff", "--no-textconv", "--stat")
        added = git("add", "--", ".")
        if added["exit_code"] != 0:
            return added
        message = str(args.get("message") or "Action brain candidate").replace("\n", " ")[:120]
        result = git("-c", "user.name=Action brain", "-c", "user.email=action@example.invalid", "commit", "-qm", message)
        if result["exit_code"] == 0:
            result["commit"] = git("rev-parse", "HEAD")["stdout"].strip()
            result["review_id"] = review["review_id"]
            result["note"] = "Local candidate commit with matching sandbox test/GPT review; not author acceptance, push or production deployment."
            durable(validations / (identifier + ".commit.json"), {"state": "committed", "commit": result["commit"],
                "tree_sha256": tree_hash(), "review_id": review["review_id"], "created_at": time.time()})
        return result
    raise ValueError("unsupported_development_operation")


def call(config, args):
    identifier = args.get("work_id", "")
    if not re.fullmatch(r"action-[0-9a-f-]{36}", identifier): raise ValueError("invalid_work_identity")
    if args.get("operation") == "inspect": return inspect_work(config, identifier, args.get("_parent_session"))
    base = Path(config["development_home"]).resolve()
    locks = base.parent / "development-locks"; locks.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = open_private(locks / (identifier + ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        ledger = WorkLedger(config, identifier, args.get("_parent_session"))
        operation = args.get("operation")
        mutates = operation in {"import", "baseline", "write", "test", "commit", "review_started", "review_receipt", "author_decision", "publish", "rollback"}
        op_path, fingerprint, prior = ledger.operation(args) if mutates else (None, None, None)
        if prior is not None: return {**prior, "duplicate": True}
        if "expected_revision" in args: ledger.check(args["expected_revision"])
        if mutates: ledger.begin_operation(operation, op_path, fingerprint)
        if operation == "projects":
            return {"state": "observed", "projects": [{"id": row["id"], "label": row.get("label", row["id"]),
                    "paths": row.get("paths", [])} for row in config.get("development_projects", []) if row.get("enabled", True)]}
        if operation == "status":
            return {"state": "observed", "work": ledger.value,
                    "test": read_private(base.parent / "development-validations" / (identifier + ".json")),
                    "review": read_private(base.parent / "development-validations" / (identifier + ".review.json"))}
        if operation in {"publish", "publication_status", "rollback"}:
            fingerprint_tree = lambda: _call(config, {"work_id": identifier, "operation": "fingerprint"})["tree_sha256"]
            result = (development_release.publish(config, ledger, args, fingerprint_tree) if operation == "publish" else
                      development_release.rollback(config, ledger, args) if operation == "rollback" else development_release.inspect(config, ledger))
            if operation != "publication_status" and result.get("state") in {"release_selected", "rollback_selected"}:
                result["revision"] = ledger.value["revision"] + 1
                ledger.commit_operation(operation, result, op_path, fingerprint, publication=result["publication"])
            elif operation != "publication_status" and result.get("state") != "unknown":
                ledger.settle_operation(op_path, fingerprint, result)
            return result
        if operation == "author_decision":
            if args.get("_role_decision") is not True or not args.get("_parent_session"):
                raise ValueError("native_author_decision_required")
            ledger.check(args.get("expected_revision"))
            decision = args.get("decision"); reason = args.get("reason")
            if decision not in {"accept", "changes", "reject"} or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
                raise ValueError("bounded_author_decision_required")
            current = _call(config, {"work_id": identifier, "operation": "fingerprint"})["tree_sha256"]
            review = read_private(base.parent / "development-validations" / (identifier + ".review.json"))
            test = read_private(base.parent / "development-validations" / (identifier + ".json"))
            if decision == "accept" and (review.get("state") != "reviewed" or review.get("decision") != "approve" or
                    review.get("tree_sha256") != current or test.get("state") != "tested" or
                    test.get("tree_sha256") != current or test.get("exit_code") != 0):
                result = {"state": "blocked", "reason": "current_candidate_test_review_not_accepted"}
                ledger.settle_operation(op_path, fingerprint, result)
                return result
            acceptance = {"decision": decision, "reason": reason.strip(), "tree_sha256": current,
                          "review_id": review.get("review_id"), "author_session": args["_parent_session"],
                          "native_call_id": args.get("_call_id"), "native_turn": args.get("_turn"), "created_at": time.time()}
            result = {"state": "recorded", "work_id": identifier, "decision": decision,
                      "revision": ledger.value["revision"] + 1, "production_published": False}
            ledger.commit_operation(operation, result, op_path, fingerprint, acceptance=acceptance)
            return result
        result = _call(config, args)
        if mutates and result.get("state") not in {"blocked", "failed", "unverified", "superseded"}:
            changes = {}
            if operation == "import": changes.update(project_id=result["project_id"], base_revision=result["base_revision"],
                source_manifest=result["source_manifest"], source_snapshot_sha256=result["snapshot_sha256"])
            if operation in {"import", "write", "baseline", "review_started", "review_receipt"}: changes["acceptance"] = None
            if operation == "baseline": changes["baseline_commit"] = result.get("baseline_commit")
            if operation == "commit": changes["commit"] = result.get("commit")
            result["revision"] = ledger.value["revision"] + 1
            ledger.commit_operation(operation, result, op_path, fingerprint, **changes)
        else:
            result.setdefault("revision", ledger.value["revision"])
            if mutates: ledger.settle_operation(op_path, fingerprint, result)
        return result
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    args = json.loads(sys.stdin.buffer.read(128 * 1024))
    try:
        result = call(config, args)
    except Exception as error:
        code = str(error)
        result = {"state": "failed", "reason": code if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,120}", code) else type(error).__name__,
                  "effect_not_confirmed": True, "automatic_replay": False}
    print(json.dumps(result, ensure_ascii=False))
