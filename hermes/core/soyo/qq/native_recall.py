# SPDX-License-Identifier: GPL-3.0-only
"""Bounded, source-aware candidate recall for the native QQ memory surface.

This module is deliberately a *candidate* retriever.  It never decides that a
fact is true, that a conflict exists, or that a candidate should be mentioned.
Those semantic decisions remain with the cognition/character models.  SQLite
substring and token matching only narrow a bounded, scope-checked pool.

The native corpus remains authoritative.  Every candidate keeps enough source
identity for the Host and model to distinguish current corpus material,
source-bound cognition, summaries, and legacy imports.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict

try:
    from . import native_cognition
except ImportError:  # pragma: no cover - native Host subprocess import
    import native_cognition


DEFAULT_SURFACE_BUDGET = 48000
MIN_SURFACE_BUDGET = 4000
MAX_SURFACE_BUDGET = 160000
RECENT_MAX_ITEMS = 40
ASSISTANT_MAX_ITEMS = 12
RECENT_ITEM_CHARS = 1600
ASSISTANT_ITEM_CHARS = 1600
MAX_QUERY_CHARS = 240
MAX_CANDIDATE_CHARS = 1100
MAX_CANDIDATES = 48

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{1,31}|\d{2,}")
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")

# Candidate source weights affect ordering only.  They do not make a source
# authoritative over another source, and they are intentionally modest so a
# relevant lower-volume source can survive round-robin selection.
SOURCE_WEIGHT = {
    "cognition": 1.00,
    "episode": 0.86,
    "workflow": 0.74,
    "fact": 0.92,
    "summary": 0.84,
    "knowledge": 0.52,
    "turn": 0.78,
    "corpus": 0.68,
}
SOURCE_ORDER = ("cognition", "episode", "workflow", "fact", "summary", "knowledge", "turn", "corpus")
SOURCE_LIMIT = {"cognition": 12, "episode": 8, "workflow": 8, "fact": 8, "summary": 5, "knowledge": 8, "turn": 8, "corpus": 8}
GRAPH_RELATIONS = frozenset({"related", "related_to", "supports", "abstracts_from"})
MAX_GRAPH_EDGES = 24


def _terms(value: str, limit: int = 32) -> list[str]:
    """Return a small deterministic term set suitable for candidate recall."""
    value = str(value or "").strip().casefold()[:MAX_QUERY_CHARS]
    if not value:
        return []
    result: list[str] = []
    seen: set[str] = set()

    def add(term: str):
        term = term.strip().casefold()
        if len(term) < 2 or term in seen:
            return
        seen.add(term)
        result.append(term)

    for word in _WORD_RE.findall(value):
        add(word)
    for chunk in _CJK_RE.findall(value):
        if len(chunk) == 1:
            add(chunk)
        else:
            for index in range(len(chunk) - 1):
                add(chunk[index:index + 2])
    return result[:limit]


def _text(value: str, limit: int = MAX_CANDIDATE_CHARS) -> str:
    return " ".join(str(value or "").split())[:limit]


def _safe_json(value, default):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _recency(stamp, now: float, half_life_days: float = 30.0) -> float:
    try:
        age = max(0.0, (now - float(stamp or now)) / 86400.0)
    except (TypeError, ValueError):
        age = 0.0
    return math.pow(0.5, age / half_life_days)


def _lexical(query_terms: list[str], *values: str) -> float:
    if not query_terms:
        return 0.0
    haystack = " ".join(str(value or "") for value in values).casefold()
    hits = sum(1 for term in query_terms if term in haystack)
    if not hits:
        return 0.0
    return min(1.0, hits / max(1, len(query_terms)))


def _candidate(source: str, candidate_id: str, *, kind: str, text: str,
               scope: str, relevance: float, provenance: str,
               source_seqs=None, source_events=None, key="", status="",
               metadata=None) -> dict:
    value = {
        "candidate_id": str(candidate_id),
        "source": source,
        "kind": kind,
        "key": _text(key, 180),
        "text": _text(text),
        "scope": scope,
        "source_seqs": sorted({int(seq) for seq in (source_seqs or []) if type(seq) is int and seq > 0}),
        "source_events": [str(item)[:180] for item in (source_events or []) if item][:8],
        "provenance": provenance,
        "relevance": round(max(0.0, min(1.0, float(relevance))), 4),
    }
    if status:
        value["status"] = status
    if metadata:
        value["metadata"] = metadata
    return value


def _scopes(domain: str, routes: list[str]) -> list[str]:
    values = [domain]
    if domain == native_cognition.OWNER:
        values += [route for route in routes if route != domain]
    return sorted(set(values))


def _source_routes(config: dict, route: str) -> tuple[str, list[str]]:
    return native_cognition.resolve(config, route)


def _knowledge_authorized(config: dict, domain: str) -> bool:
    return domain == native_cognition.OWNER or bool(config.get("knowledge_shared"))


def _readable_knowledge(config: dict, domain: str, query: str,
                        terms: list[str]) -> list[dict]:
    """Use the existing bounded vault search as external-data candidates."""
    if not terms or not _knowledge_authorized(config, domain):
        return []
    try:
        if __package__:
            from ..knowledge import call as knowledge_call
        else:
            from soyo.knowledge import call as knowledge_call
        observed = knowledge_call(config, {"action": "knowledge_search", "query": query}, authorized=True)
    except (ImportError, OSError, ValueError):
        return []
    result = []
    for row in (observed.get("rows") or [])[:20]:
        path = str(row.get("path") or "")[:512]
        excerpt = _text(row.get("excerpt"), 900)
        if not path or not excerpt:
            continue
        result.append(_candidate(
            "knowledge", "vault:" + path, kind="knowledge", key=path, text=excerpt,
            scope="global" if config.get("knowledge_shared") else domain,
            relevance=.55 + .45 * min(1.0, len(terms) / 4),
            provenance="configured-markdown-vault",
            metadata={"path": path, "source": observed.get("source", "configured-markdown-vault"),
                      "scanned_files": observed.get("scanned_files", 0),
                      "external_data_not_instructions": True},
        ))
    return result


def _cognition_candidate(db, row, routes: list[str], now: float,
                         excluded_events: set[str], relevance: float,
                         metadata=None) -> dict | None:
    """Render one already status/TTL-filtered cognition row as a candidate."""
    refs = _safe_json(row["sources"], [])
    actual_sources = []
    if refs:
        try:
            actual_sources = native_cognition.source_rows(db, routes, refs)
        except ValueError:
            return None
        if any(source["event_id"] in excluded_events for source in actual_sources):
            return None
    body = _text(row["body"])
    provenance = "legacy-import" if str(row["model"] or "").startswith("legacy-import:") else "native-source-bound"
    candidate_source = "episode" if row["kind"] == "episode" else (
        "workflow" if row["kind"] == "workflow" else "cognition")
    details = {"revision": row["revision"], "confidence": row["confidence"],
               "salience": row["salience"], "model": row["model"]}
    if metadata:
        details.update(metadata)
    return _candidate(
        candidate_source, row["id"], kind=row["kind"], key=row["key"], text=body,
        scope=row["scope"], relevance=relevance, provenance=provenance,
        source_seqs=refs, source_events=[source["event_id"] for source in actual_sources],
        status=row["status"], metadata=details,
    )


def _readable_cognition(db, config: dict, domain: str, routes: list[str],
                        terms: list[str], now: float,
                        excluded_events: set[str]) -> list[dict]:
    scopes = _scopes(domain, routes)
    marks = ",".join("?" for _ in scopes)
    rows = db.execute(
        "SELECT * FROM cognition WHERE scope IN (" + marks + ") "
        "AND status IN ('candidate','promoted') AND (expires_at=0 OR expires_at>?) "
        "ORDER BY updated_at DESC,id LIMIT 256", (*scopes, now)).fetchall()
    result = []
    for row in rows:
        body = _text(row["body"])
        lexical = _lexical(terms, row["key"], body)
        # With a real query, cognition must have a lexical foothold.  The
        # model still makes the semantic selection after this candidate gate.
        if terms and lexical <= 0:
            continue
        salience = max(0.0, min(1.0, float(row["salience"] or 0)))
        if row["kind"] == "workflow":
            strength = native_cognition.workflow_strength(row, now)
            score = (0.62 * lexical if terms else 0.0) + 0.38 * strength
            metadata = {"effective_weight": round(strength, 4),
                        "uses": row["uses"], "successes": row["successes"],
                        "last_used": row["last_used"]}
        else:
            score = (0.62 * lexical if terms else 0.0) + 0.22 * salience + 0.16 * _recency(row["updated_at"], now)
            metadata = None
        candidate = _cognition_candidate(db, row, routes, now, excluded_events, score, metadata)
        if candidate:
            result.append(candidate)
    return result


def _graph_expand(db, domain: str, routes: list[str], seeds: list[dict],
                  now: float, excluded_events: set[str]) -> list[dict]:
    """Expand active cognition/episode seeds by one approved graph edge."""
    seed_ids = [item["candidate_id"] for item in seeds
                if item.get("source") in {"cognition", "episode"}]
    if not seed_ids:
        return []
    seed_ids = list(dict.fromkeys(seed_ids))[:MAX_GRAPH_EDGES]
    source_marks = ",".join("?" for _ in seed_ids)
    relation_marks = ",".join("?" for _ in GRAPH_RELATIONS)
    edges = db.execute(
        "SELECT src_id,dst_id,relation,weight FROM memory_edges "
        "WHERE src_id IN (" + source_marks + ") AND relation IN (" + relation_marks + ") "
        "ORDER BY weight DESC,id LIMIT ?",
        (*seed_ids, *sorted(GRAPH_RELATIONS), MAX_GRAPH_EDGES),
    ).fetchall()
    if not edges:
        return []
    target_ids = list(dict.fromkeys(str(row["dst_id"]) for row in edges))
    scope_values = _scopes(domain, routes)
    scope_marks = ",".join("?" for _ in scope_values)
    target_marks = ",".join("?" for _ in target_ids)
    rows = db.execute(
        "SELECT * FROM cognition WHERE id IN (" + target_marks + ") "
        "AND scope IN (" + scope_marks + ") AND status IN ('candidate','promoted') "
        "AND (expires_at=0 OR expires_at>?)", (*target_ids, *scope_values, now),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    result = []
    seen = set()
    for edge in edges:
        target_id = str(edge["dst_id"])
        row = by_id.get(target_id)
        if not row or target_id in seen or target_id in seed_ids:
            continue
        seen.add(target_id)
        try:
            edge_weight = max(0.0, min(1.0, float(edge["weight"] or 0)))
        except (TypeError, ValueError):
            edge_weight = 0.0
        salience = max(0.0, min(1.0, float(row["salience"] or 0)))
        relevance = .45 * edge_weight + .35 * salience + .20 * _recency(row["updated_at"], now)
        candidate = _cognition_candidate(
            db, row, routes, now, excluded_events, relevance,
            {"graph_expanded": True, "graph_hops": 1, "graph_seed": str(edge["src_id"]),
             "edge_relation": edge["relation"], "edge_weight": edge_weight},
        )
        if candidate:
            result.append(candidate)
    return result


def _readable_facts(db, domain: str, routes: list[str], terms: list[str], now: float) -> list[dict]:
    scopes = list(dict.fromkeys([domain, "global", *_scopes(domain, routes)]))
    marks = ",".join("?" for _ in scopes)
    rows = db.execute(
        "SELECT f.scope,f.key,f.value,f.source FROM facts f WHERE f.scope IN (" + marks + ") "
        "AND NOT EXISTS (SELECT 1 FROM fact_revisions r WHERE r.scope=f.scope AND r.key=f.key "
        "AND r.id=(SELECT MAX(v.id) FROM fact_revisions v WHERE v.scope=f.scope AND v.key=f.key) "
        "AND r.expires_at>0 AND r.expires_at<=?) LIMIT 256", (*scopes, now)).fetchall()
    result = []
    for row in rows:
        lexical = _lexical(terms, row["key"], row["value"])
        if terms and lexical <= 0:
            continue
        score = (0.68 * lexical if terms else 0.0) + 0.32 * SOURCE_WEIGHT["fact"]
        provenance = "legacy-import" if str(row["source"] or "").startswith("legacy:") else "native-fact"
        result.append(_candidate(
            "fact", row["scope"] + ":" + row["key"], kind="fact", key=row["key"], text=row["value"],
            scope=row["scope"], relevance=score, provenance=provenance,
            metadata={"source": row["source"]},
        ))
    return result


def _readable_summaries(db, domain: str, routes: list[str], terms: list[str], now: float,
                        excluded_events: set[str]) -> list[dict]:
    # Summaries are stored in the durable domain.  A source check against the
    # actual route list prevents an imported/incorrect route from leaking.
    rows = db.execute(
        "SELECT id,route,summary,participants,created_at,source_seq,source_seqs "
        "FROM summaries WHERE route=? AND source_seq>0 ORDER BY id DESC LIMIT 96", (domain,)).fetchall()
    result = []
    for row in rows:
        refs = _safe_json(row["source_seqs"], []) or ([row["source_seq"]] if row["source_seq"] else [])
        try:
            actual_sources = native_cognition.source_rows(db, routes, refs)
        except ValueError:
            continue
        if any(source["event_id"] in excluded_events for source in actual_sources):
            continue
        lexical = _lexical(terms, row["summary"], row["participants"])
        if terms and lexical <= 0:
            continue
        score = (0.60 * lexical if terms else 0.0) + 0.40 * _recency(row["created_at"], now, 45.0)
        result.append(_candidate(
            "summary", "summary:" + str(row["id"]), kind="summary", key="summary:" + str(row["id"]),
            text=row["summary"], scope=domain, relevance=score, provenance="native-source-bound",
            source_seqs=refs, source_events=[source["event_id"] for source in actual_sources],
            metadata={"participants": _safe_json(row["participants"], [])[:16]},
        ))
    return result


def _readable_turns(db, routes: list[str], terms: list[str], now: float,
                    excluded_events: set[str]) -> list[dict]:
    marks = ",".join("?" for _ in routes)
    rows = db.execute(
        "SELECT id,route,role,sender,event_id,content,occurred_at FROM turns WHERE route IN (" + marks + ") "
        "ORDER BY occurred_at DESC,id DESC LIMIT 128", routes).fetchall()
    result = []
    for row in rows:
        if str(row["event_id"] or "") in excluded_events:
            continue
        recalled = db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'",
                              (row["route"], row["event_id"])).fetchone()
        if recalled:
            continue
        lexical = _lexical(terms, row["content"])
        if terms and lexical <= 0:
            continue
        score = (0.64 * lexical if terms else 0.0) + 0.36 * _recency(row["occurred_at"], now, 14.0)
        result.append(_candidate(
            "turn", "turn:" + str(row["id"]), kind=row["role"], key=row["event_id"], text=row["content"],
            scope=row["route"], relevance=score, provenance="native-turn",
            source_events=[row["event_id"]], metadata={"sender": row["sender"], "occurred_at": row["occurred_at"]},
        ))
    return result


def _readable_corpus(db, routes: list[str], terms: list[str], now: float,
                     excluded_events: set[str]) -> list[dict]:
    marks = ",".join("?" for _ in routes)
    rows = db.execute(
        "SELECT seq,route,body FROM messages WHERE route IN (" + marks + ") "
        "AND COALESCE(json_extract(body,'$.historical'),0)=0 "
        "ORDER BY seq DESC LIMIT 256", routes).fetchall()
    result = []
    for row in rows:
        try:
            value = json.loads(row["body"])
        except (TypeError, ValueError):
            continue
        event_id = str(value.get("event_id") or "")
        if not event_id or event_id in excluded_events:
            continue
        if db.execute("SELECT 1 FROM message_flags WHERE route=? AND event_id=? AND flag='recalled'",
                      (row["route"], event_id)).fetchone():
            continue
        text = _text(value.get("text"))
        lexical = _lexical(terms, text)
        if terms and lexical <= 0:
            continue
        score = (0.58 * lexical if terms else 0.0) + 0.42 * _recency(value.get("occurred_at"), now, 21.0)
        result.append(_candidate(
            "corpus", "message:" + str(row["seq"]), kind="episode-candidate", key=event_id, text=text,
            scope=row["route"], relevance=score, provenance="native-corpus",
            source_seqs=[row["seq"]], source_events=[event_id],
            metadata={"sender": value.get("sender_id"), "occurred_at": value.get("occurred_at")},
        ))
    return result


def _dedupe(candidates: list[dict]) -> list[dict]:
    chosen: dict[tuple, dict] = {}
    for item in candidates:
        # Facts and cognition facts with the same identity are one semantic
        # candidate.  Keep the richer/source-bound representation when present.
        family = "semantic" if item["source"] in {"fact", "cognition", "episode", "workflow"} else item["source"]
        identity = (family, item.get("kind", ""), item.get("key", ""), item.get("scope", ""))
        old = chosen.get(identity)
        if old is None or (item["source"] == "cognition" and old["source"] != "cognition") or item["relevance"] > old["relevance"]:
            chosen[identity] = item
    return list(chosen.values())


def collect(db, config: dict, route: str, query: str = "", now: float | None = None,
            *, budget_chars: int | None = None, excluded_events=None) -> dict:
    """Collect a bounded, scope-filtered candidate set for one QQ turn."""
    now = time.time() if now is None else now
    budget = max(MIN_SURFACE_BUDGET, min(MAX_SURFACE_BUDGET, int(
        budget_chars or config.get("memory_surface_budget_chars", DEFAULT_SURFACE_BUDGET))))
    query = str(query or "")[:MAX_QUERY_CHARS]
    terms = _terms(query)
    domain, routes = _source_routes(config, route)
    excluded_events = set(str(value) for value in (excluded_events or []) if value)
    # An absent/empty current input is not a license to inject the newest
    # memories from every source.  Recent scene material is assembled by the
    # caller separately; semantic candidates require an actual query foothold.
    if not terms:
        return {"query": query, "terms": [], "domain": domain, "routes": routes,
                "candidates": [], "candidate_count": 0, "available_candidates": 0,
                "budget_chars": budget, "used_chars": 0, "truncated": False}
    candidates = []
    candidates += _readable_cognition(db, config, domain, routes, terms, now, excluded_events)
    candidates += _readable_facts(db, domain, routes, terms, now)
    candidates += _readable_summaries(db, domain, routes, terms, now, excluded_events)
    candidates += _readable_knowledge(config, domain, query, terms)
    candidates += _readable_turns(db, routes, terms, now, excluded_events)
    candidates += _readable_corpus(db, routes, terms, now, excluded_events)
    candidates = _dedupe(candidates)
    seeds = list(candidates)
    candidates += _graph_expand(db, domain, routes, seeds, now, excluded_events)
    candidates = _dedupe(candidates)
    for item in candidates:
        item["relevance"] = round(item["relevance"] * SOURCE_WEIGHT.get(item["source"], .5), 4)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        grouped[item["source"]].append(item)
    for items in grouped.values():
        items.sort(key=lambda value: (-value["relevance"], value["candidate_id"]))

    # Round-robin across source classes prevents a large cognition/fact table
    # from consuming the entire surface before episodic/current candidates get
    # a chance to be considered.
    selected: list[dict] = []
    used = 0
    positions = defaultdict(int)
    while len(selected) < MAX_CANDIDATES:
        progressed = False
        for source in SOURCE_ORDER:
            items = grouped.get(source, [])
            index = positions[source]
            if index >= min(SOURCE_LIMIT[source], len(items)):
                continue
            item = items[index]
            positions[source] += 1
            cost = len(item["text"]) + len(item.get("key", "")) + 260
            if used + cost > budget:
                continue
            selected.append(item)
            used += cost
            progressed = True
            if len(selected) >= MAX_CANDIDATES:
                break
        if not progressed:
            break
    selected.sort(key=lambda value: (-value["relevance"], SOURCE_ORDER.index(value["source"])))
    available = sum(min(SOURCE_LIMIT[source], len(grouped.get(source, []))) for source in SOURCE_ORDER)
    return {"query": query, "terms": terms, "domain": domain, "routes": routes,
            "candidates": selected, "candidate_count": len(selected),
            "available_candidates": available, "budget_chars": budget,
            "used_chars": used, "truncated": available > len(selected)}


def _clip(value, limit):
    if isinstance(value, str):
        return _text(value, limit)
    if isinstance(value, dict):
        return {str(key): _clip(item, max(80, limit // 2)) for key, item in list(value.items())[:32]}
    if isinstance(value, list):
        return [_clip(item, limit) for item in value[:32]]
    return value


def _surface_candidate(item: dict) -> dict:
    """Keep candidate identity while bounding nested metadata for prompt use."""
    value = {
        "candidate_id": str(item.get("candidate_id") or "")[:180],
        "source": str(item.get("source") or "")[:32],
        "kind": str(item.get("kind") or "")[:48],
        "key": _text(item.get("key"), 180),
        "text": _text(item.get("text"), 700),
        "scope": str(item.get("scope") or "")[:180],
        "source_seqs": [seq for seq in item.get("source_seqs", [])[:16] if type(seq) is int and seq > 0],
        "source_events": [str(event)[:180] for event in item.get("source_events", [])[:8]],
        "provenance": str(item.get("provenance") or "")[:64],
        "relevance": item.get("relevance", 0),
    }
    if item.get("status"):
        value["status"] = str(item["status"])[:32]
    if item.get("metadata"):
        value["metadata"] = _clip(item["metadata"], 600)
    return value


def build_surface(recall: dict, *, recent=None, assistant_recent=None,
                  reply_context=None, commitments=None, self_state=None,
                  people=None, emotions=None, scene_state=None) -> dict:
    """Build the compact prompt surface consumed by the QQ Host hook."""
    surface_budget = max(MIN_SURFACE_BUDGET, min(MAX_SURFACE_BUDGET,
        int(recall.get("budget_chars") or DEFAULT_SURFACE_BUDGET)))
    candidates = recall.get("candidates", [])
    recent_events = {str(item.get("event_id") or "") for item in (recent or []) if item.get("event_id")}
    result = {
        "query": recall.get("query", ""),
        "domain": recall.get("domain"),
        "candidates": [],
        "recent": [],
        "assistant_recent": [],
        "reply_context": _clip(reply_context or {"state": "not_requested"}, 1800),
        "commitments": _clip(commitments or [], 700),
        "self_state": _clip(self_state or [], 700),
        "people": _clip(people or [], 700),
        "emotions": _clip(emotions or [], 500),
        "scene_state": _clip(scene_state or {}, 400),
        "source_budget_chars": surface_budget,
        "candidate_count": 0,
        "truncated": bool(recall.get("truncated")),
    }
    # Keep the whole provided recent window, newest last.  The caller already
    # bounds how many raw messages it reads; dropping them again here threw
    # away conversation the model had every right to see.
    for item in list(recent or [])[-RECENT_MAX_ITEMS:]:
        compact = {key: item.get(key) for key in ("route_id", "event_id", "sender_id", "text", "occurred_at") if key in item}
        compact["text"] = _text(compact.get("text"), RECENT_ITEM_CHARS)
        result["recent"].append(compact)
    for item in list(assistant_recent or [])[-ASSISTANT_MAX_ITEMS:]:
        compact = {key: item.get(key) for key in ("role", "sender", "event_id", "content", "occurred_at") if key in item}
        compact["content"] = _text(compact.get("content"), ASSISTANT_ITEM_CHARS)
        result["assistant_recent"].append(compact)

    def encoded_len():
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    def fold_oldest(key, text_key, digest_key):
        """Fold the oldest rows into a digest instead of deleting them silently."""
        digest = {"omitted": 0, "preview": []}
        while len(result[key]) > 1 and encoded_len() > surface_budget:
            oldest = result[key].pop(0)
            digest["omitted"] += 1
            if len(digest["preview"]) < 8:
                digest["preview"].append({"sender_id": oldest.get("sender_id"),
                                          "text": _text(oldest.get(text_key), 140)})
        if digest["omitted"]:
            result[digest_key] = digest
            result["truncated"] = True

    fold_oldest("recent", "text", "recent_digest")
    # Add candidates only while the serialized prompt surface remains within
    # the hard budget.  This measures the actual JSON representation rather
    # than an optimistic text-only estimate, so metadata cannot silently make
    # the prompt exceed the contract.
    for item in candidates:
        # A recent raw source is already represented in the bounded recent
        # window.  Keep richer cognition/summary candidates, but do not emit
        # the same corpus event a second time under another source label.
        if item.get("source") == "corpus" and recent_events.intersection(item.get("source_events", [])):
            continue
        result["candidates"].append(_surface_candidate(item))
        if encoded_len() > surface_budget:
            result["candidates"].pop()
            result["truncated"] = True
            break

    fold_oldest("assistant_recent", "content", "assistant_digest")
    # Last resort: shed re-fetchable semantic candidates, then fixed background
    # fields.  The raw recent window keeps a digest instead of disappearing.
    while encoded_len() > surface_budget and result["candidates"]:
        result["candidates"].pop()
        result["truncated"] = True
    if encoded_len() > surface_budget:
        result["reply_context"] = {"state": "bounded_out"}
        result["commitments"] = []
        result["self_state"] = []
        result["people"] = []
        result["emotions"] = []
        result["scene_state"] = {}
        result["truncated"] = True
    result["candidate_count"] = len(result["candidates"])
    result["used_chars"] = encoded_len()
    return result
