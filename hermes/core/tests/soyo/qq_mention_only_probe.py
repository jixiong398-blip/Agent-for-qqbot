"""Offline real ingress/SQLite/admission/context probe; model and QQ edges stop here.

No production home, credentials, network, service restart or real model requests.
Run only after the implementation batch is closed, with an explicit workdir.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


ACCOUNT, GROUP, SENDER = "900001", "123456", "100001"


def event(index: int, segments: list[dict], *, private: bool = False) -> dict:
    segments = deepcopy(segments)
    for segment in segments:
        if segment.get("type") == "forward":
            segment["data"]["id"] += "-" + str(index)
    return {"post_type": "message", "message_type": "private" if private else "group",
            "self_id": int(ACCOUNT), "group_id": int(GROUP), "user_id": int(SENDER),
            "sender": {"nickname": "probe-member"}, "message_id": str(index),
            "time": 1_700_000_000, "message": segments}


def text(value: str) -> dict:
    return {"type": "text", "data": {"text": value}}


def at(target: str = ACCOUNT) -> dict:
    return {"type": "at", "data": {"qq": target}}


async def probe(home: Path) -> dict:
    from gateway.config import PlatformConfig
    from plugins.platforms.onebot.adapter import OneBotAdapter, get_state_db_path
    from plugins.platforms.onebot.group_executor import AgentOutcome
    from plugins.platforms.onebot.trigger_coordinator import TriggerRequest
    from soyo.qq import ChannelConfig, ChannelRoute, PortResult, SoyoQQChannel

    counts = {"judge": 0, "agent_boundary": 0, "recall": 0, "forward": 0,
              "media": 0, "post_reply_summary": 0, "network": 0}

    def forbidden(*args, **kwargs):
        counts["network"] += 1
        raise AssertionError("Probe must not cross the network/process boundary")

    adapter = OneBotAdapter(PlatformConfig(enabled=True, extra={
        "require_mention": True, "auto_discover_token": False,
    }))
    assert adapter._load_config() and adapter._require_mention
    adapter._self_id = int(ACCOUNT)

    async def judge(*args, **kwargs):
        counts["judge"] += 1
        raise AssertionError("Mention-only traffic reached the judge")

    async def forward(*args, **kwargs):
        counts["forward"] += 1
        return "", "", []

    async def media(*args, **kwargs):
        counts["media"] += 1
        return []

    async def summary(*args, **kwargs):
        counts["post_reply_summary"] += 1

    def recall(*args, **kwargs):
        counts["recall"] += 1
        return ""

    first_started, release = asyncio.Event(), asyncio.Event()
    built_events = []

    async def agent_boundary(built_event):
        counts["agent_boundary"] += 1
        built_events.append(built_event)
        if len(built_events) == 1:
            first_started.set()
            await release.wait()
        return AgentOutcome(kind="failed", failed=True)

    adapter._trigger_coordinator._invoke_judge = judge
    adapter._extract_forward_content = forward
    adapter._get_image_files = media
    adapter._recall_context = recall
    adapter._update_rolling_summary = summary
    adapter._group_executor._run_agent_locked = agent_boundary
    worker = asyncio.create_task(adapter._persist_worker())
    ingested = 0
    try:
        with patch.object(socket.socket, "connect", forbidden), patch.object(subprocess, "Popen", forbidden):
            gs = adapter._group_states.get(GROUP)
            gs.enter_attentive()  # previous replies must not enable ambient continuation
            passive = [[text("ambient-marker")], [text("probe-bot 你在吗")], [at("all"), text("公告")],
                       [at("100002"), text("叫别人")],
                       [{"type": "reply", "data": {"id": "old-bot", "text": "quoted @bot"}}, text("续问")],
                       [{"type": "image", "data": {"file": "not-downloaded", "url": "https://example.invalid/image"}}],
                       [{"type": "forward", "data": {"id": "forward-not-fetched"}}],
                       [text("[卡片]不调查")]]
            for index in range(80):
                await adapter._process_message(event(index + 1, passive[index % len(passive)]))
                ingested += 1
            await adapter._handle_poke({"target_id": int(ACCOUNT), "group_id": int(GROUP), "user_id": int(SENDER)})
            # The actual executor/worker retry hooks may not reopen admission.
            adapter._trigger_coordinator._schedule_judge(GROUP, gs.next_seq, {})
            adapter._group_executor._rejudge_latest(GROUP, gs)
            adapter._group_executor.schedule(TriggerRequest(
                GROUP, gs.next_seq, "mention", "reply-only bypass",
                raw_msg={"_reply_to_bot": True}, is_mention=True))
            await asyncio.sleep(0.02)
            assert not adapter._trigger_coordinator._judge_tasks
            assert not adapter._group_executor._runners
            assert not adapter._media_pipeline._tasks
            assert all(value == 0 for value in counts.values()), counts

            await adapter._process_message(event(81, [at(), text("first-direct")]))
            ingested += 1
            await asyncio.wait_for(first_started.wait(), timeout=10)
            assert "ambient-marker" in built_events[0].channel_prompt
            await adapter._process_message(event(82, [text("ambient-during-direct")]))
            await adapter._process_message(event(83, [at(), text("second-direct")]))
            ingested += 2
            release.set()
            async with asyncio.timeout(10):
                while adapter._group_executor._runners:
                    await asyncio.sleep(0.01)
            assert [item.message_id for item in built_events] == ["81", "83"]
            assert "ambient-during-direct" in built_events[1].channel_prompt
            assert counts["judge"] == counts["media"] == counts["network"] == 0
            assert counts["forward"] == counts["recall"] == counts["agent_boundary"] == 2
            await asyncio.wait_for(adapter._persist_queue.join(), timeout=10)

            with sqlite3.connect(get_state_db_path()) as db:
                corpus_count = db.execute("SELECT COUNT(*) FROM corpus_messages WHERE chat_id=?", (GROUP,)).fetchone()[0]
                raw_image_rows = db.execute("SELECT COUNT(*) FROM corpus_messages WHERE content_readable LIKE '%未解析%' AND image_descriptions='[]'").fetchone()[0]
            assert corpus_count == ingested and raw_image_rows == 10, (corpus_count, ingested, raw_image_rows)

            group = ChannelRoute("probe-group", "group", GROUP, ACCOUNT, frozenset({SENDER}))
            dm = ChannelRoute("probe-dm", "private", SENDER, ACCOUNT)
            posted = []

            class Host:
                def post_event(self, envelope):
                    posted.append(envelope)
                    return PortResult("accepted")

            with SoyoQQChannel(config=ChannelConfig(ACCOUNT), routes=[group, dm], data_root=home / "channel") as channel:
                for index, segments in enumerate(passive, start=101):
                    assert channel.ingest_onebot_event(event(index, segments)).accepted
                assert channel.ingest_onebot_event(event(120, [at(), text("live-at")])).accepted
                assert channel.ingest_onebot_event(event(121, [at(), text("historical-at")]), historical=True).accepted
                assert channel.ingest_onebot_event(event(122, [text("dm-without-at")], private=True)).accepted
                assert channel.submit_pending_inbound(Host()) == 2
                retained = (channel.journal.journal_root / "inbound_context_only.jsonl").read_text().splitlines()
                assert len(retained) == len(passive) + 1
                assert not channel.journal.spool_list("inbound")
            with SoyoQQChannel(config=ChannelConfig(ACCOUNT), routes=[group, dm], data_root=home / "channel") as channel:
                assert channel.submit_pending_inbound(Host()) == 0
                assert channel.ingest_onebot_event(event(101, passive[0])).reason == "duplicate_durable"
            assert [item["event_id"] for item in posted] == ["120", "122"]

            return {"status": "passed", "counts": counts, "group_corpus_rows": corpus_count,
                    "passive_images_retained_without_inference": raw_image_rows,
                    "mention_fifo_with_ambient_context": True, "staging_host_posts": len(posted),
                    "staging_context_only_records": len(retained), "staging_restart_without_replay": True,
                    "real_model_calls": 0, "real_qq_sends": 0, "dsh_or_qq_delivery_verified": False}
    finally:
        release.set()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await adapter._trigger_coordinator.close()
        adapter._media_pipeline.cancel_all()
        await adapter.cancel_background_tasks()


if __name__ == "__main__":
    workdir = Path(sys.argv[1])
    assert workdir.is_absolute() and workdir.is_dir()
    with tempfile.TemporaryDirectory(prefix="qq-mention-probe-", dir=workdir) as temporary:
        home = Path(temporary)
        os.environ["HOME"] = str(home)
        os.environ["HERMES_HOME"] = str(home)
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        print(json.dumps(asyncio.run(probe(home)), sort_keys=True))
