// SPDX-License-Identifier: MIT
// Protect the admission boundary after actual delegated native memory settlement.
import test from 'node:test'; import assert from 'node:assert/strict';
import { canSettleCognition } from '../../soyo/dsh/host/cognition-trigger.mjs';
const config = { brain_mode: 'character-action', cognition_enabled: true };
const source = { internal: false, probe: false };
const report = { ...source, internal: true, internal_source: 'action-report', origin_job_key: 'a'.repeat(64), binding: { task_continuation: true } };
test('a completed external role is a current source opportunity', () => {
  assert.equal(canSettleCognition(config, source, 'completed', 'role', []), true);
});
test('an action report may settle sources deferred while the original role delegated', () => {
  assert.equal(canSettleCognition(config, report, 'completed', 'role', [{ parent_session: 'role', state: 'completed' }]), true);
});
test('an unbound report name cannot create a settlement opportunity', () => {
  assert.equal(canSettleCognition(config, { ...report, origin_job_key: 'foreign' }, 'completed', 'role', []), false);
  assert.equal(canSettleCognition(config, { ...report, binding: {} }, 'completed', 'role', []), false);
});
test('notes, plans and legacy consultation events do not acquire report authority', () => {
  for (const kind of ['scene-note', 'schedule', 'gpt-consultation'])
    assert.equal(canSettleCognition(config, { ...report, internal_source: kind }, 'completed', 'role', []), false);
});
test('failure, cancellation and explicit probes do not dispatch memory', () => {
  for (const reason of ['error', 'cancelled', undefined]) assert.equal(canSettleCognition(config, source, reason, 'role', []), false);
  assert.equal(canSettleCognition(config, { ...source, probe: true }, 'completed', 'role', []), false);
});
test('same-scene in-flight action blocks settlement; another scene does not confer authority', () => {
  assert.equal(canSettleCognition(config, report, 'completed', 'role', [{ parent_session: 'role', state: 'running' }]), false);
  assert.equal(canSettleCognition(config, report, 'completed', 'role', [{ parent_session: 'other', state: 'running' }]), true);
});
test('an inactive deployment cannot wake cognition from any source', () => {
  assert.equal(canSettleCognition({ ...config, cognition_enabled: false }, report, 'completed', 'role', []), false);
  assert.equal(canSettleCognition({ ...config, brain_mode: 'legacy' }, report, 'completed', 'role', []), false);
});
