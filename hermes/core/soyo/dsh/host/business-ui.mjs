// SPDX-License-Identifier: MIT
// Business UI read face and native route drafts/apply; no Asuna persona, Mongo, model generation, or QQ writer.
import { open, rename } from 'node:fs/promises';
import { constants } from 'node:fs';
import { dirname } from 'node:path';
import { randomUUID, createHash } from 'node:crypto';
import { Remote, RemoteError, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol';
import { dualMode } from './role-runtime.mjs';
import { gatewayHeartbeat } from './gateway-status.mjs';
import { developmentOperation } from './development-broker.mjs';
import { gptReviewSource } from './review-source.mjs';
import { openPrivate, syncDirectory, isRoot, operatorEnabled } from './platform.mjs';

const NAMESPACE = 'soyo-asuna-ui';
const ROUTE_KEYS = new Set(['provider', 'model', 'reasoningEffort', 'maxTokens']);
const CATEGORIES = { documents: 'facts', self: 'state', relation: 'people', summary: 'turns',
  source: 'messages', affect: 'emotions', cognition: 'cognition', goals: 'goals', legacy: 'legacy', events: 'events', qzone: 'qzone', deliveries: 'deliveries', notes: 'scene_notes', all: 'all' };
const kindCategory = { fact: 'fact', self_state: 'self', person: 'relation', turn: 'turn', source: 'source',
  emotion: 'affect', cognition: 'cognition', goal: 'goal', action: 'jobs', platform_event: 'event', qzone: 'qzone', delivery: 'delivery', legacy_read_only: 'legacy', scene_note: 'note' };
const clean = text => String(text ?? '').replace(/\bsk-[A-Za-z0-9_-]{16,}/g, '<credential-redacted>').slice(0, 16000);
const date = value => {
  if (value === undefined || value === null || value === '') return null;
  const numeric = Number(value), stamp = new Date(Number.isFinite(numeric) ? numeric < 1e11 ? numeric * 1000 : numeric : value);
  return Number.isFinite(stamp.getTime()) ? stamp.toISOString() : null;
};
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const entryId = (category, id) => 'soyo-memory:' + Buffer.from(JSON.stringify({ category, id: String(id) })).toString('base64url');
const route = value => Object.fromEntries(Object.entries(value ?? {}).filter(([key]) => ROUTE_KEYS.has(key)));
const routesKey = routes => hash(['character', 'action'].map(lane => [...ROUTE_KEYS].map(key => routes[lane]?.[key] ?? (key === 'reasoningEffort' ? '' : null))));
const applying = new Set(['queued', 'waiting', 'restarting', 'rolling_back']);

async function privateConfig(path) {
  const file = await openPrivate(path, 2 * 1024 * 1024);
  try {
    const stat = await file.stat();
    const text = await file.readFile('utf8');
    return { value: JSON.parse(text), digest: createHash('sha256').update(text).digest('hex'), stat };
  } finally { await file.close(); }
}
async function writeConfig(path, value, stat) {
  const temporary = path + '.' + randomUUID() + '.tmp';
  const file = await open(temporary, 'wx', stat.mode & 0o777);
  try {
    await file.writeFile(JSON.stringify(value, null, 2) + '\n'); await file.sync();
    if (isRoot()) await file.chown(stat.uid, stat.gid);
  } finally { await file.close(); }
  await rename(temporary, path);
  await syncDirectory(dirname(path));
}

const initializers = [];
export class BusinessUiApi extends TypertRemoteService {
  constructor(ctx, data, brains, configFile, { applyStrategy, mutateMemory, mutateGoal } = {}) {
    super(ctx, 'soyoUi'); Object.assign(this, { runtime: ctx, data, brains, configFile, applyStrategy, mutateMemory, mutateGoal, applyPath: configFile + '.ui-apply.json' });
    for (const init of initializers) init.call(this);
  }
  scene(sessionId) {
    const task = [...this.brains.tasks.values()].find(task => task.child_session_id === sessionId);
    const parent = task?.parent_session ?? sessionId;
    return this.data.bySession(parent) ?? [...this.data.scenes.values()].find(scene => scene.enabled && scene.predecessor_sessions?.includes(parent));
  }
  async identity(request) {
    const id = request?.session_id;
    if (typeof id !== 'string') throw Error('Native session required');
    const task = [...this.brains.tasks.values()].find(task => task.child_session_id === id);
    const config = this.data.config;
    const character = config.character_name || 'Bot', action = config.collaborator?.label || '行动助手';
    const review = [...(this.runtime.get('soyoReviews')?.rows.values() ?? [])].find(row => row.session_id === id);
    if (review) return { lane: 'reviewer', label: (review.source?.label ?? 'GPT · 独立审阅（来源未记录）') + '（无执行权限）', parent_session_id: review.parent_session,
      review_id: review.id, scene_kind: 'gpt-review', source: review.source ?? null };
    if (task) return { lane: 'executor', label: action + ' · 行动脑', parent_session_id: task.parent_session, task_id: task.id };
    if ([...this.brains.tasks.values()].some(task => task.parent_session === id && task.actor.kind === 'native-schedule'))
      return { lane: 'character', label: character + ' · 定时角色脑', scene_kind: 'schedule' };
    if (id?.startsWith('soyo-public-note-home-'))
      return { lane: 'character', label: character + ' · 公开便签检查', scene_kind: 'outside-note', owner_grant: false };
    if (id.startsWith('soyo-peer-')) return { lane: 'helper', label: '旧Peer记录（只读，不重跑）', scene_kind: 'legacy-peer', owner_grant: false };
    if (id === config.collaborator?.session_id) return { lane: 'helper', label: action + ' · 历史辅助会话（非当前第三脑）' };
    const scene = this.scene(id);
    if (scene) return { lane: 'character', label: character + ' · 角色脑', scene_kind: scene.message_type, scene_name: scene.name };
    if (config.collaborator?.owner_sessions?.includes(id)) return { lane: 'character', label: character + ' · 本机角色脑', scene_kind: 'local' };
    return null; // Never infer a brain from the selected provider/model.
  }
  async development(request) {
    if (!request || typeof request.session_id !== 'string' || Object.keys(request).some(key => !['session_id', 'work_id'].includes(key)))
      throw Error('Native author session required');
    const service = this.runtime.get('soyoReviews'), reviewer = this.reviewerView();
    const reviewSession = [...(service?.rows.values() ?? [])].find(row => row.session_id === request.session_id);
    const child = [...this.brains.tasks.values()].find(task => task.child_session_id === request.session_id);
    const parent = reviewSession?.parent_session ?? child?.parent_session ?? request.session_id;
    const own = [...this.brains.tasks.values()].filter(task => task.parent_session === parent);
    const visible = own.filter(task => task.actor.capabilities?.includes('host.root') && task.actor.session_class !== 'public' && task.purpose !== 'cognition');
    if (!visible.length && !this.data.config.collaborator?.owner_sessions?.includes(parent))
      return { bound: false, works: [], reviews: [], detail: null, reviewer, model_woken: false, platform_sends: 0 };
    const reviews = service?.list({ session_id: parent }).rows ?? [];
    let detail = null;
    if (request.work_id) {
      const work = visible.find(task => task.id === request.work_id);
      if (!work) throw Error('Candidate belongs to another author');
      this.brains.recheckDevelopmentTask(work);
      detail = await developmentOperation(this.configFile, this.data.config,
        { operation: 'inspect', work_id: work.id, _parent_session: work.parent_session });
    }
    return { bound: true, works: visible.sort((a, b) => b.created_at - a.created_at).slice(0, 40).map(task => ({
      id: task.id, objective: clean(task.objective), state: task.state, handover: task.handover, child_session_id: task.child_session_id })),
      detail, reviews, reviewer, model_woken: false, platform_sends: 0,
      note: '只读实际候选、测试、独立审阅、Bot决定、commit及版本选择账；不创建工程、不重跑、不发平台。' };
  }
  reviewerView() {
    const service = this.runtime.get('soyoReviews');
    return { ...gptReviewSource(this.runtime, this.data.config), route_locked: dualMode(this.data.config),
      duty_state: service?.ready && !service.stopping ? 'ready' : service ? 'initializing' : 'not-mounted',
      review_records: service?.rows.size ?? 0, pending_reviews: service?.pendingCount() ?? 0 };
  }
  sceneTitle(scene) { return (scene.message_type === 'group' ? '群聊 · ' : '私聊 · ') + scene.name; }
  memoryRow(row, category, scene) {
    return { id: entryId(category, row.id), kind: kindCategory[row.kind] ?? category, title: clean(row.title),
      excerpt: clean(row.text).slice(0, 180), status: row.recalled ? 'recalled' : row.status ?? row.state ?? (row.kind === 'delivery' ? row.title : ''), updated_at: date(row.updated_at ?? row.occurred_at),
      scene_title: ['shared', 'global'].includes(row.scope) ? '所有对话共用（Bot 原生记录）'
        : row.scope === 'owner' ? 'owner 私有记录' : this.sceneTitle(scene) };
  }
  async memory(request) {
    const scene = this.scene(request?.session_id); if (!scene) throw Error('NOT_BOUND: native Bot scene required');
    if (request.id) return this.memoryDetail(request, scene);
    const category = request.category ?? 'summary', offset = request.offset ?? 0, search = request.search ?? '';
    if (!Number.isInteger(offset) || offset < 0 || offset > 100000 || typeof search !== 'string' || search.length > 160) throw Error('Bounded memory page required');
    if (category === 'jobs') {
      const tasks = [...this.brains.tasks.values()].filter(task => this.scene(task.parent_session)?.route_id === scene.route_id &&
        clean(task.objective + '\n' + (task.report ?? '')).includes(search)).sort((a, b) => b.created_at - a.created_at);
      return { rows: tasks.slice(offset, offset + 24).map(task => this.memoryRow({ id: task.id, kind: 'action',
        title: task.objective, text: task.report ?? '', status: task.state, updated_at: task.updated_at }, 'jobs', scene)),
        next_offset: tasks.length > offset + 24 ? offset + 24 : null, scene_title: this.sceneTitle(scene), linked_scene_titles: [], subject_name: scene.name };
    }
    const stored = CATEGORIES[category]; if (!stored) throw Error('Memory category is not implemented in Bot');
    const page = ['deliveries', 'scene_notes'].includes(stored) ? await this.data.page({ session_id: scene.session_id, category: stored, offset, search })
      : await this.data.read({ action: 'page', route: scene.route_id, category: stored, offset, search, summary_only: true });
    return { rows: page.rows.map(row => this.memoryRow(row, stored === 'all' ? row.data_category : stored, scene)),
      next_offset: page.next_offset, scene_title: this.sceneTitle(scene), linked_scene_titles: [], subject_name: scene.name,
      evidence_source: 'native-Soyo-read-only-data', model_woken: false };
  }
  async memoryDetail(request, scene) {
    if (typeof request.id !== 'string' || request.id.length > 4096 || !request.id.startsWith('soyo-memory:')) throw Error('Native memory identity required');
    const key = JSON.parse(Buffer.from(request.id.slice(12), 'base64url').toString());
    if (typeof key.id !== 'string' || key.id.length > 2048) throw Error('Bounded memory identity required');
    let row, sources = [];
    if (key.category === 'jobs') {
      const task = this.brains.tasks.get(key.id);
      if (!task || this.scene(task.parent_session)?.route_id !== scene.route_id) throw Error('Memory belongs to a different scene');
      row = { id: task.id, kind: 'action', title: task.objective, text: task.report ?? '', status: task.state, updated_at: task.updated_at };
    } else if (key.category === 'deliveries') {
      const job = this.data.jobs.get(key.id);
      if (!job || job.probe || job.envelope?.route_id !== scene.route_id) throw Error('Native receipt not found in this scene');
      row = { id: job.key, kind: 'delivery', status: job.receipt?.status ?? job.state,
        text: [clean(job.publication?.text), job.receipt ? JSON.stringify(job.receipt, null, 2) : '尚无平台成功回执，不能当成已送达。'].join('\n\n'),
        occurred_at: job.receipt?.occurred_at ?? job.created_at };
    } else if (key.category === 'scene_notes') {
      // These ledgers are bounded and already filtered by the native scene.
      let page;
      for (let offset = 0; offset <= 100000; offset += 24) {
        page = await this.data.page({ session_id: scene.session_id, category: key.category, offset, search: '' });
        row = page.rows.find(row => String(row.id) === key.id); if (row || page.next_offset === null) break;
      }
    } else {
      if (!Object.values(CATEGORIES).includes(key.category) || key.category === 'all') throw Error('Unsupported detail category');
      const detail = await this.data.read({ action: 'detail', route: scene.route_id, category: key.category, id: key.id });
      row = detail.row; sources = detail.sources ?? [];
    }
    if (!row) throw Error('Native memory record not found');
    return { category: kindCategory[row.kind] ?? key.category, status: row.recalled ? 'recalled' : row.status ?? row.state ?? '',
      body: clean(row.text + (row.kind === 'qzone' ? '\n\n【保留的平台回执字段】\n' + JSON.stringify(row.receipt ?? {}) +
        '\n缺少真实post-id的旧条目仍保留历史标志，但不能作为完整送达验收。' : '')),
      occurred_at: date(row.occurred_at), generated_at: row.kind === 'cognition' ? date(row.updated_at) : null, speaker: row.sender_id ?? row.source ?? '',
       sources: [...sources.map(source => ({ _id: 'source:' + source.id, category: 'source', text: clean(source.text),
         author: source.sender_id, occurred_at: date(source.occurred_at), scene_title: this.sceneTitle(scene) })),
         ...(row.role_sources ?? []).map(source => ({ _id: 'role-source:' + source.id, category: 'role-expression',
            text: clean(source.thought), author: (this.data.config.character_name || 'Bot') + '（实际角色表达，非QQ成员）', occurred_at: date(source.occurred_at),
           scene_title: this.sceneTitle(scene), native_call_id: source.call_id, native_call_seq: source.call_seq, native_session_id: source.session_id, native_turn: source.turn }))],
      corrected: row.kind === 'cognition' && row.revision > 1, sources_truncated: false,
       evidence_source: row.kind === 'cognition' ? 'native-source-bound-model-cognition' : 'native-record-not-derived-summary',
       ...(row.kind === 'scene_note' ? { note_origin: row.native_origin ?? null, note_provenance: {
         source_place: row.source, target_place: row.target, trust: row.trust ?? null, mode: row.mode,
         read_at: date(row.read_at), reply_to: row.reply_to ?? null, reply_note_id: row.reply_note_id ?? null,
         wake_session_id: row.wake_session_id ?? null, wake_state: row.wake_state ?? null,
         source_check: row.source_check ?? null, platform_receipt: false } } : {}),
       ...(row.kind === 'goal' ? { revision: row.revision, goal_id: Number(row.id), goal_revisions: row.revisions,
         goal_mutation: { allowed: Boolean(this.mutateGoal) && scene.enabled && request.session_id === scene.session_id,
           policy_epoch: scene.policy_epoch, id: request.id }, evidence_source: 'native-persistent-goal-ledger' } : {}),
       ...(row.kind === 'cognition' ? { revision: row.revision, memory_kind: row.memory_kind, model: row.model, revisions: row.revisions, attribution: row.attribution,
        operator_corrections: row.operator_corrections ?? [], source_seqs: row.source_seqs,
        mutation: { allowed: Boolean(this.mutateMemory) && scene.enabled && request.session_id === scene.session_id,
          policy_epoch: scene.policy_epoch, expected_revision: row.revision, id: request.id } } : {}), model_woken: false };
  }
  async memoryMutation(request) {
    if (!this.mutateMemory) throw Error('Native memory operator backend is unavailable');
    const fields = new Set(['session_id','policy_epoch','id','operation','expected_revision','request_id','reason','body','sources']);
    if (!request || Array.isArray(request) || typeof request !== 'object' || Object.keys(request).some(key => !fields.has(key)))
      throw Error('The native scene and actor cannot be supplied or overridden by a mutation');
    const scene = this.scene(request?.session_id);
    if (!scene?.enabled || scene.session_id !== request.session_id || scene.policy_epoch !== request.policy_epoch)
      throw Error('MEMORY_SCENE_CONFLICT: reload the current native scene');
    if (typeof request.id !== 'string' || request.id.length > 4096 || !request.id.startsWith('soyo-memory:')) throw Error('Native memory identity required');
    const key = JSON.parse(Buffer.from(request.id.slice(12),'base64url').toString());
    if (key.category !== 'cognition' || !/^[a-f0-9]{64}$/.test(key.id ?? '') ||
        !['correct','forget'].includes(request.operation) || !Number.isSafeInteger(request.expected_revision) || request.expected_revision < 1 ||
        typeof request.request_id !== 'string' || !/^[A-Za-z0-9_-]{16,80}$/.test(request.request_id)) throw Error('Bounded cognition operation required');
    const args = { action: request.operation === 'correct' ? 'correct_memory' : 'forget_memory', route_id: scene.route_id,
      id: key.id, expected_revision: request.expected_revision, reason: request.reason, request_id: request.request_id,
      ...(request.operation === 'correct' ? { body: request.body, sources: request.sources } : {}) };
    let result;
    try { result = await this.mutateMemory(args); }
    catch (error) {
      const code = String(error.message ?? '').split(':')[0];
      if (/^COGNITION_(?:CONFLICT|OPERATION_CONFLICT|PERMISSION)$/.test(code))
        throw new RemoteError('memory/' + code.toLowerCase(), code, { reload_required: true });
      throw error;
    }
    return { ...result, model_woken: false, platform_sends: 0 };
  }
  async goalMutation(request) {
    if (!this.mutateGoal) throw Error('Native goal operator backend is unavailable');
    const fields=new Set(['session_id','policy_epoch','id','status','expected_revision','request_id','reason']);
    if (!request || typeof request!=='object' || Array.isArray(request) || Object.keys(request).some(key=>!fields.has(key))) throw Error('Host-bound goal operator request required');
    const scene=this.scene(request.session_id);
    if (!scene?.enabled || scene.session_id!==request.session_id || scene.policy_epoch!==request.policy_epoch) throw Error('GOAL_SCENE_CONFLICT: reload current native scene');
    if (typeof request.id!=='string' || !request.id.startsWith('soyo-memory:') || request.id.length>4096) throw Error('Native goal identity required');
    const key=JSON.parse(Buffer.from(request.id.slice(12),'base64url').toString());
    if (key.category!=='goals' || !/^[1-9][0-9]{0,14}$/.test(key.id) || !['cancelled','open','blocked'].includes(request.status) ||
        !Number.isSafeInteger(request.expected_revision) || request.expected_revision<1 || !/^[A-Za-z0-9_-]{16,80}$/.test(request.request_id??'')) throw Error('Bounded goal operator decision required');
    try {
      const value=await this.mutateGoal({route_id:scene.route_id,commitment_id:Number(key.id),expected_revision:request.expected_revision,
        goal_request_id:'goal-ui-'+request.request_id,status:request.status,reason:request.reason});
      return {...value,model_woken:false,platform_sends:0};
    } catch(error) {
      const code=String(error.message??'').split(':')[0];
      if (/^GOAL_(?:CONFLICT|OPERATION_CONFLICT)$/.test(code)) throw new RemoteError('goal/'+code.toLowerCase(),code,{reload_required:true});
      throw error;
    }
  }
  appliedRoutes(config = this.data.config) {
    const action = config.action_agent_options ?? (dualMode(config) ? config.collaborator : config.agent_options);
    return { character: { reasoningEffort: '', ...route(config.agent_options) }, action: { reasoningEffort: '', ...route(action),
       maxTokens: action?.maxTokens ?? config.collaborator?.max_tokens ?? (dualMode(config) ? 16384 : 8192) } };
  }
  descriptor() {
    const row = this.runtime.settings.describe({ redactSecrets: true }).find(row => row.ns === NAMESPACE);
    if (!row) throw Error('Native Bot UI settings namespace is not ready');
    return row;
  }
  savedRoutes() {
    const base = this.appliedRoutes(), stored = this.descriptor().value.routes ?? {};
    return { character: { ...base.character, ...route(stored.character) }, action: { ...base.action, ...route(stored.action) } };
  }
  settingsView() {
    const row = this.descriptor();
    return { status: 'ready', writable: this.runtime.settings.writable, revision: row.revision,
      value: { routes: this.savedRoutes() }, base: { routes: this.appliedRoutes() }, user: { routes: row.user?.routes ?? {} } };
  }
  async providers() {
    return Promise.all(this.runtime.llm.listProviders().map(async provider => {
      const models = [];
      try {
        for (const entry of await this.runtime.llm.listModels(provider.id)) {
          const model = await this.runtime.llm.resolveModelInfo(provider.id, entry.id);
          models.push({ id: model.id, name: model.name, contextWindow: model.context?.contextWindow,
            maxTokens: model.defaultMaxTokens, reasoning: model.reasoning });
        }
      } catch { /* An unavailable provider remains visible, without leaking credentials/errors. */ }
      return { id: provider.id, name: provider.name, models };
    }));
  }
  async gatewayStatus() {
    let heartbeat;
    try { heartbeat = (await privateConfig(this.data.config.status_file ?? dirname(this.configFile) + '/qq-gateway-status.json')).value; }
    catch { /* An unavailable/malformed heartbeat is not a live connection. */ }
    return { ...gatewayHeartbeat(heartbeat), model_woken: false, platform_sends: 0 };
  }
  async status() {
    const config = this.data.config;
    const operation = await this.applyOperation();
    const gateway = await this.gatewayStatus();
    const value = { lifecycle: { state: applying.has(operation?.phase) ? 'applying' : operation?.phase === 'failed' ? 'failed' : 'ready',
      ...(operation?.phase === 'failed' ? { error: '后台应用未完成，原配置/失败证据保留；请刷新后核对。' } : {}) },
      worker: { database: 'sqlite', self_source: 'native', channel_titles: ['QQ'],
        channels_active: gateway.state === 'connected', integration_state: gateway.state === 'connected' ? 'RUNNING'
          : gateway.state === 'stale' ? 'STALE' : ['unavailable','unknown'].includes(gateway.state) ? 'UNKNOWN' : 'STOPPED',
        transport_observation: gateway,
        schedules_active: Boolean(this.runtime.get('schedule')) },
      providers: await this.providers(), personas: [{ id: 'soyo', name: config.character_name || 'Bot' }], applied: { routes: this.appliedRoutes() },
      pending: routesKey(this.savedRoutes()) !== routesKey(this.appliedRoutes()), publications: [],
      host_mode: config.direct_root && isRoot() ? 'direct-root' : 'user',
       collaborator: { model: config.collaborator?.model ?? null, route_unchanged: true },
       reviewer: this.reviewerView(), model_woken: false };
    this.lastStatus = value; return value;
  }
  async validateRoutes(routes) {
    if (dualMode(this.data.config) && (routes.action.provider !== this.data.config.collaborator?.provider || routes.action.model !== this.data.config.collaborator?.model))
      throw Error('The single GPT executor route is fixed; change only its reasoning/output budget here');
    for (const value of Object.values(routes)) {
      if (typeof value.provider !== 'string' || typeof value.model !== 'string' || !value.provider || !value.model) throw Error('Provider and model required');
      const model = await this.runtime.llm.resolveModelInfo(value.provider, value.model);
      if (value.reasoningEffort && !model.reasoning?.efforts?.some(effort => effort.id === value.reasoningEffort)) throw Error('Reasoning effort not supported by this model');
      if (!Number.isSafeInteger(value.maxTokens) || value.maxTokens < 1 || value.maxTokens > (model.context?.contextWindow ?? 1048576)) throw Error('Bounded output budget required');
    }
  }
  async saveSettings(ops, revision) {
    if (this.applying || applying.has((await this.applyOperation())?.phase)) throw Error('Native application is pending; reload after reconnecting');
    if (!Array.isArray(ops) || ops.length > 16 || revision !== this.descriptor().revision) throw Error('SETTINGS_CONFLICT: reload the native settings view');
    const next = structuredClone(this.savedRoutes());
    for (const op of ops) {
      if (!['set', 'unset'].includes(op.op) || op.path?.length !== 3 || op.path[0] !== 'routes' ||
        !['character', 'action'].includes(op.path[1]) || !ROUTE_KEYS.has(op.path[2])) throw Error('Only character/action route fields are editable');
      const [, lane, key] = op.path;
      if (op.op === 'set') next[lane][key] = op.value;
      else if (this.appliedRoutes()[lane][key] !== undefined) next[lane][key] = this.appliedRoutes()[lane][key];
      else delete next[lane][key];
    }
    await this.validateRoutes(next);
    await this.runtime.settings.mutate(NAMESPACE, ops, revision);
    return { saved: true, applied: false, model_woken: false };
  }
  async applyOperation() {
    try { return (await privateConfig(this.applyPath)).value; }
    catch (error) { if (error.code !== 'ENOENT') throw error; return null; }
  }
  async applySettings() {
    if (this.applying) throw Error('Native route application is already pending');
    this.applying = true;
    try {
      if (applying.has((await this.applyOperation())?.phase)) throw Error('Native route application is already pending');
      const revision = this.descriptor().revision, routes = this.savedRoutes(); await this.validateRoutes(routes);
      if (revision !== this.descriptor().revision) throw Error('SETTINGS_CONFLICT: saved routes changed before apply');
      if (!this.runtime.settings.writable) throw Error('Native settings are read-only');
      if (!this.applyStrategy && !operatorEnabled(this.data.config)) throw Error('Owner operator backend required');
      if (this.runtime.agents.list().some(agent => agent.status === 'running') || [...this.data.jobs.values()].some(job => ['queued', 'running', 'settling'].includes(job.state)) ||
        [...this.brains.tasks.values()].some(task => ['queued', 'starting', 'running'].includes(task.state)) || this.brains.pendingCount() > 0)
        throw Error('Native work is active; wait for it to settle before applying routes');
      const current = await privateConfig(this.configFile);
      if (routesKey(this.appliedRoutes(current.value)) !== routesKey(this.appliedRoutes())) throw Error('SETTINGS_CONFLICT: private routes changed outside this editor');
      const next = { ...current.value, agent_options: { ...current.value.agent_options, ...routes.character },
        action_agent_options: { ...(current.value.action_agent_options ?? current.value.agent_options), ...routes.action } };
      for (const options of [next.agent_options, next.action_agent_options]) if (options.reasoningEffort === '') delete options.reasoningEffort;
      if (this.applyStrategy) {
        await writeConfig(this.configFile, next, current.stat);
        try { await this.applyStrategy(next); }
        catch (error) { await writeConfig(this.configFile, current.value, current.stat); throw error; }
      } else {
        if (this.data.config.lifecycle?.mode !== 'supervisor') throw Error('Instance supervisor is required for settings application');
        const operation = { id: randomUUID(), phase: 'queued', created_at: Date.now(), revision, routes, expected_config_digest: current.digest };
        await writeConfig(this.applyPath, operation, current.stat);
      }
      return { ...this.lastStatus, applied: { routes: this.appliedRoutes() }, pending: !this.applyStrategy,
        lifecycle: { state: this.applyStrategy ? 'ready' : 'applying' } };
    } finally { this.applying = false; }
  }
  personaSources() { return null; } // No imported Asuna persona jobs or documents.
}
for (const name of ['identity', 'development', 'memory', 'memoryMutation', 'goalMutation', 'settingsView', 'status', 'gatewayStatus', 'saveSettings', 'applySettings', 'personaSources'])
  Remote(BusinessUiApi.prototype[name], { name, kind: 'method', static: false, private: false, addInitializer: init => initializers.push(init) });
