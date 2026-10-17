// A real native ToolRuntime -> real Dashboard HTTP design probe, no model/QQ.
// Invoke from a disposable directory containing the pinned npm dependencies.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import vm from 'node:vm';

const [python, dashboardDir, pluginDir] = process.argv.slice(2);
assert(python && dashboardDir && pluginDir, 'Pass python, Dashboard source and plugin directories.');
const require = createRequire(process.cwd() + '/package.json');
const load = name => import(require.resolve(name));
const [{ Context }, { ToolRuntime }, prompt, { Session }, { SlotCore }, React, renderer] = await Promise.all([
  load('@deepseek-ai/cordis'), load('@deepseek-ai/dsh-tools'), load('@deepseek-ai/dsh-system-prompt'),
  load('@deepseek-ai/dsh-session'), load('@deepseek-ai/dsh-client-ui-slots'), load('react'), load('react-dom/server'),
]);
const Dashboard = await import(new URL('index.mjs', `file://${pluginDir}/`));
const packageRequire = createRequire(pluginDir + '/package.json');
assert.equal(packageRequire.resolve('@soyo/dsh-dashboard/package.json'), pluginDir + '/package.json');
assert.equal(packageRequire.resolve('@soyo/dsh-dashboard/client'), pluginDir + '/client.js');
const fixture = spawn(python, [new URL('dashboard_http_fixture.py', import.meta.url).pathname, dashboardDir],
  { stdio: ['ignore', 'pipe', 'inherit'], env: {
    PATH: '/usr/bin:/bin', LANG: 'C.UTF-8', TZ: 'UTC', PYTHONDONTWRITEBYTECODE: '1',
  } });
const line = createInterface({ input: fixture.stdout });
const ready = await Promise.race([
  once(line, 'line').then(([value]) => JSON.parse(value)),
  once(fixture, 'exit').then(() => { throw new Error('HTTP fixture exited before readiness.'); }),
]);
line.close();
const fixtureKey = (await readFile(ready.key_file, 'utf8')).trim();
const authorization = 'Basic ' + Buffer.from('admin:' + fixtureKey).toString('base64');
const fixtureFetch = path => fetch(ready.url + path, { headers: { Authorization: authorization } });
const ctx = new Context();
try {
  for (const path of ['/', '/static/admin.js', '/api/session', '/api/runtime']) {
    const denied = await fetch(ready.url + path);
    assert.equal(denied.status, 401);
    assert.match(denied.headers.get('www-authenticate'), /^Basic /);
    assert.equal((await denied.json()).csrf, undefined);
  }
  await ctx.plugin(prompt.SystemPrompt, {});
  await ctx.plugin(ToolRuntime, {});
  const config = { apiURL: ready.url, publicURL: 'https://dashboard.example.invalid/', accessKeyFile: ready.key_file,
    readSessionIds: ['reader'], controlSessionIds: ['trusted-action'] };
  await ctx.plugin(Dashboard, config);
  assert(ctx.tools.schemas().some(tool => tool.name === 'soyo_dashboard'));
  const callers = new Map();
  const call = (id, action, extra = {}) => {
    if (!callers.has(id)) callers.set(id, { session: Session.create(id) });
    return ctx.tools.execute({ callId: `probe-${id}-${action}`, name: 'soyo_dashboard',
      arguments: { action, ...extra }, agent: callers.get(id), signal: new AbortController().signal });
  };
  const status = await call('trusted-action', 'status');
  assert.equal(status.isError, false, JSON.stringify(status));
  assert.equal(status.value.backend, 'dsh');
  assert.equal(status.value.services.gateway.running, true);
  const beforeDenial = await (await fixtureFetch('/fixture/observations')).json();
  assert.equal((await call('qq-external', 'restart')).isError, true);
  assert.equal((await call('reader', 'restart')).isError, true);
  assert.equal((await call('trusted-action', 'status', { service: 'napcat' })).isError, true);
  assert.equal((await call('trusted-action', 'delete')).isError, true);
  const afterDenial = await (await fixtureFetch('/fixture/observations')).json();
  assert.equal(afterDenial.api_reads, beforeDenial.api_reads, 'Denied calls must not reach management HTTP.');
  const logs = await call('reader', 'logs');
  assert.equal(logs.isError, false, JSON.stringify(logs));
  assert.match(logs.value.log, /Synthetic Dashboard journal/);
  const restart = await call('trusted-action', 'restart');
  assert.equal(restart.isError, false, JSON.stringify(restart));
  assert.equal(restart.value.state, 'scheduled');
  await fixtureFetch('/fixture/backend/hermes');
  assert.equal((await call('trusted-action', 'restart')).isError, true, 'Wrong backend must refuse before CSRF/mutation.');
  assert.equal((await (await fixtureFetch('/fixture/observations')).json()).posts.length, 1);
  await fixtureFetch('/fixture/backend/dsh');
  await fixtureFetch('/fixture/drop-next-receipt');
  const lost = await call('trusted-action', 'restart');
  assert.equal(lost.isError, false, JSON.stringify(lost));
  assert.equal(lost.value.state, 'unknown');
  const observations = await (await fixtureFetch('/fixture/observations')).json();
  assert.equal(observations.isolation_checks, 2);
  assert.equal(observations.dropped_receipts, 1);
  assert.deepEqual(observations.posts.map(post => post.body.service), ['dashboard', 'dashboard']);
  assert(!observations.commands.some(command => command[0] === 'napcat'));

  // Execute the published client entry format with the actual DSH pure SlotCore.
  // This is NOT a full DSH Web loader/DOM/auth test.
  let module;
  const injectionRows = [];
  ctx.emit('webserver/index-inject', injectionRows);
  const navigation = injectionRows.find(row => row.name === '__SOYO_DASHBOARD_URL__');
  assert.equal(navigation?.value, 'https://dashboard.example.invalid');
  assert(!JSON.stringify(injectionRows).includes('trusted-action'), 'Never publish permission config to browser.');
  assert(!JSON.stringify(injectionRows).includes(fixtureKey), 'Never publish access key to browser.');
  vm.runInNewContext(await readFile(pluginDir + '/client.js', 'utf8'), {
    URL, window: { __SOYO_DASHBOARD_URL__: navigation.value,
      __ModuleLoader__: { load: value => { module = value; } } },
  });
  const slots = new SlotCore();
  slots.register({ name: 'root', children: { 'sidebar.footer.action': { kind: 'list', scope: 'root' } } }, () => null);
  module.factory(name => { assert.equal(name, 'react'); return React; }).apply({ slots: {
    inject: (_name, callback) => callback(), register: slots.register.bind(slots),
  } });
  const entry = slots.entriesOfSlot('sidebar.footer.action')[0];
  assert(entry, 'Client sidebar contribution missing.');
  const html = renderer.renderToStaticMarkup(React.createElement(entry.component, { wide: true }));
  assert.match(html, /管理 Web/);
  assert.match(html, /noopener noreferrer/);
  assert(!html.includes('iframe'));
  console.log(JSON.stringify({ passed: true, dshVersion: '0.2.0-rc.2', native_tool_runtime_http_verified: true,
    http_key_auth_verified: true, csrf_scheduled_only: true, wrong_backend_mutations: 0, denied_call_http_requests: 0,
    lost_receipt_unknown_no_retry: true, unauthorized_mutations: 0, napcat_commands: 0,
    client_slot_core_render_verified: true, manifest_export_verified: true,
    dsh_web_or_model_or_production_service_verified: false }));
} finally {
  try {
    await ctx.fiber.dispose();
  } finally {
    if (fixture.exitCode === null && fixture.signalCode === null) {
      const exited = once(fixture, 'exit');
      fixture.kill('SIGTERM');
      await exited;
    }
  }
}
