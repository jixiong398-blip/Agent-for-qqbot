"""Contracts for the extracted Soyo QQ channel; run only after batch closure."""

from __future__ import annotations

from pathlib import Path

import pytest

from soyo.qq import (
    BY_ID,
    BY_NAME,
    ChannelRoute,
    OutboundIntent,
    OutboundPlanError,
    SeenLRU,
    SoyoQQJournal,
    build_outbound_plan,
    classify_onebot_event,
    classify_send_response,
    parse_message,
)


def _group_route() -> ChannelRoute:
    return ChannelRoute(
        route_id="group-fixture",
        message_type="group",
        target_id="123456",
        account_id="900001",
        allowed_sender_ids=frozenset({"100001"}),
    )


def test_real_mentions_are_separate_from_plain_at_text():
    parsed = parse_message(
        [
            {"type": "text", "data": {"text": "@not-a-mention "}},
            {"type": "at", "data": {"qq": "900001"}},
            {"type": "image", "data": {"file": "img-1", "url": "https://example.invalid/img"}},
            {"type": "reply", "data": {"id": "42"}},
        ]
    )

    assert parsed.at_ids == ("900001",)
    assert parsed.reply_to == "42"
    assert len(parsed.media) == 1
    assert "@not-a-mention" in parsed.text


def test_qq_faces_keep_raw_names_ids_and_unknown_id_fallback():
    parsed = parse_message([
        {"type": "face", "data": {"id": "277", "raw": {"faceText": "/汪汪"}}},
        {"type": "face", "data": {"id": "9999"}},
    ])
    assert len(BY_ID) == 289
    assert BY_NAME["汪汪"] == "277"
    assert parsed.media[0].placeholder == "[表情:汪汪]"
    assert dict(parsed.media[0].metadata)["face_id"] == "277"
    assert parsed.media[1].placeholder == "[表情:id-9999]"
    assert BY_ID["424"] == "你不对劲"
    assert BY_NAME["你不对劲"] == "424"
    assert BY_NAME["续标识"] == "424"


def test_qq_sticker_metadata_distinguishes_custom_market_and_photo():
    parsed = parse_message([
        {"type": "image", "data": {"file": "a" * 32 + ".gif", "sub_type": "1"}},
        {"type": "image", "data": {"file": "b" * 32 + ".gif", "emoji_id": "e" * 32,
                                       "emoji_package_id": "p", "key": "k"}},
        {"type": "image", "data": {"file": "c" * 32 + ".jpg", "sub_type": "0"}},
    ])
    assert [dict(item.metadata).get("sticker") for item in parsed.media] == ["custom", "market", None]
    assert parsed.media[0].placeholder == "[表情包]"
    assert parsed.media[1].placeholder == "[表情包]"
    assert parsed.media[2].placeholder == "[图片（未解析）]"


def test_known_face_tokens_encode_to_real_face_segments_and_unknown_stays_text():
    route = ChannelRoute("dm-face", "private", "100001", "900001")
    plan = build_outbound_plan(
        OutboundIntent("pub-face", "attempt-face", route.route_id, "private", route.target_id,
                       "笑[表情:汪汪][表情:不存在]", account_id=route.account_id), route)
    assert [segment["type"] for segment in plan.params["message"]] == ["text", "face", "text"]
    assert plan.params["message"][1]["data"] == {"id": "277"}
    assert plan.params["message"][2]["data"]["text"] == "[表情:不存在]"


def test_inbound_requires_route_and_sender_snapshot():
    event = {
        "post_type": "message",
        "message_type": "group",
        "self_id": "900001",
        "group_id": "123456",
        "user_id": "100001",
        "message_id": "m1",
        "message": [{"type": "text", "data": {"text": "你好"}}],
    }
    seen = SeenLRU()
    accepted = classify_onebot_event(
        event,
        account_id="900001",
        routes={"group-fixture": _group_route()},
        seen=seen,
    )
    assert accepted.accepted
    assert accepted.envelope is not None
    assert accepted.envelope.route_id == "group-fixture"

    denied = classify_onebot_event(
        {**event, "user_id": "100002", "message_id": "m2"},
        account_id="900001",
        routes={"group-fixture": _group_route()},
    )
    assert not denied.accepted
    assert denied.reason == "unauthorized_sender"


def test_duplicate_guard_is_scoped_by_route_and_event_time():
    seen = SeenLRU()
    assert seen.add_if_new(("route-a", "m1", 1))
    assert not seen.add_if_new(("route-a", "m1", 1))
    assert seen.add_if_new(("route-b", "m1", 1))


def test_group_outbound_promotes_only_explicit_account_marker():
    route = _group_route()
    plan = build_outbound_plan(
        OutboundIntent(
            publication_id="pub-1",
            attempt_id="attempt-1",
            route_id=route.route_id,
            message_type="group",
            target_id=route.target_id,
            text="你好 @qq:100001，纯文本 @someone",
            account_id=route.account_id,
        ),
        route,
    )
    assert plan.action == "send_group_msg"
    assert [segment["type"] for segment in plan.params["message"]] == ["text", "at", "text"]
    assert "@someone" in plan.params["message"][2]["data"]["text"]


def test_private_reply_is_supported_as_a_bounded_reply_segment():
    route = ChannelRoute(
        route_id="dm-fixture",
        message_type="private",
        target_id="100001",
        account_id="900001",
    )
    plan = build_outbound_plan(
        OutboundIntent(publication_id="pub-1", attempt_id="attempt-1", route_id=route.route_id,
            message_type="private", target_id=route.target_id, text="你好", reply_to="42", account_id=route.account_id),
        route,
    )
    assert plan.params['message'][0] == {'type': 'reply', 'data': {'id': '42'}}


def test_send_receipt_distinguishes_accepted_failed_and_unknown():
    accepted = classify_send_response(
        {"retcode": 0, "data": {"message_id": 42}},
        publication_id="pub-1",
        attempt_id="attempt-1",
    )
    failed = classify_send_response(
        {"retcode": 100, "wording": "rejected"},
        publication_id="pub-2",
        attempt_id="attempt-2",
    )
    unknown = classify_send_response(
        {"retcode": 1200, "message": "sendMsg Timeout"},
        publication_id="pub-3",
        attempt_id="attempt-3",
    )
    assert accepted.status == "platform_accepted"
    assert accepted.platform_message_id == "42"
    assert failed.status == "failed"
    assert unknown.status == "unknown"


def test_journal_requires_absolute_root_and_keeps_spools(tmp_path: Path):
    with pytest.raises(ValueError, match="absolute root"):
        SoyoQQJournal("relative/channel-data")

    root = tmp_path / "channel-data"
    with SoyoQQJournal(root) as journal:
        path = journal.spool_add("inbound", {"event_id": "e1"}, key="route-e1")
        assert path in journal.spool_list("inbound")
        assert journal.read_json(path)["event_id"] == "e1"


@pytest.mark.parametrize("response", [{}, {"retcode": False, "data": {"message_id": 42}},
                                      {"retcode": 0, "status": "failed", "data": {"message_id": 42}}])
def test_malformed_or_contradictory_response_is_unknown(response):
    assert classify_send_response(response, publication_id="pub", attempt_id="attempt").status == "unknown"


def test_authorization_ids_are_not_truncated_or_guessed():
    with pytest.raises(ValueError):
        ChannelRoute("route", "group", "１２３４５６", "900001")
    with pytest.raises(ValueError):
        ChannelRoute("r" * 161, "group", "123456", "900001")
