# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""OneBot outbound planning and receipt classification.

The planner creates an action but never sends it.  The response classifier
uses only the platform response as evidence: a missing/ambiguous response is
``unknown`` and must not be silently converted into a retry or a success.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    MAX_REPLY_ID_CHARS,
    MAX_MESSAGE_SEGMENTS,
    MAX_TEXT_CHARS,
    ChannelRoute,
    OutboundIntent,
    OutboundPlan,
    Receipt,
    bounded_id,
    bounded_text,
    qq_id,
)


AT_MARKER = re.compile(r"(?<![A-Za-z0-9.@_-])@qq:([0-9]{1,20})(?![A-Za-z0-9_-])")
SEND_ACTIONS = {"private": "send_private_msg", "group": "send_group_msg"}
GROUP_SEGMENTS = frozenset({"reply", "text", "at"})
PRIVATE_SEGMENTS = frozenset({"text", "reply"})
MAX_REPLY_PARTS = 64
DEFAULT_REPLY_PART_CHARS = 1800


class OutboundPlanError(ValueError):
    """A stable, bounded reason why an outbox item cannot be sent."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = bounded_id(code, limit=80) or "invalid_outbound"
        super().__init__(message or self.code)


def encode_group_text(text: str) -> list[dict[str, Any]]:
    """Promote only explicit ``@qq:<digits>`` markers to real at segments."""

    segments: list[dict[str, Any]] = []
    protected = []
    cursor, fence = 0, None
    for line in text.splitlines(keepends=True):
        matched = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and matched:
            fence = (matched.group(1)[0], len(matched.group(1)), cursor)
        elif fence and matched and matched.group(1)[0] == fence[0] and len(matched.group(1)) >= fence[1] and not line[matched.end():].strip():
            protected.append((fence[2], cursor + len(line))); fence = None
        cursor += len(line)
    if fence: protected.append((fence[2], len(text)))
    position = 0
    for match in AT_MARKER.finditer(text):
        if any(start <= match.start() < end for start, end in protected): continue
        if not qq_id(match.group(1)):
            continue
        before = text[position:match.start()]
        if before:
            segments.append({"type": "text", "data": {"text": before}})
        segments.append({"type": "at", "data": {"qq": match.group(1)}})
        position = match.end()
    tail = text[position:]
    if tail:
        segments.append({"type": "text", "data": {"text": tail}})
    return segments


def split_reply_text(
    text: str,
    *,
    max_chars: int = DEFAULT_REPLY_PART_CHARS,
    max_parts: int = MAX_REPLY_PARTS,
) -> list[str]:
    """Reproduce Hermes' user-visible multiline delivery without streaming.

    DSH still publishes one checked final answer.  The channel worker expands
    that frozen answer into bounded platform messages only after the host has
    settled normally.  Blank lines are boundaries, ordinary lines remain
    separate (the old QQ adapter used a short human-like delay), and an
    overlong line is hard-wrapped so a single OneBot request cannot grow
    without bound.
    """

    if not isinstance(text, str) or not text.strip():
        return []
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 80:
        raise ValueError("max_chars must be an integer >= 80")
    if isinstance(max_parts, bool) or not isinstance(max_parts, int) or not 1 <= max_parts <= MAX_REPLY_PARTS:
        raise ValueError("max_parts must be between 1 and 64")

    parts: list[str] = []
    code, fence = [], None
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        matched = re.match(r"^ {0,3}(`{3,}|~{3,})", raw)
        if fence:
            code.append(raw)
            if matched and matched.group(1)[0] == fence[0] and len(matched.group(1)) >= fence[1] and not raw[matched.end():].strip():
                block = '\n'.join(code)
                if len(block) > max_chars: raise OutboundPlanError('code_block_too_long')
                parts.append(block); code = []; fence = None
            continue
        if matched:
            fence = (matched.group(1)[0], len(matched.group(1))); code.append(raw); continue
        line = raw.rstrip()
        if not line.strip(): continue
        while len(line) > max_chars:
            cut = line.rfind(" ", 0, max_chars + 1)
            if cut < max_chars // 2:
                cut = max_chars
            parts.append(line[:cut].rstrip())
            line = line[cut:].lstrip()
        if line:
            parts.append(line)
    if code:
        block = '\n'.join(code)
        if len(block) > max_chars: raise OutboundPlanError('code_block_too_long')
        parts.append(block)

    if len(parts) > max_parts:
        # No partial/truncated final is published as if it were the complete
        # answer. The caller retains the frozen final in its failed outbox.
        raise OutboundPlanError("too_many_reply_parts")
    return parts


def build_outbound_plan(intent: OutboundIntent, route: ChannelRoute) -> OutboundPlan:
    """Build a bounded OneBot send action after re-checking the route.

    Attachment bytes must already have been authorized and validated by the
    channel. The planner never fetches remote or model-authored local paths.
    """

    publication_id = bounded_id(intent.publication_id, limit=160)
    attempt_id = bounded_id(intent.attempt_id, limit=160)
    if not publication_id or not attempt_id:
        raise OutboundPlanError("missing_publication_identity")
    if intent.route_id != route.route_id:
        raise OutboundPlanError("route_mismatch")
    if qq_id(intent.account_id) != route.account_id:
        raise OutboundPlanError("account_mismatch")
    if not route.matches_target(intent.message_type, intent.target_id):
        raise OutboundPlanError("target_not_authorized")
    if not isinstance(intent.text, str):
        raise OutboundPlanError("invalid_text")
    if len(intent.text) > MAX_TEXT_CHARS:
        raise OutboundPlanError("text_too_long")
    text = intent.text if isinstance(intent.text, str) else ""
    attachment = intent.attachment
    if attachment is not None:
        if not isinstance(attachment, Mapping):
            raise OutboundPlanError("invalid_attachment")
        file_path = attachment.get("path")
        if not isinstance(file_path, str) or not file_path or not Path(file_path).is_absolute():
            raise OutboundPlanError("invalid_attachment_path")
        if not Path(file_path).is_file() or Path(file_path).is_symlink():
            raise OutboundPlanError("attachment_unavailable")
        suffix = Path(file_path).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise OutboundPlanError("unsupported_attachment")
    if not text.strip() and attachment is None:
        raise OutboundPlanError("empty_text")
    action = SEND_ACTIONS[intent.message_type]
    segments: list[dict[str, Any]] = []
    if intent.message_type == "group":
        reply_to = bounded_id(intent.reply_to, limit=MAX_REPLY_ID_CHARS)
        if intent.reply_to is not None and not reply_to:
            raise OutboundPlanError("invalid_reply_id")
        if reply_to:
            segments.append({"type": "reply", "data": {"id": reply_to}})
        if text.strip():
            segments.extend(encode_group_text(text))
        if attachment is not None:
            segments.append({"type": "image", "data": {"file": attachment["path"]}})
        allowed = GROUP_SEGMENTS | {"image"}
        target_key = "group_id"
    else:
        reply_to = bounded_id(intent.reply_to, limit=MAX_REPLY_ID_CHARS)
        if intent.reply_to is not None and not reply_to: raise OutboundPlanError('invalid_reply_id')
        if reply_to: segments.append({'type': 'reply', 'data': {'id': reply_to}})
        if text.strip():
            segments.append({"type": "text", "data": {"text": text}})
        if attachment is not None:
            segments.append({"type": "image", "data": {"file": attachment["path"]}})
        allowed = PRIVATE_SEGMENTS | {"image"}
        target_key = "user_id"

    if not segments:
        raise OutboundPlanError("empty_segments")
    if len(segments) > MAX_MESSAGE_SEGMENTS:
        raise OutboundPlanError("too_many_segments")
    segment_types = tuple(str(segment.get("type") or "") for segment in segments)
    if any(segment_type not in allowed for segment_type in segment_types):
        raise OutboundPlanError("segment_guard")
    return OutboundPlan(
        action=action,
        params={target_key: int(route.target_id),
                "message": segments},
        route_id=route.route_id,
        target_id=route.target_id,
        segment_types=segment_types,
    )


def build_outbound_plans(
    intent: OutboundIntent,
    route: ChannelRoute,
    *,
    max_chars: int = DEFAULT_REPLY_PART_CHARS,
    max_parts: int = MAX_REPLY_PARTS,
) -> list[OutboundPlan]:
    """Build the frozen sequence sent for one final publication.

    The first part owns the reply segment.  An attachment is deliberately a
    single-part publication; callers must not claim an image was delivered by
    silently discarding it.
    """

    if intent.attachment is not None:
        return [build_outbound_plan(intent, route)]
    if not isinstance(intent.text, str) or len(intent.text) > MAX_TEXT_CHARS:
        raise OutboundPlanError("invalid_text" if not isinstance(intent.text, str) else "text_too_long")
    parts = split_reply_text(intent.text, max_chars=max_chars, max_parts=max_parts)
    if not parts:
        raise OutboundPlanError("empty_text")
    result: list[OutboundPlan] = []
    for index, part in enumerate(parts):
        child = OutboundIntent(
            publication_id=intent.publication_id,
            attempt_id=intent.attempt_id,
            route_id=intent.route_id,
            message_type=intent.message_type,
            target_id=intent.target_id,
            text=part,
            reply_to=intent.reply_to if index == 0 else None,
            account_id=intent.account_id,
        )
        result.append(build_outbound_plan(child, route))
    return result


def _safe_response(response: Any) -> dict[str, Any]:
    """Keep only bounded response fields suitable for a host receipt."""

    if not isinstance(response, Mapping):
        return {"shape": "non_mapping"}
    result: dict[str, Any] = {}
    retcode = response.get("retcode")
    if isinstance(retcode, int) and not isinstance(retcode, bool):
        result["retcode"] = retcode
    data = response.get("data")
    if isinstance(data, Mapping):
        message_id = bounded_id(data.get("message_id"), limit=160)
        if message_id:
            result["message_id"] = message_id
    for key in ("message", "wording"):
        value = bounded_text(response.get(key), limit=240).strip()
        if value:
            result[key] = value
    return result


def _is_platform_timeout(response: Mapping[str, Any]) -> bool:
    if response.get("retcode") == 1200:
        return True
    text = " ".join(
        bounded_text(response.get(key), limit=240).lower()
        for key in ("message", "wording")
    )
    return "timeout" in text or "timed out" in text


def classify_send_response(
    response: Any,
    *,
    publication_id: str,
    attempt_id: str,
) -> Receipt:
    """Turn one platform response into a non-ambiguous host receipt."""

    publication = bounded_id(publication_id, limit=160)
    attempt = bounded_id(attempt_id, limit=160)
    if not publication or not attempt:
        raise ValueError("receipt requires exact publication/attempt identity")
    safe = _safe_response(response)
    if not isinstance(response, Mapping):
        return Receipt(publication, attempt, "unknown", "no_platform_response", response=safe)

    retcode = response.get("retcode")
    if isinstance(retcode, bool) or not isinstance(retcode, int):
        return Receipt(publication, attempt, "unknown", "invalid_platform_response", response=safe)
    status = response.get("status")
    if status is not None and status not in ("ok", "failed"):
        return Receipt(publication, attempt, "unknown", "invalid_platform_response", response=safe)
    message_id = bounded_id(
        (response.get("data") or {}).get("message_id")
        if isinstance(response.get("data"), Mapping)
        else None,
        limit=160,
    )
    if retcode == 0 and status == "failed":
        return Receipt(publication, attempt, "unknown", "contradictory_platform_response", response=safe)
    if _is_platform_timeout(response):
        return Receipt(publication, attempt, "unknown", "platform_send_timeout", response=safe)
    if retcode == 0 and message_id:
        return Receipt(
            publication,
            attempt,
            "platform_accepted",
            "platform_accepted",
            platform_message_id=message_id,
            response=safe,
        )
    if retcode == 0:
        return Receipt(publication, attempt, "unknown", "missing_platform_message_id", response=safe)
    retcode_text = bounded_id(retcode, limit=40) or "missing_retcode"
    return Receipt(publication, attempt, "failed", f"retcode_{retcode_text}", response=safe)
