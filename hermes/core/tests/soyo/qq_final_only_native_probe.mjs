// SPDX-License-Identifier: MIT
// Historical filename. Committed-stage contract: actual Host/Agent/worker/outbox.
// No OneBot writer, production config, credentials or user sessions are loaded.
// Usage: node qq_final_only_native_probe.mjs <native-runtime> <python>
import assert from 'node:assert/strict';
import http from 'node:http';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { mkdir, mkdtemp, cp, symlink, writeFile, readFile, readdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { setTimeout as delay } from 'node:timers/promises';
import { spawnSync } from 'node:child_process';

const [runtime, python] = process.argv.slice(2);
assert(runtime && python, 'Pass the installed native runtime and Python executable.');
const native = resolve(runtime), core = fileURLToPath(new URL('../../', import.meta.url));
// Match the deployed supervisor's explicit worker import/ACL environment.
process.env.SOYO_WORKER_ROOT = core;
process.env.SOYO_PYTHON = resolve(python);
const root = await mkdtemp(join(tmpdir(), 'qq-final-only-'));
process.env.DSH_HOME = join(root, 'dsh');
process.env.DSH_TELEMETRY_DISABLED = '1';
process.env.SOYO_HOST_PERMISSION_MODE = 'workspace-write';
const require = createRequire(join(native, 'package.json'));
const base = createRequire(require.resolve('@deepseek-ai/dsh-base'));
const load = name => import(pathToFileURL(base.resolve('@deepseek-ai/dsh-' + name)).href);
await symlink(join(native, 'node_modules'), join(root, 'node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
await cp(join(core, 'soyo/dsh/host'), join(root, 'host'), { recursive: true });
const { workerEnvironment } = await import(pathToFileURL(join(root, 'host/platform.mjs')));
const { Context } = await import(pathToFileURL(require.resolve('@deepseek-ai/cordis')).href);
const { LlmAdapter } = await load('llm');
const ctx = new Context();
const config = {
  account_id: '900001', admin_ids: ['100001'], memory_private_peers: ['100001'],
  native_root: join(root, 'qq-native'), workspace: join(root, 'work'), action_workdir: join(root, 'work'),
  python: resolve(python), corpus_db: join(root, 'memory/corpus.db'),
  memory_script: join(core, 'soyo/qq/native_memory.py'), data_script: join(core, 'soyo/qq/native_data.py'),
  tool_script: join(core, 'soyo/qq/native_tools.py'), media_root: join(root, 'media'),
  media_script: join(core, 'soyo/qq/native_media.py'),
  soul_file: join(root, 'SOUL.md'), behavior_file: join(root, 'BEHAVIOR.md'),
  host_socket: join(root, 'host.sock'), host_key: 'final_only_fixture_' + 'a'.repeat(40),
  http_url: 'http://127.0.0.1:1', onebot_token: 'fixture-not-a-live-token',
  brain_mode: 'character-action', cognition_enabled: false, operator_ui_enabled: false,
  agent_options: { provider: 'final-only-fixture', model: 'synthetic', maxTokens: 2048 },
  action_agent_options: { provider: 'final-only-fixture', model: 'synthetic', maxTokens: 2048 },
  turn_timeout_ms: 30000, qq_private_quiet_window_ms: 1, qq_private_batch_max_wait_ms: 50,
};
if (process.platform === 'win32' || Buffer.byteLength(config.host_socket) >= 104) {
  const port = http.createServer();
  await new Promise(resolve => port.listen(0, '127.0.0.1', resolve));
  config.host_url = 'http://127.0.0.1:' + port.address().port;
  await new Promise(resolve => port.close(resolve));
}
for (const dir of ['work', 'media', 'dsh']) await mkdir(join(root, dir), { recursive: true, mode: 0o700 });
await writeFile(config.soul_file, '# Persona\nFixture character; private thoughts are not publications.\n', { mode: 0o600 });
await writeFile(config.behavior_file, '# Behavior\nUse completed finals only.\n', { mode: 0o600 });
const configFile = join(root, 'config.json');
await writeFile(configFile, JSON.stringify(config), { mode: 0o600 });
if (process.platform === 'win32') {
  const secured = spawnSync(python, ['-B', '-c',
    'import sys;sys.path.insert(0,sys.argv[1]);from soyo.platform import protect;protect(sys.argv[2],directory=True);[protect(p) for p in sys.argv[3:]]',
    core, root, configFile, config.soul_file, config.behavior_file], { encoding: 'utf8' });
  assert.equal(secured.status, 0, secured.stderr);
}
const specs = [
  ['llm'], ['session'], ['session-log-deepseek'], ['typert-registry'], ['agent'],
  ['session-projection'], ['system-prompt', { personaPrefix: '' }], ['tools'],
  ['storage'], ['storage-json', { root: join(root, 'storages') }], ['storage-domain', { backend: 'json' }],
  ['session-persistence-jsonl', { root: join(root, 'sessions'), compression: 'zstd' }],
  ['session-query-sqlite', { path: ':memory:', openAt: 'never' }],
  ['session-projection-cache', { writeEveryEvents: 200, writeIntervalMs: 5000 }],
  ['workspace'], ['sandbox-policy', { mode: 'workspace-write', workspaceRoot: root }],
  ['sandbox-local'], ['fs-sandbox'], ['fs-observation-policy'], ['working-directory'],
  ['subprocess-local'], ['shell-env'], ['jobs-local'], ['user-approval', { policy: 'never' }],
  ['permission-presets', { defaultPreset: 'workspace-write', presets: {
    'workspace-write': { sandbox: 'workspace-write', approval: 'never' },
    'read-only': { sandbox: 'read-only', approval: 'never' },
    'danger-full-access': { sandbox: 'danger-full-access', approval: 'never' },
  } }],
  [process.platform === 'win32' ? 'pwsh-sandbox' : 'bash-sandbox'],
  ['attachment-local'], ['spill-local'], ['spill-policy'], ['subagent'],
  ['agent-loop', { agents: [] }], ['session-checkpoint-policy'],
];
const textOf = message => (message?.content ?? []).filter(block => block.type === 'text').map(block => block.text).join('');
const calls = [], events = [];
const normalFinal = 'FIXTURE_NORMAL_FINAL: 回应温柔一点，think 先是你引用的文字。';
let releaseAction;
const actionGate = new Promise(resolve => { releaseAction = resolve; });
class Fixture extends LlmAdapter {
  async listModels(provider) { return [{ provider, id: 'synthetic', name: 'Final-only fixture' }]; }
  async resolveModel(provider, id) { return { provider, id, name: 'Final-only fixture',
    inputModalities: ['text','image'], context: { contextWindow: 100000 } }; }
  async *stream(options) {
    // Runtime memory notices include earlier case markers; they are not the
    // current input. Select the actual channel/handback frame, not its history.
    const input = options.messages.findLast(message => message.role === 'user' &&
      /^(?:【本轮唯一当前输入】|【我自己交代出去的事回来了)/.test(textOf(message)))
      ?? options.messages.findLast(message => message.role === 'user');
    const current = textOf(input);
    const results = options.messages.slice(options.messages.lastIndexOf(input) + 1).filter(message => message.role === 'tool');
    const action = options.sessionId.startsWith('soyo-action-');
    const report = current.startsWith('【我自己交代出去的事回来了');
    calls.push({ session: options.sessionId, current, results: results.map(textOf), tools: (options.tools ?? []).map(t => t.name) });
    if (action) {
      await actionGate;
      yield { type: 'text-delta', index: 0, text: 'FIXTURE_ACTION_REPORT: bounded no-effect task completed.' };
      yield { type: 'finish', reason: { kind: 'stop' } }; return;
    }
    const delegate = current.includes('FIXTURE_DELEGATE') && !report;
    const toolError = current.includes('FIXTURE_TOOL_ERROR');
    const noFinal = current.includes('FIXTURE_NO_FINAL');
    const reasoning = current.includes('FIXTURE_REASONING');
    const recallImage = current.includes('FIXTURE_IMAGE_RECALL');
    const scripted = [['soyo_think', { thought: toolError ? 'x'.repeat(400) : 'Internal fixture decision.' }]];
    if (recallImage) {
      scripted.push(['soyo_recall_images', { message_id: 'fixture-old-image' }]);
      const receipt = results.map(textOf).find(text => text.includes('"items"'));
      if (receipt) {
        const path = JSON.parse(receipt).items?.[0]?.path;
        assert(path, 'recall must materialize the actual scoped source');
        scripted.push(['read_image', { file_path: path }]);
      }
    }
    if (delegate) scripted.push(['soyo_action_brain', { objective: 'FIXTURE_ACTION: no-effect report only; no tools or QQ sends.' }]);
    if (results.length < scripted.length) {
      const [name, args] = scripted[results.length];
      let index = 0;
      if (reasoning) yield { type: 'reasoning-delta', index: index++, text: 'PRIVATE_REASONING_BLOCK' };
      yield { type: 'text-delta', index: index++, text: 'NORMAL_PRE_TOOL: 我去看看，等我一下。think 是普通引用。' };
      yield { type: 'tool-call-delta', index, id: 'final-only-' + calls.length, name, argumentsDelta: JSON.stringify(args) };
      yield { type: 'finish', reason: { kind: 'tool-calls' } }; return;
    }
    if (toolError) throw Error('Intentional fixture model failure after an actual tool error');
    if (noFinal) { yield { type: 'finish', reason: { kind: 'max-tokens' } }; return; }
    yield { type: 'text-delta', index: 0, text: report ? 'FIXTURE_RESULT_FINAL' : delegate ? 'FIXTURE_STAGE_FINAL'
      : reasoning ? 'FIXTURE_REASONING_FINAL' : normalFinal };
    yield { type: 'finish', reason: { kind: 'stop' } };
  }
}
function request(path, body = {}) {
  return new Promise((resolve, reject) => {
    const endpoint = config.host_url ? { hostname: '127.0.0.1', port: new URL(config.host_url).port } : { socketPath: config.host_socket };
    const req = http.request({ ...endpoint, path, method: 'POST', headers: {
      Authorization: 'Bearer ' + config.host_key, 'Content-Type': 'application/json',
    } }, res => { let text = ''; res.on('data', b => { text += b; }); res.on('end', () => {
      try { assert.equal(res.statusCode, 200, text); resolve(JSON.parse(text)); } catch (error) { reject(error); }
    }); });
    req.setTimeout(15000, () => req.destroy(Error('Fixture HTTP request timed out')));
    req.on('error', reject); req.end(JSON.stringify(body));
  });
}
async function until(observe) {
  const end = Date.now() + 30000;
  while (Date.now() < end) { const result = await observe(); if (result) return result; await delay(25); }
  throw Error('Probe timed out; see trace.json in ' + root);
}
async function jobs() {
  return Promise.all((await readdir(join(config.native_root, 'jobs'))).filter(n => /^[a-f0-9]{64}\.json$/.test(n))
    .map(async n => JSON.parse(await readFile(join(config.native_root, 'jobs', n), 'utf8'))));
}
async function outboxWithCount(expected) {
  // A completed JSON file becomes visible at rename, before directory fsync
  // and the in-memory ready index settle. Observe the actual outbox contract,
  // not that narrower filesystem window, without weakening the exact count.
  return until(async () => {
    const items = (await request('/outbox')).items;
    assert(items.length <= expected, 'unexpected duplicate or extra publication');
    return items.length === expected ? items : null;
  });
}
async function submit(marker, expectedState = 'complete', extra = {}) {
  const accepted = await request('/inbound', { envelope: { account_id: config.account_id, route_id: 'qq-private-100001',
    target_id: '100001', sender_id: '100001', message_type: 'private', event_id: marker,
    occurred_at: Date.now() / 1000, text: marker + ': synthetic isolated owner input.', ...extra } });
  assert.equal(accepted.kind, 'accepted');
  const row = await until(async () => {
    const row = (await jobs()).find(row => row.key === accepted.key);
    return ['complete', 'failed', 'suppressed'].includes(row?.state) ? row : null;
  });
  assert.equal(row.state, expectedState, JSON.stringify(row));
  assert.equal(row.probe, false, '/probe bypasses the old progress bug; use real inbound admission');
  return row;
}
let result;
try {
  for (const [name, settings] of specs) { const module = await load(name); await ctx.plugin(module.default ?? module, settings ?? {}); }
  assert(ctx.attachments, 'native attachment storage must actually be mounted');
  ctx.llm.registerAdapter(['final-only-fixture'], new Fixture());
   ctx.on('session/event', (session, event) => events.push({ session: session.id, ...event }), { global: true });
  // Omit unused startup-only UI/settings dependencies, not the critical boundary.
  const qq = await import(pathToFileURL(join(root, 'host/qq-native.mjs')).href);
  await qq.apply(ctx, { configFile });
  await request('/routes', { routes: [{ route_id: 'qq-private-100001', target_id: '100001', message_type: 'private', name: 'Synthetic owner' }] });
  const ordinary = await submit('FIXTURE_NORMAL');
  assert.equal(ordinary.publication.text, normalFinal, 'Do not filter normal final text by thought-like keywords');
   assert.equal((await outboxWithCount(2)).length, 2, 'normal speech before tools is a separate publication');
  const separated = await submit('FIXTURE_REASONING');
  assert.equal(separated.publication.text, 'FIXTURE_REASONING_FINAL');
  const toolError = await submit('FIXTURE_TOOL_ERROR', 'suppressed');
  assert.equal(toolError.reason, 'error');
  assert(!toolError.publication);
  const noFinal = await submit('FIXTURE_NO_FINAL', 'suppressed');
  assert.equal(noFinal.reason, 'max-tokens');
  assert(!noFinal.publication, 'Never fall back to a previous assistant text when no final exists');
   assert.equal((await outboxWithCount(6)).length, 6, 'completed earlier speech stays valid even when later work fails');
  assert(events.some(e => e.type === 'tool/result' && e.data.message.isError), 'The tool error must actually execute');
  const stage = await submit('FIXTURE_DELEGATE');
  assert.equal(stage.publication.text, 'FIXTURE_STAGE_FINAL');
  assert(calls.some(c => c.results.some(value => value.includes('"execution_state":"queued"'))), 'Actual immediate queue acceptance');
  assert(!calls.some(c => c.current.includes('【我自己交代出去的事回来了')), 'Stage final must settle before the gated action returns');
  releaseAction();
  const followup = await until(async () => (await jobs()).find(row => row.origin_job_key === stage.key && row.internal_source === 'action-report' && row.state === 'complete'));
  assert.equal(followup.publication.text, 'FIXTURE_RESULT_FINAL');
   const all = await jobs(), outbox = await outboxWithCount(11);
  assert.equal(all.filter(j => j.internal_source === 'role-progress').length, 0, 'do not revive the old untyped progress path');
  assert.equal(outbox.length, 11);
  assert.equal(new Set(outbox.map(p => p.publication_id)).size, 11);
  assert(outbox.every(p => !/PRIVATE_REASONING_BLOCK/.test(p.text)));
  assert.equal(outbox.filter(p => p.publication_id.startsWith('qq-stage-')).length, 7);
  assert(events.some(e => e.type === 'assistant/message' && e.data.message.content.some(b => b.type === 'tool-call') && textOf(e.data.message).includes('NORMAL_PRE_TOOL')));
  assert(events.some(e => e.type === 'assistant/message' && e.data.message.content.some(b => b.type === 'reasoning')));
  const stagePublication = outbox.find(p => p.publication_id.startsWith('qq-stage-'));
  const permit={publication_id:stagePublication.publication_id,attempt_id:stagePublication.attempt_id,part_index:0};
  assert.equal((await request('/v1/channels/qq/outbox/authorize',permit)).kind,'accepted');
  assert.equal((await request('/v1/channels/qq/outbox/authorize',permit)).kind,'duplicate');
  const png = join(config.media_root, 'old-fixture.png');
  // Valid RGBA/CRC fixture: magic bytes alone are not enough for native sharp admission.
  await writeFile(png, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg==', 'base64'), { mode: 0o600 });
  const prepare = spawnSync(python, ['-B','-c',
    'import sys,json,time;sys.path.insert(0,sys.argv[1]);from soyo.qq import native_memory,media_cache;from soyo.platform import protect;c=json.load(open(sys.argv[2]));protect(sys.argv[3]);media_cache.record(c,"fixture-old-ref","image",{"path":sys.argv[3],"media_type":"image/png","name":"old.png"});native_memory.record(c,{"route_id":"qq-private-100001","event_id":"fixture-old-image","sender_id":"100001","target_id":"100001","message_type":"private","occurred_at":time.time()-7200,"text":"an old scoped source","media":[{"kind":"image","ref":"fixture-old-ref"}]})',
    core, configFile, png], { encoding:'utf8' });
  assert.equal(prepare.status,0,prepare.stderr);
  const materialized = spawnSync(python, ['-B', config.media_script, configFile], {
    env: workerEnvironment(), input: JSON.stringify({ media: [{kind:'image',ref:'invalid-first-reference'},{kind:'image',ref:'fixture-old-ref'}] }), encoding:'utf8' });
  assert.equal(materialized.status,0,materialized.stderr);
  assert.equal(JSON.parse(materialized.stdout).items[0]?.source_index,1,materialized.stdout);
  await ctx.attachments.saveImages([{ data: await readFile(png), mediaType:'image/png', name:'old-fixture.png' }]);
  const quoted = await submit('FIXTURE_IMAGE_QUOTE','complete',{reply_to:'fixture-old-image',media:[{kind:'image',ref:'invalid-first-reference'}]});
  const quotedCall = calls.find(call => call.current.includes('FIXTURE_IMAGE_QUOTE'));
  assert.match(quotedCall.current, /本轮引用的消息/, 'a failed first image must not relabel the old quoted image as current');
  const beforeRead=events.filter(e=>e.type==='tool/result'&&e.data.message.isError).length;
  const recalled = await submit('FIXTURE_IMAGE_RECALL');
  assert(recalled.admitted_image_paths.includes(png), 'delegation must retain the same admitted old-image capability');
  assert(calls.some(c=>c.current.includes('FIXTURE_IMAGE_RECALL')&&c.results.some(t=>t.includes('old-fixture.png'))));
  assert.equal(events.filter(e=>e.type==='tool/result'&&e.data.message.isError).length,beforeRead,'read_image must accept the retrieved original');
  const cancel = await request('/inbound',{envelope:{account_id:config.account_id,route_id:'qq-private-100001',
    target_id:'100001',sender_id:'100001',message_type:'private',event_id:'FIXTURE_STOP',occurred_at:Date.now()/1000,text:'/stop'}});
  await until(async()=>(await jobs()).find(j=>j.key===cancel.key&&j.state==='cancelled'));
  assert.equal((await request('/outbox')).items.length,0,'cancellation removes queued stages and finals');
  const unused=outbox.filter(p=>p.publication_id.startsWith('qq-stage-')).at(-1);
  assert.equal((await request('/v1/channels/qq/outbox/authorize',{publication_id:unused.publication_id,attempt_id:unused.attempt_id,part_index:0})).kind,'reject');
  result = { normal_final_unchanged: true, intermediate_text_retained_in_session: true, intermediate_publications: 7,
    reasoning_text_tool_case: true, tool_error_suppressed: true, missing_final_suppressed: true,
    asynchronous_stage_final: true, action_report_final: true, outbox_finals: 4, unique_publications:outbox.length,
    unique_stage_identities:true, queued_stage_cancelled:true, quoted_old_image_materialized:true,
    failed_image_source_index_preserved:true, old_image_recall_and_native_read:true };
  await writeFile(join(root, 'evidence.json'), JSON.stringify(result, null, 2), { mode: 0o600 });
  console.log(JSON.stringify({ root, ...result, external_model_calls: 0, qq_writer_installed: false }));
} finally {
  await writeFile(join(root, 'trace.json'), JSON.stringify({ calls, events }, null, 2), { mode: 0o600 });
  releaseAction(); await ctx.fiber.dispose();
}
