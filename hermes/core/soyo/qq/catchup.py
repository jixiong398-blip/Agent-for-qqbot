# SPDX-License-Identifier: GPL-3.0-only
# Modified/reference-based Soyo slice, 2026-10-10. See NOTICE.md and LICENSE.
"""Explicit, bounded history replay into the same durable inbound path.

This does not fetch QQ history by itself.  The injected HistoryPort owns the
OneBot history API shape, authentication and deadlines.  Disabled by default;
an incomplete page run never advances the durable cursor past a missed gap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, TYPE_CHECKING

from .contracts import bounded_id
from .host import HistoryPage, HistoryPort
from .journal import identity_digest

if TYPE_CHECKING:
    from .service import SoyoQQChannel


@dataclass(frozen=True)
class CatchupPolicy:
    route_ids: tuple[str, ...] = ()
    lookback_hours: float = 1.0
    max_pages: int = 5
    page_size: int = 100

    def __post_init__(self) -> None:
        if (not isinstance(self.route_ids, tuple) or len(self.route_ids) > 32
                or len(set(self.route_ids)) != len(self.route_ids)
                or any(not isinstance(route, str) or bounded_id(route, limit=160) != route
                       for route in self.route_ids)):
            raise ValueError("catchup requires explicit, unique route ids")
        if (isinstance(self.lookback_hours, bool) or not isinstance(self.lookback_hours, (int, float))
                or not math.isfinite(self.lookback_hours) or not 0 < self.lookback_hours <= 24
                or isinstance(self.max_pages, bool) or not isinstance(self.max_pages, int)
                or not 1 <= self.max_pages <= 5
                or isinstance(self.page_size, bool) or not isinstance(self.page_size, int)
                or not 1 <= self.page_size <= 100):
            raise ValueError("catchup limits exceed the staging budget")


def _timestamp(event: Mapping[str, Any]) -> float:
    value = event.get("time")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value) if math.isfinite(value) and value > 0 else 0.0


class CatchupRunner:
    def __init__(self, channel: "SoyoQQChannel", policy: CatchupPolicy = CatchupPolicy()) -> None:
        self.channel = channel
        self.policy = policy

    def run(self, history: HistoryPort) -> dict[str, int]:
        """One recovery cycle; no outbox, platform send or host POST is used.

        HistoryPort must include the since boundary.  Equal-time rows are safe:
        their exact route/event/time dedup keys remain in the channel journal.
        A cursor is a send time, not an ordered message id.
        """

        totals = {"routes": 0, "rows": 0, "spooled": 0, "complete": 0, "incomplete": 0}
        with self.channel._worker_lock:
            if self.channel._closed:
                raise RuntimeError("QQ channel is closed")
            now = self.channel._now()
            for route_id in self.policy.route_ids:
                route = self.channel.routes.get(route_id)
                if route is None or not route.enabled:
                    self.channel.counters.inc("catchup_route_revoked")
                    continue
                path = self.channel.journal.catchup_root / (identity_digest(route.account_id, route.route_id) + ".json")
                since = max(0.0, now - self.policy.lookback_hours * 3600)
                try:
                    saved = self.channel.journal.read_json(path)
                except FileNotFoundError:
                    pass
                else:
                    moment = saved.get("occurred_at") if isinstance(saved, dict) else None
                    if (not isinstance(saved, dict) or saved.get("account_id") != route.account_id
                            or saved.get("route_id") != route_id or isinstance(moment, bool)
                            or not isinstance(moment, (int, float)) or not math.isfinite(moment)
                            or not 0 <= moment <= now):
                        raise ValueError("corrupt catchup cursor; refusing to skip history")
                    since = float(moment)
                totals["routes"] += 1
                newest = since
                cursor = None
                cursors = set()
                complete = False
                for _ in range(self.policy.max_pages):
                    try:
                        page = history.get_history_page(route, since=since, cursor=cursor, limit=self.policy.page_size)
                    except Exception:
                        self.channel.counters.inc("catchup_history_error")
                        break
                    if (not isinstance(page, HistoryPage) or not isinstance(page.events, (tuple, list))
                            or len(page.events) > self.policy.page_size
                            or any(not isinstance(event, Mapping) for event in page.events)
                            or not isinstance(page.complete, bool)):
                        self.channel.counters.inc("catchup_invalid_page")
                        break
                    for event in sorted(page.events, key=_timestamp):
                        moment = _timestamp(event)
                        totals["rows"] += 1
                        if not moment or not since <= moment <= now:
                            continue
                        decision = self.channel.ingest_onebot_event(event, historical=True, expected_route_id=route_id)
                        if decision.accepted:
                            totals["spooled"] += 1
                        if decision.accepted or decision.reason in ("duplicate_local", "duplicate_durable"):
                            newest = max(newest, moment)
                    if page.complete and page.next_cursor is None:
                        complete = True
                        break
                    next_cursor = bounded_id(page.next_cursor, limit=240)
                    if page.complete or not next_cursor or next_cursor in cursors:
                        self.channel.counters.inc("catchup_invalid_cursor")
                        break
                    cursors.add(next_cursor)
                    cursor = next_cursor
                if complete:
                    # Spool commits precede cursor commit.  A crash before this
                    # write replays input, but can never skip unpersisted input.
                    self.channel.journal.write_json(path, {
                        "account_id": route.account_id, "route_id": route_id, "occurred_at": newest,
                    })
                    totals["complete"] += 1
                else:
                    totals["incomplete"] += 1
                    self.channel.counters.inc("catchup_incomplete")
        return totals
