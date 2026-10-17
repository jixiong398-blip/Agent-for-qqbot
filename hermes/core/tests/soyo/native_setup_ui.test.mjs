// SPDX-License-Identifier: MIT
// Real client module contract with inert RPC. No DOM server, model or QQ operation.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

const source = readFileSync(new URL('../../soyo/dsh/dashboard/client.js', import.meta.url), 'utf8');

function fixture() {
  let module, cursor = 0;
  const hooks = [], effects = [], calls = [], slots = [];
  const React = {
    Fragment: 'fragment',
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }),
    useState(initial) {
      const index = cursor++;
      if (!(index in hooks)) hooks[index] = initial;
      return [hooks[index], value => { hooks[index] = typeof value === 'function' ? value(hooks[index]) : value; }];
    },
    useRef: initial => ({ current: initial }),
    useEffect: action => effects.push(action),
  };
  const value = { configured: false, config: { character_name: 'My Bot', action_uses_character: true,
    models: { character: {}, action: {} }, onebot: { enabled: false, admin_ids: [], account_id: '', http_url: '', ws_url: '' },
    host_permission_mode: 'workspace-write', model_profiles: {}, time_zone: '', revision: 1 },
    persona: { text: '', digest: 'fixture', presets: [] }, operation: {},
    status: { services: { web: { running: true, pid: 42 }, napcat: { running: false }, gateway: { running: false, state: 'disabled' } } },
    napcat: { installed: true, version: 'fixture-version', accounts: [], launch_ready: true, webui_url: 'http://127.0.0.1:12345/' } };
  const ctx = {
    slots: { inject: (_name, register) => register(), register: (meta, component) => slots.push({ meta, component }) },
    connection: { rpc: { call: async (_endpoint, method) => { calls.push(method); if (method === 'botSetup/status') return { ok: true, value: value.status }; if (method === 'botSetup/logs') return { ok: true, value: { lines: ['fixture line'] } }; return { ok: true, value }; } } },
  };
  runInNewContext(source, {
    window: { __SOYO_DASHBOARD_URL__: 'http://127.0.0.1:12345', __ModuleLoader__: { load: row => { module = row; } } },
    URL, JSON, setInterval: () => 0, clearInterval: () => {},
  });
  module.factory(() => React).apply(ctx);
  const section = id => slots.find(row => row.meta.id === id).component;
  const render = id => {
    cursor = 0;
    const raw = section(id);
    if (id === 'soyo-dashboard') return raw({});
    const element = raw({});
    return element.type(element.props);
  };
  const mount = async id => {
    render(id);
    const pending = effects.splice(0);
    for (const action of pending) action();
    await new Promise(resolve => setImmediate(resolve));
    return render(id);
  };
  return { render, mount, calls };
}

function all(node) {
  if (!node || typeof node !== 'object') return [];
  return [node, ...(node.children || []).flatMap(all)];
}
const find = (tree, predicate) => all(tree).find(predicate);
const label = (tree, value) => find(tree, node => node.props['aria-label'] === value);

test('native settings page uses scoped responsive theme tokens and a persistent save footer', async () => {
  const app = fixture(), tree = await app.mount('soyo-bot-models');
  assert.ok(find(tree, node => node.props.className === 'bqs-page'));
  assert.equal(find(tree, node => node.props.className === 'bqs-top-title').children.join(''), '模型与脑区');
  const css = find(tree, node => node.type === 'style').children.join('');
  assert.match(css, /--dsw-alias-bg-base/);
  assert.match(css, /--dsw-alias-label-primary/);
  assert.match(css, /@media \(max-width: 600px\)/);
  assert.match(css, /prefers-reduced-motion/);
  assert.doesNotMatch(css, /(?:^|\n)(?:body|html|button|input)\s*[{,]/);
  assert.doesNotMatch(css, /@import|url\(/);
  assert(find(tree, node => node.type === 'footer' && node.props.className === 'bqs-footer'));
  assert.equal(find(tree, node => node.props.type === 'submit').props.disabled, false);
  assert.deepEqual(app.calls, ['botSetup/view']);
});

test('brain controls retain write-only keys, advanced budgets and distinct purple/blue lanes', async () => {
  const app = fixture(); let tree = await app.mount('soyo-bot-models');
  assert.equal(label(tree, 'API Key（留空保留已存密钥）').props.type, 'password');
  assert.equal(label(tree, 'API Key（留空保留已存密钥）').props.value, '');
  assert.equal(label(tree, '已确认的上下文上限').props.type, 'number');
  assert(find(tree, node => node.type === 'details'));
  const reuse = label(tree, '行动脑复用角色脑的供应商和模型（会话与职责仍独立）');
  reuse.props.onChange({ target: { checked: false } }); tree = app.render('soyo-bot-models');
  assert.equal(all(tree).filter(node => node.props['aria-label'] === '模型 ID').length, 2);
  assert(find(tree, node => node.props['data-tone'] === 'purple'));
  assert(find(tree, node => node.props['data-tone'] === 'blue'));
  assert.deepEqual(app.calls, ['botSetup/view']);
});

test('each settings page keeps its own controls and never auto-starts NapCat', async () => {
  const qq = fixture();
  let tree = await qq.mount('soyo-bot-qq');
  assert.equal(label(tree, '显式启用 QQ 接入').props.checked, false);
  assert.equal(label(tree, '启动 NapCat').props.disabled, false);
  assert.equal(label(tree, '打开 NapCat 管理页面 ↗').props.rel, 'noopener noreferrer');
  assert.equal(label(tree, '重新连接 QQ').props.disabled, true);
  assert.deepEqual(qq.calls, ['botSetup/view']);
  const persona = fixture();
  tree = await persona.mount('soyo-bot-persona');
  assert.equal(label(tree, '人格正文').type, 'textarea');
  assert.ok(all(tree).find(node => node.type === 'input' && node.props.value === 'My Bot'));
  assert.deepEqual(persona.calls, ['botSetup/view']);
});

test('management page embeds service status and logs with an optional standalone link', async () => {
  const app = fixture(), tree = await app.mount('soyo-dashboard');
  assert.equal(all(tree).filter(node => node.props.className === 'bqs-service-row').length, 3);
  assert.equal(all(tree).find(node => node.type === 'select').props.value, 'manager');
  assert(find(tree, node => node.type === 'pre' && node.props.className === 'bqs-logs'));
  const link = all(tree).find(node => node.type === 'a' && node.props.className === 'bqs-button');
  assert.equal(link.props.href, 'http://127.0.0.1:12345');
  assert.equal(link.props.rel, 'noopener noreferrer');
  assert.deepEqual(app.calls.slice(0, 2), ['botSetup/status', 'botSetup/logs']);
});
