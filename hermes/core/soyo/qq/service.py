# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Injected QQ worker: durable input and attempt-scoped, non-repeating sends.

No listener, thread, model, HTTP client or WebSocket is started here.  The
future host owns scheduling and timeouts; this staging worker owns its journal.
"""

from __future__ import annotations

import functools
import hashlib
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Optional

from .contracts import ChannelRoute, InboundDecision, InboundEnvelope, OutboundIntent, Receipt, bounded_id, qq_id
from .host import HostPort, OutboxClaim, PlatformPort, PortResult, extract_claims
from .inbound import MEDIA_MODES, SeenLRU, classify_onebot_event
from .journal import Counters, SoyoQQJournal, identity_digest
from .outbound import OutboundPlanError, build_outbound_plan, build_outbound_plans, classify_send_response


MAX_EVENT_TRIES = 10
MAX_RECEIPT_TRIES = 20
MAX_SPOOL_ITEMS_PER_CALL = 32


def _serialized(method: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(method)
    def call(self: "SoyoQQChannel", *args: Any, **kwargs: Any) -> Any:
        with self._worker_lock:
            if self._closed:
                raise RuntimeError("QQ channel is closed")
            return method(self, *args, **kwargs)
    return call


@dataclass(frozen=True)
class ChannelConfig:
    account_id: str
    media_mode: str = "full"
    require_group_mention: bool = True
    chunk_delay_seconds: float = 0.6
    reply_part_chars: int = 1800
    max_reply_parts: int = 64
    attachment_root: str = ""


class SoyoQQChannel:
    """Single writer for one account and one explicit, private data root."""

    def __init__(
        self, *, config: ChannelConfig,
        routes: Mapping[str, ChannelRoute] | Iterable[ChannelRoute],
        data_root: Path | str, journal: Optional[SoyoQQJournal] = None,
        counters: Optional[Counters] = None, seen: Optional[SeenLRU] = None,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        account = qq_id(config.account_id)
        if (not account or config.media_mode not in MEDIA_MODES
                or not isinstance(config.require_group_mention, bool)
                or isinstance(config.chunk_delay_seconds, bool)
                or not isinstance(config.chunk_delay_seconds, (int, float))
                or not 0 <= float(config.chunk_delay_seconds) <= 10
                or isinstance(config.reply_part_chars, bool)
                or not isinstance(config.reply_part_chars, int)
                or not 80 <= config.reply_part_chars <= 10000
                or isinstance(config.max_reply_parts, bool)
                or not isinstance(config.max_reply_parts, int)
                or not 1 <= config.max_reply_parts <= 64):
            raise ValueError("invalid channel account/media mode")
        self.config = ChannelConfig(account, config.media_mode, config.require_group_mention,
                                     float(config.chunk_delay_seconds), config.reply_part_chars,
                                     config.max_reply_parts, str(config.attachment_root or ""))
        self._worker_lock = threading.RLock()
        self._closed = False
        self._now = now_fn
        self.routes = MappingProxyType(self._route_map(routes))
        root = Path(data_root)
        if not root.is_absolute() or (journal is not None and journal.root.resolve() != root.resolve()):
            raise ValueError("data_root must be absolute and match the injected journal")
        self.journal = journal if journal is not None else SoyoQQJournal(root)
        self.counters = counters if counters is not None else Counters()
        # SeenLRU has __len__: an injected empty LRU is not a missing LRU.
        self.seen = seen if seen is not None else SeenLRU()
        self.journal.attach_channel(account)

    def _route_map(self, routes: Mapping[str, ChannelRoute] | Iterable[ChannelRoute]) -> dict[str, ChannelRoute]:
        values = routes.values() if isinstance(routes, Mapping) else routes
        result: dict[str, ChannelRoute] = {}
        targets = set()
        for route in values:
            if not isinstance(route, ChannelRoute) or route.account_id != self.config.account_id:
                raise ValueError("route account/type mismatch")
            target = (route.message_type, route.target_id)
            if route.route_id in result or (route.enabled and target in targets):
                raise ValueError("duplicate or ambiguous route")
            result[route.route_id] = route
            if route.enabled:
                targets.add(target)
        return result

    @_serialized
    def replace_routes(self, routes: Mapping[str, ChannelRoute] | Iterable[ChannelRoute]) -> None:
        """Trusted configuration update; queued input is reauthorized at POST."""

        self.routes = MappingProxyType(self._route_map(routes))

    @_serialized
    def ingest_onebot_event(
        self, event: Any, *, historical: bool = False, expected_route_id: str | None = None,
    ) -> InboundDecision:
        """Spool before caching; failure to persist is never called accepted."""

        if not isinstance(historical, bool):
            raise ValueError("historical must be a trusted boolean")
        routes = self.routes
        if expected_route_id is not None:
            route = routes.get(expected_route_id)
            if route is None:
                return InboundDecision(False, "source_route_missing")
            routes = {route.route_id: route}
        decision = classify_onebot_event(
            event, account_id=self.config.account_id, routes=routes,
            seen=self.seen, media_mode=self.config.media_mode, historical=historical,
        )
        if not decision.accepted or decision.envelope is None:
            self.counters.inc("inbound_" + decision.reason)
            return decision
        envelope = decision.envelope
        added = self.journal.enqueue_inbound(envelope, dict(decision.metadata))
        self.seen.add_if_new((envelope.route_id + ":" + envelope.scene_id, envelope.event_id, int(envelope.occurred_at)))
        if not added:
            self.counters.inc("inbound_duplicate_durable")
            return InboundDecision(False, "duplicate_durable", envelope, decision.metadata)
        self.counters.inc("inbound_spooled")
        return decision

    @_serialized
    def submit_pending_inbound(self, host: HostPort, *, limit: int = MAX_SPOOL_ITEMS_PER_CALL) -> int:
        submitted = 0
        processed = 0
        budget = self._limit(limit)
        for path in self.journal.spool_list("inbound"):
            if processed >= budget:
                break
            blob = self._read_spool(path, "inbound")
            if blob is None or not self._due(blob):
                continue
            processed += 1
            try:
                envelope = InboundEnvelope.from_dict(blob["envelope"])
                if path.name != self.journal.event_key(envelope) + ".json":
                    raise ValueError("inbound identity mismatch")
            except (KeyError, TypeError, ValueError):
                self.journal.quarantine(path, "invalid_inbound")
                self.counters.inc("inbound_unreadable")
                continue
            route = self.routes.get(envelope.route_id)
            if (route is None or route.account_id != envelope.account_id
                    or not route.matches_target(envelope.message_type, envelope.target_id)
                    or not route.accepts_sender(envelope.sender_id)):
                self.journal.append("inbound_rejected", {"reason": "route_revoked", "item": blob})
                self.journal.finish_inbound(path, envelope, "route_revoked")
                self.counters.inc("inbound_rejected")
                continue
            if (envelope.message_type == "group" and self.config.require_group_mention
                    and (envelope.historical or envelope.account_id not in envelope.mentioned_account_ids)):
                # Keep authorized context locally, never POST it for an agent
                # to judge. Quoted replies/@all/plain names are not self @s.
                # Historical @s are context too, not restart reply obligations.
                self.journal.append("inbound_context_only", {"item": blob})
                self.journal.finish_inbound(path, envelope, "context_only")
                self.counters.inc("inbound_context_only")
                continue
            try:
                result = self._host_result(host.post_event(envelope.as_dict()))
            except Exception as error:
                result = PortResult("retry", error=type(error).__name__)
            if result.accepted or result.rejected:
                outcome = "submitted" if result.accepted else "host_rejected"
                self.journal.append("inbound_" + outcome, {
                    "event_id": envelope.event_id, "route_id": envelope.route_id,
                    "result": result.kind, "code": result.code,
                    **({"item": blob} if result.rejected else {}),
                })
                self.journal.finish_inbound(path, envelope, outcome)
                self.counters.inc("inbound_" + outcome)
                submitted += int(result.accepted)
            else:
                self._retry(path, blob, MAX_EVENT_TRIES)
                self.counters.inc("inbound_retries")
        return submitted

    @_serialized
    def process_outbox_claim(self, claim: OutboxClaim, platform: PlatformPort, host: HostPort) -> Receipt:
        """A publication is fenced before sending, including across restart.

        Same attempt: re-report its stored receipt.  Different attempt: UNKNOWN
        without sending.  Explicit retry authorization is not implemented in
        this first slice, and changing an attempt id cannot bypass the fence.
        """

        if not isinstance(claim, OutboxClaim):
            raise ValueError("expected OutboxClaim")
        old = self.journal.read_attempt(claim.publication_id)
        if old is not None:
            saved = self._recover_attempt(old)
            if saved.attempt_id == claim.attempt_id:
                self.counters.inc("outbox_duplicate_attempt")
                self._report_receipt(host, saved, force=True)
                return saved
            receipt = Receipt(claim.publication_id, claim.attempt_id, "unknown", "publication_already_attempted")
            self._report_receipt(host, receipt, force=True)
            self.counters.inc("outbox_fenced_attempt")
            return receipt

        fingerprint = ""
        try:
            # This is a product port shape, NOT a claim about DSH's HTTP schema.
            fingerprint = identity_digest(dict(claim.item))
            intent = self._intent_from_claim(claim)
            route = self.routes.get(intent.route_id)
            if route is None:
                raise OutboundPlanError("route_not_allowed")
            plans = build_outbound_plans(intent, route,
                                         max_chars=self.config.reply_part_chars,
                                         max_parts=self.config.max_reply_parts)
        except (OutboundPlanError, TypeError, ValueError) as error:
            receipt = Receipt(claim.publication_id, claim.attempt_id, "failed",
                              getattr(error, "code", "outbox_shape_reject"))
            self._save_attempt(receipt, fingerprint, phase="complete")
            self._report_receipt(host, receipt)
            self.counters.inc("outbox_failed")
            return receipt

        provisional = Receipt(claim.publication_id, claim.attempt_id, "unknown", "platform_send_interrupted")
        self._save_attempt(provisional, fingerprint, phase="started")
        # If persistence above fails, send is never invoked.  If the process
        # exits anywhere after it, recovery is conservative and never re-sends.
        part_receipts: list[Receipt] = []
        try:
            for index, plan in enumerate(plans):
                if index:
                    time.sleep(self.config.chunk_delay_seconds)
                response = platform.send(plan)
                part_receipts.append(classify_send_response(
                    response, publication_id=claim.publication_id,
                    attempt_id=claim.attempt_id))
                self._save_attempt(Receipt(claim.publication_id, claim.attempt_id, "unknown", "multipart_in_progress",
                    response={"parts": [item.as_dict() for item in part_receipts], "planned_parts": len(plans)}), fingerprint, phase="started")
                if part_receipts[-1].status != "platform_accepted":
                    break
            accepted = [item for item in part_receipts if item.status == "platform_accepted"]
            uncertain = [item for item in part_receipts if item.status == "unknown"]
            failed = [item for item in part_receipts if item.status == "failed"]
            if uncertain or (failed and accepted):
                status = "unknown"
                reason = "partial_platform_uncertain" if accepted else "platform_part_unknown"
            elif failed:
                status = "failed"
                reason = "platform_part_failed"
            else:
                status = "platform_accepted"
                reason = "platform_accepted"
            response = {
                "parts": [item.as_dict() for item in part_receipts],
                "part_count": len(part_receipts),
                "planned_parts": len(plans), "cancelled_parts": len(plans) - len(part_receipts),
            }
            receipt = Receipt(
                claim.publication_id, claim.attempt_id, status, reason,
                platform_message_id=(accepted[-1].platform_message_id if accepted else None),
                response=response,
            )
        except Exception as error:
            receipt = Receipt(claim.publication_id, claim.attempt_id, "unknown", "platform_transport_uncertain",
                              response={"error_type": type(error).__name__, "parts": [item.as_dict() for item in part_receipts],
                                        "planned_parts": len(plans)})
        self._save_attempt(receipt, fingerprint, phase="complete")
        self._report_receipt(host, receipt)
        self.counters.inc("outbox_" + receipt.status)
        return receipt

    @_serialized
    def recover_pending_attempts(self) -> int:
        """Rebuild missing receipt queues from durable fences; no platform port."""

        count = 0
        for path in sorted(self.journal.attempts_root.glob("*.json")):
            record = self.journal.read_json(path)
            if not isinstance(record, dict) or path != self.journal.attempt_path(record.get("publication_id")):
                raise ValueError("corrupt publication fence; refusing recovery")
            receipt = self._recover_attempt(record)
            self.journal.queue_receipt(receipt)
            count += 1
        return count

    @_serialized
    def replay_receipts(self, host: HostPort, *, limit: int = MAX_SPOOL_ITEMS_PER_CALL) -> int:
        self.recover_pending_attempts()
        reported = 0
        processed = 0
        budget = self._limit(limit)
        for path in self.journal.spool_list("receipts"):
            if processed >= budget:
                break
            blob = self._read_spool(path, "receipts")
            if blob is not None and self._due(blob):
                processed += 1
                reported += int(self._post_saved_receipt(host, path, blob))
        return reported

    @_serialized
    def poll_outbox(self, host: HostPort, platform: PlatformPort, *, wait_seconds: int = 0) -> tuple[Receipt, ...]:
        """One bounded claim cycle, receipts first; not an implicit daemon."""

        if isinstance(wait_seconds, bool) or not isinstance(wait_seconds, int) or not 0 <= wait_seconds <= 20:
            raise ValueError("claim wait must be 0..20 seconds")
        self.replay_receipts(host)
        try:
            result = self._host_result(host.claim_outbox(wait_seconds=wait_seconds))
            claims = extract_claims(result)
        except Exception:
            self.counters.inc("outbox_claim_errors")
            return ()
        if result.kind == "retry":
            self.counters.inc("outbox_claim_errors")
        return tuple(self.process_outbox_claim(claim, platform, host) for claim in claims)

    def _intent_from_claim(self, claim: OutboxClaim) -> OutboundIntent:
        item = claim.item
        # Do not silently discard media/admin/raw-segment obligations and then
        # claim success for a text-only send.
        for key in ("attachments", "sticker", "media", "message", "segments", "admin"):
            if key in item and item[key] is not None and item[key] != []:
                raise OutboundPlanError("unsupported_outbox_content")
        if item.get("kind", "message") != "message":
            raise OutboundPlanError("unsupported_outbox_kind")
        target = item.get("target")
        if not isinstance(target, Mapping):
            raise OutboundPlanError("target_missing")
        message_type = target.get("type")
        if message_type == "dm":
            message_type = "private"
        if message_type not in ("private", "group"):
            raise OutboundPlanError("target_type_invalid")
        route_id = bounded_id(item.get("route_id"), limit=160)
        target_id = qq_id(target.get("id"))
        if not route_id or not target_id:
            raise OutboundPlanError("target_identity_missing")
        attachment = item.get("attachment")
        if attachment is not None:
            if not isinstance(attachment, Mapping) or not isinstance(attachment.get("path"), str):
                raise OutboundPlanError("unsupported_outbox_content")
            attachment_path = Path(attachment["path"]).resolve()
            if Path(attachment["path"]).is_symlink():
                raise OutboundPlanError("attachment_symlink")
            if not self.config.attachment_root:
                raise OutboundPlanError("attachment_root_missing")
            root = Path(self.config.attachment_root).resolve()
            try:
                attachment_path.relative_to(root)
            except ValueError:
                raise OutboundPlanError("attachment_outside_root")
            attachment = dict(attachment, path=str(attachment_path))
            if attachment_path.stat().st_size > 20 * 1024 * 1024:
                raise OutboundPlanError("attachment_too_large")
            if attachment.get("sha256"):
                if hashlib.sha256(attachment_path.read_bytes()).hexdigest() != attachment["sha256"]:
                    raise OutboundPlanError("attachment_hash_mismatch")
        elif item.get("image_path"):
            attachment_path = Path(str(item["image_path"])).resolve()
            if not self.config.attachment_root:
                raise OutboundPlanError("attachment_root_missing")
            try:
                attachment_path.relative_to(Path(self.config.attachment_root).resolve())
            except ValueError:
                raise OutboundPlanError("attachment_outside_root")
            attachment = {"path": str(attachment_path)}
        return OutboundIntent(
            claim.publication_id, claim.attempt_id, route_id, message_type,
            target_id, item.get("text", ""), item.get("reply_to"), qq_id(item.get("account_id")),
            attachment,
        )

    def _save_attempt(self, receipt: Receipt, fingerprint: str, *, phase: str) -> None:
        self.journal.write_attempt({
            "publication_id": receipt.publication_id, "attempt_id": receipt.attempt_id,
            "account_id": self.config.account_id, "claim_sha256": fingerprint,
            "phase": phase, "receipt": receipt.as_dict(),
        })

    def _recover_attempt(self, record: dict[str, Any]) -> Receipt:
        receipt = Receipt.from_dict(record["receipt"])
        if (record.get("account_id") != self.config.account_id
                or record.get("publication_id") != receipt.publication_id
                or record.get("attempt_id") != receipt.attempt_id
                or record.get("phase") not in ("started", "complete")):
            raise ValueError("corrupt publication fence")
        if record["phase"] == "started":
            receipt = Receipt(receipt.publication_id, receipt.attempt_id, "unknown", "platform_send_interrupted",
                              response=receipt.response)
            self._save_attempt(receipt, record.get("claim_sha256", ""), phase="complete")
            self.counters.inc("outbox_recovered_unknown")
        return receipt

    def _report_receipt(self, host: HostPort, receipt: Receipt, *, force: bool = False) -> None:
        path = self.journal.queue_receipt(receipt)
        blob = self.journal.read_json(path)
        if Receipt.from_dict(blob["receipt"]).as_dict() != receipt.as_dict():
            raise ValueError("attempt receipt changed; refusing to overwrite evidence")
        if force or (blob.get("report_state") == "pending" and self._due(blob)):
            self._post_saved_receipt(host, path, blob)

    def _post_saved_receipt(self, host: HostPort, path: Path, blob: dict[str, Any]) -> bool:
        try:
            receipt = Receipt.from_dict(blob["receipt"])
            if blob.get("publication_id") != receipt.publication_id or path != self.journal.receipt_path(receipt):
                raise ValueError("receipt identity mismatch")
        except (KeyError, TypeError, ValueError):
            self.journal.quarantine(path, "invalid_receipt")
            self.counters.inc("receipts_unreadable")
            return False
        try:
            result = self._host_result(host.post_receipt(receipt.publication_id, receipt.as_dict()))
        except Exception as error:
            result = PortResult("retry", error=type(error).__name__)
        if result.accepted or result.rejected:
            updated = dict(blob, report_state="reported" if result.accepted else "rejected")
            self.journal.write_json(path, updated)
            self.counters.inc("receipts_reported" if result.accepted else "receipts_rejected")
            return result.accepted
        self._retry(path, blob, MAX_RECEIPT_TRIES)
        self.counters.inc("receipts_retries")
        return False

    def _read_spool(self, path: Path, bucket: str) -> dict[str, Any] | None:
        try:
            value = self.journal.read_json(path)
            if not isinstance(value, dict):
                raise ValueError("invalid spool item")
            return value
        except (OSError, ValueError):
            self.journal.quarantine(path, "unreadable_" + bucket)
            self.counters.inc(bucket + "_unreadable")
            return None

    def _retry(self, path: Path, blob: dict[str, Any], ceiling: int) -> None:
        previous = blob.get("tries", 0)
        previous = previous if isinstance(previous, int) and not isinstance(previous, bool) else 0
        tries = max(0, previous) + 1
        updated = dict(blob, tries=tries, next_try_at=self._now() + min(300, 2 ** min(tries, 8)))
        if tries >= ceiling:
            updated["blocked"] = True
            if "receipt" in blob:
                updated["report_state"] = "blocked"
            self.counters.inc("retry_budget_exhausted")
        self.journal.write_json(path, updated)

    def _due(self, blob: dict[str, Any]) -> bool:
        if blob.get("blocked"):
            return False
        next_try = blob.get("next_try_at", 0.0)
        return isinstance(next_try, (int, float)) and next_try <= self._now()

    @staticmethod
    def _host_result(value: Any) -> PortResult:
        return value if isinstance(value, PortResult) else PortResult("retry", error="invalid_host_result")

    @staticmethod
    def _limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValueError("limit must be an integer")
        return max(0, min(limit, MAX_SPOOL_ITEMS_PER_CALL))

    def health_snapshot(self) -> dict[str, Any]:
        result = self.journal.health_snapshot()
        result.update({"account_id": self.config.account_id, "routes": len(self.routes), "closed": self._closed})
        result.update(self.counters.snapshot())
        return result

    def close(self) -> None:
        with self._worker_lock:
            self._closed = True
            self.journal.close()

    def __enter__(self) -> "SoyoQQChannel":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
