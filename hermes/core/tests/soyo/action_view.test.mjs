// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import test from 'node:test';
import { actionThread } from '../../soyo/dsh/host/action-view.mjs';

const task = overrides => ({ id: 'action-test', parent_session: 'parent', child_session_id: 'child', objective: 'Bounded objective',
  created_at: 1000, updated_at: 4000, state: 'completed', handover: 'character_read', report: 'Actual native report',
  thread: [{ speaker: 'character', text: 'Bounded objective', at: 1000 },
    { speaker: 'action', text: 'Checked input', at: 2000 }], ...overrides });
const events = [{ seq: 5, type: 'turn/start', time: 1500, data: { turn: 1 } },
  { seq: 10, type: 'tool/call', time: 2000, data: { turn: 1 } },
  { seq: 15, type: 'turn/end', time: 3000, data: { turn: 1 } }];

test('native range/tool count and character-read status preserve source values', () => {
  const result = actionThread(task(), events);
  assert.deepEqual(result.native, { after_seq: 4, through_seq: 15, tool_calls: 1 });
  const work = result.entries.find(row => row.kind === 'work');
  assert.equal(work.duration_ms, 1500);
  assert.equal(work.child_session_id, 'child');
  assert.equal(result.entries.find(row => row.kind === 'handback').state, 'taken');
  assert.equal(result.model_woken, false);
});
test('a later rejected turn cannot extend earlier work or its tool count', () => {
  const result = actionThread(task(), [...events,
    { seq: 20, type: 'turn/start', time: 5000, data: { turn: 2 } },
    { seq: 21, type: 'tool/call', time: 5100, data: { turn: 2 } },
    { seq: 25, type: 'turn/end', time: 6000, data: { turn: 2 } }]);
  assert.equal(result.native.through_seq, 15);
  assert.equal(result.native.tool_calls, 1);
});
test('a ready report is handing, not already read', () => {
  assert.equal(actionThread(task({ handover: 'ready_for_character' }), events).entries.at(-1).state, 'handing');
});
test('failed hand-back records the turn error without claiming completion or retry', () => {
  const row = actionThread(task({ handover: 'handback_failed', handover_error: 'parent_turn_failed' }), events).entries.at(-1);
  assert.equal(row.state, 'missed'); assert.equal(row.cause, 'turn'); assert.equal(row.error, 'parent_turn_failed');
});
test('cold pause and explicit cancellation remain distinct', () => {
  const paused = actionThread(task({ state: 'paused', report: '', handover: 'pending', reason: 'host_restart' }), events.slice(0, 2));
  assert.equal(paused.entries.at(-1).state, 'paused');
  const stopped = actionThread(task({ state: 'failed', report: '', handover: 'no_report', reason: 'aborted' }), events);
  assert.equal(stopped.entries.at(-1).state, 'stopped');
});
test('no native turn means no fabricated work row', () => {
  const result = actionThread(task({ state: 'starting', report: '', handover: 'pending' }), []);
  assert.equal(result.entries.some(row => row.kind === 'work'), false);
  assert.equal(result.native.tool_calls, 0);
  assert.equal(result.entries.at(-1).state, 'queued');
});
