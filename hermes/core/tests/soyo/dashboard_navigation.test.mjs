// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

test('Bot settings live in the DSH settings dialog, not the sidebar footer', () => {
  const source = readFileSync(new URL('../../soyo/dsh/dashboard/client.js', import.meta.url), 'utf8');
  let plugin; const slots = [];
  const window = { __AGENT_QQBOT_OWNER__: { sessionId: 'fixture-owner', label: 'My chosen name' },
    __SOYO_DASHBOARD_URL__: 'http://127.0.0.1:12345', __ModuleLoader__: { load: value => { plugin = value; } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }) };
  const ctx = {
    slots: { inject: (_name, register) => register(), register: (meta, component) => slots.push({ meta, component }) },
    connection: { rpc: { call: async () => ({ ok: true, value: {} }) } },
  };
  runInNewContext(source, { window, URL });
  plugin.factory(() => React).apply(ctx);
  assert.equal(slots.filter(row => row.meta.name === 'sidebar.footer.action').length, 0);
  const sections = slots.filter(row => row.meta.name === 'settings.section');
  assert.deepEqual(sections.map(row => row.meta.id),
    ['soyo-bot-models', 'soyo-bot-persona', 'soyo-bot-qq', 'soyo-dashboard']);
  assert.deepEqual(sections.map(row => row.meta.order), [30, 31, 32, 34]);
  assert.deepEqual(sections.map(row => row.meta.label), ['模型与脑区', '角色设定', 'NapCat / QQ', '管理 Web']);
  assert.ok(!sections.some(row => /Owner/.test(row.meta.label)), 'owner session stays in the normal session list');
});
