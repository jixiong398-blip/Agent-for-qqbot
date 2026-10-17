// SPDX-License-Identifier: MIT
// Read-only presentation values from the action ledger and its actual native log.
const iso = value => new Date(value).toISOString();
const id = (task, part) => task.id + ':' + part;

export function actionThread(task, events) {
  const start = events.find(event => event.type === 'turn/start');
  // A rejected/manual follow-up must not enlarge the delegated work range.
  const end = start && events.find(event => event.type === 'turn/end' && event.data.turn === start.data.turn);
  const next = start && events.find(event => event.type === 'turn/start' && event.seq > start.seq);
  const run = events.filter(event => !next || event.seq < next.seq);
  const after = start ? start.seq - 1 : -1;
  const terminal = ['completed', 'failed', 'paused'].includes(task.state);
  const through = end?.seq ?? run.at(-1)?.seq;
  const calls = run.filter(event => event.type === 'tool/call' && event.seq > after &&
    (through === undefined || event.seq <= through)).length;
  const entries = [{ id: id(task, 'open'), thread: task.id, kind: 'open', title: task.objective,
    parent_session_id: task.parent_session, child_session_id: task.child_session_id, after_seq: after, at: iso(task.created_at) }];
  const messages = task.thread ?? [];
  for (const [index, message] of messages.entries()) {
    // Review has its own duty/ledger/card. It is not a tool effect or another
    // action message, even when it was requested by this executor.
    if (['action_report', 'gpt_review'].includes(message.speaker)) continue;
    entries.push({ id: id(task, 'message-' + index), thread: task.id,
      kind: message.speaker === 'action_question' ? 'question' : message.speaker === 'action' ? 'progress' : 'message',
      from: message.speaker === 'character' ? 'character' : 'action', text: message.text, at: iso(message.at) });
  }
  const settledAt = end?.time ?? task.updated_at ?? task.created_at;
  if (terminal && through !== undefined && start) entries.push({ id: id(task, 'work'), thread: task.id, kind: 'work',
    child_session_id: task.child_session_id, after_seq: after, through_seq: through,
    duration_ms: Math.max(0, settledAt - start.time), tool_calls: calls, at: iso(settledAt) });
  if (task.report) entries.push({ id: id(task, 'report'), thread: task.id, kind: 'report', from: 'action',
    text: task.report, at: iso(settledAt) });
  const states = { queued: 'queued', starting: 'queued', running: 'running', completed: 'done', failed: 'failed', paused: 'paused', cancelled: 'stopped' };
  const state = task.state === 'failed' && task.reason === 'aborted' ? 'stopped' : states[task.state] ?? 'paused';
  entries.push({ id: id(task, 'status'), thread: task.id, kind: 'status', state,
    reason: task.reason ?? '', at: iso(settledAt) });
  const handbacks = { ready_for_character: 'handing', character_read: 'taken', handback_deferred: 'missed', handback_failed: 'missed' };
  if (handbacks[task.handover]) entries.push({ id: id(task, 'handback'), thread: task.id, kind: 'handback',
    state: handbacks[task.handover], outcome: task.state === 'completed' ? 'done' : 'failed',
    cause: task.handover === 'handback_failed' ? 'turn' : 'report', error: task.handover_error ?? '',
    at: iso(task.updated_at ?? settledAt) });
  return { id: task.id, parent_session_id: task.parent_session, child_session_id: task.child_session_id, entries,
    native: { after_seq: after, through_seq: through ?? null, tool_calls: calls },
    evidence_source: 'durable-action-ledger-and-native-child-events', model_woken: false };
}
