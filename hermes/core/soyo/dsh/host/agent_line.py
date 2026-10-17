#!/usr/bin/env python3
"""Minimal route-scoped Agent Line client; tokens never appear in argv/output."""
from __future__ import annotations

import argparse
import json
import os
import os
import stat
from pathlib import Path

import httpx
from soyo.platform import assert_private
from soyo.transport import private_client


def load(path: Path) -> dict:
    assert_private(path, max_bytes=2 * 1024 * 1024)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", choices=("send", "poll", "status", "receipt"))
    parser.add_argument("--route", required=True)
    parser.add_argument("--event-id")
    parser.add_argument("--text")
    parser.add_argument("--publication-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--receipt-status", choices=("platform_accepted", "failed", "unknown"))
    args = parser.parse_args()
    config = load(args.config)
    route = next((item for item in (config.get("agent_line", {}).get("routes", [])) if item.get("id") == args.route), None)
    if not route:
        raise SystemExit("unknown Agent Line route")
    assert_private(Path(route["key_file"]), max_bytes=129)
    key = Path(route["key_file"]).read_text(encoding="utf-8").strip()
    socket = config.get("agent_line_socket") or config.get("agent_line", {}).get("socket")
    headers = {"Authorization": "Bearer " + key}
    payload = {"route_id": args.route}
    if args.command == "send":
        if not args.event_id or args.text is None:
            raise SystemExit("send requires --event-id and --text")
        payload.update(event_id=args.event_id, text=args.text)
        endpoint = "/send"
    elif args.command == "poll":
        endpoint = "/poll"
    elif args.command == "status":
        endpoint = "/status"
    else:
        if not args.publication_id or not args.attempt_id or not args.receipt_status:
            raise SystemExit("receipt requires --publication-id --attempt-id --receipt-status")
        payload.update(publication_id=args.publication_id,
                       receipt={"publication_id": args.publication_id, "attempt_id": args.attempt_id,
                                "status": args.receipt_status, "reason": "client_received",
                                **({"platform_message_id": "agent-line-client"} if args.receipt_status == "platform_accepted" else {})})
        endpoint = "/receipt"
    with private_client(config, "agent_line", key=key, timeout=30) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
