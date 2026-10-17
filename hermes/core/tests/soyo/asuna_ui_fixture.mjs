// SPDX-License-Identifier: MIT
// Loader-only synthetic inference over the real Soyo DualBrain/native log seam.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { LlmAdapter, createMessage } from '@deepseek-ai/dsh-llm';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { DualBrain } from './soyo-plugins/host/dual-brain.mjs';
import { QQData } from './soyo-plugins/host/qq-data.mjs';
import { BusinessUiApi } from './soyo-plugins/host/business-ui.mjs';
import { spawn } from 'node:child_process';

export const name = 'soyo-asuna-ui-fixture';
export const inject = ['llm', 'agents', 'sessions', 'sessionPersistence', 'sessionQuery',
  'sessionProjectionCache', 'workspaceRegistry', 'subagents', 'tools', 'systemPrompt', 'settings'];
export async function apply(ctx, settings) {
  const root = settings.root, parentId = 'soyo-ui-fixture-parent';
  await mkdir(root, { recursive: true });
  const callCounter = join(root, 'model-calls.json');
  await writeFile(callCounter, JSON.stringify({ synthetic_model_calls: 0, external_model_calls: 0 }), { mode: 0o600 });
  const route = { provider: 'soyo-ui-fixture', model: 'synthetic' };
  let modelCalls = 0;
  class Adapter extends LlmAdapter {
    async listModels(provider) { return [{ provider, id: route.model, name: 'Synthetic UI fixture' }]; }
    async resolveModel(provider, id) { return { provider, id, name: 'Synthetic UI fixture', context: { contextWindow: 100000 } }; }
    async *stream(options) {
      modelCalls += 1;
      await writeFile(callCounter, JSON.stringify({ synthetic_model_calls: modelCalls, external_model_calls: 0 }), { mode: 0o600 });
      const source = options.messages.findLast(message => message.role === 'user');
      const after = options.messages.slice(options.messages.lastIndexOf(source) + 1);
      const done = after.filter(message => message.role === 'tool').length;
      // The provider boundary deliberately strips Host-only message.source.
      const child = String(options.sessionId).startsWith('soyo-action-');
      const returned = !child && options.messages.some(message => (message.content ?? []).some(
        block => block.type === 'text' && block.text.includes('FIXTURE_NATIVE_HANDBACK:')));
      const calls = child ? [['report_progress', { text: 'FIXTURE_NATIVE_PROGRESS: 正在核对记录。' }],
        ['ask_character', { text: 'FIXTURE_NATIVE_QUESTION: 保留原来的方案吗？' }],
        ['report_progress', { text: 'FIXTURE_NATIVE_CHECK: 已核对三项记录。' }]] : returned ? [] : [
        ['soyo_think', { thought: 'FIXTURE_NATIVE_THOUGHT: 委托行动脑核对，结果回来再判断。' }],
        ['soyo_action_brain', { objective: 'FIXTURE_NATIVE_OBJECTIVE: 核对三项记录并给出报告，不操作外部平台。' }]];
      await delay(250, undefined, { signal: options.signal });
      // Declared synthetic provider usage, carried by the real native fold.
      // This is not a claim about external-model tokens.
      yield { type: 'usage', usage: { inputTokens: 1600 + done * 100, outputTokens: 80 } };
      if (done < calls.length) {
        const [tool, args] = calls[done];
        yield { type: 'tool-call-delta', index: 0, id: 'ui-fixture-' + modelCalls, name: tool, argumentsDelta: JSON.stringify(args) };
        yield { type: 'finish', reason: { kind: 'tool-calls' } }; return;
      }
      yield { type: 'text-delta', index: 0, text: child ? 'FIXTURE_NATIVE_ACTION_REPORT: 三项记录核对完成；未操作平台。'
        : returned ? 'FIXTURE_NATIVE_CHARACTER_READ: 已核对行动报告。' : 'FIXTURE_NATIVE_PARENT: 已交给行动脑，等实际结果。' };
      yield { type: 'finish', reason: { kind: 'stop' } };
    }
  }
  ctx.llm.registerAdapter([route.provider], new Adapter());
  await mkdir(root, { recursive: true });
  const configFile = join(root, 'fixture-config.json');
  const config = JSON.parse(await readFile(configFile, 'utf8'));
  let parent;
  const brains = new DualBrain(ctx, '', config, () => null, async task => {
    await parent.whenIdle();
    parent.followup(createMessage({ role: 'user', source: { kind: 'soyo-consultation', channel: 'soyo-qq', current: true,
      internal_source: 'action-report' }, content: [{ type: 'text', text: 'FIXTURE_NATIVE_HANDBACK: ' + task.report }] }));
    await parent.whenIdle(); await ctx.sessions.flush(parent.session);
    await brains.acknowledge(task.id, 'fixture-parent-return', true);
    await writeFile(join(root, 'ready.json'), JSON.stringify({ parent_id: parent.id, child_id: task.child_session_id,
      task_id: task.id, synthetic_model_calls: modelCalls, external_model_calls: 0, qq_sends: 0 }));
  });
  await brains.initialize();
  const data = new QQData(ctx, config, args => new Promise((resolve, reject) => {
    const child = spawn(config.python, ['-B', config.data_script, configFile], { stdio: ['pipe', 'pipe', 'pipe'] });
    let text = ''; child.stdout.on('data', part => text += part); child.stderr.resume();
    child.on('error', reject); child.on('close', code => { if (code) reject(Error('Fixture native read worker failed')); else {
      try { resolve(JSON.parse(text)); } catch (error) { reject(error); }
    } }); child.stdin.end(JSON.stringify(args));
  }), new Map());
  data.scenes.set('qq-private-100001', { route_id: 'qq-private-100001', message_type: 'private', name: 'Synthetic scene',
    target_id: '100001', session_id: parentId, enabled: true });
  new BusinessUiApi(ctx, data, brains, configFile, { applyStrategy: async next => Object.assign(config, next) });
  // Cold UI inspection retains the completed native logs without re-running
  // the synthetic task or waking either Agent.
  try { await readFile(join(root, 'ready.json')); return; }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const handle = await ctx.agents.create({ sessionId: parentId, meta: { cwd: root }, agentOptions: route,
    setup: scope => {
      scope.tools.restrict({ allow: [] });
      scope.tools.register(defineTool({ name: 'soyo_think', description: 'Fixture-only thought record',
        parameters: { thought: { type: 'string', required: true } },
        output: { schema: { type: 'object', additionalProperties: true }, render: () => [{ type: 'text', text: '{"state":"recorded"}' }] },
        execute: () => ({ state: 'recorded' }) }));
    } });
  parent = handle.agent;
  const workspace = await ctx.workspaceRegistry.create(root, 'Soyo · Asuna UI fixture');
  await workspace.attachSession(parent.id);
  parent.session.append('session/title', { title: 'Soyo · 原生内联控件验证', source: { kind: 'user' }, messageSeqs: [] });
  parent.followup(createMessage({ role: 'user', source: { kind: 'user', channel: 'soyo-qq', current: true }, content: [{ type: 'text', text: 'Synthetic UI fixture; no QQ or external model.' }] }));
  await parent.whenIdle(); await ctx.sessions.flush(parent.session);
  ctx.effect(() => async () => { await handle.dispose(); });
}
