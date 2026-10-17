// SPDX-License-Identifier: MIT
// Local invariants after real HTTP/file receipt mechanism viability.
import test from 'node:test';
import assert from 'node:assert/strict';
import { publicationOutcome, platformMessageIdentity } from '../../soyo/dsh/host/automation-receipts.mjs';

const expected = { publication_id: 'automation-pub', attempt_id: 'attempt', kind: 'message' };
const work = { publication: expected };
const received = extra => ({ ...expected, receipt: { ...expected, status: 'platform_accepted', platform_message_id: 'real-recorded-id', ...extra } });
test('Schedule acknowledgement without receipt cannot complete an external run', () => {
  assert.equal(publicationOutcome(work, expected), null);
});
test('only matching publication and attempt can be platform evidence', () => {
  assert.equal(publicationOutcome(work, received()).state, 'completed');
  assert.equal(publicationOutcome(work, { ...received(), publication_id: 'foreign' }).state, 'unknown');
  assert.equal(publicationOutcome(work, received({ attempt_id: 'foreign' })).state, 'unknown');
});
test('empty and bool message IDs never stand in for actual platform identities', () => {
  for (const platform_message_id of ['', null, undefined, true, false, 0, 'has space', 'x\n'])
    assert.equal(publicationOutcome(work, received({ platform_message_id })).state, 'unknown');
});
test('failure and ambiguity stay separate and carry exact receipt evidence', () => {
  const failed = received({ status: 'failed', reason: 'platform-rejected' });
  assert.equal(publicationOutcome(work, failed).state, 'failed');
  assert.equal(publicationOutcome(work, received({ status: 'unknown' })).state, 'unknown');
  assert.equal(publicationOutcome(work, failed).platform_receipt.reason, 'platform-rejected');
});
test('opaque IDs and negative OneBot integer IDs remain supported', () => {
  for (const value of ['om_feishu_id', '-12345', 42, -42]) assert(platformMessageIdentity(value));
  for (const value of [true, {}, [], NaN, Infinity, 0]) assert(!platformMessageIdentity(value));
});
test('a malformed retained publication cannot freeze all receipt reconciliation', () => {
  for (const publication of [null, [], 'not-a-record', {}]) assert.equal(publicationOutcome(work, publication).state, 'unknown');
});
