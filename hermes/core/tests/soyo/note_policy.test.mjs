// SPDX-License-Identifier: MIT
// Fast limit invariants after native local role/action/file/audit viability was demonstrated.
import test from 'node:test';
import assert from 'node:assert/strict';
import { noteQuotaReason, noteTextLimit } from '../../soyo/dsh/host/note-policy.mjs';

const now = Date.parse('2026-10-13T12:00:00Z');
const publicSource = { route_id: 'qq-group-123456', consumer: 'current', session_class: 'public', probe: false };
const owner = { ...publicSource, route_id: 'dsh-owner:soyo-owner', session_class: 'owner_private' };
const home = { kind: 'home', place: 'dsh-owner:soyo-owner' }, group = { kind: 'group', place: 'qq-group-654321' };
const row = (index, changes = {}) => ({ from: publicSource.route_id, to: group.place, from_class: 'public', target_kind: 'group',
  from_consumer: 'past-' + index, probe: false, created_at: now, ...changes });
const rows = (count, changes = {}) => Array.from({ length: count }, (_, index) => row(index, changes));

test('only trusted home-to-home gets the 1500 codepoint limit', () => {
  assert.equal(noteTextLimit(owner, home), 1500);
  assert.equal(noteTextLimit(owner, { kind: 'dm', home: true }), 1500);
  assert.equal(noteTextLimit(publicSource, home), 300);
  assert.equal(noteTextLimit(owner, group), 300);
});
test('two per original consumer independent of model child session', () => {
  assert.match(noteQuotaReason(rows(2, { from_consumer: 'current' }), publicSource, group, now), /两张/);
});
test('daily total includes settled notes from all scenes', () => {
  assert.match(noteQuotaReason(rows(40, { state: 'read' }), owner, home, now), /daily total 40/);
  assert.equal(noteQuotaReason(rows(39), owner, home, now), null);
});
test('public home daily cap also counts legacy owner DM destinations', () => {
  assert.match(noteQuotaReason(rows(6, { to: home.place, target_kind: 'home' }), publicSource, home, now), /daily 6/);
  const legacyHome = 'qq-private-100001';
  assert.match(noteQuotaReason(rows(6, { to: legacyHome, target_kind: 'dm' }), publicSource, home, now, 'Asia/Shanghai', new Set([legacyHome])), /daily 6/);
});
test('public pair cap is separate from total public group cap', () => {
  assert.match(noteQuotaReason(rows(3), publicSource, group, now), /group-pair daily 3/);
  assert.match(noteQuotaReason(rows(10, { from: 'qq-group-999999' }), publicSource, group, now), /daily total 10/);
});
test('trusted home is not restricted by public-only group quotas', () => {
  assert.equal(noteQuotaReason(rows(10), owner, group, now), null);
});
test('previous calendar day does not consume current day quota', () => {
  assert.equal(noteQuotaReason(rows(40, { created_at: now - 86400000 }), owner, home, now), null);
});
test('calendar midnight follows the deployment timezone', () => {
  const previous = Date.parse('2026-10-12T15:59:00Z'), today = Date.parse('2026-10-12T16:01:00Z');
  assert.equal(noteQuotaReason(rows(40, { created_at: previous }), owner, home, today, 'Asia/Shanghai'), null);
  assert.match(noteQuotaReason(rows(40, { created_at: previous }), owner, home, today, 'UTC'), /daily total 40/);
});
test('synthetic probe notes cannot consume or borrow live quotas', () => {
  assert.equal(noteQuotaReason(rows(40, { probe: true }), owner, home, now), null);
  assert.equal(noteQuotaReason(rows(40), { ...owner, probe: true }, home, now), null);
});
