// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { test } from 'node:test';

test('Bot owner shortcut opens only the explicitly configured session, including a blank owner', () => {
  const source = readFileSync(new URL('../../soyo/dsh/dashboard/client.js', import.meta.url), 'utf8');
  let plugin; const slots = [], opened = [];
  const window = { __AGENT_QQBOT_OWNER__: { sessionId: 'fixture-owner', label: 'My chosen name' },
    __SOYO_DASHBOARD_URL__: 'http://127.0.0.1:12345', __ModuleLoader__: { load: value => { plugin = value; } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }) };
  const ctx = { slots: { inject: (_name, register) => register(), register: (meta, component) => slots.push({ meta, component }) },
    uiWorkspace: { openSession: id => opened.push(id) } };
  runInNewContext(source, { window, URL }); plugin.factory(() => React).apply(ctx);
  const node = slots.find(row => row.meta.id === 'bot-owner').component({ wide: true });
  assert.equal(node.props['aria-label'], '打开 Bot 主会话');
  assert.equal(node.children[0], 'My chosen name · Owner');
  assert.equal(opened.length, 0);
  node.props.onClick(); assert.deepEqual(opened, ['fixture-owner']);
  assert.equal(slots.find(row => row.meta.id === 'soyo-dashboard').component({ wide: true }).props['aria-label'], '打开 Bot 管理 Web');
});
