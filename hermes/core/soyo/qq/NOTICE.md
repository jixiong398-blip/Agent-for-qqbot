# Soyo QQ channel staging — source and license notice

SPDX-License-Identifier: GPL-3.0-only

This package is a modified/reference-based Soyo channel slice informed by
AsunaCognitionCore's `@asuna/napcat-qq` adapter. It is not represented as a
clean-room implementation or a drop-in upstream adapter.

- Upstream: https://github.com/eamars/AsunaCognitionCore
- Upstream authors: AsunaCognitionCore / napcat-qq contributors.
- Frozen reference: `a89c945a8560e3d7bf702d0815ee91ed7b2a1363`.
- Reference path: `packages/channels/napcat-qq/integration/qqadapter/`.
- License declaration: `packages/channels/napcat-qq/package.json`,
  `@asuna/napcat-qq@0.2.0`, `GPL-3.0-only`.
- Full license: `LICENSE` in this directory. There is no warranty.

Modified on 2026-10-10 for the Soyo staging boundary:

- Typed route/account/event/outbox/receipt contracts replace the upstream
  configuration and HTTP payload coupling.
- Inbound mention/reply/media normalization and outbound `@qq:<digits>`
  encoding retain reference behavior, with bounded inputs and strict identity
  checks. Native media materialization and owner/admin-gated action ports are
  implemented in the DSH worker; the reference adapter itself is not copied.
- Explicit injected ports replace concrete HTTP/WS clients and worker threads.
- Journal persistence adds inbound tombstones, account-bound single-writer
  ownership, a publication fence before send, immutable same-attempt receipts,
  conservative crash recovery and no automatic publication re-send.
- Catch-up is opt-in, bounded, historical and uses the durable ingress path;
  incomplete runs do not advance a cursor past a history gap.

Modified on 2026-10-11 for mention-only group admission: authorized ambient
group events remain in the local journal but are not posted to the host for
model judgment. Only a real self-account mention admits a live group event;
historical events do not create new reply obligations. Private routes retain
their separate authorization and admission behavior.

Modified on 2026-10-11 for native DSH transport: explicit loopback OneBot
HTTP/WS clients, authenticated private Host socket, live member snapshots and
independent corpus/memory I/O. The separate native Host plugin uses the
official Agent/session services. No Hermes agent/Gateway loop is imported.

Modified further on 2026-10-11: bounded operator-only read projections for
native data views and send-time-aware corpus identities preserving legacy
rows. Data browsing cannot wake a model or mutate legacy memory stores.

The reference snapshot is not a complete runnable upstream installation:
faces resources, vendor dependencies and host runtime were not imported.
Historical extraction ledgers are private maintenance records, not public
installation prerequisites. Public source and distribution boundaries are
summarized in `THIRD_PARTY_NOTICES.md` and `MIGRATION.md` at the repository root.

The original Hermes MIT notice for derived contracts/requirements remains
in `core/LICENSE`. This notice does
not change that license or assert that the entire repository is GPL. Combined
distribution, corresponding source and dependency compatibility must be
reviewed before packaging or publication; none is authorized by this change.
