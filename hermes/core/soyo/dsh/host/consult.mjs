// SPDX-License-Identifier: MIT
// Persistent GPT collaborator with the same native host tools as Soyo.
import { open, rename } from 'node:fs/promises';
import { constants } from 'node:fs';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createMessage } from '@deepseek-ai/dsh-llm';
import { credentialRef } from '@deepseek-ai/dsh-credentials';
import { SessionPersistenceNotFoundError } from '@deepseek-ai/dsh-session-persistence';
import { HOST_TOOL_NAMES } from './role-runtime.mjs';
import { mountNativeHostTools } from './native-host-tools.mjs';
import { PERSONA_PREFIX_SECTION } from '@deepseek-ai/dsh-system-prompt';
import { openPrivate, syncDirectory } from './platform.mjs';

const helperStates = new WeakMap();
const helperSessionId = config => config.collaborator?.session_id || 'soyo-gpt-helper';

function helperState(ctx) {
  let state = helperStates.get(ctx);
  if (!state) { state = { handle: null, tail: Promise.resolve(), cleaned: false }; helperStates.set(ctx, state); }
  return state;
}

async function durable(path, value) {
  const temporary = path + '.' + randomUUID() + '.tmp';
  const file = await open(temporary, 'wx', 0o600);
  try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); }
  finally { await file.close(); }
  await rename(temporary, path);
  await syncDirectory(join(path, '..'));
}

export async function configureCollaborator(ctx, config) {
  const settings = config.collaborator;
  if (!settings) return;
  const ref = credentialRef(settings.credential_ref);
  let file;
  try {
    file = await openPrivate(settings.key_file, 256);
    const key = (await file.readFile('utf8')).trim();
    const existing = await ctx.credentials.resolve(ref);
    if (existing && existing.value !== key) throw Error('Existing collaborator credential differs; do not overwrite');
    if (!existing) await ctx.credentials.set(ref, key);
  } catch (error) {
    if (error.code !== 'ENOENT' || !(await ctx.credentials.describe(ref)).configured) throw Error('Collaborator credential not ready');
  } finally { await file?.close(); }
  try {
    for (const item of await ctx.sessionQuery.listSessions()) {
      const id = item.header?.id;
      if (id?.startsWith('soyo-consult-')) await ctx.workspaceRegistry.archiveSession(id, { stopActivity: true }).catch(() => {});
    }
  } catch {}
}

async function consultOne(ctx, config, question, parent, signal, state) {
  const settings = config.collaborator;
  if (!settings || typeof question !== 'string' || !question.trim() || question.length > 4000 || /\bsk-[A-Za-z0-9_-]{16,}/.test(question)) throw Error('Bounded, credential-free question required');
  const sessionId = helperSessionId(config);
  if (!state.cleaned) {
    try {
      for (const item of await ctx.sessionQuery.listSessions()) {
        const id = item.header?.id;
        if (id?.startsWith('soyo-consult-')) await ctx.workspaceRegistry.archiveSession(id, { stopActivity: true }).catch(() => {});
      }
    } catch {}
    state.cleaned = true;
  }
  let last, end, turn;
  const observe = ctx.on('session/event', (session, event) => {
    if (session.id !== sessionId) return;
    if (event.type === 'turn/start') turn = event.data.turn;
    if (event.type === 'assistant/message' && event.data.turn === turn) last = event;
    if (event.type === 'turn/end' && event.data.turn === turn) end = event;
  }, { global: true });
  try {
    if (!state.handle) {
      const setup = async (scope, agent) => {
        scope.tools.restrict({ allow: [] });
        await mountNativeHostTools(scope, agent);
        scope.tools.presentAs('native');
        scope.tools.guard(exec => HOST_TOOL_NAMES.has(exec.name)
          ? undefined : 'GPT consultation may use only the shared native Host tools');
        scope.on('system-prompt/assemble', async (_assembly, { agent: assembledAgent }, next) => {
          const assembly = await next();
          if (assembledAgent?.id !== agent.id || !Array.isArray(assembly.tools)) return assembly;
          // Inherited global declarations (e.g. Schedule) are not executable
          // under the guard. Do not advertise capabilities GPT cannot use.
          return { ...assembly, tools: assembly.tools.filter(tool => HOST_TOOL_NAMES.has(tool.name)) };
        });
        scope.systemPrompt.suppressRuntimeContext();
        scope.on('agent/pre-step', (payload, next) => payload.messages.some(message => message.source?.rpcId) ? Promise.resolve({ kind: 'reject' }) : next());
        scope.systemPrompt.section({ name: PERSONA_PREFIX_SECTION, order: scope.systemPrompt.getSectionOrder('DEPLOYMENT_PERSONA_PREFIX'), interpolate: false,
          text: '你是主角色的可信技术辅助脑/第二意见，实际模型标识为 ' + settings.model + '。主角色负责判断和对外沟通；可以把工程问题交给你分析、执行和审阅。只使用当前清单实际授予的 native Host 工具，权限受当前用户和配置模式限制，不默认有 root。工具返回的 exit_code/stdout/stderr 和真实回执才是事实，不把计划、启动或部分输出说成完成。只根据本次问句和材料回答，不自动拥有 QQ 历史或附件。不要向 QQ 发送消息，不伪造授权和平台回执；完成后交回真实结果、失败原因和未决项。' });
      };
      const options = { signal, agentOptions: { provider: settings.provider, model: settings.model,
        maxTokens: settings.max_tokens ?? 16384, ...(settings.reasoning_effort ? {reasoningEffort:settings.reasoning_effort} : {}) },
        setup, meta: { cwd: join(config.workspace, 'consultations'), ...(parent ? { parentSession: parent } : {}) } };
      try {
        state.handle = await ctx.agents.resume({ ...options, resumeSessionId: sessionId });
      } catch (error) {
        if (!(error instanceof SessionPersistenceNotFoundError) && error.code !== 'SESSION_QUERY_SESSION_NOT_FOUND') throw error;
        state.handle = await ctx.agents.create({ ...options, sessionId });
        state.handle.agent.session.append('session/title', { title: 'GPT · 技术辅助脑', source: { kind: 'user' }, messageSeqs: [] });
      }
      const workspace = await ctx.workspaceRegistry.create(join(config.workspace, 'consultations'), `${config.character_name || 'Bot'} · 辅助脑`);
      await workspace.setTitle(`${config.character_name || 'Bot'} · 辅助脑`);
      await workspace.attachSession(sessionId);
    }
    const handle = state.handle;
    const cancel = () => handle.agent.cancel({ kind: 'hook', reason: 'Caller cancelled' });
    signal?.addEventListener('abort', cancel, { once: true });
    try {
      handle.agent.followup(createMessage({ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: question }] }));
      await handle.agent.whenIdle(); await ctx.sessions.flush(handle.agent.session);
    } finally { signal?.removeEventListener('abort', cancel); }
    const blocks = last?.data.message.content ?? [];
    const text = blocks.filter(block => block.type === 'text').map(block => block.text).join('').trim();
    if (end?.data.reason.kind !== 'completed' || last?.data.interrupted || !text || blocks.some(block => !['text', 'reasoning'].includes(block.type))) throw Error('Collaborator did not complete normally');
    const events = handle.agent.session.snapshotEvents().filter(event => event.data?.turn === turn);
    const nativeReceipts = events.filter(event => event.type === 'tool/call').map(call => {
      const result = events.find(event => event.type === 'tool/result' && event.data.message.toolCallId === call.data.callId);
      return { session_id: sessionId, tool: call.data.name, call_id: call.data.callId,
        call_seq: call.seq, result_seq: result?.seq ?? null, is_error: Boolean(result?.data.message.isError) };
    });
    return { state: 'answered', role: 'GPT · 技术辅助脑', model: settings.model, text: text.replace(/\bsk-[A-Za-z0-9_-]{16,}/g, '<credential-redacted>').slice(0, 12000), session_id: sessionId,
      native_receipts: nativeReceipts,
      note: 'GPT 报告与主机工具结果分开保存；报告不代替平台投递回执。问询复用固定辅助脑会话；QQ 原话和附件不会自动转发。' };
  } finally { observe(); }
}

export function consult(ctx, config, question, parent, signal) {
  const state = helperState(ctx);
  const work = state.tail.catch(() => {}).then(() => consultOne(ctx, config, question, parent, signal, state));
  state.tail = work.catch(() => {});
  return work;
}

/**
 * Queue GPT without making the character turn wait for it.  The request and
 * result are durable records; the host callback creates a later native Soyo
 * turn.  There is no wall-clock consultation deadline.  Only the host
 * lifetime signal can cancel the helper.
 */
export async function consultLater(ctx, config, question, parent, signal, metadata = {}, onSettled = () => {}) {
  const settings = config.collaborator;
  if (!settings || typeof question !== 'string' || !question.trim() || question.length > 4000 ||
      /\bsk-[A-Za-z0-9_-]{16,}/.test(question)) throw Error('Bounded, credential-free question required');
  const requestId = 'consult-' + randomUUID();
  const path = join(config.workspace, 'consultations', requestId + '.json');
  const record = { request_id: requestId, parent_session: parent ?? null, question,
    state: 'queued', created_at: Date.now(), ...metadata };
  await durable(path, record);
  const state = helperState(ctx);
  const work = state.tail.catch(() => {}).then(async () => {
    record.state = 'running'; record.started_at = Date.now(); await durable(path, record);
    try {
      const result = await consultOne(ctx, config, question, parent, signal, state);
      record.state = result.state === 'answered' ? 'answered' : 'settled';
      record.finished_at = Date.now(); record.result = result;
      await durable(path, record);
      await onSettled({ request_id: requestId, record, result });
      return result;
    } catch (error) {
      record.state = 'failed'; record.finished_at = Date.now();
      record.error = { name: error.name ?? 'Error', message: String(error.message ?? '').slice(0, 500) };
      await durable(path, record);
      await onSettled({ request_id: requestId, record, error });
      throw error;
    }
  });
  state.tail = work.catch(() => {});
  return { state: 'accepted', request_id: requestId, role: 'GPT · 技术辅助脑',
    note: '协作者已进入后台协作队列；本轮角色先继续回答。协作者完成后会以新的原生角色回合回传指导，不是当前回合的同步结果。' };
}
