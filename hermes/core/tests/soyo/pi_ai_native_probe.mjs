// SPDX-License-Identifier: MIT
// Actual pinned SDK artifacts, synthetic events and a fetch stub only.
// Usage: node pi_ai_native_probe.mjs <isolated-native-runtime>
import assert from 'node:assert/strict';
import { readdir, readFile, lstat, realpath } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

assert(process.argv[2], 'Pass an isolated native runtime, not a running deployment.');
const modules = join(resolve(process.argv[2]), 'node_modules');
const packages = new Set();
for (const [directory, suffix] of [['.pnpm', 'node_modules/@earendil-works/pi-ai'], ['.portable', '']]) {
  for (const entry of await readdir(join(modules, directory), { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.isSymbolicLink()) continue;
    const candidate = join(modules, directory, entry.name, suffix);
    try {
      const info = await lstat(candidate);
      if (!info.isDirectory() || info.isSymbolicLink()) continue;
      const manifest = JSON.parse(await readFile(join(candidate, 'package.json'), 'utf8'));
      if (manifest.name !== '@earendil-works/pi-ai') continue;
      assert.equal(manifest.version, '1.1.0');
      packages.add(await realpath(candidate));
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}
assert(packages.size, 'No physical reviewed pi-ai artifacts found');
const model = { id: 'fixture', name: 'Synthetic fixture', provider: 'fixture', api: 'openai-responses',
  baseUrl: 'https://example.invalid/v1', input: ['text'], reasoning: false, contextWindow: 8192, maxTokens: 1024,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } };
let cases = 0, stubRequests = 0;
for (const packageRoot of packages) {
  const { processResponsesStream } = await import(pathToFileURL(join(packageRoot, 'dist/api/openai-responses-shared.js')));
  for (const terminal of [undefined, null, 42, '{"value":"fixture"}']) {
    const events = [
      { type: 'response.output_item.added', output_index: 0,
        item: { type: 'function_call', id: 'fc_fixture', call_id: 'call_fixture', name: 'bounded_tool', arguments: '' } },
      { type: 'response.function_call_arguments.delta', output_index: 0, delta: '{"value":"fixture"}' },
      { type: 'response.function_call_arguments.done', output_index: 0, ...(terminal === undefined ? {} : { arguments: terminal }) },
      { type: 'response.output_item.done', output_index: 0,
        item: { type: 'function_call', id: 'fc_fixture', call_id: 'call_fixture', name: 'bounded_tool' } },
      { type: 'response.completed', response: { id: 'resp_fixture', status: 'completed', output: [] } },
    ];
    const output = { content: [], stopReason: 'pending', usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
    const emitted = [];
    await processResponsesStream((async function* () { yield* events; })(), output, { push: event => emitted.push(event) }, model);
    assert.equal(output.stopReason, 'toolUse');
    assert.deepEqual(output.content[0].arguments, { value: 'fixture' });
    assert.equal(output.content[0].partialJson, undefined, 'scratch buffers must not persist');
    assert(emitted.some(event => event.type === 'toolcall_end'));
    cases++;
  }
  const provider = await import(pathToFileURL(join(packageRoot, 'dist/api/openai-responses.js')));
  const secret = 'sk-' + 'a'.repeat(30), endpoint = 'https://private.example.invalid/secret';
  const emitted = [];
  for await (const event of provider.stream(model, { messages: [{ role: 'user', content: 'fixture', timestamp: 0 }] }, {
    apiKey: 'fixture-not-a-real-key', maxRetries: 0, timeoutMs: 1000,
    fetch: async () => {
      stubRequests++;
      throw new TypeError('Synthetic fetch failure', { cause: Error('SAFE_CAUSE_CODE ' + endpoint + ' Bearer ' + secret) });
    },
  })) emitted.push(event);
  const message = emitted.find(event => event.type === 'error')?.error?.errorMessage;
  assert(message && message.includes('SAFE_CAUSE_CODE'), String(message));
  assert(!message.includes(secret) && !message.includes(endpoint), 'diagnostic must redact endpoints and credentials');
  assert(message.length < 2500, 'cause diagnostics are bounded');
}
assert.equal(stubRequests, packages.size, 'synthetic transport failure is not retried');
console.log(JSON.stringify({ physical_sdk_copies: packages.size, terminal_argument_cases: cases,
  cause_redaction_verified: true, synthetic_fetch_calls: stubRequests, external_requests: 0 }));
