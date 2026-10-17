// Real authenticated native settings/credential metadata; no model requests or writes.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

const [base, keyFile, evidenceFile] = process.argv.slice(2);
assert(base && keyFile && evidenceFile, 'Pass URL/keyfile/evidence file.');
const expectedBaseURL = process.env.SOYO_PROBE_EXPECTED_MODEL_BASE_URL;
assert(typeof expectedBaseURL === 'string' && expectedBaseURL.trim(), 'Explicit SOYO_PROBE_EXPECTED_MODEL_BASE_URL required; no supplier default.');
const key = (await readFile(keyFile, 'utf8')).trim();
const settingsPath = '/api/settings/describe';
assert.equal((await fetch(base + settingsPath)).status, 401);
const login = await fetch(base + '/soyo-login', { method: 'POST', redirect: 'manual',
  headers: { Origin: base, 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ key }), signal: AbortSignal.timeout(15000) });
assert.equal(login.status, 303);
const cookie = login.headers.get('set-cookie').split(';', 1)[0];
const request = (path, options = {}) => fetch(base + path, { signal: AbortSignal.timeout(15000),
  ...options, headers: { Cookie: cookie, Origin: base, ...(options.headers ?? {}) } });
const rpc = async (endpoint, args = {}) => {
  const response = await request('/api/' + endpoint, { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method: endpoint, payload: { args } }) });
  assert.equal(response.status, 200, endpoint);
  const envelope = await response.json();
  assert(envelope.result?.ok, endpoint + ' was rejected');
  return envelope.result.value;
};
const root = await (await request('/')).text();
assert(root.includes('__SOYO_DSH_REMOTE_SETTINGS__'));
assert(!root.includes(key));
const bootMatch = root.match(/globalThis\["__DSH_BOOT__"\]\s*=\s*([^<]+)<\/script>/);
assert(bootMatch, 'Native boot graph');
const boot = JSON.parse(bootMatch[1]);
const settingsEntry = boot.entries.find(row => row.id === '@deepseek-ai/dsh-client-ui-settings');
assert(settingsEntry, 'Native settings client entry');
const clientURL = new URL(settingsEntry.url, base + '/');
assert.equal(clientURL.origin, new URL(base).origin);
assert(clientURL.pathname.startsWith('/plugins/'));
const asset = await request(clientURL.pathname + clientURL.search);
assert.equal(asset.status, 200);
const client = await asset.text();
assert(client.includes('remoteSettings.origin === globalThis.location?.origin'));
assert(!client.includes('$host.isLoopback ='), 'Do not forge host locality');
assert.equal((await request(settingsPath, { headers: { Origin: 'http://attacker.invalid' } })).status, 403);
const described = await rpc('settings/describe');
assert.equal(described.writable, true);
const namespace = described.namespaces.find(row => row.ns === 'llm-pi-ai');
assert(namespace, 'Native model namespace must be served');
const profile = namespace.value.providers['soyo-model'];
assert(profile, 'Existing primary route, not a new provider');
assert.equal(profile.api, 'openai-responses');
assert.equal(profile.baseURL, expectedBaseURL);
const directory = await rpc('llm/listConfigurableProviders');
assert(directory.some(row => row.provider === 'soyo-model'));
const credentials = await rpc('credentials/describe', { refs: [profile.apiKeyEnv] });
assert.equal(credentials[profile.apiKeyEnv].configured, true);
assert(!('value' in credentials[profile.apiKeyEnv]) && !('key' in credentials[profile.apiKeyEnv]));
const result = { passed: true, native_settings_describe_verified: true, native_settings_writable: true,
  exact_origin_opt_in_asset_verified: true, cross_origin_and_unauthenticated_denied: true,
  model_provider_directory_verified: true, provider: 'soyo-model', display_name: profile.displayName,
  protocol: profile.api, model: profile.models[0].id, credential_metadata_redacted: true,
  model_requests: 0, settings_writes: 0, qq_connected: false, full_browser_dom_verified: false };
await writeFile(evidenceFile, JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify(result));
