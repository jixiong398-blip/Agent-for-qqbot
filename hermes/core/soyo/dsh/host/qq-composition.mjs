// SPDX-License-Identifier: MIT
// QQ-specific Agent composition. Keep this separate from the broad Web preset.

export const QQ_AGENT_PRESET_ID = 'soyo-qq-compaction';

function eventsOf(session) {
  try {
    const events = session?.snapshotEvents?.();
    return Array.isArray(events) ? events : [];
  } catch {
    return [];
  }
}

export function recordedAgentPreset(session) {
  let preset = typeof session?.header?.agentPreset === 'string'
    ? session.header.agentPreset : null;
  for (const event of eventsOf(session)) {
    if (event.type === 'agent-preset/selected' && typeof event.data?.agentPreset === 'string') {
      preset = event.data.agentPreset;
    }
  }
  return preset;
}

export function prepareSessionPreset(session, presetId) {
  const events = eventsOf(session);
  const preset = recordedAgentPreset(session);
  if (preset && preset !== presetId) {
    throw Object.assign(new Error('Session uses a different Agent preset; rotate the session'),
      { code: 'AGENT_PRESET_CONFLICT' });
  }
  if (!preset && events.some(event => event.type === 'turn/start')) {
    throw Object.assign(new Error('Session has turns but no Agent preset; rotate the session'),
      { code: 'AGENT_PRESET_EPOCH_REQUIRED' });
  }
  return { preset, needsSelection: !preset };
}

export function prepareQQSessionPreset(session) {
  return prepareSessionPreset(session, QQ_AGENT_PRESET_ID);
}
