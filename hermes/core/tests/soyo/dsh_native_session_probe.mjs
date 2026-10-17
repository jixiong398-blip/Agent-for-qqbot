// Passive evidence over the actual native mux; never submits prompts/tools or connects QQ.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';

const [base, keyFile, release, sessionId, evidenceFile, referenceFile] = process.argv.slice(2);
assert(base && keyFile && release && sessionId && evidenceFile, 'URL/keyfile/release/session/evidence required.');
const require = createRequire(release + '/package.json');
const WebSocket = require('ws');
const key = (await readFile(keyFile, 'utf8')).trim();
const login = await fetch(base + '/soyo-login', { method: 'POST', redirect: 'manual',
  headers: { Origin: base, 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ key }), signal: AbortSignal.timeout(15000) });
assert.equal(login.status, 303, 'Native login');
const cookie = login.headers.get('set-cookie').split(';', 1)[0];
const events = new Map();
let projections, cursor;
const result = await new Promise((resolve, reject) => {
  const socket = new WebSocket(base.replace(/^http/, 'ws') + '/api/remote.mux', { headers: { Cookie: cookie, Origin: base } });
  const timer = setTimeout(() => { socket.terminate(); reject(new Error('Native turn did not settle within 90s.')); }, 90000);
  const finish = (value) => { clearTimeout(timer); socket.close(); resolve(value); };
  function observe() {
    const ordered = [...events.values()].sort((a, b) => a.seq - b.seq);
    const start = ordered.findLast(event => event.type === 'turn/start');
    if (!start) return;
    const turnEvents = ordered.filter(event => event.seq >= start.seq);
    const end = turnEvents.findLast(event => event.type === 'turn/end');
    if (!end) return;
    const header = ordered.findLast(event => event.type === 'request/header')?.data.header.config;
    const context = ordered.findLast(event => event.type === 'request/context')?.data;
    const calls = turnEvents.filter(event => event.type === 'tool/call');
    const results = turnEvents.filter(event => event.type === 'tool/result');
    const assistants = turnEvents.filter(event => event.type === 'assistant/message');
    const last = assistants.at(-1)?.data.message;
    const texts = last?.content.filter(block => block.type === 'text').map(block => block.text).join('') || '';
    const marker = 'SoyoNativeEvidence_20261011_R1_83B1';
    const readResults = results.filter(event => !event.data.message.isError &&
      calls.some(call => call.data.name === 'read' && call.data.callId === event.data.message.toolCallId));
    const toolMarker = readResults.some(event => JSON.stringify(event.data.message.content).includes(marker));
    // Hash only durable proof records, not private prompts/SOUL or live stream frames.
    const proofRecords = turnEvents.filter(event => ['assistant/message', 'tool/call', 'tool/result', 'turn/end'].includes(event.type));
    const digest = createHash('sha256').update(JSON.stringify(proofRecords)).digest('hex');
    finish({ sessionId, cursor, turn: start.data.turn, turn_end_reason: end.data.reason,
      request_header: header, context_metadata: context, tool_calls: calls.map(event => ({
        name: event.data.name, probe_file_requested: event.data.arguments.includes('native-probe.txt') })),
      read_result_marker_present: toolMarker, final_marker_present: texts.includes(marker),
      final_says_soyo: /Soyo|そよ|祥子|素世/.test(texts),
      final_source: last?.source && { provider: last.source.provider, model: last.source.model },
      target_context_projection: projections?.values?.modelSelection,
      proof_records_sha256: digest, proof_record_count: proofRecords.length,
      actual_tool_count: calls.length, qq_connected: false, prompts_submitted_by_probe: 0 });
  }
  socket.on('error', error => { clearTimeout(timer); reject(error); });
  socket.on('open', () => socket.send(JSON.stringify({ type: 'open', streamId: randomUUID(), endpoint: 'session/follow',
    payload: { args: { request: { address: { kind: 'session', sessionId }, assistantStream: true, maxMessages: 100 } } } })));
  socket.on('message', raw => {
    try {
      const message = JSON.parse(raw.toString());
      if (message.type === 'error') throw new Error('Native follow rejected.');
      if (message.type !== 'item') return;
      const frame = message.value;
      if (frame.type === 'snapshot') {
        projections = frame.projections; cursor = frame.cursor;
        for (const { event } of frame.records) events.set(event.seq, event);
        observe();
      } else if (frame.type === 'event') { events.set(frame.event.seq, frame.event); observe(); }
    } catch (error) { clearTimeout(timer); socket.terminate(); reject(error); }
  });
});
await writeFile(evidenceFile, JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify(result));
assert.equal(result.turn_end_reason.kind, 'completed', 'Actual native turn completion');
assert.equal(result.request_header.provider, 'soyo-model');
assert.equal(result.request_header.model, 'deepseek-v4-flash-vision');
assert.equal(result.request_header.maxTokens, 1024, 'Native header budget, including restored sessions');
assert(result.read_result_marker_present && result.final_marker_present && result.final_says_soyo,
  'Actual read result, correct final marker and Soyo identity required');
assert.deepEqual(result.tool_calls.map(call => call.name), ['read'], 'Read-only probe must not execute other tools');
if (referenceFile) {
  const before = JSON.parse(await readFile(referenceFile, 'utf8'));
  assert.equal(result.proof_records_sha256, before.proof_records_sha256, 'Durable proof must survive host restart');
  assert.equal(result.turn, before.turn);
  console.log(JSON.stringify({ native_session_restart_restore_verified: true, proof_records_unchanged: true }));
}
