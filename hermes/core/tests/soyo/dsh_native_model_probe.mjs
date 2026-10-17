// Diagnostic, not acceptance: real Cordis LlmRuntime -> official pi-ai adapter -> primary wire.
// One bounded attempt; optional exact-payload nonstream control. No agent, tools, QQ or settings writes.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { createHash, randomUUID } from 'node:crypto';

const [base, home, release, evidenceFile, ...flags] = process.argv.slice(2);
assert(base && home && release && evidenceFile, 'Pass native URL/private home/runtime release/evidence file.');
const expectedBaseURL = process.env.SOYO_PROBE_EXPECTED_MODEL_BASE_URL;
const expectedModel = process.env.SOYO_PROBE_EXPECTED_MODEL_ID;
assert(typeof expectedBaseURL === 'string' && expectedBaseURL.trim(), 'Explicit SOYO_PROBE_EXPECTED_MODEL_BASE_URL required; no supplier default.');
assert(typeof expectedModel === 'string' && expectedModel.trim(), 'Explicit SOYO_PROBE_EXPECTED_MODEL_ID required; no deployment model default.');
const controlFlag = flags.includes('--nonstream-control');
const sessionFlag = flags.find(flag => flag.startsWith('--session='));
const beforeFlag = flags.find(flag => flag.startsWith('--before-seq='));
const minimalWithTools = flags.includes('--minimal-with-tools');
assert(flags.every(flag => flag === '--nonstream-control' || flag === '--minimal-with-tools' ||
  flag.startsWith('--session=') || flag.startsWith('--before-seq=')), 'Unknown diagnostic option');
assert(!minimalWithTools || sessionFlag, 'Tool definitions must come from a real native session');
assert(!beforeFlag || sessionFlag);
const loginKey = (await readFile(home + '/web-access-key', 'utf8')).trim();
const login = await fetch(base + '/soyo-login', { method: 'POST', redirect: 'manual',
  headers: { Origin: base, 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ key: loginKey }), signal: AbortSignal.timeout(15000) });
assert.equal(login.status, 303);
const cookie = login.headers.get('set-cookie').split(';', 1)[0];
async function rpc(endpoint, args = {}) {
  const response = await fetch(base + '/api/' + endpoint, { method: 'POST',
    headers: { Cookie: cookie, Origin: base, 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method: endpoint, payload: { args } }),
    signal: AbortSignal.timeout(15000) });
  assert.equal(response.status, 200);
  const envelope = await response.json();
  assert(envelope.result?.ok, 'Native configuration read failed');
  return envelope.result.value;
}
const described = await rpc('settings/describe');
const profile = described.namespaces.find(row => row.ns === 'llm-pi-ai')?.value.providers['soyo-model'];
assert(profile, 'Only the existing explicit primary route');
assert.equal(profile.api, 'openai-responses');
assert.equal(profile.baseURL, expectedBaseURL);
assert(profile.models.some(model => model.id === expectedModel));
const environmentLine = (await readFile(home + '/runtime.env', 'utf8')).split('\n')
  .find(line => line.startsWith(profile.apiKeyEnv + '='));
assert(environmentLine, 'Explicit runtime credential reference');
const modelKey = JSON.parse(environmentLine.slice(profile.apiKeyEnv.length + 1));
assert(typeof modelKey === 'string' && modelKey.trim());
const metadata = await rpc('credentials/describe', { refs: [profile.apiKeyEnv] });
assert(metadata[profile.apiKeyEnv].configured, 'Credential metadata must be configured');
const require = createRequire(release + '/package.json');
const load = name => import(require.resolve(name));
const [{ Context }, llm, pi, launch] = await Promise.all([
  load('@deepseek-ai/cordis'), load('@deepseek-ai/dsh-llm'),
  load('@deepseek-ai/dsh-llm-pi-ai'), load('@deepseek-ai/dsh-launch-environment'),
]);
let messages = [{ role: 'user', content: [{ type: 'text',
  text: 'Return exactly OK. This is a connectivity check, no tools or actions.' }] }];
let tools, toolHistory, sessionId, requestConfig;
let sessionEvidence;
if (sessionFlag) {
  sessionId = sessionFlag.slice('--session='.length);
  assert(sessionId.length > 0);
  const WebSocket = require('ws');
  const frame = await new Promise((resolve, reject) => {
    const socket = new WebSocket(base.replace(/^http/, 'ws') + '/api/remote.mux',
      { headers: { Cookie: cookie, Origin: base } });
    const timer = setTimeout(() => { socket.terminate(); reject(new Error('Passive snapshot timeout')); }, 20000);
    socket.on('error', error => { clearTimeout(timer); reject(error); });
    socket.on('open', () => socket.send(JSON.stringify({ type: 'open', streamId: randomUUID(), endpoint: 'session/follow',
      payload: { args: { request: { address: { kind: 'session', sessionId }, assistantStream: true, maxMessages: 100 } } } })));
    socket.on('message', raw => {
      try {
        const reply = JSON.parse(raw.toString());
        if (reply.type === 'error') throw new Error('Native follow rejected');
        if (reply.type !== 'item' || reply.value?.type !== 'snapshot') return;
        clearTimeout(timer); socket.close(); resolve(reply.value);
      } catch (error) { clearTimeout(timer); socket.terminate(); reject(error); }
    });
  });
  const events = frame.records.map(record => record.event);
  assert.equal(events[0]?.seq, 0, 'Refuse partial logs: original history cannot be reconstructed');
  assert(events.every((event, index) => event.seq === index), 'Contiguous native event prefix required');
  const end = beforeFlag ? Number(beforeFlag.slice('--before-seq='.length)) : events.length;
  assert(Number.isSafeInteger(end) && end > 0 && end <= events.length);
  const { Session } = await load('@deepseek-ai/dsh-session');
  const session = Session.create(sessionId, events.slice(0, end), undefined, 0);
  const header = session.requestHeader();
  assert.equal(header.config.provider, 'soyo-model');
  assert.equal(header.config.model, expectedModel, 'Never diagnose a different model silently');
  assert.equal(header.config.maxTokens, 1024, 'Current bounded budget only');
  tools = header.tools;
  requestConfig = header.config;
  if (!minimalWithTools) {
    messages = session.deriveMessages();
    toolHistory = session.toolHistory();
  }
  sessionEvidence = { session_id: sessionId, before_seq_exclusive: end,
    source_cursor: frame.cursor, native_session_derivation: !minimalWithTools,
    only_tool_catalog_adopted: minimalWithTools, original_log_unchanged: true,
    history_message_count: messages.length, tool_schema_count: tools?.length ?? 0,
    system_bytes: messages.filter(message => message.role === 'system')
      .reduce((count, message) => count + Buffer.byteLength(JSON.stringify(message.content)), 0) };
}
const safe = value => String(value).replaceAll(modelKey, '<redacted>').replaceAll(loginKey, '<redacted>')
  .replace(/Bearer\s+\S+|sk-[A-Za-z0-9_-]+/g, '<redacted>').slice(0,900);
const wire = [];
const realFetch = globalThis.fetch;
let captured;
globalThis.fetch = async (input, init) => {
  const request = new Request(input, init);
  const url = new URL(request.url);
  assert.equal(url.href, profile.baseURL.replace(/\/$/, '') + '/responses', 'No alternate supplier or endpoint');
  assert.equal(request.method, 'POST');
  assert.equal(wire.length, 0, 'No SDK retry');
  const bodyText = await request.clone().text();
  const payload = JSON.parse(bodyText);
  captured = { payload, headers: new Headers(request.headers), url: url.href };
  const record = { endpoint: url.origin + url.pathname, method: request.method,
    model: payload.model, fields: Object.keys(payload).sort(), stream: payload.stream,
    max_output_tokens: payload.max_output_tokens, store: payload.store,
    reasoning_field_present: Object.hasOwn(payload, 'reasoning'),
    previous_response_id_present: Object.hasOwn(payload, 'previous_response_id'),
    prompt_cache_key_present: Object.hasOwn(payload, 'prompt_cache_key'),
    input_items: payload.input.length,
    input_types: payload.input.map(item => item.type ?? item.role),
    input_bytes: Buffer.byteLength(JSON.stringify(payload.input)),
    tool_count: payload.tools?.length ?? 0,
    body_bytes: Buffer.byteLength(bodyText),
    request_sha256: createHash('sha256').update(bodyText).digest('hex'),
    authorization_matches_runtime_reference: request.headers.get('authorization') === 'Bearer ' + modelKey };
  wire.push(record);
  const response = await realFetch(input, init);
  record.http_status = response.status;
  record.content_type = response.headers.get('content-type');
  if (!response.ok) {
    const data = await response.clone().json().catch(() => null);
    const error = data?.error ?? data;
    record.error = error && { code: safe(error.code), type: safe(error.type), message: safe(error.message),
      trace_id: error.trace_id && safe(error.trace_id) };
  }
  return response;
};
const ctx = new Context();
const result = { diagnostic_only: true, native_llm_runtime_verified: false, native_adapter_mount_verified: false,
  provider: 'soyo-model', model: expectedModel, settings_writes: 0, tools_executed: 0,
  qq_connected: false, production_service_restarted: false, private_prompts_exported: false,
    full_native_agent_verified: false, session_diagnostic: sessionEvidence, wire };
try {
  ctx.provide('launchEnvironment', launch.createLaunchEnvironmentSnapshot([
    { source: 'process', values: { [profile.apiKeyEnv]: modelKey } },
  ]));
  await ctx.plugin(llm.LlmRuntime);
  await ctx.plugin(pi, { providers: { 'soyo-model': profile } });
  assert(ctx.llm.listProviders().some(row => row.id === 'soyo-model'));
  result.native_adapter_mount_verified = true;
  const assembler = new llm.BlockAssembler();
  const chunks = {};
  const prepared = await ctx.llm.prepareCall(requestConfig ?? { provider: result.provider, model: result.model, maxTokens: 1024 });
  result.prepared_config = prepared.config;
  result.prepared_context = prepared.context;
  for await (const chunk of prepared.stream({ ...prepared.config,
    messages, ...(tools ? { tools } : {}), ...(toolHistory ? { toolHistory } : {}),
    ...(sessionId ? { sessionId } : {}),
    signal: AbortSignal.timeout(60000) })) {
    chunks[chunk.type] = (chunks[chunk.type] ?? 0) + 1;
    assembler.push(chunk);
  }
  const text = assembler.blocks().filter(block => block.type === 'text').map(block => block.text).join('');
  result.chunk_counts = chunks;
  result.finish = { kind: assembler.finish.kind, ...(assembler.finish.failure ? {
    failure: { code: assembler.finish.failure.code, message: safe(assembler.finish.failure.message) } } : {}) };
  result.usage = assembler.usage;
  result.returned_ok = text.trim() === 'OK';
  result.native_llm_runtime_verified = assembler.finish.kind === 'stop' &&
    (sessionFlag && !minimalWithTools ? Boolean(text.trim()) : result.returned_ok);
  assert.equal(wire.length, 1, 'The design probe must reach the actual provider wire once');
  assert(wire[0].authorization_matches_runtime_reference);
  assert.equal(wire[0].max_output_tokens, 1024);
  assert.equal(wire[0].reasoning_field_present, false);
  assert.equal(wire[0].previous_response_id_present, false);
  if (controlFlag) {
    const payload = { ...captured.payload, stream: false };
    const response = await realFetch(captured.url, { method: 'POST', headers: captured.headers,
      body: JSON.stringify(payload), signal: AbortSignal.timeout(60000) });
    const data = await response.json();
    const text = data.output?.filter(item => item.type === 'message').flatMap(item => item.content ?? [])
      .filter(part => part.type === 'output_text').map(part => part.text).join('') ?? '';
    const error = data.error ?? (response.ok ? undefined : data);
    result.nonstream_control = { same_native_payload_except_stream: true, http_status: response.status,
      returned_ok: text.trim() === 'OK', response_status: data.status, usage: data.usage,
      ...(error ? { error: { code: safe(error.code), type: safe(error.type), message: safe(error.message),
        trace_id: error.trace_id && safe(error.trace_id) } } : {}) };
  }
} catch (error) {
  result.probe_error = { name: error.name, code: error.code, message: safe(error.message) };
  process.exitCode = 1;
} finally {
  globalThis.fetch = realFetch;
  try { await ctx.fiber.dispose(); } catch (error) { result.dispose_error = safe(error.message); }
  await writeFile(evidenceFile, JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
  console.log(JSON.stringify(result));
}
