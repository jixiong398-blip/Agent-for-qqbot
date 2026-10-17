#!/usr/bin/env python3
"""Operator entry point for the Hermes -> native DSH Schedule migration.

The default is a dry plan.  ``--apply`` creates only future native Schedule
rows, records the legacy id mapping, and never edits or re-enables jobs.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx
from soyo.platform import assert_private
from soyo.transport import private_client


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = args.config
    assert_private(path, max_bytes=2 * 1024 * 1024)
    config = json.loads(path.read_text(encoding="utf-8"))
    headers = {"Authorization": "Bearer " + config["host_key"]}
    with private_client(config, "automation", timeout=20) as client:
        response = client.post("/migrate-schedules", json={"dry_run": not args.apply})
        response.raise_for_status()
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
