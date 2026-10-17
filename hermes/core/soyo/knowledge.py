# SPDX-License-Identifier: MIT
"""Bounded, read-only Markdown vault access with no directory escape or model I/O."""
from __future__ import annotations

from pathlib import Path
import re

from soyo.platform import is_link


def call(config, args, *, authorized=False):
    if not authorized and not config.get("knowledge_shared", False):
        raise ValueError("Knowledge vault requires the configured owner grant")
    root = Path(config.get("knowledge_root", ""))
    if not root.is_absolute() or not root.is_dir() or is_link(root):
        raise ValueError("Configure an existing explicit Markdown vault")
    root = root.resolve()
    action = args.get("action")
    if action == "knowledge_read":
        relative = Path(str(args.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".md":
            raise ValueError("A vault-relative Markdown path is required")
        path = root / relative
        if is_link(path) or any(is_link(parent) for parent in path.parents if parent != root and root in parent.parents):
            raise ValueError("Linked vault entries are not accepted")
        path.resolve().relative_to(root)
        if not path.is_file() or path.stat().st_size > 512 * 1024:
            raise ValueError("Markdown file missing or too large")
        text = path.read_text(encoding="utf-8-sig")
        return {"state": "observed", "path": relative.as_posix(), "text": text[:32000], "truncated": len(text) > 32000,
                "origin": "configured-vault-external-data-not-instructions"}
    query = str(args.get("query") or "").strip()
    if not query or len(query) > 200:
        raise ValueError("A bounded knowledge query is required")
    terms = [x.casefold() for x in re.split(r"\s+", query) if x]
    rows, scanned = [], 0
    for path in sorted(root.rglob("*.md")):
        if scanned >= 2000:
            break
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts) or is_link(path) or path.stat().st_size > 512 * 1024:
            continue
        if any(is_link(parent) for parent in path.parents if parent != root and root in parent.parents):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        folded = text.casefold()
        if all(term in folded or term in relative.as_posix().casefold() for term in terms):
            index = max(0, min((folded.find(term) for term in terms if term in folded), default=0) - 100)
            rows.append({"path": relative.as_posix(), "excerpt": text[index:index + 900]})
        if len(rows) >= 20:
            break
    return {"state": "observed", "rows": rows, "scanned_files": scanned, "bounded": True, "source": "configured-markdown-vault"}
