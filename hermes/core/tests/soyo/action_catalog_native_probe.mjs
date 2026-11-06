// SPDX-License-Identifier: MIT
// Real installed Session and V4 codec cold-restore gate. No models or QQ, no mocks of the critical boundary.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ensureActionCatalog, recoverActionCatalogEvents } from '../../soyo/dsh/host/action-catalog.mjs';
const require = createRequire(resolve(process.argv[2], 'package.json'));
const native = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-session')).href);
const pr = createRequire(require.resolve('@deepseek-ai/dsh-session-persistence-jsonl'));
const format = await import(pathToFileURL(pr.resolve('@deepseek-ai/dsh-session-format-v3-to-v4')).href);
const header = { version: 4, id: 'catalog-recovery-probe', createdAt: 1, isSeeded: false, delegationDepth: 0 };
const p = native.Session.create(header.id, [], header, 0);
const child = { id: 'probe-child', header: { createdAt: 2, parentSession: p.id } };
const descriptor = { mode: 'one-shot', label: 'Initial work' };
ensureActionCatalog(p, child, descriptor);
ensureActionCatalog(p, child, { ...descriptor, label: 'Second work in same child' });
const known = new Set(native.KNOWN_SESSION_EVENT_TYPES);
const cold = events => {
  const serialized = events.map(event => format.releasedV4SessionFormatCodec.encodeEvent(event));
  const restored = JSON.parse(JSON.stringify(serialized));
  format.restoreReleasedV4Artifact({ header, inheritedEventCount: 0, events: restored }, known);
  return native.Session.create(header.id, restored, header, 0);
};
const events = p.snapshotEvents();
cold(events);
const catalog = events.find(event => event.type === 'subagent/catalog');
assert(catalog);
const broken = [...events, { ...catalog, seq: events.length, time: Date.now() }];
assert.throws(() => cold(broken), /duplicate catalog child/);
const recovered = recoverActionCatalogEvents(broken);
cold(recovered.events);
assert.deepEqual(recovered.repairedSeqs, [events.length]);
const { Context } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')).href);
const persistence = await import(pathToFileURL(require.resolve('@deepseek-ai/dsh-session-persistence-jsonl')).href);
const root = await mkdtemp(join(tmpdir(), 'action-catalog-persistence-probe-'));
let ctx = new Context();
try {
  await ctx.plugin(persistence, { root, compression: 'zstd' });
  const writer = await ctx.sessionPersistence.create(header);
  try { await writer.append(recovered.events); await writer.flush(); } finally { await writer.close(); }
  await ctx.fiber.dispose();
  ctx = new Context();
  await ctx.plugin(persistence, { root, compression: 'zstd' });
  const reader = await ctx.sessionPersistence.open(header.id, 'read');
  try { assert.deepEqual((await reader.read()).events, recovered.events); } finally { await reader.close(); }
} finally { await ctx.fiber.dispose(); }
console.log(JSON.stringify({ native_duplicate_reproduced: true, repeated_discovery_cold_restore: true,
  audit_recovery_cold_restore: true, native_checksummed_zstd_cold_read: true, models_called: 0, qq_connected: false }));
