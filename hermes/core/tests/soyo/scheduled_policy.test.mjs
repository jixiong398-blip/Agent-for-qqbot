// SPDX-License-Identifier: MIT
// Decision-boundary invariants after actual native Schedule/role/action viability.
import test from 'node:test'; import assert from 'node:assert/strict';
import { scheduledDecision, scheduledEffectApproved } from '../../soyo/dsh/host/scheduled-policy.mjs';
const make = () => ({ id: 'occurrence', role_session_id: 'role', action_task_id: 'task', initial_role_completed: true, publication: { kind: 'qzone', text: 'draft' } });
const task = { parent_session: 'role', actor: { occurrence_id: 'occurrence' }, state: 'completed' };
const decision = { task_id: 'task', decision: 'approve', reason: 'actual artifact observed' };
test('only the exact reported occurrence and native role can decide', () => {
  assert.equal(scheduledDecision(make(), task, decision, 'feedback', 1).at, 1);
  for (const foreign of [{ ...task, parent_session: 'foreign' }, { ...task, actor: { occurrence_id: 'foreign' } }])
    assert.throws(() => scheduledDecision(make(), foreign, decision, 'feedback'), /reported task/);
});
test('first-stage intent is not approval of a future result', () => {
  assert.throws(() => scheduledDecision(make(), task, decision, 'initial'), /reported task/);
});
test('successful model prose cannot approve an absent artifact', () => {
  const work = make(); delete work.publication;
  assert.throws(() => scheduledDecision(work, task, decision, 'feedback'), /artifact/);
});
test('failed executor or interrupted character cannot release a staged publication', () => {
  assert.throws(() => scheduledDecision(make(), { ...task, state: 'failed' }, decision, 'feedback'), /artifact/);
  const work = { ...make(), role_decision: decision };
  assert.equal(scheduledEffectApproved(work, false), false);
  assert.equal(scheduledEffectApproved({ ...work, initial_role_completed: false }, true), false);
  assert.equal(scheduledEffectApproved(work, true), true);
});
test('silent and blocked decisions never create publication permission', () => {
  for (const value of ['silent', 'blocked']) {
    const work = make(); work.role_decision = scheduledDecision(work, task, { ...decision, decision: value }, 'feedback');
    assert.equal(scheduledEffectApproved(work, true), false);
  }
});
test('a durable report decision cannot be silently overwritten', () => {
  const work = make(); work.role_decision = scheduledDecision(work, task, decision, 'feedback');
  assert.throws(() => scheduledDecision(work, task, { ...decision, decision: 'silent' }, 'feedback'), /already/);
});
