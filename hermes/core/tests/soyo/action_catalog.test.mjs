// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import test from 'node:test';
import { actionWorkRegistryKey, canReuseActionWork, ensureActionCatalog, normalizeActionWorkKey,
  recoverActionCatalogEvents, sameActionScope } from '../../soyo/dsh/host/action-catalog.mjs';

const descriptor = { mode: 'one-shot', label: 'First bounded task' };
const child = { id: 'child', header: { parentSession: 'parent', createdAt: 10 } };
const parent = (events = [], inheritedEventCount = 0) => ({ id: 'parent', inheritedEventCount,
  snapshotEvents: () => events,
  append(type, data) { events.push({ seq: events.length, time: 20, type, data }); } });

test('repeated task discovery registers one child, not one catalog per task', () => {
  const p = parent();
  assert.equal(ensureActionCatalog(p, child, descriptor), true);
  for (let i = 0; i < 10; i++) assert.equal(ensureActionCatalog(p, child, { ...descriptor, label: 'Follow up ' + i }), false);
  assert.equal(p.snapshotEvents().length, 1);
});
test('conflicting identities, damaged catalogs and different parents fail closed', () => {
  assert.throws(() => ensureActionCatalog(parent(), { ...child, header: { ...child.header, parentSession: 'other' } }, descriptor), /different parent/);
  const p = parent(); ensureActionCatalog(p, child, descriptor);
  assert.throws(() => ensureActionCatalog(p, { ...child, header: { ...child.header, createdAt: 99 } }, descriptor), /identity changed/);
  assert.throws(() => ensureActionCatalog(parent([...p.snapshotEvents(), { ...p.snapshotEvents()[0], seq: 1 }]), child, descriptor), /explicit recovery/);
});
test('repair keeps all event positions and payloads and is idempotent', () => {
  const p = parent(); ensureActionCatalog(p, child, descriptor);
  const first = p.snapshotEvents()[0];
  const events = [first, { seq: 1, time: 30, type: 'user/message', data: { text: 'keep' } },
    { ...first, seq: 2, time: 40, data: { ...first.data, label: 'New task same child' } }];
  const recovered = recoverActionCatalogEvents(events);
  assert.deepEqual(recovered.repairedSeqs, [2]);
  assert.deepEqual(recovered.events[0], events[0]); assert.deepEqual(recovered.events[1], events[1]);
  assert.deepEqual(recovered.events[2], { ...events[2], type: 'plugin:soyo/action-catalog-reuse', ignorable: true });
  assert.deepEqual(recoverActionCatalogEvents(recovered.events).repairedSeqs, []);
  assert.throws(() => recoverActionCatalogEvents([first, { ...first, seq: 1, data: { ...first.data, childCreatedAt: 99 } }]), /Conflicting/);
});
test('inherited catalogs do not count as this parent discovering its child', () => {
  const p = parent(); ensureActionCatalog(p, child, descriptor);
  const seeded = parent(p.snapshotEvents(), 1);
  assert.equal(ensureActionCatalog(seeded, child, descriptor), true);
});
test('work reuse cannot cross parent, sender, capabilities or policy epochs', () => {
  const actor = { kind: 'qq-scene', route_id: 'scene', sender_id: 'owner', policy_epoch: 1,
    session_class: 'owner_private', capabilities: ['host.root', 'action.delegate'] };
  const task = { parent_session: 'parent', actor };
  assert(sameActionScope(task, { ...actor, capabilities: [...actor.capabilities].reverse() }, 'parent', false));
  assert(!sameActionScope(task, actor, 'other', false));
  assert(!sameActionScope(task, { ...actor, sender_id: 'stranger' }, 'parent', false));
  assert(!sameActionScope(task, { ...actor, policy_epoch: 2 }, 'parent', false));
  assert(!sameActionScope(task, { ...actor, capabilities: ['action.delegate'] }, 'parent', false));
  assert(!sameActionScope(task, actor, 'parent', true));
});

test('action continuation is explicit and bounded; an omitted key cannot reuse a child', () => {
  const actor = { kind: 'qq-scene', route_id: 'qq-private-test', sender_id: 'owner', policy_epoch: 1,
    session_class: 'owner_private', capabilities: ['host.root', 'action.delegate'] };
  const previous = { parent_session: 'parent', actor, sandbox_only: false, state: 'completed' };
  const held = { session_id: 'soyo-action-child', last_used_at: 900 };
  assert.equal(normalizeActionWorkKey(undefined), null);
  assert.equal(normalizeActionWorkKey('image-ref'), 'image-ref');
  assert.equal(actionWorkRegistryKey(actor, 'image-ref'), 'qq-scene:qq-private-test:image-ref');
  assert.equal(canReuseActionWork({ held: null, previous, actor, parentId: 'parent', sandboxOnly: false,
    ttlMs: 200, now: 1000 }), false);
  assert.equal(canReuseActionWork({ held, previous, actor, parentId: 'parent', sandboxOnly: false,
    ttlMs: 200, now: 1000 }), true);
  assert.equal(canReuseActionWork({ held, previous, actor, parentId: 'parent', sandboxOnly: false,
    ttlMs: 100, now: 1000 }), false);
  assert.equal(canReuseActionWork({ held: { ...held, session_archived: true }, previous, actor,
    parentId: 'parent', sandboxOnly: false, ttlMs: 200, now: 1000 }), false);
  assert.equal(canReuseActionWork({ held, previous: { ...previous, session_archived: true }, actor,
    parentId: 'parent', sandboxOnly: false, ttlMs: 200, now: 1000 }), false);
  assert.equal(canReuseActionWork({ held, previous, actor, parentId: 'parent', sandboxOnly: false,
    ttlMs: 200, now: 1000, archived: true }), false);
  assert.equal(canReuseActionWork({ held, previous, actor, parentId: 'parent', sandboxOnly: false,
    ttlMs: 200, now: 1000, fresh: true }), false);
  assert.throws(() => normalizeActionWorkKey('not a key'), /bounded/);
  assert.throws(() => normalizeActionWorkKey('x'.repeat(121)), /bounded/);
});
