# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""OneBot v11 inbound normalization and route authorization.

This is the product-side half of the Asuna-style channel boundary.  It does
not open a socket, call NapCat, submit to DSH, inspect a model, or persist a
message.  The caller must first authorize a route; only then are message
segments parsed and turned into a bounded envelope.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from .contracts import (
    MAX_MEDIA_ITEMS,
    MAX_MEDIA_REF_CHARS,
    MAX_MESSAGE_SEGMENTS,
    MAX_TEXT_CHARS,
    ChannelRoute,
    InboundDecision,
    InboundEnvelope,
    MediaRef,
    bounded_id,
    qq_id,
)


MEDIA_MODES = frozenset({"full", "annotate", "off"})
REPLY_ONLY_FALLBACK = "[回复消息（无文字）]"
MENTION_ONLY_FALLBACK = "[非文字消息（未解析）]"

_MEDIA_LABELS = {
    "image": "图片",
    "face": "表情",
    "record": "语音",
    "audio": "语音",
    "video": "视频",
    "file": "文件",
    "json": "卡片消息",
    "xml": "卡片消息",
    "forward": "合并转发",
    "location": "位置",
    "poke": "戳一戳",
    "contact": "名片",
}


class SeenLRU:
    """Bounded, route-scoped local duplicate guard."""

    def __init__(self, capacity: int = 512):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self._lock = threading.Lock()
        self._items: OrderedDict[tuple[str, str, int], None] = OrderedDict()

    def add_if_new(self, key: tuple[str, str, int]) -> bool:
        with self._lock:
            if key in self._items:
                return False
            self._items[key] = None
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
            return True

    def contains(self, key: tuple[str, str, int]) -> bool:
        with self._lock:
            return key in self._items

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


@dataclass(frozen=True)
class ParsedMessage:
    text: str
    text_with_at: str
    text_with_media: str
    text_with_at_media: str
    at_ids: tuple[str, ...]
    at_all_count: int
    at_other_count: int
    reply_to: Optional[str]
    forward_refs: tuple[str, ...]
    reply_extra: int
    media: tuple[MediaRef, ...]
    media_extra: int
    other_segments: int
    truncated: bool = False


def _clean(value: Any, limit: int) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)[:limit]
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit].strip()


def _event_time(event: Mapping[str, Any]) -> float:
    try:
        value = event.get("time", 0.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return 0.0
        timestamp = float(value)
        if math.isfinite(timestamp) and timestamp > 0:
            return timestamp
    except (TypeError, ValueError, OverflowError):
        pass
    # Receive time must not enter the identity: reconnect/history replay of an
    # event lacking send time still has the same dedup key and host envelope.
    return 0.0


def _media_ref(segment_type: str, data: Mapping[str, Any]) -> MediaRef:
    label = _MEDIA_LABELS.get(segment_type, f"{segment_type or '未知'}消息")
    ref_value = data.get("url") or data.get("file") or data.get("file_id")
    if segment_type == "forward":
        ref_value = data.get("id") or data.get("message_id") or data.get("forward_id") or ref_value
    ref = _clean(ref_value, MAX_MEDIA_REF_CHARS)
    name = _clean(data.get("file_name") or data.get("name") or data.get("summary"), 80)
    known_content = segment_type in {"face", "location", "poke", "contact"}
    suffix = "" if known_content else "（未解析）"
    placeholder = f"[{label}:{name}{suffix}]" if name else f"[{label}{suffix}]"
    metadata: list[tuple[str, str]] = []
    for source, target, limit in (
        ("sub_type", "sub_type", 20),
        ("file_id", "file_id", 120),
        ("file_size", "size", 20),
    ):
        value = _clean(data.get(source), limit)
        if value:
            metadata.append((target, value))
    return MediaRef(
        kind=segment_type or "unknown",
        placeholder=placeholder,
        ref=ref,
        label=name,
        metadata=tuple(metadata),
    )


def parse_message(message: Any) -> ParsedMessage:
    """Parse text, real mentions, replies, and bounded media metadata.

    A textual ``@`` is never promoted to a mention.  Only a real OneBot
    ``at`` segment contributes to ``at_ids``.
    """

    if isinstance(message, str):
        return ParsedMessage(message[:MAX_TEXT_CHARS], message[:MAX_TEXT_CHARS],
                             message[:MAX_TEXT_CHARS], message[:MAX_TEXT_CHARS],
                              (), 0, 0, None, (), 0, (), 0, 0, len(message) > MAX_TEXT_CHARS)

    if not isinstance(message, list):
        return ParsedMessage("", "", "", "", (), 0, 0, None, (), 0, (), 0, 0)

    text_parts: list[str] = []
    at_parts: list[str] = []
    media_parts: list[str] = []
    at_media_parts: list[str] = []
    at_ids: list[str] = []
    media: list[MediaRef] = []
    at_all_count = 0
    at_other_count = 0
    reply_to: Optional[str] = None
    forward_refs: list[str] = []
    reply_extra = 0
    media_extra = 0
    other_segments = 0

    truncated = False
    lengths = [0, 0, 0, 0]

    def append_piece(index: int, parts: list[str], value: str) -> None:
        nonlocal truncated
        room = MAX_TEXT_CHARS - lengths[index]
        if len(value) > room:
            truncated = True
        piece = value[:room]
        if piece:
            parts.append(piece)
            lengths[index] += len(piece)

    for segment in message[:MAX_MESSAGE_SEGMENTS]:
        if not isinstance(segment, Mapping):
            other_segments += 1
            continue
        segment_type = segment.get("type")
        segment_type = segment_type[:40].strip().lower() if isinstance(segment_type, str) else ""
        data = segment.get("data")
        data = data if isinstance(data, Mapping) else {}
        if segment_type == "text":
            value = data.get("text")
            if isinstance(value, str):
                append_piece(0, text_parts, value)
                append_piece(1, at_parts, value)
                append_piece(2, media_parts, value)
                append_piece(3, at_media_parts, value)
        elif segment_type == "at":
            target = bounded_id(data.get("qq") or data.get("user_id") or data.get("uid"), limit=80)
            if qq_id(target):
                if target not in at_ids:
                    at_ids.append(target)
                shown = "@" + target
                append_piece(1, at_parts, shown)
                append_piece(3, at_media_parts, shown)
            elif target.lower() == "all" or target == "全体":
                at_all_count += 1
                append_piece(1, at_parts, "@全体")
                append_piece(3, at_media_parts, "@全体")
            else:
                at_other_count += 1
        elif segment_type == "reply":
            reply_id = bounded_id(data.get("id") or data.get("message_id"), limit=120)
            if reply_id and reply_to is None:
                reply_to = reply_id
            elif reply_id:
                reply_extra += 1
        else:
            other_segments += 1
            item = _media_ref(segment_type, data)
            if segment_type == "forward" and item.ref and item.ref not in forward_refs:
                forward_refs.append(item.ref)
            if len(media) < MAX_MEDIA_ITEMS:
                media.append(item)
            else:
                media_extra += 1
            append_piece(2, media_parts, item.placeholder)
            append_piece(3, at_media_parts, item.placeholder)

    return ParsedMessage(
        text="".join(text_parts)[:MAX_TEXT_CHARS],
        text_with_at="".join(at_parts)[:MAX_TEXT_CHARS],
        text_with_media="".join(media_parts)[:MAX_TEXT_CHARS],
        text_with_at_media="".join(at_media_parts)[:MAX_TEXT_CHARS],
        at_ids=tuple(at_ids),
        at_all_count=at_all_count,
        at_other_count=at_other_count,
        reply_to=reply_to,
        forward_refs=tuple(forward_refs[:MAX_MEDIA_ITEMS]),
        reply_extra=reply_extra,
        media=tuple(media),
        media_extra=media_extra,
        other_segments=other_segments,
        truncated=truncated or len(message) > MAX_MESSAGE_SEGMENTS,
    )


def _route_for_event(
    routes: Mapping[str, ChannelRoute] | Iterable[ChannelRoute],
    message_type: str,
    target_id: str,
    account_id: str,
) -> Optional[ChannelRoute]:
    candidates = routes.values() if isinstance(routes, Mapping) else routes
    matches = [route for route in candidates if isinstance(route, ChannelRoute)
               and route.account_id == account_id and route.matches_target(message_type, target_id)]
    return matches[0] if len(matches) == 1 else None


def _report_text(parsed: ParsedMessage, route: ChannelRoute, media_mode: str) -> Optional[str]:
    if media_mode == "off":
        text = parsed.text_with_at if route.message_type == "group" else parsed.text
        return text if text.strip() else None

    text = parsed.text_with_at_media if route.message_type == "group" else parsed.text_with_media
    if parsed.text.strip():
        return text
    if media_mode == "annotate":
        return None
    if parsed.media:
        return text
    if parsed.reply_to:
        return REPLY_ONLY_FALLBACK
    if route.account_id in parsed.at_ids:
        return MENTION_ONLY_FALLBACK
    return None


def classify_onebot_event(
    event: Any,
    *,
    account_id: str,
    routes: Mapping[str, ChannelRoute] | Iterable[ChannelRoute],
    seen: Optional[SeenLRU] = None,
    media_mode: str = "full",
    historical: bool = False,
) -> InboundDecision:
    """Authorize and normalize one OneBot message without side effects."""

    if not isinstance(event, Mapping):
        return InboundDecision(False, "bad_shape")
    if event.get("post_type") != "message":
        return InboundDecision(False, "nonmessage")
    message_type = event.get("message_type")
    if message_type not in ("private", "group"):
        return InboundDecision(False, "unsupported_message_type")

    account = qq_id(account_id)
    if not account or qq_id(event.get("self_id")) != account:
        return InboundDecision(False, "wrong_self")
    sender_id = qq_id(event.get("user_id"))
    if not sender_id:
        return InboundDecision(False, "bad_shape")
    if sender_id == account:
        return InboundDecision(False, "self_echo")

    target_id = qq_id(event.get("group_id") if message_type == "group" else sender_id)
    if not target_id:
        return InboundDecision(False, "bad_shape")
    route = _route_for_event(routes, message_type, target_id, account)
    if route is None:
        return InboundDecision(False, "route_not_allowed")
    if not route.accepts_sender(sender_id):
        return InboundDecision(False, "unauthorized_sender")

    event_id = bounded_id(event.get("message_id"), limit=160)
    if not event_id:
        return InboundDecision(False, "bad_shape")
    parsed = parse_message(event.get("message"))
    if media_mode not in MEDIA_MODES:
        return InboundDecision(False, "invalid_media_mode")
    mode = media_mode
    text = _report_text(parsed, route, mode)
    if text is None:
        return InboundDecision(False, "no_text")

    occurred_at = _event_time(event)
    if seen is not None and seen.contains((route.route_id + ":" + route.scene_id, event_id, int(occurred_at))):
        return InboundDecision(False, "duplicate_local")

    over_host_limit = parsed.truncated or len(text) > MAX_TEXT_CHARS
    text = text[:MAX_TEXT_CHARS]

    envelope = InboundEnvelope(
        route_id=route.route_id,
        account_id=account,
        message_type=route.message_type,
        target_id=target_id,
        sender_id=sender_id,
        event_id=event_id,
        text=text,
        occurred_at=occurred_at,
        mentioned_account_ids=parsed.at_ids,
        reply_to=parsed.reply_to,
        forward_refs=parsed.forward_refs,
        media=parsed.media if mode != "off" else (),
        historical=historical,
    )
    metadata = {
        "route_id": route.route_id,
        "scene_id": route.scene_id,
        "chars": len(text),
        "media_segments": len(parsed.media) + parsed.media_extra,
        "media_only": not parsed.text.strip(),
        "mentions": len(parsed.at_ids),
        "at_all_segments": parsed.at_all_count,
        "at_other_segments": parsed.at_other_count,
        "has_reply": bool(parsed.reply_to),
        "forward_refs": len(parsed.forward_refs),
        "reply_extra": parsed.reply_extra,
        "non_text_segments": parsed.other_segments,
        "over_host_limit": over_host_limit,
    }
    return InboundDecision(True, "accepted", envelope, metadata)


# Short alias for channel workers and future DSH adapter wiring.
classify = classify_onebot_event
