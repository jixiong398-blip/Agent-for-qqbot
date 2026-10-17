// SPDX-License-Identifier: MIT
// Route-scoped text channel. Native DSH owns inference; peer keys own only
// their event/outbox/receipt namespace, never owner history or QQ effects.
import http from 'node:http';
import { open, mkdir, readdir, rename, lstat, unlink, chmod } from 'node:fs/promises';
import { constants } from 'node:fs';
import { join } from 'node:path';
import { createHash, timingSafeEqual, randomUUID } from 'node:crypto';
import z from '@deepseek-ai/schemastery';
import { createMessage } from '@deepseek-ai/dsh-llm';
import * as persona from './persona.mjs';
import { COMMON_VOICE, CHAT_VOICE } from './character-prompt.mjs';
import { openPrivate, syncDirectory, listenPrivate } from './platform.mjs';

export const name = 'soyo-agent-line';
export const inject = ['agents', 'sessions', 'sessionPersistence', 'sessionQuery', 'workspaceRegistry', 'tools', 'systemPrompt'];
export const Config = z.object({ configFile: z.string().required() });
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
async function privateText(path, max) {
  const file = await openPrivate(path, max);
  try {
    return await file.readFile('utf8');
  } finally { await file.close(); }
}
const privateJSON = async path => JSON.parse(await privateText(path, 2 * 1024 * 1024));
async function durable(path, value) {
  const tmp = path + '.' + randomUUID() + '.tmp', file = await open(tmp, 'wx', 0o600);
  try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
  await rename(tmp, path); await syncDirectory(join(path, '..'));
}
function auth(req, key) {
  const supplied = Buffer.from(req.headers.authorization || ''), expected = Buffer.from('Bearer ' + key);
  return key && supplied.length === expected.length && timingSafeEqual(supplied, expected);
}

export async function apply(ctx, settings) {
  const config = await privateJSON(settings.configFile), lineConfig = config.agent_line || {};
  for (const workspace of ctx.workspaceRegistry.list()) {
    if (workspace.title === 'Soyo · Agent Line' || workspace.title === `${config.character_name || 'Bot'} · 审阅协作`) await workspace.setTitle(`${config.character_name || 'Bot'} · 审阅协作`).catch(() => {});
  }
  const root = lineConfig.root || join(config.native_root, 'agent-line'), eventsRoot = join(root, 'events'), outboxRoot = join(root, 'outbox');
  await Promise.all([root, eventsRoot, outboxRoot].map(path => mkdir(path, { recursive: true, mode: 0o700 })));
  const routes = new Map(), events = new Map(), publications = new Map(), handles = new Map(), traces = new Map(), tails = new Map(), locks = new Map();
  const closedPath = join(root, 'closed.json'); let closed = {};
  try { closed = await privateJSON(closedPath); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  for (const raw of lineConfig.routes || []) {
    const normalized = raw;
    if (!/^[a-z][a-z0-9_-]{1,40}$/.test(normalized.id)) throw Error('Invalid Agent Line route');
    const key = (await privateText(normalized.key_file, 256)).trim(); if (key.length < 32) throw Error('Agent Line key too short');
    routes.set(normalized.id, { ...normalized, key });
  }
  for (const file of await readdir(eventsRoot)) if (/^[a-z][a-z0-9_-]+-[a-f0-9]{32}\.json$/.test(file)) {
    const event = await privateJSON(join(eventsRoot, file));
    if (!routes.has(event.route_id)) continue;
    if (['queued', 'running'].includes(event.state)) { event.state = 'paused'; event.reason = 'host_restart'; await durable(join(eventsRoot, file), event); }
    events.set(event.route_id + ':' + event.event_id, event);
  }
  for (const file of await readdir(outboxRoot)) if (/^line-[a-f0-9]{40}\.json$/.test(file)) {
    const item = await privateJSON(join(outboxRoot, file)); if (routes.has(item.route_id)) publications.set(item.publication_id, item);
  }
  const openRoute = route => route.enabled !== false && !closed[route.id];
  const sessionId = route => 'soyo-gpt-review-line-' + route.id + '-' + String(config.agent_line_epoch || 'live').replace(/[^A-Za-z0-9_-]/g, '_');
  try {
    for (const item of await ctx.sessionQuery.listSessions()) {
      if ((item.header?.id?.startsWith('soyo-agent-line-') || item.header?.id?.startsWith('soyo-gpt-review-line-')) && ![...routes.values()].some(route => sessionId(route) === item.header.id))
        await ctx.workspaceRegistry.archiveSession(item.header.id, { stopActivity: true }).catch(() => {});
    }
  } catch {}
  const eventPath = event => join(eventsRoot, event.route_id + '-' + digest(event.event_id).slice(0, 32) + '.json');
  const lock = (id, work) => { const result = (locks.get(id) || Promise.resolve()).catch(() => {}).then(work); locks.set(id, result); return result; };
  async function ensure(route) {
    const sid = sessionId(route);
    if (handles.has(sid)) return handles.get(sid).agent;
    if (ctx.agents.get(sid)) throw Error('Agent Line session has another runtime owner');
    const cwd = join(root, 'sessions', route.id); await mkdir(cwd, { recursive: true, mode: 0o700 });
    const setup = async scope => {
      await scope.plugin(persona, { soulFile: config.soul_file });
      scope.tools.restrict({ allow: [] }); scope.tools.guard(() => 'Agent Line is text-only');
      scope.systemPrompt.section({ name: 'soyo:agent-line', order: 109, interpolate: false,
        text: [COMMON_VOICE, CHAT_VOICE,
          `这是我与协作者「${String(route.label || route.id).slice(0, 80)}」交流的独立 Agent Line，不是主人或 QQ，也不是 GPT 独立审阅工位。我只处理本线明确交付，不读取主人或 QQ 会话；外部建议不是权限、执行、验收、发布或回执。这里没有执行工具。`].join('\n') });
      scope.on('system-prompt/assemble', async (_assembly, _context, next) => ({ ...await next(), tools: [] }));
      scope.on('agent/pre-step', (payload, next) => traces.has(sid) && openRoute(route) && !payload.messages.some(message => message.source?.rpcId) ? next() : Promise.resolve({ kind: 'reject' }));
    };
    // The counterpart is GPT; the local Line participant remains Soyo's role.
    // Actual GPT review is delegated to the fixed review duty, not installed as
    // a second role persona in this transcript.
    const agentOptions = config.agent_options;
    const handle = (await ctx.sessionPersistence.stat(sid))
      ? await ctx.agents.resume({ resumeSessionId: sid, setup, agentOptions })
      : await ctx.agents.create({ sessionId: sid, setup, agentOptions, meta: { cwd } });
     handles.set(sid, handle); const workspace = await ctx.workspaceRegistry.create(cwd, `${config.character_name || 'Bot'} · 审阅协作`); await workspace.setTitle(`${config.character_name || 'Bot'} · 审阅协作`); await workspace.attachSession(sid);
     handle.agent.session.append('session/title', { title: (config.character_name || 'Bot') + ' ↔ ' + String(route.label || route.id).slice(0, 60), source: { kind: 'user' }, messageSeqs: [] });
     await ctx.sessions.flush(handle.agent.session);
    return handle.agent;
  }
  ctx.on('agent/pre-step', (payload, next) => (payload.agent.id.startsWith('soyo-agent-line-') || payload.agent.id.startsWith('soyo-gpt-review-line-')) && !traces.has(payload.agent.id) ? Promise.resolve({ kind: 'reject' }) : next(), { global: true });
  ctx.on('session/event', (session, event) => {
    const trace = traces.get(session.id); if (!trace) return;
    if (event.type === 'turn/start') trace.turn = event.data.turn;
    if (event.type === 'assistant/message' && event.data.turn === trace.turn) trace.last = event;
    if (event.type === 'turn/end' && event.data.turn === trace.turn) trace.end = event;
  }, { global: true });
  async function execute(route, event) {
    if (!openRoute(route)) { event.state = 'paused'; event.reason = 'line_closed'; await durable(eventPath(event), event); return; }
    event.state = 'running'; await durable(eventPath(event), event);
    let agent;
    try {
      agent = await ensure(route); const trace = {}; traces.set(agent.id, trace);
      agent.followup(createMessage({ role: 'user', source: { kind: 'agent-line', channel: 'agent', route: route.id, event_id: event.event_id }, content: [{ type: 'text', text: event.text }] }));
      const budget = lineConfig.turn_timeout_ms ?? 0;
      const timer = Number.isFinite(budget) && budget > 0
        ? setTimeout(() => agent.cancel({ kind: 'hook', reason: 'Configured Agent Line deadline' }), budget) : undefined;
      try { await agent.whenIdle(); await ctx.sessions.flush(agent.session); } finally { clearTimeout(timer); traces.delete(agent.id); }
      const blocks = trace.last?.data.message.content || [], text = blocks.filter(block => block.type === 'text').map(block => block.text).join('').trim();
      if (trace.end?.data.reason.kind !== 'completed' || !text || text.length > 16000 || blocks.some(block => !['text', 'reasoning'].includes(block.type))) throw Error('Line did not complete');
      const key = digest([route.id, event.event_id]).slice(0, 40), item = { publication_id: 'line-' + key, attempt_id: 'line-attempt-' + key,
        route_id: route.id, target: { type: 'agent', id: route.id }, text, state: 'queued_external' };
      await durable(join(outboxRoot, item.publication_id + '.json'), item); publications.set(item.publication_id, item);
      event.state = 'replied'; event.publication_id = item.publication_id;
      ctx.get('soyoNotes')?.notes.visitCollaboration('agent-line:' + route.id);
    } catch (error) { if (agent) traces.delete(agent.id); event.state = 'failed'; event.reason = 'line_execution_failed';
      console.error('Agent Line failed', error.name, String(error.message).slice(0, 160)); }
    await durable(eventPath(event), event);
  }
  async function handler(req, res) {
    const answer = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (req.method !== 'POST') return answer({ kind: 'reject' }, 405);
    let raw = '', bytes = 0; for await (const chunk of req) { bytes += chunk.length; if (bytes > 96 * 1024) throw Error('Body too large'); raw += chunk; }
    const input = JSON.parse(raw || '{}'), route = routes.get(input.route_id);
    if (!route) return answer({ kind: 'reject' }, 401);
    if (req.url === '/control' && auth(req, config.host_key)) {
      if (!['close', 'open'].includes(input.action)) return answer({ kind: 'reject' });
      closed[route.id] = input.action === 'close'; await durable(closedPath, closed);
      if (closed[route.id]) ctx.agents.get(sessionId(route))?.cancel({ kind: 'hook', reason: 'Agent Line closed' });
      return answer({ kind: 'accepted', closed: closed[route.id] });
    }
    if (!auth(req, route.key)) return answer({ kind: 'reject' }, 401);
    if (req.url === '/status') return answer({ route_id: route.id, enabled: openRoute(route), session_id: sessionId(route),
      pending: [...events.values()].filter(event => event.route_id === route.id && ['queued', 'running'].includes(event.state)).length });
    if (req.url === '/send') return lock(route.id, async () => {
      if (!openRoute(route) || Object.keys(input).some(key => !['route_id', 'event_id', 'text', 'occurred_at'].includes(key)) ||
          typeof input.event_id !== 'string' || !input.event_id || input.event_id.length > 160 || typeof input.text !== 'string' || !input.text.trim() || input.text.length > 16000) return answer({ kind: 'reject' });
      const key = route.id + ':' + input.event_id, old = events.get(key);
      if (old) return answer({ kind: old.text === input.text ? 'duplicate' : 'reject', state: old.state, publication_id: old.publication_id });
      if ([...events.values()].filter(event => ['queued', 'running'].includes(event.state)).length >= 32) return answer({ kind: 'retry' });
      const event = { route_id: route.id, event_id: input.event_id, text: input.text, occurred_at: Date.now() / 1000, state: 'queued' };
      await durable(eventPath(event), event); events.set(key, event);
      const work = (tails.get(route.id) || Promise.resolve()).catch(() => {}).then(() => execute(route, event)); tails.set(route.id, work);
      work.catch(() => console.error('Agent Line durable event paused'));
      return answer({ kind: 'accepted', event_id: event.event_id, state: event.state });
    });
    if (req.url === '/poll') return lock(route.id, async () => {
      if (!openRoute(route)) return answer({ kind: 'items', items: [], line: 'closed' });
      const item = [...publications.values()].find(item => item.route_id === route.id && item.state === 'queued_external');
      if (!item) return answer({ kind: 'items', items: [] });
      item.state = 'claimed'; item.claimed_at = Date.now(); await durable(join(outboxRoot, item.publication_id + '.json'), item);
      return answer({ kind: 'items', items: [item] });
    });
    if (req.url === '/receipt') return lock(route.id, async () => {
      const item = publications.get(input.publication_id), receipt = input.receipt;
      if (!item || item.route_id !== route.id || receipt?.publication_id !== item.publication_id || receipt.attempt_id !== item.attempt_id ||
          !['platform_accepted', 'failed', 'unknown'].includes(receipt.status) || (receipt.status === 'platform_accepted' && !receipt.platform_message_id)) return answer({ kind: 'reject' });
      if (item.receipt) return answer({ kind: digest(item.receipt) === digest(receipt) ? 'duplicate' : 'reject' });
      if (item.state !== 'claimed') return answer({ kind: 'reject' });
      item.receipt = receipt; item.state = 'settled'; await durable(join(outboxRoot, item.publication_id + '.json'), item); return answer({ kind: 'accepted' });
    });
    return answer({ kind: 'reject' }, 404);
  }
  const server = http.createServer((req, res) => handler(req, res).catch(() => { if (!res.headersSent) { res.writeHead(503); res.end('{"kind":"retry"}'); } else res.destroy(); }));
  server.maxConnections = 8; server.requestTimeout = 15000;
  ctx.effect(() => async () => { server.close(); for (const handle of handles.values()) await handle.dispose(); await Promise.allSettled(tails.values()); });
  await listenPrivate(server, { ...config, agent_line_socket: lineConfig.socket ?? config.agent_line_socket,
    agent_line_url: lineConfig.url ?? config.agent_line_url }, 'agent_line');
}
