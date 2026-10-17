// SPDX-License-Identifier: MIT
import test from 'node:test';
import assert from 'node:assert/strict';
import { shouldDispatch, backoffMs } from '../../soyo/dsh/host/cognition-roller.mjs';

test('an in-flight batch is never dispatched twice', () => {
  assert.deepEqual(shouldDispatch({ state: 'in_flight' }, 1000), { dispatch: false, reason: 'in_flight' });
});

test('a due batch is dispatched even after a low-traffic window', () => {
  assert.deepEqual(shouldDispatch({ state: 'due', reason: 'idle' }, 1000), { dispatch: true, reason: 'idle' });
});

test('a waiting or failed batch respects the local backoff', () => {
  assert.equal(shouldDispatch({ state: 'not_due', reason: 'waiting' }, 1000).dispatch, false);
  assert.equal(shouldDispatch({ state: 'due', reason: 'failed-retry' }, 1000, 2000).dispatch, false);
  assert.equal(shouldDispatch({ state: 'due', reason: 'failed-retry' }, 3000, 2000).dispatch, true);
});

test('backoff is bounded and grows with repeated failures', () => {
  assert.equal(backoffMs(0), 60000);
  assert.equal(backoffMs(1), 120000);
  assert.equal(backoffMs(99), 30 * 60 * 1000);
});
