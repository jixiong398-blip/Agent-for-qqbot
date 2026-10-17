// SPDX-License-Identifier: MIT
// The character lane's small Runtime API.  It deliberately mirrors the
// Asuna contract without importing Asuna or turning a QQ message into a
// generic DSH owner session:
//
//   durable input -> scene/policy binding -> immutable capability snapshot
//   -> native role tools -> per-call recheck -> final publication
//
// The model sees only the tools exposed by the current binding.  A prompt or
// a QQ message can describe a permission, but neither can create one.

const ADMIN_ACTIONS = new Set([
  'set_group_ban', 'set_group_kick', 'set_group_admin', 'set_group_card',
  'set_group_name', 'set_group_leave', '_del_group_notice',
  '_set_group_notice', 'set_group_portrait', 'set_profile',
  'set_online_status', 'delete_msg', 'send_group_forward_msg',
  'send_private_forward_msg', 'forward_group_single_msg',
  'forward_friend_single_msg', 'set_group_add_request',
]);

const READ_TOOLS = new Set([
  'qq_members', 'qq_friends', 'qq_status', 'qq_group_info', 'qq_group_system',
  'qq_stranger_info', 'qq_get_msg', 'qq_get_msg_history', 'qq_notice_read',
  'qq_at_all_remain', 'qq_online_clients', 'qq_permissions',
]);

const OWNER_ONLY_TOOLS = new Set([
  'soyo_qq_forward', 'qq_like', 'qq_sign', 'qq_poke', 'qq_upload_file',
  'qq_recall', 'qq_emoji_like', 'qq_essence', 'qq_ban', 'qq_unban',
  'qq_kick', 'qq_admin', 'qq_card', 'qq_group_name', 'qq_leave',
  'qq_group_avatar', 'qq_invite_approve', 'qq_notice', 'qq_notice_delete',
  'qq_set_profile', 'qq_forward_log', 'qq_forward_msg',
]);

export const HOST_TOOL_NAMES = new Set([
  'bash', 'read', 'read_image', 'write', 'edit', 'glob', 'grep',
  'job_output', 'job_list', 'job_kill',
]);

export const CHARACTER_TOOL_NAMES = new Set([
  'soyo_think', 'soyo_action_brain', 'soyo_action_status', 'soyo_action_message', 'soyo_action_stop',
  'soyo_consult', 'soyo_development_decide', 'soyo_request_help', 'soyo_external_request', 'read_image',
]);
export const dualMode = config => config.brain_mode === 'character-action';

const INTERNAL_READ_ACTIONS = new Set(['recall', 'cognition_read', 'cognition_prepare', 'cognition_status']);
const hasCapability = (binding, name) => binding?.capabilities instanceof Set
  ? binding.capabilities.has(name) : Array.isArray(binding?.capabilities) && binding.capabilities.includes(name);

const ownerOf = (config, envelope) => new Set(
  (config.admin_ids ?? config.memory_private_peers ?? []).map(String),
).has(String(envelope?.sender_id));

const ownerGroupIds = config => new Set(
  Array.isArray(config.owner_group_ids) ? config.owner_group_ids.map(String) : [],
);

/**
 * A group sender is an owner only when two independent deployment facts agree:
 * the authenticated sender id is an owner id and this exact group is in the
 * explicit owner-group allowlist.  The inbound Host also checks that the
 * sender is a member of the durable scene; message text, nickname and QQ
 * role fields never participate in this decision.
 */
export const privateOwnerOf = (config, envelope) => envelope?.message_type === 'private' && ownerOf(config, envelope);
export const ownerGroupOf = (config, envelope) => envelope?.message_type === 'group' &&
  ownerOf(config, envelope) && ownerGroupIds(config).has(String(envelope?.target_id)) &&
  envelope?.route_id === 'qq-group-' + String(envelope?.target_id);
export const ownerActorOf = (config, envelope) => privateOwnerOf(config, envelope) || ownerGroupOf(config, envelope);

function toolVisible(name, binding) {
  if (binding.internal && !binding.owner_continuation && !binding.task_continuation) return name === 'soyo_think' || name === 'soyo_memory' ||
    (binding.note_delivery && (name === 'pass_note' || name === 'leave_note'));
  if (name === 'soyo_think' || name === 'soyo_memory' || name === 'soyo_qq_action' || name === 'soyo_qq_read') return true;
  if (READ_TOOLS.has(name)) return true;
  if (OWNER_ONLY_TOOLS.has(name)) return hasCapability(binding, 'qq.manage');
  if (name === 'soyo_consult') return hasCapability(binding, 'gpt.consult');
  if (name === 'soyo_live2d') return hasCapability(binding, 'host.root');
  if (name === 'soyo_request_help') return binding.session_class === 'public' && !binding.internal && binding.lane !== 'action';
  if (name === 'soyo_external_request') return binding.session_class === 'owner_private' && !binding.internal && binding.lane !== 'action';
  if (name === 'soyo_development_decide') return hasCapability(binding, 'host.root') && hasCapability(binding, 'gpt.review');
  if (name === 'soyo_peer_ask' || name === 'soyo_review_candidate' || name === 'soyo_review_status')
    return hasCapability(binding, 'gpt.review') && hasCapability(binding, 'host.root');
  if (name === 'pass_note') return binding.session_class === 'owner_private';
  if (name === 'leave_note') return binding.session_class !== 'owner_private';
  if (HOST_TOOL_NAMES.has(name)) return hasCapability(binding, 'host.root');
  if (name.startsWith('soyo_action_')) return hasCapability(binding, 'action.delegate');
  if (name.startsWith('schedule_')) return hasCapability(binding, 'schedule.manage');
  return false;
}

function capabilities(config, envelope, internal = false, ownerContinuation = false) {
  const result = new Set(['memory.recall', 'qq.read']);
  if (dualMode(config) && (privateOwnerOf(config, envelope) || ownerGroupOf(config, envelope))) result.add('action.delegate');
  if (privateOwnerOf(config, envelope) && (!internal || ownerContinuation)) {
    result.add('memory.write');
    result.add('qq.manage');
    result.add('gpt.consult');
    result.add('gpt.review');
    result.add('action.delegate');
    result.add('schedule.manage');
    result.add('profile.manage');
    result.add('host.root');
  }
  // The owner may use the existing direct-root/action path from an explicitly
  // bound group, but a group turn never receives the private-only GPT,
  // Schedule, Peer or legacy-memory grants.
  if (ownerGroupOf(config, envelope) && (!internal || ownerContinuation)) {
    result.add('qq.manage');
    result.add('host.root');
  }
  return result;
}

export class SoyoRoleRuntime {
  constructor(config, logger = console) {
    this.config = config;
    this.logger = logger;
    this.active = new Map();
  }

  /** The API admission record persisted with a job before the model is woken. */
  admit(job, envelope = job.envelope) {
    const internal = Boolean(job.internal);
    const ownerContinuation = internal && ['gpt-consultation', 'action-report'].includes(job.internal_source) &&
      /^[a-f0-9]{64}$/.test(job.origin_job_key ?? '') && ownerActorOf(this.config, envelope);
    const sessionClass = privateOwnerOf(this.config, envelope) ? 'owner_private'
      : ownerGroupOf(this.config, envelope) ? 'owner_group' : 'public';
    const binding = {
      api: 'soyo-character-runtime-v1',
      lane: 'character',
      channel: 'qq',
      route_id: String(envelope.route_id),
      scene_id: String(envelope.route_id),
      policy_epoch: Number.isInteger(job.policy_epoch) ? job.policy_epoch : 1,
      operation: 'qq:' + job.key + ':TURN:' + String(job.turn_generation ?? 0),
      actor: { sender_id: String(envelope.sender_id), message_type: envelope.message_type },
      session_class: sessionClass,
      internal,
      owner_continuation: ownerContinuation,
      task_continuation: dualMode(this.config) && internal && job.internal_source === 'action-report' && /^[a-f0-9]{64}$/.test(job.origin_job_key ?? ''),
      note_delivery: internal && job.internal_source === 'scene-note',
      capabilities: [...capabilities(this.config, envelope, internal, ownerContinuation)],
    };
    job.binding = binding;
    job.capabilities = binding.capabilities;
    return binding;
  }

  begin(agent, job, envelope = job.envelope, lane = 'character') {
    const binding = job.binding ?? this.admit(job, envelope);
    const state = {
      agent_id: agent.id,
      lane,
      session_id: agent.id,
      job_key: job.key,
      operation: binding.operation,
      binding,
      capabilities: new Set(binding.capabilities),
      internal: Boolean(job.internal),
      thought: Boolean(job.thought),
      tool_calls: 0,
      seen: new Set(),
    };
    this.active.set(agent.id, state);
    return state;
  }

  current(agentOrId) {
    const id = typeof agentOrId === 'string' ? agentOrId : agentOrId?.id;
    return id ? this.active.get(id) : undefined;
  }

  exposed(agentOrId) {
    const state = this.current(agentOrId);
    if (!state) return new Set();
    if (dualMode(this.config)) {
      if (state.lane === 'action') return this.executionTools(state.binding);
      const visible = new Set([...CHARACTER_TOOL_NAMES].filter(name => name === 'soyo_consult' ? state.capabilities.has('gpt.consult')
        : name === 'soyo_development_decide' ? state.capabilities.has('host.root') && state.capabilities.has('gpt.review')
          : name === 'soyo_request_help' ? state.binding.session_class === 'public' && !state.binding.internal && !state.binding.task_continuation
          : name === 'soyo_external_request' ? state.binding.session_class === 'owner_private' && !state.binding.internal && !state.binding.task_continuation
          : true));
      // A public turn may still use its scene's bounded QQ/read tools, but a
      // request originating outside the owner lane must not jump straight into
      // the action brain.  It goes through the durable request-note path.
      if (state.binding.session_class === 'public' && !state.binding.internal && !state.binding.task_continuation) {
        for (const name of ['soyo_action_brain', 'soyo_action_message', 'soyo_action_stop']) visible.delete(name);
      }
      return visible;
    }
    if (state.internal && !state.binding.owner_continuation) return new Set(['soyo_think', 'soyo_memory',
      ...(state.binding.note_delivery ? [state.binding.session_class === 'owner_private' ? 'pass_note' : 'leave_note'] : [])]);
    return new Set([
      'soyo_think', 'soyo_memory', 'soyo_qq_action', 'soyo_qq_read',
      state.binding.session_class === 'owner_private' ? 'pass_note' : 'leave_note',
      ...READ_TOOLS,
      ...(state.capabilities.has('qq.manage') ? OWNER_ONLY_TOOLS : []),
      ...(state.capabilities.has('gpt.consult') ? ['soyo_consult'] : []),
      ...(state.capabilities.has('host.root') ? HOST_TOOL_NAMES : []),
      ...(state.capabilities.has('action.delegate') ? [
         'soyo_action_brain', 'soyo_action_status', 'soyo_action_message', 'soyo_action_stop',
       ] : []),
      ...(state.binding.session_class === 'public' && !state.binding.internal ? ['soyo_request_help'] : []),
      ...(state.binding.session_class === 'owner_private' && !state.binding.internal ? ['soyo_external_request'] : []),
      ...(state.capabilities.has('schedule.manage') ? [
        'schedule_create', 'schedule_list', 'schedule_update', 'schedule_delete',
      ] : []),
    ]);
  }

  /** Immutable tool duties are separate from the origin actor's permissions. */
  executionTools(binding) {
    if (binding.cognition_only) return new Set(['soyo_memory']);
    const candidates = ['soyo_memory', 'soyo_qq_action', 'soyo_qq_read', 'soyo_live2d', 'soyo_peer_ask', 'soyo_review_candidate', 'soyo_review_status', 'pass_note', 'leave_note',
      ...READ_TOOLS, ...OWNER_ONLY_TOOLS, ...HOST_TOOL_NAMES,
      'schedule_create', 'schedule_list', 'schedule_update', 'schedule_delete'];
    return new Set(candidates.filter(name => toolVisible(name, binding)));
  }

  /** Monotonic DSH guard: absence of a current native binding is a denial. */
  guard(exec) {
    const state = this.current(exec?.agent);
    if (!state) return 'ROLE_INPUT_NOT_ADMITTED: 当前没有已持久化并绑定场景的 Bot 回合';
    if (exec.agent?.id !== state.agent_id) return 'ROLE_SESSION_BINDING_MISMATCH: 工具不属于当前 Bot 会话';
    const dutyAllowed = dualMode(this.config) ? this.exposed(exec.agent).has(exec.name)
      : toolVisible(exec.name, state.binding) && this.exposed(exec.agent).has(exec.name);
    if (!dutyAllowed) {
      return 'CAPABILITY_DENIED: 当前 scene/policy epoch 没有 ' + exec.name + '；权限必须由宿主回合 grant 提供';
    }
    if (state.lane !== 'action' && !state.thought && exec.name !== 'soyo_think') {
      return 'TURN_PROTOCOL: 本回合必须先调用 soyo_think 写一小段心里话，再使用其他工具';
    }
    if (state.lane !== 'action' && state.thought && exec.name === 'soyo_think') {
      return 'TURN_PROTOCOL: soyo_think 每回合只能调用一次';
    }
    return undefined;
  }

  markThought(agentOrId, thought) {
    const state = this.current(agentOrId);
    if (!state) throw Error('ROLE_INPUT_NOT_ADMITTED');
    if (state.thought) throw Error('TURN_PROTOCOL: thought already recorded');
    if (typeof thought !== 'string' || !thought.trim() || thought.length > 360) throw Error('Bounded thought required');
    state.thought = true;
    return state;
  }

  markTool(exec) {
    const state = this.current(exec?.agent);
    if (state) state.tool_calls += 1;
    return state;
  }

  /** Per-call checks that need arguments, kept outside prompt text. */
  argumentGuard(exec, args = {}) {
    const state = this.current(exec?.agent);
    if (!state) throw Error('ROLE_INPUT_NOT_ADMITTED');
    if (state.binding.cognition_only && (exec.name !== 'soyo_memory' || !['cognition_read', 'cognition_status', 'cognition_apply'].includes(args.action)))
      throw Error('COGNITION_DUTY: automatic settlement has only its own batch read/apply tools');
    if (state.internal && !state.binding.owner_continuation && !state.binding.task_continuation && exec.name === 'soyo_memory' && !INTERNAL_READ_ACTIONS.has(args.action)) {
      throw Error('CAPABILITY_DENIED: GPT 回传整理回合只有受限记忆读取，不能写状态或发起新行动');
    }
    if (exec.name === 'soyo_qq_action') {
      const action = String(args.action || '');
      if (ADMIN_ACTIONS.has(action) && !state.capabilities.has('qq.manage')) {
        throw Error('CAPABILITY_DENIED: 当前 QQ 场景没有部署 owner 管理 grant');
      }
    }
    if (exec.name === 'soyo_consult' && !state.capabilities.has('gpt.consult')) {
      throw Error('CAPABILITY_DENIED: GPT consultation is owner-private only');
    }
    return state;
  }

  finish(agentOrId, job) {
    const state = this.current(agentOrId);
    if (state && job && !job.thought) job.thought = state.thought;
    if (state) {
      job.tool_calls = state.tool_calls;
      job.binding = { ...state.binding, tool_calls: state.tool_calls, thought: state.thought };
    }
    if (state) this.active.delete(state.agent_id);
    return state;
  }

  snapshot(agentOrId) {
    const state = this.current(agentOrId);
    if (!state) return null;
    return { ...state.binding, capabilities: [...state.capabilities], thought: state.thought, tool_calls: state.tool_calls };
  }
}

export function runtimeEnvelope(job, context = {}) {
  return {
    api: 'soyo-character-runtime-v1',
    operation: job.binding?.operation ?? 'qq:' + job.key + ':TURN:0',
    scene: {
      id: job.binding?.scene_id ?? job.envelope.route_id,
      route_id: job.envelope.route_id,
      policy_epoch: job.binding?.policy_epoch ?? 1,
      message_type: job.envelope.message_type,
      target_id: job.envelope.target_id,
    },
    actor: { sender_id: job.envelope.sender_id, account_id: job.envelope.account_id },
    session_class: job.binding?.session_class ?? 'public',
    capabilities: job.binding?.capabilities ?? [],
    internal: Boolean(job.internal),
    context,
  };
}
