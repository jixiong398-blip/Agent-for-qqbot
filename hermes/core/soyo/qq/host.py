# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Injected host/transport ports for the Soyo QQ channel.

These are contracts, not HTTP clients.  The DSH host adapter will implement
them with its authenticated channel API; a OneBot worker will implement the
platform port.  Keeping the ports here prevents the product package from
learning Hermes homes, DSH tokens, or NapCat socket details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .contracts import ChannelRoute, OutboundPlan, bounded_id


MAX_OUTBOX_CLAIMS = 32


@dataclass(frozen=True)
class PortResult:
    """Bounded result of a host API operation."""

    kind: str
    code: int | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def accepted(self) -> bool:
        return self.kind in {"ok", "accepted", "duplicate"}

    @property
    def retryable(self) -> bool:
        return self.kind == "retry"

    @property
    def rejected(self) -> bool:
        return self.kind == "reject"


@dataclass(frozen=True)
class OutboxClaim:
    """One host-owned publication claimed for this channel."""

    publication_id: str
    attempt_id: str
    item: Mapping[str, Any]

    def __post_init__(self) -> None:
        if (not isinstance(self.publication_id, str)
                or not self.publication_id
                or bounded_id(self.publication_id, limit=160) != self.publication_id
                or not isinstance(self.attempt_id, str)
                or not self.attempt_id
                or bounded_id(self.attempt_id, limit=160) != self.attempt_id
                or not isinstance(self.item, Mapping)):
            raise ValueError("claim requires exact publication/attempt identity and item")
        for key in ("publication_id", "attempt_id"):
            if key in self.item and self.item[key] != getattr(self, key):
                raise ValueError("claim identity mismatch")


@runtime_checkable
class HostPort(Protocol):
    """Minimum DSH host surface required by the channel worker."""

    def post_event(self, envelope: Mapping[str, Any]) -> PortResult:
        ...

    def claim_outbox(self, *, wait_seconds: int = 0) -> PortResult:
        ...

    def post_receipt(self, publication_id: str, receipt: Mapping[str, Any]) -> PortResult:
        ...


@runtime_checkable
class PlatformPort(Protocol):
    """Minimum OneBot/NapCat surface; implementation owns real network I/O."""

    def send(self, plan: OutboundPlan) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class HistoryPage:
    """Adapter-normalized history; cursor semantics belong to the adapter."""

    events: Sequence[Mapping[str, Any]] = ()
    next_cursor: str | None = None
    complete: bool = True


@runtime_checkable
class HistoryPort(Protocol):
    def get_history_page(
        self, route: ChannelRoute, *, since: float, cursor: str | None, limit: int,
    ) -> HistoryPage:
        ...


@runtime_checkable
class AttachmentPort(Protocol):
    """Optional host-owned artifact bytes port for a later media slice."""

    def get_attachment(
        self,
        publication_id: str,
        attempt_id: str,
        artifact_id: str,
        *,
        max_bytes: int,
        expected_sha256: str,
    ) -> PortResult:
        ...


def extract_claims(result: PortResult) -> Sequence[OutboxClaim]:
    """Decode a bounded host claim response without guessing its shape."""

    if result.kind != "items":
        return ()
    if not isinstance(result.payload, Mapping):
        raise ValueError("invalid outbox payload")
    raw_items = result.payload.get("items")
    if not isinstance(raw_items, list) or len(raw_items) > MAX_OUTBOX_CLAIMS:
        raise ValueError("invalid outbox items")
    claims: list[OutboxClaim] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise ValueError("invalid outbox item")
        claims.append(OutboxClaim(raw.get("publication_id"), raw.get("attempt_id"), dict(raw)))
    return tuple(claims)
