# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Soyo's Hermes-independent QQ channel boundary.

The package is intentionally transport-free.  A future DSH adapter can wire
these contracts to Asuna's host API/OneBot worker without importing Hermes'
Gateway, registry, session database, or agent loop.
"""

from .contracts import (
    ChannelRoute,
    InboundDecision,
    InboundEnvelope,
    MediaRef,
    OutboundIntent,
    OutboundPlan,
    Receipt,
)
from .inbound import SeenLRU, classify_onebot_event, parse_message
from .journal import Counters, SoyoQQJournal
from .catchup import CatchupPolicy, CatchupRunner
from .host import HistoryPage, HistoryPort, HostPort, OutboxClaim, PlatformPort, PortResult
from .service import ChannelConfig, SoyoQQChannel
from .outbound import (
    OutboundPlanError,
    build_outbound_plan,
    build_outbound_plans,
    classify_send_response,
    encode_group_text,
    split_reply_text,
)

__all__ = [
    "ChannelRoute",
    "InboundDecision",
    "InboundEnvelope",
    "MediaRef",
    "OutboundIntent",
    "OutboundPlan",
    "Receipt",
    "SeenLRU",
    "classify_onebot_event",
    "parse_message",
    "Counters",
    "SoyoQQJournal",
    "OutboundPlanError",
    "build_outbound_plan",
    "build_outbound_plans",
    "classify_send_response",
    "encode_group_text",
    "split_reply_text",
    "ChannelConfig",
    "SoyoQQChannel",
    "HostPort",
    "PlatformPort",
    "PortResult",
    "OutboxClaim",
    "HistoryPage",
    "HistoryPort",
    "CatchupPolicy",
    "CatchupRunner",
]
