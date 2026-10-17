# SPDX-License-Identifier: MIT
"""Authorized QQ canary: async Soyo -> native GPT file write -> Soyo read -> receipts.

This posts a clearly labelled synthetic owner test to the authenticated Host;
it does NOT claim the test is a real user/OneBot inbound event. Two actual QQ
private publications are expected. Only a fresh /var/tmp test file is written.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx


def native_turns(home: Path, session_id: str, first_seq: int = 0) -> list[dict]:
    paths = list((home / "sessions").glob(f"*/{session_id}/session.v4.jsonl.zstd"))
    assert len(paths) == 1
    raw = subprocess.check_output(["/usr/bin/zstd", "-dc", str(paths[0])], text=True)
    return [row for line in raw.splitlines() if line.strip()
            and (row := json.loads(line)).get("seq", -1) >= first_seq]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--verify-existing", help="Verify a completed canary job without sending again")
    args = parser.parse_args()
    home = args.config.parent
    config = json.loads(args.config.read_text())
    owner = str((config.get("admin_ids") or config["memory_private_peers"])[0])
    existing = json.loads((Path(config['native_root']) / 'jobs' / (args.verify_existing + '.json')).read_text()) if args.verify_existing else None
    nonce = existing['envelope']['event_id'].removeprefix('authorized-native-cooperation-') if existing else uuid.uuid4().hex
    artifact = Path("/var/tmp") / ("soyo-native-cooperation-" + nonce + ".txt")
    body = "COOP_FILE_" + nonce
    waiting = "COOP_PENDING_" + nonce
    done = "COOP_DONE_" + nonce
    event_id = "authorized-native-cooperation-" + nonce
    result = {"status": "unverified", "synthetic_host_input": True, "qq_receipts": [], "test_file": str(artifact)}
    try:
        helper_session = config["collaborator"].get("session_id", "soyo-gpt-helper")
        previous = native_turns(home, helper_session)
        helper_after = 0 if existing else previous[-1]["seq"] + 1
        text = (f"帮我做一下两边合作的文件测试：去问 GPT，让它用 write 创建 {artifact}，"
                f"内容写 {body}，工具参数是 file_path 和 content，写后读回核对。只操作这个新文件，不改其他文件/服务。"
                f"你把事交给它后先回复我 {waiting}，别等结果，也别自己抢先写。"
                f"等 GPT 回来，你自己用 read 读这个文件，看到内容后回复 {done} 和正文。")
        envelope = {"account_id": config["account_id"], "route_id": "qq-private-" + owner,
                    "message_type": "private", "target_id": owner, "sender_id": owner,
                    "event_id": event_id, "occurred_at": time.time(), "text": text}
        with httpx.Client(transport=httpx.HTTPTransport(uds=config["host_socket"]), base_url="http://soyo.local",
                          trust_env=False, headers={"Authorization": "Bearer " + config["host_key"]},
                          timeout=httpx.Timeout(None, connect=10, write=10, pool=10)) as client:
            if existing:
                origin_key = existing['key']
            else:
                accepted = client.post("/inbound", json={"envelope": envelope, "context": {"recent": []}}).raise_for_status().json()
                assert accepted["kind"] == "accepted", accepted
                origin_key = accepted["key"]
            result["origin_job_key"] = origin_key
            until = time.monotonic() + 600
            jobs = []
            while True:
                jobs = [json.loads(path.read_text()) for path in Path(config["native_root"]).joinpath("jobs").glob("*.json")]
                jobs = [job for job in jobs if job.get("key") == origin_key or job.get("origin_job_key") == origin_key]
                if len(jobs) >= 2 and all(job.get("receipt") for job in jobs):
                    break
                origin = next((job for job in jobs if job.get('key') == origin_key), None)
                if origin and origin.get('state') == 'complete' and origin.get('receipt') and not origin.get('consultation_ids'):
                    raise AssertionError('main role did not call GPT; not a GPT timeout')
                if any(job.get("state") in {"failed", "suppressed"} for job in jobs):
                    raise AssertionError({"failed_jobs": [{"key": j["key"], "state": j["state"], "reason": j.get("reason")} for j in jobs]})
                if time.monotonic() > until:
                    raise AssertionError("observer ended; pending work not cancelled or repeated")
                time.sleep(2)
            origin = next(job for job in jobs if job["key"] == origin_key)
            continuation = next(job for job in jobs if job.get("internal_source") == "gpt-consultation")
            assert waiting in origin["publication"]["text"]
            assert done in continuation["publication"]["text"] and body in continuation["publication"]["text"]
            for job in [origin, continuation]:
                assert job["receipt"]["status"] == "platform_accepted"
                result["qq_receipts"].append({"publication_id": job["publication"]["publication_id"],
                                             "platform_message_id": job["receipt"]["platform_message_id"],
                                             "part_count": job["receipt"]["response"].get("part_count")})
            gpt = native_turns(home, helper_session, helper_after)
            gpt_calls = [row["data"] for row in gpt if row.get("type") == "tool/call"]
            writes = [call for call in gpt_calls if call.get("name") == "write" and
                      json.loads(call["arguments"]).get("file_path") == str(artifact)]
            assert writes, {"actual_gpt_tools": [call.get("name") for call in gpt_calls]}
            assert any(row.get('type') == 'tool/result' and
                       row['data']['message'].get('toolCallId') in {call['callId'] for call in writes} and
                       not row['data']['message'].get('isError') for row in gpt), 'GPT native write must succeed'
            soyo = native_turns(home, continuation["session_id"])
            soyo = [row for row in soyo if row.get("data", {}).get("turn") == continuation["turn"]]
            reads = [row["data"] for row in soyo if row.get("type") == "tool/call" and
                     row["data"].get("name") == "read" and json.loads(row["data"]["arguments"]).get("file_path") == str(artifact)]
            assert reads, "Soyo must actually read GPT's file, not echo its report"
            assert any(row.get('type') == 'tool/result' and
                       row['data']['message'].get('toolCallId') in {call['callId'] for call in reads} and
                       not row['data']['message'].get('isError') and body in json.dumps(row['data']['message'].get('content', []))
                       for row in soyo), 'Soyo native read must return the stored marker'
            assert artifact.stat().st_uid == 0 and artifact.read_text().strip() == body
            result.update(status="verified", gpt_native_write=True, soyo_native_read=True,
                          file_owner_uid=artifact.stat().st_uid,
                          continuation_capabilities=continuation["binding"]["capabilities"])
    except BaseException as error:
        result["error"] = str(error)[:1600]
        raise
    finally:
        args.evidence.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(args.evidence, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
