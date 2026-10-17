// SPDX-License-Identifier: MIT
// Deterministic scheduling invariants only; native execution-slot fairness is a separate boundary.
import test from 'node:test';
import assert from 'node:assert/strict';
import { AuthorActionQueue } from '../../soyo/dsh/host/action-queue.mjs';

test('authors rotate while each author retains FIFO order', () => {
  const queue = new AuthorActionQueue();
  queue.add('alice', 'a1'); queue.add('alice', 'a2'); queue.add('alice', 'a3');
  queue.add('bob', 'b1'); queue.add('bob', 'b2');
  assert.deepEqual(Array.from({ length: 5 }, () => queue.next()), ['a1', 'b1', 'a2', 'b2', 'a3']);
  assert.equal(queue.next(), null);
  assert.equal(queue.size, 0);
});

test('capacity rejection does not accept or displace existing work', () => {
  const queue = new AuthorActionQueue(2);
  queue.add('alice', 'a1'); queue.add('bob', 'b1');
  assert.throws(() => queue.add('carol', 'c1'), /ACTION_QUEUE_FULL/);
  assert.equal(queue.size, 2);
  assert.deepEqual([queue.next(), queue.next(), queue.next()], ['a1', 'b1', null]);
});

test('cancel one queued item without disturbing another author', () => {
  const queue = new AuthorActionQueue();
  queue.add('alice', 'a1'); queue.add('alice', 'a2'); queue.add('bob', 'b1');
  assert.equal(queue.remove('a1'), true);
  assert.equal(queue.remove('missing'), false);
  assert.deepEqual([queue.next(), queue.next()], ['a2', 'b1']);
});

test('removing the last item frees its author and a queue slot', () => {
  const queue = new AuthorActionQueue(2);
  queue.add('alice', 'a1'); queue.add('bob', 'b1');
  assert.equal(queue.remove('a1'), true);
  queue.add('carol', 'c1');
  assert.deepEqual([queue.next(), queue.next()], ['b1', 'c1']);
});

test('newly arriving author joins the next round, not ahead of accepted work', () => {
  const queue = new AuthorActionQueue();
  queue.add('alice', 'a1'); queue.add('alice', 'a2'); queue.add('bob', 'b1');
  assert.equal(queue.next(), 'a1');
  queue.add('carol', 'c1');
  assert.deepEqual([queue.next(), queue.next(), queue.next()], ['b1', 'a2', 'c1']);
});
