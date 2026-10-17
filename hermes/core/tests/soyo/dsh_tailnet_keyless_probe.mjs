// Real tailnet ingress -> native signed cookie/RPC/mux; no models, sessions created, or QQ sends.
import assert from 'node:assert/strict';
import http from 'node:http';
import { writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';

const [base, release, evidence, expectedModel] = process.argv.slice(2);
assert(base && release && evidence, 'Pass tailnet URL, native release, and private evidence file.');
const require = createRequire(release + '/package.json');
const WebSocket = require('ws');
let cookie;
const request = (path, options = {}) => fetch(base + path, { redirect: 'manual',
  signal: AbortSignal.timeout(15000), ...options,
  headers: { ...(cookie ? { Cookie: cookie } : {}), ...(options.headers || {}) } });
const wireRequest = headers => new Promise((resolve, reject) => {
  const req = http.get(base + '/', { headers }, res => {
    res.resume(); resolve({ status: res.statusCode, cookie: res.headers['set-cookie'] });
  });
  req.setTimeout(8000, () => req.destroy(new Error('Wire-header check timed out.')));
  req.on('error', reject);
});

for (const path of ['/api/session/list', '/plugins/soyo-dashboard/client.js']) {
  const denied = await request(path);
  assert.equal(denied.status, 401);
  assert.equal(denied.headers.get('set-cookie'), null);
}
assert.equal((await request('/?token=not-a-token')).status, 400);
assert.equal((await request('/soyo-login', { method: 'POST' })).status, 404);
for (const headers of [{ Host: 'attacker.invalid' }, { Origin: 'http://attacker.invalid' },
  { 'Sec-Fetch-Site': 'cross-site' }]) {
  const denied = await wireRequest(headers);
  assert.equal(denied.status, 403);
  assert.equal(denied.cookie, undefined);
}
const deniedUpgrade = (headers, path = '/api/remote.mux') => new Promise((resolve, reject) => {
  const socket = new WebSocket(base.replace(/^http/, 'ws') + path, { headers });
  const timer = setTimeout(() => { socket.terminate(); reject(new Error('Upgrade fence timed out.')); }, 8000);
  socket.on('unexpected-response', (_request, response) => {
    clearTimeout(timer); response.resume(); socket.terminate(); resolve(response.statusCode);
  });
  socket.on('open', () => { clearTimeout(timer); socket.close(); reject(new Error('Unexpected upgrade admission.')); });
  socket.on('error', error => { clearTimeout(timer); reject(error); });
});
assert.equal(await deniedUpgrade({ Origin: base }), 403);

const initial = await request('/');
assert.equal(initial.status, 303);
assert.equal(initial.headers.get('location'), './');
const nativeCookie = initial.headers.get('set-cookie');
assert.match(nativeCookie, /^dsh-auth-/);
assert.match(nativeCookie, /HttpOnly; SameSite=Strict/);
cookie = nativeCookie.split(';', 1)[0];
const root = await request('/');
assert.equal(root.status, 200);
const html = await root.text();
assert.match(html, /__DSH_BOOT__/);
assert(!html.includes('action="/soyo-login"'));
assert(!html.includes('type="password"'));
assert(!/[?&]token=/.test(html));
assert.equal((await request('/api/session/list', { headers: { Origin: 'http://attacker.invalid' } })).status, 403);
assert.equal(await deniedUpgrade({ Cookie: cookie, Origin: 'http://attacker.invalid' }), 403);
assert.equal(await deniedUpgrade({ Cookie: cookie, Origin: base }, '/not-a-native-mux'), 403);

const method = 'settings/describe';
const settings = await request('/api/' + method, { method: 'POST',
  headers: { Origin: base, 'Content-Type': 'application/json' },
  body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method, payload: { args: {} } }) });
assert.equal(settings.status, 200);
const data = await settings.json();
assert.equal(data.result.ok, true);
const providers = data.result.value.namespaces.find(row => row.ns === 'llm-pi-ai').value.providers;
assert.equal(providers['soyo-model'].baseURL, 'http://127.0.0.1:31899/v1');
assert.equal(typeof providers['soyo-model'].models[0].id, 'string');
if (expectedModel) assert.equal(providers['soyo-model'].models[0].id, expectedModel);

async function muxReady() {
  await new Promise((resolve, reject) => {
    const socket = new WebSocket(base.replace(/^http/, 'ws') + '/api/remote.mux',
      { headers: { Cookie: cookie, Origin: base } });
    const timer = setTimeout(() => { socket.terminate(); reject(new Error('Native mux readiness timeout.')); }, 10000);
    socket.on('error', error => { clearTimeout(timer); reject(error); });
    socket.on('open', () => socket.send(JSON.stringify({ type: 'open', streamId: 'keyless-readiness',
      endpoint: '$events', payload: { args: {} } })));
    socket.on('message', raw => {
      const value = JSON.parse(raw.toString());
      if (value.type === 'error') { clearTimeout(timer); socket.close(); reject(new Error('Native mux rejected readiness.')); }
      if (value.type === 'item' && value.value?.type === 'ready') { clearTimeout(timer); socket.close(); resolve(); }
    });
  });
}
const deadline = Date.now() + 120000;
while (true) {
  try { await muxReady(); break; }
  catch (error) { if (Date.now() >= deadline) throw error; await delay(2000); }
}
const proof = { passed: true, no_key_required: true, native_cookie_preserved: true,
  token_urls_denied: true, host_origin_cross_site_fence_preserved: true,
  unauthenticated_api_denied: true, websocket_fence_preserved: true,
  native_settings_read: true, native_mux_ready: true, model: providers['soyo-model'].models[0].id,
  model_requests: 0, session_creates: 0, qq_sends: 0, browser_dom_verified: false };
await writeFile(evidence, JSON.stringify(proof, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
console.log(JSON.stringify(proof));
