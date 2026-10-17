"""Small offline regressions; real journal I/O, substituted network ports."""

from dataclasses import replace

import pytest

from soyo.qq import (CatchupPolicy, CatchupRunner, ChannelConfig, ChannelRoute, HistoryPage,
                     OutboxClaim, PortResult, SeenLRU, SoyoQQChannel)


ROUTE = ChannelRoute("fixture-group", "group", "123456", "900001", frozenset({"100001"}))


def _event():
    return {"post_type": "message", "message_type": "group", "self_id": ROUTE.account_id,
            "group_id": ROUTE.target_id, "user_id": "100001", "message_id": "message-1",
            "message": [{"type": "at", "data": {"qq": ROUTE.account_id}},
                        {"type": "text", "data": {"text": "fixture"}}]}


def _claim(**extra):
    return OutboxClaim("publication-1", "attempt-1", {
        "account_id": ROUTE.account_id, "route_id": ROUTE.route_id,
        "target": {"type": "group", "id": ROUTE.target_id}, "text": "fixture", **extra,
    })


class Ports:
    def __init__(self):
        self.sends = 0
        self.events = []
        self.receipts = []
        self.claims = []

    def send(self, plan):
        self.sends += 1
        return {"retcode": 0, "data": {"message_id": 42}}

    def post_event(self, envelope):
        self.events.append(envelope)
        return PortResult("accepted")

    def post_receipt(self, publication_id, receipt):
        self.receipts.append(receipt)
        return PortResult("accepted")

    def claim_outbox(self, *, wait_seconds=0):
        items, self.claims = self.claims, []
        return PortResult("items", payload={"items": items})


def _channel(root, **extra):
    return SoyoQQChannel(config=ChannelConfig(ROUTE.account_id), routes=[ROUTE], data_root=root, **extra)


def test_same_attempt_across_restart_only_reposts_the_identical_receipt(tmp_path):
    ports = Ports()
    with _channel(tmp_path) as channel:
        first = channel.process_outbox_claim(_claim(), ports, ports)
    with _channel(tmp_path) as channel:
        second = channel.process_outbox_claim(_claim(), ports, ports)
        later = channel.process_outbox_claim(replace(_claim(), attempt_id="attempt-2"), ports, ports)
    assert ports.sends == 1
    assert first.as_dict() == second.as_dict()
    assert ports.receipts[:2] == [first.as_dict(), first.as_dict()]
    assert later.status == "unknown"


def test_failed_spool_write_does_not_consume_the_event(tmp_path, monkeypatch):
    seen = SeenLRU()
    with _channel(tmp_path, seen=seen) as channel:
        writer = channel.journal.write_json
        with monkeypatch.context() as patch:
            patch.setattr(channel.journal, "write_json", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
            with pytest.raises(OSError):
                channel.ingest_onebot_event(_event())
        assert len(seen) == 0
        assert channel.journal.write_json == writer
        assert channel.ingest_onebot_event(_event()).accepted


def test_inbound_without_send_time_is_deduplicated_after_submission_and_restart(tmp_path):
    ports = Ports()
    with _channel(tmp_path) as channel:
        assert channel.ingest_onebot_event(_event()).accepted
        assert channel.submit_pending_inbound(ports) == 1
    with _channel(tmp_path) as channel:
        decision = channel.ingest_onebot_event(_event())
        assert decision.reason == "duplicate_durable"
        assert channel.submit_pending_inbound(ports) == 0
    assert len(ports.events) == 1


def test_route_revocation_and_media_obligations_fail_before_external_io(tmp_path):
    ports = Ports()
    with _channel(tmp_path) as channel:
        channel.ingest_onebot_event(_event())
        channel.replace_routes([replace(ROUTE, enabled=False)])
        assert channel.submit_pending_inbound(ports) == 0
        channel.replace_routes([ROUTE])
        receipt = channel.process_outbox_claim(_claim(attachment={"artifact_id": "image-1"}), ports, ports)
    assert not ports.events
    assert ports.sends == 0
    assert receipt.status == "failed"
    assert receipt.reason == "unsupported_outbox_content"


def test_catchup_partial_page_keeps_cursor_and_marks_durable_input_historical(tmp_path):
    class History:
        def get_history_page(self, route, **kwargs):
            return HistoryPage(({**_event(), "time": 100.0},), next_cursor="more", complete=False)

    with _channel(tmp_path, now_fn=lambda: 200.0) as channel:
        report = CatchupRunner(channel, CatchupPolicy((ROUTE.route_id,), max_pages=1)).run(History())
        assert report["spooled"] == 1
        assert report["incomplete"] == 1
        assert not list(channel.journal.catchup_root.glob("*.json"))
        item = channel.journal.read_json(channel.journal.spool_list("inbound")[0])
        assert item["envelope"]["historical"] is True


def test_bounded_poll_uses_structured_claim_identity(tmp_path):
    ports = Ports()
    claim = _claim()
    ports.claims = [{**claim.item, "publication_id": claim.publication_id, "attempt_id": claim.attempt_id}]
    with _channel(tmp_path) as channel:
        assert channel.poll_outbox(ports, ports)[0].status == "platform_accepted"
        assert channel.poll_outbox(ports, ports) == ()
    assert ports.sends == 1
    assert ports.receipts[0]["attempt_id"] == claim.attempt_id


def test_group_ambient_history_and_reply_are_local_only_but_live_self_at_submits(tmp_path):
    ports = Ports()
    events = [
        {**_event(), "message_id": "plain", "message": [{"type": "text", "data": {"text": "ambient"}}]},
        {**_event(), "message_id": "all", "message": [{"type": "at", "data": {"qq": "all"}},
                                                    {"type": "text", "data": {"text": "announcement"}}]},
        {**_event(), "message_id": "reply", "message": [{"type": "reply", "data": {"id": "42"}}]},
    ]
    with _channel(tmp_path) as channel:
        for item in events:
            assert channel.ingest_onebot_event(item).accepted
        assert channel.ingest_onebot_event({**_event(), "message_id": "historical"}, historical=True).accepted
        assert channel.ingest_onebot_event(_event()).accepted
        assert channel.submit_pending_inbound(ports) == 1
        retained = (channel.journal.journal_root / "inbound_context_only.jsonl").read_text(encoding="utf-8")
        assert all(item["message_id"] in retained for item in events)
        assert "historical" in retained
        assert not channel.journal.spool_list("inbound")
    with _channel(tmp_path) as channel:
        assert channel.submit_pending_inbound(ports) == 0
        assert channel.ingest_onebot_event(events[0]).reason == "duplicate_durable"
    assert [item["event_id"] for item in ports.events] == ["message-1"]


def test_local_context_write_failure_never_loses_or_posts_the_passive_event(tmp_path, monkeypatch):
    ports = Ports()
    ambient = {**_event(), "message": [{"type": "text", "data": {"text": "ambient"}}]}
    with _channel(tmp_path) as channel:
        assert channel.ingest_onebot_event(ambient).accepted
        with monkeypatch.context() as patch:
            patch.setattr(channel.journal, "append", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
            with pytest.raises(OSError):
                channel.submit_pending_inbound(ports)
        assert channel.journal.spool_list("inbound")
        assert not ports.events
        assert channel.submit_pending_inbound(ports) == 0
        assert not channel.journal.spool_list("inbound")


def test_mention_policy_requires_trusted_boolean(tmp_path):
    with pytest.raises(ValueError):
        SoyoQQChannel(config=ChannelConfig(ROUTE.account_id, require_group_mention="true"),
                      routes=[ROUTE], data_root=tmp_path)
