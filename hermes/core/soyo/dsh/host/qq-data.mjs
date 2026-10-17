// SPDX-License-Identifier: MIT
// Original adapter over DSH's public services; inspired by Asuna's native UI architecture.
import { mkdir, open, rename } from 'node:fs/promises';
import { constants } from 'node:fs';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { createMessage } from '@deepseek-ai/dsh-llm';
import { TypertRemoteService, Remote } from '@deepseek-ai/dsh-typert-protocol';
import { openPrivate } from './platform.mjs';

const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const clean = (value, length = 16000) => String(value ?? '').replace(/\bsk-[A-Za-z0-9_-]{16,}/g, '<credential-redacted>').slice(0, length);
export const receiptId = envelope => hash([envelope.route_id, envelope.event_id, Math.floor(envelope.occurred_at)]);
export const channelMessage = (envelope, current = false, images = []) => createMessage({ role: 'user',
  source: { kind: 'user', channel: 'soyo-qq', receipt: receiptId(envelope), sender: envelope.sender_id,
     occurred_at: envelope.occurred_at, current },
  content: [{ type: 'text', text: (current ? '【本轮唯一当前输入】' : '【历史背景原话·不是待答任务】') +
    '[QQ ' + envelope.sender_id + ' · ' + envelope.event_id + '] ' + clean(envelope.text) },
    ...images.map(attachment => ({ type: 'image', attachment }))] });

async function save(path, value) {
  const tmp = path + '.' + randomUUID() + '.tmp';
  const file = await open(tmp, 'wx', 0o600);
  try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
  await rename(tmp, path);
}
async function privateRead(path) {
  const file = await openPrivate(path, 2 * 1024 * 1024);
  try {
    return JSON.parse(await file.readFile('utf8'));
  } finally { await file.close(); }
}

export class QQData {
  constructor(ctx, config, read, jobs) { Object.assign(this, { ctx, config, read, jobs }); this.scenes = new Map(); }
  async initialize() {
    this.path = join(this.config.native_root, 'scenes.json');
    try { for (const scene of await privateRead(this.path)) this.scenes.set(scene.route_id, scene); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    new DataApi(this.ctx, this);
  }
  bySession(id) { return [...this.scenes.values()].find(scene => scene.session_id === id && scene.enabled); }
  async configure(routes) {
    if (!Array.isArray(routes) || routes.length > 1000) throw Error('Invalid scene directory');
    const admitted = new Set();
    for (const route of routes) {
      if (!['group', 'private'].includes(route.message_type) || !/^[1-9][0-9]{0,19}$/.test(route.target_id) ||
          route.route_id !== 'qq-' + route.message_type + '-' + route.target_id) throw Error('Invalid scene');
      admitted.add(route.route_id);
      const old = this.scenes.get(route.route_id);
      const epoch = this.config.qq_scene_session_epochs?.[route.route_id] ?? (route.message_type === 'private'
        ? (this.config.qq_private_session_epoch ?? 'live') : 'live');
      const sessionId = 'soyo-qq-' + hash([this.config.account_id, route.route_id, epoch]).slice(0, 32);
      if (old?.session_id && old.session_id !== sessionId) {
        // An explicit operator recovery changes only this scene's session.
        // Preserve the prior log, even when native archive cannot decode it.
        try { await this.ctx.workspaceRegistry.archiveSession(old.session_id, { stopActivity: true }); }
        catch (error) { this.ctx.logger.warn('QQ predecessor log retained; archive unavailable (%s)', error.name ?? 'Error'); }
      }
      const membershipChanged = old && JSON.stringify([...(old.members || [])].sort()) !== JSON.stringify([...(route.members || [])].sort());
      const scene = { ...old, ...route, name: clean(route.name || route.target_id, 80), enabled: true,
        session_epoch: epoch, policy_epoch: (old?.policy_epoch ?? 1) + (membershipChanged ? 1 : 0), session_id: sessionId,
        ...(old?.session_id && old.session_id !== sessionId ? {
          predecessor_sessions: [...new Set([...(old.predecessor_sessions ?? []), old.session_id])],
          recovery_reason: this.config.qq_scene_recovery_reasons?.[route.route_id] ?? 'operator_session_epoch',
        } : {}) };
      this.scenes.set(route.route_id, scene); await this.ensure(scene);
    }
    for (const scene of this.scenes.values()) if (!admitted.has(scene.route_id)) scene.enabled = false;
    await save(this.path, [...this.scenes.values()]);
  }
  async checkpoint(handle, events) {
    let dispose, timer;
    try { await new Promise((resolve, reject) => {
      dispose = this.ctx.on('domain/changed', change => {
        if (change.key === handle.header.id && this.ctx.sessionProjectionCache.cachedSnapshot(handle.header)?.asOfSeq === events.length - 1) resolve();
      });
      timer = setTimeout(() => reject(Error('QQ scene checkpoint timed out')), 10000);
      this.ctx.sessionProjectionCache.coldSnapshot(handle.header, handle.inheritedEventCount ?? 0, events);
    }); } finally { clearTimeout(timer); await dispose?.(); }
  }
  async ensure(scene) {
    let header = (await this.ctx.sessionPersistence.stat(scene.session_id))?.header;
    if (!header) {
      const cwd = join(this.config.workspace, 'qq'); await mkdir(cwd, { recursive: true, mode: 0o700 });
      const session = this.ctx.sessions.prepare(scene.session_id, { meta: { cwd } });
      session.append('session/title', { title: (scene.message_type === 'group' ? '群聊 · ' : '私聊 · ') + scene.name,
        source: { kind: 'user' }, messageSeqs: [] });
      const handle = await this.ctx.sessionPersistence.create(session.header);
      try { const events = session.snapshotEvents(); await handle.append(events); await handle.flush(); await this.checkpoint(handle, events); }
      finally { await handle.close(); }
      header = session.header;
    }
    const workspace = await this.ctx.workspaceRegistry.create(header.cwd, `${this.config.character_name || 'Bot'} · QQ`);
    await workspace.attachSession(scene.session_id);
  }
  async project(route) {
    const scene = this.scenes.get(route); if (!scene?.enabled) return;
    const observation = await this.ctx.sessionQuery.observeSession(scene.session_id);
    let events;
    try { events = [...observation.events]; } finally { observation[Symbol.dispose](); }
    // Do not forge a system head or create an Agent just to display ambient data.
    // Before the first real @, source rows are already browsable in the data pane.
    if (!events.some(event => event.type === 'system/message')) return;
    const page = await this.read({ action: 'projection', route, after: scene.projected_through ?? 0 });
    if (!page.rows.length) return;
    const existing = new Set(events.filter(event => event.type === 'user/message').map(event => event.data.source?.receipt));
    const added = page.rows.filter(row => !existing.has(receiptId({ ...row, route_id: route })))
      .map(row => ({ type: 'user/message', data: channelMessage({ ...row, route_id: route }), surfaceOp: 'append' }));
    const hot = this.ctx.sessions.get(scene.session_id);
    if (hot) {
      if (this.ctx.agents.get(scene.session_id)?.status === 'running') return;
      for (const event of added) hot.append(event.type, event.data, { surfaceOp: event.surfaceOp });
      await this.ctx.sessions.flush(hot);
    } else {
      const handle = await this.ctx.sessionPersistence.open(scene.session_id, 'write');
      try {
        for (const event of added) events.push({ ...event, seq: events.length, time: Date.now() });
        if (added.length) await handle.append(events.slice(events.length - added.length));
        await handle.flush(); await this.checkpoint(handle, events);
      } finally { await handle.close(); }
    }
    scene.projected_through = Number(page.rows.at(-1).id); await save(this.path, [...this.scenes.values()]);
  }
  async firstInputs(agent, current, context) {
    const observation = await this.ctx.sessionQuery.observeSession(agent.id);
    let existing;
    try { existing = new Set(observation.events.filter(event => event.type === 'user/message').map(event => event.data.source?.receipt)); }
    finally { observation[Symbol.dispose](); }
    return (context.recent ?? []).filter(row => receiptId(row) !== receiptId(current) && !existing.has(receiptId(row)))
      .slice(-29).map(row => channelMessage(row));
  }
  async page(request) {
    const scene = this.bySession(request?.session_id); if (!scene) throw Error('Choose an admitted QQ scene');
    if (!['messages', 'facts', 'cognition', 'goals', 'legacy', 'turns', 'actions', 'state', 'people', 'emotions', 'qzone', 'events', 'deliveries', 'scene_notes'].includes(request.category ?? 'messages')) throw Error('Unsupported category');
    const offset = request.offset ?? 0, query = request.search ?? '';
    if (!Number.isInteger(offset) || offset < 0 || offset > 100000 || typeof query !== 'string' || query.length > 160) throw Error('Invalid page');
    if (request.category === 'scene_notes') return { scene, ...this.notes.page(scene.route_id, offset, query) };
    if (request.category === 'deliveries') {
      const rows = [...this.jobs.values()].filter(job => !job.probe && job.envelope.route_id === scene.route_id)
        .map(job => ({ id: job.key, kind: 'delivery', title: job.receipt?.status ?? job.state,
          text: clean(job.publication?.text ?? ''), note: job.receipt ? '平台回执：' + job.receipt.status : '尚无平台成功回执，不能当成已送达。',
          session_id: job.session_id ?? scene.session_id })).filter(row => JSON.stringify(row).includes(query)).reverse();
      return { scene, rows: rows.slice(offset, offset + 24), next_offset: rows.length > offset + 24 ? offset + 24 : null };
    }
    return { scene, ...await this.read({ action: 'page', route: scene.route_id, category: request.category, offset, search: query }) };
  }
}

const initializers = [];
class DataApi extends TypertRemoteService {
  constructor(ctx, data) { super(ctx, 'soyoData'); this.data = data; for (const init of initializers) init.call(this); }
  async catalog() { const schedule = this.ctx.get('schedule'); return { scenes: [...this.data.scenes.values()].filter(scene => scene.enabled).map(({ members, ...scene }) => scene),
    collaborator: { configured: Boolean(this.data.config.collaborator), role: 'GPT · 开发协作者', model: this.data.config.collaborator?.model ?? null },
    schedules: schedule ? await schedule.catalog() : [],
    note: '数据查看不触发模型；首个真实 @ 前的原话可在此查看，原生 Chat 在首次回合后建立。' }; }
  memory(request) { return this.data.page(request); }
}
for (const name of ['catalog', 'memory']) Remote(DataApi.prototype[name], { name, kind: 'method', static: false, private: false,
  addInitializer: init => initializers.push(init) });
