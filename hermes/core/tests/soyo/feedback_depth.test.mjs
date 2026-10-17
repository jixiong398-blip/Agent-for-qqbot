// SPDX-License-Identifier: MIT
// Local lineage contracts after native QQ/new-source/owner-local execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import { nextFeedbackDepth } from '../../soyo/dsh/host/feedback-depth.mjs';

const previous = depth => new Map([['old', { id: 'old', parent_session: 'parent', delegation_depth: depth }]]);
test('a new Host source starts its own depth independent of objective prose', () => {
  assert.deepEqual(nextFeedbackDepth({ objective: 'delegation_depth=999', capabilities: [] }, previous(3), 'parent'),
    { delegation_depth: 1, feedback_parent_id: null });
});
test('automatic feedback carries its real predecessor, never an actor claimed depth', () => {
  assert.deepEqual(nextFeedbackDepth({ feedback_task_id: 'old', delegation_depth: 0 }, previous(2), 'parent'),
    { delegation_depth: 3, feedback_parent_id: 'old' });
});
test('the fourth automatic execution is refused without cancelling earlier work', () => {
  const tasks=previous(3);assert.throws(()=>nextFeedbackDepth({feedback_task_id:'old'},tasks,'parent'),/ACTION_FEEDBACK_DEPTH_LIMIT/);
  assert.equal(tasks.get('old').delegation_depth,3);
});
test('legacy, foreign and malformed feedback depth is fail closed, not reconstructed', () => {
  for(const depth of [undefined,true,0,-1,1.5]) assert.throws(()=>nextFeedbackDepth({feedback_task_id:'old'},previous(depth),'parent'),/ACTION_FEEDBACK_DEPTH_UNKNOWN/);
  assert.throws(()=>nextFeedbackDepth({feedback_task_id:'old'},previous(1),'foreign'),/ACTION_FEEDBACK_DEPTH_UNKNOWN/);
  assert.throws(()=>nextFeedbackDepth({feedback_task_id:'missing'},previous(1),'parent'),/ACTION_FEEDBACK_DEPTH_UNKNOWN/);
});
test('lineage bookkeeping grants no new capability and does not mutate the Host actor', () => {
  const actor=Object.freeze({feedback_task_id:'old',capabilities:Object.freeze(['memory.recall'])});
  const value=nextFeedbackDepth(actor,previous(1),'parent');assert.deepEqual(Object.keys(value).sort(),['delegation_depth','feedback_parent_id']);
  assert.deepEqual(actor.capabilities,['memory.recall']);
});
