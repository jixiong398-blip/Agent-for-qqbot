# SPDX-License-Identifier: GPL-3.0-only
"""Offline subprocess probe: journal/fsync/flock/restart, NOT DSH or QQ delivery.

Run only after closing the implementation batch.  Work directory is explicit;
all "external sends" here are file markers from a substituted platform port.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from soyo.qq import ChannelConfig, ChannelRoute, OutboxClaim, PortResult, SoyoQQChannel, SoyoQQJournal


ROUTE = ChannelRoute("probe-group", "group", "123456", "900001", frozenset({"100001"}))
CLAIM = OutboxClaim("probe-publication", "probe-attempt", {
    "account_id": ROUTE.account_id, "route_id": ROUTE.route_id,
    "target": {"type": "group", "id": ROUTE.target_id}, "text": "offline fixture",
})


def channel(root: Path) -> SoyoQQChannel:
    return SoyoQQChannel(config=ChannelConfig(ROUTE.account_id), routes=[ROUTE], data_root=root)


class Ports:
    def __init__(self, root: Path, mode: str = "recover") -> None:
        self.root, self.mode, self.receipts = root, mode, []

    def send(self, plan):
        if self.mode == "recover":
            raise AssertionError("recovery tried to resend")
        SoyoQQJournal.write_json(self.root / "platform-marker.json", {"calls": 1})
        if self.mode == "kill-in-send":
            print("SEND_STARTED", flush=True)
            threading.Event().wait(60)
            raise AssertionError("parent did not kill the probe child")
        return {"retcode": 0, "data": {"message_id": 42}}

    def post_receipt(self, publication_id, receipt):
        self.receipts.append(receipt)
        if self.mode == "exit-in-receipt":
            SoyoQQJournal.write_json(self.root / "host-marker.json", receipt)
            os._exit(74)
        return PortResult("accepted")


def run_probe(workdir: Path) -> dict[str, object]:
    if not workdir.is_absolute():
        raise ValueError("probe requires an absolute work directory")
    with tempfile.TemporaryDirectory(prefix="soyo-qq-probe-", dir=workdir) as temporary:
        root = Path(temporary)
        crash = root / "send-crash"
        child = subprocess.Popen([sys.executable, __file__, "child", str(crash), "kill-in-send"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            assert ready and child.stdout.readline().strip() == "SEND_STARTED", "child did not reach send"
            try:
                unexpected = channel(crash)
            except RuntimeError:
                lock_denied = True
            else:
                unexpected.close()
                raise AssertionError("second writer acquired the same root")
            child.kill()
            child.communicate(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
        ports = Ports(crash)
        with channel(crash) as worker:
            assert worker.replay_receipts(ports) == 1
            saved = worker.process_outbox_claim(CLAIM, ports, ports)
            assert saved.status == "unknown" and saved.reason == "platform_send_interrupted"
            assert ports.receipts == [saved.as_dict(), saved.as_dict()]
        assert json.loads((crash / "platform-marker.json").read_text()) == {"calls": 1}

        receipt_gap = root / "receipt-crash"
        result = subprocess.run([sys.executable, __file__, "child", str(receipt_gap), "exit-in-receipt"],
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 74, result.stderr
        original = json.loads((receipt_gap / "host-marker.json").read_text())
        ports = Ports(receipt_gap)
        with channel(receipt_gap) as worker:
            assert worker.replay_receipts(ports) == 1
            assert ports.receipts == [original]
            assert original["status"] == "platform_accepted" and original["platform_message_id"] == "42"
        forbidden = [name for name in sys.modules if name in ("run_agent", "hermes_state", "hermes_constants")
                     or name.startswith(("gateway.", "plugins.platforms.onebot"))]
        assert not forbidden, forbidden
        return {"status": "passed", "single_writer_lock": lock_denied,
                "send_crash": "unknown_without_resend", "receipt_crash": "identical_receipt_without_resend",
                "hermes_runtime_imports": forbidden, "dsh_or_qq_delivery_verified": False}


if __name__ == "__main__":
    if sys.argv[1] == "child":
        root, mode = Path(sys.argv[2]), sys.argv[3]
        ports = Ports(root, mode)
        with channel(root) as worker:
            worker.process_outbox_claim(CLAIM, ports, ports)
    else:
        print(json.dumps(run_probe(Path(sys.argv[1])), sort_keys=True))
