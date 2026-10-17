// SPDX-License-Identifier: MIT
// Canonical success contracts after actual native exit7/write/read viability.
import test from 'node:test'; import assert from 'node:assert/strict';
import { effectObservation } from '../../soyo/dsh/host/effect-observation.mjs';
const bash = extra => ({ isError: false, value: { kind: 'foreground', exitCode: 0, signal: null, timedOut: false, aborted: false, ...extra } });
test('nonzero exit is not successful just because the tool did not throw', () => {
  assert.equal(effectObservation('bash', bash({ exitCode: 7 })).verified, false);
  assert.equal(effectObservation('bash', bash({})).verified, true);
});
test('timeout, stop, signal, denial and pending jobs are not completed effects', () => {
  for (const value of [{ timedOut: true }, { aborted: true }, { signal: 'SIGTERM' }, { kind: 'background' }, { kind: 'promoted' }, { sandbox: { denied: true } }, { sandbox: { runnerFailed: true } }])
    assert.equal(effectObservation('bash', bash(value)).verified, false);
});
test('model text and tool protocol success alone are not canonical file effects', () => {
  assert.equal(effectObservation('write', { isError: false, content: [{ type: 'text', text: 'created' }] }).verified, false);
  assert.equal(effectObservation('write', { isError: false, value: { path: '/fixture/file' } }).verified, true);
  assert.equal(effectObservation('write', { isError: true, value: { path: '/fixture/file' } }).verified, false);
});
test('QQ business rejection does not become a successful platform action', () => {
  assert.equal(effectObservation('qq_kick', { isError: false, value: { success: false, error: 'not_admin' } }).verified, false);
  assert.equal(effectObservation('qq_status', { isError: false, value: { success: true, data: { online: true } } }).verified, true);
});
test('candidate completion and internal memory work never imply production release', () => {
  const result=effectObservation('soyo_development',{isError:false,value:{state:'completed',exit_code:0,commit:'fixture'}});
  assert.equal(result.state,'candidate-only');assert.equal(result.verified,true);
  assert.equal(effectObservation('soyo_memory',{isError:false,value:{state:'commitment_recorded'}}).verified,false);
});
