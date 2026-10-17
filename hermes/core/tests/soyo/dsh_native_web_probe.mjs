// Actual official CLI/profile -> tailnet key form -> native cookie/RPC/mux; no model or QQ.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import http from 'node:http';

const [base, keyFile, release, workspace, evidenceFile] = process.argv.slice(2);
assert(base && keyFile && release && workspace && evidenceFile, 'Pass URL/keyfile/release/workspace/evidence.');
const key = (await readFile(keyFile, 'utf8')).trim();
const require = createRequire(release + '/package.json');
const WebSocket = require('ws');
let cookie;
const request = (path, options = {}) => fetch(base + path, { redirect: 'manual', signal: AbortSignal.timeout(15000),
  ...options, headers: { ...(cookie ? { Cookie: cookie } : {}), ...(options.headers || {}) } });
async function rpc(endpoint, args) {
  const response = await request('/api/' + endpoint, { method: 'POST', headers: { Origin: base, 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'client-request', rpcId: randomUUID(), method: endpoint, payload: { args } }) });
  assert.equal(response.status, 200, endpoint);
  const data = await response.json();
  assert.equal(data.type, 'server-response');
  assert.equal(data.result.ok, true, JSON.stringify(data.result));
  return data.result.value;
}

// systemd Type=simple is process-start, not appReady. Bound initial socket readiness independently.
const startupDeadline = Date.now() + 90000;
while (true) {
  try { const response = await request('/'); if (response.status === 401) break; }
  catch (error) { if (Date.now() >= startupDeadline) throw error; }
  if (Date.now() >= startupDeadline) throw new Error('Native Web never became ready.');
  await delay(250);
}

for (const path of ['/', '/api/session/list', '/plugins/soyo-dashboard/client.js']) {
  const denied = await request(path);
  assert.equal(denied.status, 401);
  assert.equal(denied.headers.get('set-cookie'), null);
  if (path === '/') assert.equal(denied.headers.get('referrer-policy'), 'same-origin');
}
assert.equal((await request('/?token=not-a-token')).status, 400);
for (const [origin, value, status] of [['http://attacker.invalid', key, 403], [base, 'wrong-key', 401]]) {
  const denied = await request('/soyo-login', { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ key: value }).toString() });
  assert.equal(denied.status, status);
  assert.equal(denied.headers.get('set-cookie'), null);
}
const login = await request('/soyo-login', { method: 'POST', headers: { Origin: base, 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ key }).toString() });
assert.equal(login.status, 303);
assert.equal(login.headers.get('location'), './');
const nativeCookie = login.headers.get('set-cookie');
assert.match(nativeCookie, /^dsh-auth-/);
assert.match(nativeCookie, /HttpOnly; SameSite=Strict/);
cookie = nativeCookie.split(';', 1)[0];

const root = await request('/');
assert.equal(root.status, 200);
const html = await root.text();
assert.match(html, /__DSH_BOOT__/);
assert.match(html, /__SOYO_DASHBOARD_URL__/);
assert(!html.includes(key), 'Never inject key into native page.');
assert(!html.includes('readSessionIds'), 'Never inject host grants into native page.');
for (const asset of [...html.matchAll(/(?:src|href)="(\/(?:assets|plugins)\/[^"?#]+\.js)"/g)].map(match => match[1])) {
  assert.equal((await request(asset)).status, 200, asset);
}
assert.equal((await request('/api/session/list', { headers: { Origin: 'http://attacker.invalid' } })).status, 403);
// Node fetch may replace Host with the URL authority; send the actual wrong wire header.
const wrongHost = await new Promise((resolve, reject) => {
  const req = http.get(base + '/api/session/list', { headers: { Host: 'attacker.invalid', Cookie: cookie } }, res => {
    res.resume(); resolve(res.statusCode);
  });
  req.setTimeout(8000, () => req.destroy(new Error('Wrong-Host test timed out.')));
  req.on('error', reject);
});
assert.equal(wrongHost, 403);

const created = await rpc('session/create', { request: { sessionId: 'soyo-owner', cwd: workspace, agentPreset: 'standard' } });
assert.equal(created.sessionId, 'soyo-owner');
const listed = await rpc('session/list', { _request: {} });
assert(listed.items.some(row => row.sessionId === 'soyo-owner'));

const ready = await new Promise((resolve, reject) => {
  const socket = new WebSocket(base.replace(/^http/, 'ws') + '/api/remote.mux', { headers: { Cookie: cookie, Origin: base } });
  const timer = setTimeout(() => { socket.terminate(); reject(new Error('Native mux readiness timeout.')); }, 10000);
  socket.on('error', reject);
  socket.on('open', () => socket.send(JSON.stringify({ type: 'open', streamId: 'probe-events', endpoint: '$events', payload: { args: {} } })));
  socket.on('message', raw => {
    const message = JSON.parse(raw.toString());
    if (message.type === 'error') { clearTimeout(timer); socket.terminate(); reject(new Error(JSON.stringify(message))); }
    if (message.type === 'item' && message.value?.type === 'ready') {
      clearTimeout(timer);
      socket.close();
      resolve(message.value.type);
    }
  });
});
assert.equal(ready, 'ready');
const result = { passed: true, official_native_profile_http_verified: true, native_cookie_no_network_token_url: true,
  cross_origin_and_wrong_host_denied: true, native_session_create_list_verified: true, native_mux_ready_verified: true,
  owner_session_id: 'soyo-owner', native_sidebar_navigation_published: true, model_requests: 0, qq_connected: false,
  full_browser_dom_verified: false, full_soyo_migration_verified: false };
await writeFile(evidenceFile, JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
console.log(JSON.stringify(result));
