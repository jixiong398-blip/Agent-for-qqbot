# SPDX-License-Identifier: MIT
"""Actual native Agent/bash/Responses probe; never sends QQ by default.

Run only after closing the current implementation/config batch, as root when
the production Host owns its socket. A marker alone is not proof: this reads
native tool results and requires an actual bash exit 0 / uid 0.
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


def events(home: Path, session_id: str) -> list[dict]:
    matches = list((home / "sessions").glob(f"*/{session_id}/session.v4.jsonl.zstd"))
    if len(matches) != 1:
        raise AssertionError("exact native session log required")
    raw = subprocess.check_output(["/usr/bin/zstd", "-dc", str(matches[0])], text=True)
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def proof(home: Path, session_id: str, marker: str) -> dict:
    records = events(home, session_id)
    start = next(row for row in reversed(records) if row.get("type") == "turn/start")
    turn = [row for row in records if row.get("seq", -1) >= start["seq"]]
    end = next(row for row in reversed(turn) if row.get("type") == "turn/end")
    calls = [row["data"] for row in turn if row.get("type") == "tool/call"]
    result_ids = {call["callId"] for call in calls if call.get("name") == "bash" and
                  json.loads(call["arguments"]).get("command", "").strip() == "id -u"}
    outputs = []
    for row in turn:
        if row.get("type") != "tool/result":
            continue
        message = row["data"]["message"]
        if message.get("toolCallId") in result_ids and not message.get("isError"):
            outputs.append("\n".join(block.get("text", "") for block in message.get("content", []) if block.get("type") == "text"))
    assistants = [row for row in turn if row.get("type") == "assistant/message"]
    final = "".join(block.get("text", "") for block in assistants[-1]["data"]["message"]["content"] if block.get("type") == "text")
    # Native bash renders stdout only on exit 0; nonzero/signal/timeout appends
    # a marker. Do not invent an "exit code: 0" marker that it never emits.
    root_result = any(value.strip() == "0" for value in outputs)
    header = next(row["data"]["header"] for row in reversed(turn) if row.get("type") == "request/header")
    selection = header.get("config", {})
    result = {"session_id": session_id, "turn": start["data"]["turn"],
              "completed": end["data"]["reason"]["kind"] == "completed",
              "tools_called": [call.get("name") for call in calls], "uid_zero_tool_result": root_result,
              "marker_in_final": marker in final, "provider": selection.get("provider"), "model": selection.get("model")}
    assert result["completed"] and root_result and result["marker_in_final"], result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    home = args.config.parent
    config = json.loads(args.config.read_text())
    owner = str((config.get("admin_ids") or config["memory_private_peers"])[0])
    nonce = uuid.uuid4().hex
    main_marker, gpt_marker = "SOYO_ROOT_" + nonce, "GPT_ROOT_" + nonce
    envelope = {"account_id": config["account_id"], "route_id": "qq-private-" + owner,
                "message_type": "private", "target_id": owner, "sender_id": owner,
                "event_id": "direct-root-probe-" + nonce, "occurred_at": time.time(),
                "text": f"原生主机工具只读验证：先调用 soyo_think，然后调用 bash 执行唯一命令 id -u，description 写确认当前用户。检查真实 exit code 后最终仅回复 {main_marker}。本轮不要问 GPT、不要调用其他工具或更改文件。"}
    evidence = {"status": "unverified", "observer_uid": os.getuid(), "qq_sends": 0}
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=config["host_socket"]), base_url="http://soyo.local",
                          trust_env=False, headers={"Authorization": "Bearer " + config["host_key"]},
                          timeout=httpx.Timeout(None, connect=10, write=10, pool=10)) as client:
            health = client.post("/health").raise_for_status().json()
            evidence["host"] = health
            assert health["effective_uid"] == 0 and health["host_mode"] == "direct-root", health
            accepted = client.post("/probe", json={"envelope": envelope, "context": {"recent": []}}).raise_for_status().json()
            assert accepted["kind"] == "accepted", accepted
            key = accepted["key"]
            observed_until = time.monotonic() + 240
            while True:
                job = client.post("/job", json={"key": key}).raise_for_status().json()
                if job["state"] in {"complete", "failed", "suppressed"}:
                    break
                if time.monotonic() > observed_until:
                    raise AssertionError("observer ended; native turn not cancelled or retried")
                time.sleep(1)
            assert job["state"] == "complete", job
            evidence["soyo"] = proof(home, job["session_id"], main_marker)
            print(json.dumps({"soyo_native_root": evidence["soyo"]}), flush=True)
            result = client.post("/consult-probe", json={"question":
                f"原生工具只读验证。直接调用 bash 执行唯一命令 id -u，description 写 Confirm native process user。检查真实工具结果及 exit code 后，最终只回复 {gpt_marker}。禁止更改文件或调用其他工具。"}).raise_for_status().json()
            assert result["state"] == "answered" and gpt_marker in result["text"], result
            evidence["gpt"] = proof(home, result["session_id"], gpt_marker)
            assert evidence["gpt"]["provider"] == config["collaborator"]["provider"], evidence
            evidence["status"] = "verified"
            print(json.dumps({"gpt_native_root": evidence["gpt"]}), flush=True)
    except BaseException as error:
        evidence["error"] = str(error)[:1600]
        raise
    finally:
        args.evidence.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd = os.open(args.evidence, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(evidence, file, ensure_ascii=False, indent=2)
        print(json.dumps(evidence, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
