# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Platform-neutral contracts for the Soyo QQ channel.

The contracts are deliberately narrower than OneBot's event shape.  The
future DSH channel owns transport I/O and host HTTP; this package owns the
product-facing route, inbound, outbound, and receipt vocabulary.  No Hermes
runtime module, credential, socket, or model client is imported here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, FrozenSet, Literal, Mapping, Optional, Tuple


MAX_ID_CHARS = 240
MAX_ROUTE_ID_CHARS = 160
MAX_TEXT_CHARS = 16_000
MAX_REPLY_ID_CHARS = 120
MAX_MEDIA_ITEMS = 8
MAX_MEDIA_REF_CHARS = 2_048
MAX_MESSAGE_SEGMENTS = 256

MessageType = Literal["private", "group"]
ReceiptStatus = Literal["platform_accepted", "failed", "unknown"]


def bounded_id(value: Any, *, limit: int = MAX_ID_CHARS) -> str:
    """Validate an identifier without truncation or object coercion.

    Truncating an identity can alias an unauthorized route to an authorized
    one.  Display text may be shortened; authorization and dedup keys may not.
    """

    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return ""
    text = str(value).strip()
    if not text or len(text) > limit or any(char.isspace() or ord(char) < 32 for char in text):
        return ""
    return text


def qq_id(value: Any) -> str:
    """A canonical ASCII account/group id, never a guessed Unicode number."""

    text = bounded_id(value, limit=20)
    return text if re.fullmatch(r"[1-9][0-9]{0,19}", text) else ""


def bounded_text(value: Any, *, limit: int = MAX_TEXT_CHARS) -> str:
    """Return bounded text without allowing arbitrary objects into a contract."""

    return value[:limit] if isinstance(value, str) else ""


@dataclass(frozen=True)
class ChannelRoute:
    """One explicitly authorized QQ scene.

    A group route requires a sender snapshot.  An empty snapshot denies all
    group senders instead of accidentally turning a missing member list into
    an allow-all route.  A private route admits only its configured peer.
    """

    route_id: str
    message_type: MessageType
    target_id: str
    account_id: str
    allowed_sender_ids: FrozenSet[str] = field(default_factory=frozenset)
    enabled: bool = True

    def __post_init__(self) -> None:
        route_id = bounded_id(self.route_id, limit=MAX_ROUTE_ID_CHARS)
        target_id = qq_id(self.target_id)
        account_id = qq_id(self.account_id)
        if not route_id or not target_id or not account_id:
            raise ValueError("route_id, target_id, and account_id are required")
        if self.message_type not in ("private", "group"):
            raise ValueError("message_type must be private or group")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        if not isinstance(self.allowed_sender_ids, (set, frozenset, tuple, list)):
            raise ValueError("allowed_sender_ids must be an explicit sender snapshot")
        sender_ids = frozenset(
            qq_id(value) for value in self.allowed_sender_ids
        )
        if "" in sender_ids:
            raise ValueError("sender snapshot contains an invalid account id")
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "account_id", account_id)
        object.__setattr__(self, "allowed_sender_ids", sender_ids)

    @property
    def scene_id(self) -> str:
        return f"qq:{self.account_id}:{self.message_type}:{self.target_id}"

    def matches_target(self, message_type: str, target_id: Any) -> bool:
        return (
            self.enabled
            and message_type == self.message_type
            and qq_id(target_id) == self.target_id
        )

    def accepts_sender(self, sender_id: Any) -> bool:
        sender = qq_id(sender_id)
        if not self.enabled or not sender:
            return False
        if self.message_type == "private":
            return sender == self.target_id
        return sender in self.allowed_sender_ids


@dataclass(frozen=True)
class MediaRef:
    """Bounded metadata for one inbound non-text segment; never contains bytes."""

    kind: str
    placeholder: str
    ref: str = ""
    label: str = ""
    metadata: Tuple[Tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "placeholder": self.placeholder,
        }
        if self.ref:
            result["ref"] = self.ref
        if self.label:
            result["label"] = self.label
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result


@dataclass(frozen=True)
class InboundEnvelope:
    """Authorized, normalized inbound event passed toward DSH."""

    route_id: str
    account_id: str
    message_type: MessageType
    target_id: str
    sender_id: str
    event_id: str
    text: str
    occurred_at: float = 0.0
    mentioned_account_ids: Tuple[str, ...] = ()
    reply_to: Optional[str] = None
    forward_refs: Tuple[str, ...] = ()
    media: Tuple[MediaRef, ...] = ()
    historical: bool = False

    @property
    def scene_id(self) -> str:
        return f"qq:{self.account_id}:{self.message_type}:{self.target_id}"

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "route_id": self.route_id,
            "account_id": self.account_id,
            "message_type": self.message_type,
            "target_id": self.target_id,
            "sender_id": self.sender_id,
            "event_id": self.event_id,
            "text": self.text,
            "occurred_at": self.occurred_at,
            "mentioned_account_ids": list(self.mentioned_account_ids),
            "scene_id": self.scene_id,
            "historical": self.historical,
        }
        if self.reply_to:
            result["reply_to"] = self.reply_to
        if self.forward_refs:
            result["forward_refs"] = list(self.forward_refs)
        if self.media:
            result["media"] = [item.as_dict() for item in self.media]
        return result

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "InboundEnvelope":
        """Read a spool item without forwarding arbitrary authority fields."""

        if not isinstance(values, Mapping):
            raise ValueError("invalid inbound envelope")
        account = qq_id(values.get("account_id"))
        target = qq_id(values.get("target_id"))
        sender = qq_id(values.get("sender_id"))
        route = bounded_id(values.get("route_id"), limit=MAX_ROUTE_ID_CHARS)
        event = bounded_id(values.get("event_id"), limit=160)
        message_type = values.get("message_type")
        text = values.get("text")
        moment = values.get("occurred_at", 0.0)
        if (not all((account, target, sender, route, event))
                or message_type not in ("private", "group")
                or not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS
                or isinstance(moment, bool) or not isinstance(moment, (int, float))
                or not math.isfinite(moment) or moment < 0):
            raise ValueError("invalid inbound envelope")
        mentions = values.get("mentioned_account_ids", [])
        raw_forward_refs = values.get("forward_refs", [])
        raw_media = values.get("media", [])
        historical = values.get("historical", False)
        if (not isinstance(mentions, list) or len(mentions) > MAX_MESSAGE_SEGMENTS
                or any(not qq_id(value) for value in mentions)
                or not isinstance(raw_forward_refs, list) or len(raw_forward_refs) > MAX_MEDIA_ITEMS
                or any(not bounded_id(value, limit=MAX_REPLY_ID_CHARS) for value in raw_forward_refs)
                or not isinstance(raw_media, list) or len(raw_media) > MAX_MEDIA_ITEMS
                or not isinstance(historical, bool)):
            raise ValueError("invalid inbound metadata")
        media = []
        for item in raw_media:
            if not isinstance(item, Mapping):
                raise ValueError("invalid media metadata")
            metadata = item.get("metadata", {})
            if not isinstance(metadata, Mapping) or len(metadata) > 3:
                raise ValueError("invalid media metadata")
            media.append(MediaRef(
                kind=bounded_text(item.get("kind"), limit=40),
                placeholder=bounded_text(item.get("placeholder"), limit=160),
                ref=bounded_text(item.get("ref"), limit=MAX_MEDIA_REF_CHARS),
                label=bounded_text(item.get("label"), limit=80),
                metadata=tuple((bounded_text(key, limit=40), bounded_text(value, limit=120))
                               for key, value in metadata.items()),
            ))
        reply = values.get("reply_to")
        if reply is not None and not bounded_id(reply, limit=MAX_REPLY_ID_CHARS):
            raise ValueError("invalid reply id")
        return cls(route, account, message_type, target, sender, event, text,
                   float(moment), tuple(qq_id(value) for value in mentions),
                   bounded_id(reply, limit=MAX_REPLY_ID_CHARS) or None,
                   tuple(bounded_id(value, limit=MAX_REPLY_ID_CHARS) for value in raw_forward_refs),
                   tuple(media), historical)


@dataclass(frozen=True)
class InboundDecision:
    """Classification result; rejection carries only a bounded machine reason."""

    accepted: bool
    reason: str
    envelope: Optional[InboundEnvelope] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "accepted": self.accepted,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }
        if self.envelope is not None:
            result["envelope"] = self.envelope.as_dict()
        return result


@dataclass(frozen=True)
class OutboundIntent:
    """Host outbox item waiting for a platform send attempt."""

    publication_id: str
    attempt_id: str
    route_id: str
    message_type: MessageType
    target_id: str
    text: str
    reply_to: Optional[str] = None
    account_id: str = ""
    attachment: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class OutboundPlan:
    """Validated OneBot action parameters, still requiring a real transport."""

    action: str
    params: Mapping[str, Any]
    route_id: str
    target_id: str
    segment_types: Tuple[str, ...]


@dataclass(frozen=True)
class Receipt:
    """The only platform outcome the host may use to advance an outbox item."""

    publication_id: str
    attempt_id: str
    status: ReceiptStatus
    reason: str
    platform_message_id: Optional[str] = None
    response: Mapping[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        """Terminal for this send attempt, not proof of end-user delivery."""
        return self.status in {"platform_accepted", "failed", "unknown"}

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "Receipt":
        if not isinstance(values, Mapping):
            raise ValueError("invalid receipt")
        publication = bounded_id(values.get("publication_id"), limit=160)
        attempt = bounded_id(values.get("attempt_id"), limit=160)
        status = values.get("status")
        reason = bounded_id(values.get("reason"), limit=120)
        response = values.get("response", {})
        message_id = bounded_id(values.get("platform_message_id"), limit=160) or None
        if (not publication or not attempt or not reason
                or status not in ("platform_accepted", "failed", "unknown")
                or not isinstance(response, Mapping)
                or (status == "platform_accepted" and message_id is None)):
            raise ValueError("invalid receipt")
        return cls(publication, attempt, status, reason, message_id, dict(response))

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "publication_id": self.publication_id,
            "attempt_id": self.attempt_id,
            "status": self.status,
            "reason": self.reason,
            "response": dict(self.response),
        }
        if self.platform_message_id:
            result["platform_message_id"] = self.platform_message_id
        return result
