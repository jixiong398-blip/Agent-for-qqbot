// SPDX-License-Identifier: MIT
// QQ session composition must fail closed before a legacy turn can use a new preset.
import assert from 'node:assert/strict';
import test from 'node:test';
import { prepareQQSessionPreset, QQ_AGENT_PRESET_ID, recordedAgentPreset } from '../../soyo/dsh/host/qq-composition.mjs';

const session = (events = [], header = {}) => ({
  header: { id: 'soyo-qq-fixture', isSeeded: false, ...header },
  snapshotEvents: () => events,
});

test('a blank QQ session selects the dedicated compaction preset', () => {
  const value = prepareQQSessionPreset(session());
  assert.deepEqual(value, { preset: null, needsSelection: true });
});

test('a QQ session records the dedicated preset without reselecting it', () => {
  const value = prepareQQSessionPreset(session([], { agentPreset: QQ_AGENT_PRESET_ID }));
  assert.deepEqual(value, { preset: QQ_AGENT_PRESET_ID, needsSelection: false });
  assert.equal(recordedAgentPreset(session([], { agentPreset: QQ_AGENT_PRESET_ID })), QQ_AGENT_PRESET_ID);
});

test('a legacy session with turns requires an explicit epoch rotation', () => {
  assert.throws(
    () => prepareQQSessionPreset(session([{ type: 'turn/start', data: { turn: 1 } }])),
    error => error.code === 'AGENT_PRESET_EPOCH_REQUIRED',
  );
});

test('a session using another preset cannot be silently rebound to QQ', () => {
  assert.throws(
    () => prepareQQSessionPreset(session([], { agentPreset: 'standard' })),
    error => error.code === 'AGENT_PRESET_CONFLICT',
  );
  assert.throws(
    () => prepareQQSessionPreset(session([{ type: 'agent-preset/selected', data: { agentPreset: 'standard' } }])),
    error => error.code === 'AGENT_PRESET_CONFLICT',
  );
  assert.throws(
    () => prepareQQSessionPreset(session([{ type: 'agent-preset/selected', data: { agentPreset: 'standard' } }],
      { agentPreset: QQ_AGENT_PRESET_ID })),
    error => error.code === 'AGENT_PRESET_CONFLICT',
  );
});
