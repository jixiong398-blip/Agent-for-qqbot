  // Source currency only: native tool/result and the durable Bot action ledger.
  const aliases = {
    soyo_think: ['think', args => args],
    soyo_action_brain: ['delegate', args => ({ title: args.objective, brief: args.objective })],
    soyo_action_status: ['read_report', args => args],
    soyo_action_message: ['message_action', args => ({ message: args.text })],
    soyo_action_stop: ['stop_action', args => ({ reason: args.id })],
    ask_character: ['ask_character', args => ({ question: args.text })],
    report_progress: ['report_progress', args => ({ note: args.text })],
    soyo_consult: ['soyo_consult', args => args],
    soyo_memory: ['recall', args => args],
    soyo_automation_decision: ['soyo_automation_decision', args => args],
    soyo_review_candidate: ['soyo_review_candidate', args => args],
    soyo_review_status: ['soyo_review_status', args => args],
    soyo_peer_ask: ['soyo_peer_ask', args => args],
    soyo_development: ['soyo_development', args => args],
    soyo_development_decide: ['soyo_development_decide', args => args],
  };
  TOOL_ICONS.soyo_consult = 'IconQuestionOutlineRegular';
  TOOL_SUMMARY.soyo_consult = 'question'; TOOL_BODY.soyo_consult = 'question';
  DICTIONARY.zh['tool.soyo_consult'] = '请 GPT 协助';
  DICTIONARY.en['tool.soyo_consult'] = 'Ask GPT';
  TOOL_SUMMARY.soyo_automation_decision = 'decision'; TOOL_BODY.soyo_automation_decision = 'reason';
  DICTIONARY.zh['tool.soyo_automation_decision'] = '发布取舍（不发送）';
  DICTIONARY.en['tool.soyo_automation_decision'] = 'Publication decision (no send)';
  for (const [name, zh, en, summary] of [
    ['soyo_review_candidate', '提交中转站GPT独立审阅（异步）', 'Request relay GPT review (async)', 'question'],
    ['soyo_review_status', '核对实际审阅状态', 'Read review status', 'id'],
    ['soyo_peer_ask', '请中转站GPT提供第二意见（非执行）', 'Ask relay GPT for a second opinion', 'question'],
    ['soyo_development', '操作隔离候选工程（非验收）', 'Operate on isolated candidate work', 'operation'],
    ['soyo_development_decide', 'Bot候选验收决定（非发布）', 'Bot candidate decision (not publication)', 'reason'],
  ]) { DICTIONARY.zh['tool.'+name]=zh;DICTIONARY.en['tool.'+name]=en;TOOL_SUMMARY[name]=summary;TOOL_BODY[name]=summary; }
  // A completed flag settles the native Turn, not acceptance of the goal.
  DICTIONARY.zh['collab.state.done'] = '行动回合已结束';
  DICTIONARY.en['collab.state.done'] = 'Action turn ended';
  DICTIONARY.zh['collab.outcome.done'] = '行动回合已结束';
  DICTIONARY.en['collab.outcome.done'] = 'Action turn ended';
  DICTIONARY.zh['collab.paused'] = '宿主重启时暂停了；旧记录保留，不会自动重跑。';
  DICTIONARY.en['collab.paused'] = 'Paused at Host restart; records are retained and work is not replayed.';
  DICTIONARY.zh['collab.missed.retry'] = '报告记录保留；核对后再续接。';
  DICTIONARY.en['collab.missed.retry'] = 'The report is retained; review it before continuing.';
  Object.assign(DICTIONARY.zh, {
    'memory.aria': 'Bot 记忆', 'memory.guide': '当前场景的原生记忆、原话与真实行动报告',
    'memory.kind.all': '原生记忆总览', 'memory.notBound': '当前会话没有 QQ 场景绑定；不会借用其他会话的私有记忆。',
    'memory.kind.documents': '结构化记忆', 'memory.kind.summary': '原生回合记录', 'memory.kind.legacy': '旧私有知识（只读）',
    'memory.kind.cognition': '来源化认知', 'memory.category.cognition': '来源化记录',
    'memory.kind.goals': '持续目标', 'memory.category.goal': '持续目标',
    'memory.status.open': '待做', 'memory.status.done': '已记结清决定（核对效果证据）', 'memory.status.cancelled': '已取消', 'memory.status.blocked': '有阻塞', 'memory.status.snoozed': '暂缓',
    'goal.edit': '目标控制', 'goal.note': '只更新原稳定目标，不运行模型、任务或平台；结清须由行动器关联实际效果证据。',
    'goal.reason': '目标决定原因', 'goal.cancel': '取消目标', 'goal.open': '恢复为待做', 'goal.block': '标记阻塞',
    'memory.provenance.model': '模型提炼来源', 'memory.provenance.operator': '人工纠错（非模型产物）',
    'memory.provenance.own': '自身感受：引用实际角色表达，不将QQ成员情绪当成Bot的感受。',
    'memory.provenance.note': '内部便签来源（不是当地用户发言、审阅意见或平台送达回执）',
    'memory.provenance.noteLegacy': '旧便签未保存新来源字段；不补造原生调用或权限。',
    'memory.edit.latest': '最新已存版本（下方草稿未替换）',
    'memory.status.candidate': '候选（未晋升）', 'memory.status.promoted': '已晋升', 'memory.status.withdrawn': '来源撤回',
    'memory.status.forgotten': '已遗忘（旧版保留）', 'memory.status.expired': '已过期',
    'memory.edit': '人工纠错 / 遗忘', 'memory.edit.body': '纠错正文', 'memory.edit.reason': '原因',
    'memory.edit.sources': '关联原话序号（逗号分隔）', 'memory.edit.correct': '保存纠错新版本', 'memory.edit.forget': '遗忘（移出上下文）',
    'memory.edit.reload': '核对最新版本（保留草稿）', 'memory.edit.note': '人工纠错不调用模型。关联原话用于审计，不冒称证明新正文；遗忘保留旧版本和原话。',
    'memory.edit.audit': '已记录人工操作', 'memory.edit.conflict': '操作未完成；草稿保留，请核对版本和来源后再提交。',
    'memory.kind.notes': '跨会话便签', 'memory.kind.deliveries': '平台发送回执', 'memory.kind.events': '平台事件', 'memory.kind.qzone': 'Qzone 发布账',
    'memory.category.fact': '结构化记忆', 'memory.category.turn': '原生回合', 'memory.category.legacy': '旧私有知识',
    'memory.category.event': '平台事件', 'memory.category.delivery': '发送回执', 'memory.category.qzone': 'Qzone 发布账',
    'memory.category.note': '跨会话便签', 'memory.category.jobs': '原生行动报告', 'memory.status.completed': '行动回合已结束',
    'memory.status.recalled': '已撤回', 'memory.status.platform_accepted': '平台已接收', 'memory.status.unknown': '回执未确认',
    'memory.status.failed': '未正常完成', 'memory.status.paused': '暂停（记录保留）', 'memory.status.running': '进行中',
    'settings.aria': 'Bot 角色设置', 'settings.status': '业务宿主：{state} · 数据：{database}',
    'settings.note': '路由草稿由 DSH 原生设置保存。点应用后后台重启，重连再核对；会话自己的模型选择优先于默认路由。API Key 仍在原生模型服务设置中，不在此页回显。',
    'settings.activated': '已提交后台应用；请在重连后核对状态。', 'settings.selfSource.native': 'Bot 私有数据（未导入旧上下文）',
    'settings.state.applying': '后台应用中', 'settings.state.failed': '应用未完成（原配置保留）',
    'settings.transport.aria': 'Gateway 状态观察', 'settings.transport.note': '仅核对持久心跳，不代表新连接探测或消息送达。',
    'settings.transport.connected': '最近心跳：连接正常', 'settings.transport.connecting': '最近心跳：连接中',
    'settings.transport.disconnected': '最近心跳：已断开', 'settings.transport.stale': '心跳已过期，当前连接未确认',
    'settings.transport.unknown': '心跳状态未确认', 'settings.transport.unavailable': '心跳读面不可用',
    'settings.transport.age': '心跳距今约 {seconds} 秒',
    'trigger.gpt_result': 'GPT 交回了协作结果', 'trigger.internal': '内部续接', 'session.settings': '角色设置',
    'brain.helper': 'GPT · 历史辅助会话', 'brain.reviewer': '中转站 GPT · 独立审阅', 'ui.scope': 'Bot 业务控件',
    'trigger.review': 'GPT 收到独立审阅材料', 'trigger.review_result': 'GPT 交回独立审阅意见',
    'review.aria': '中转站GPT审阅来源', 'review.title': '中转站 GPT · 独立审阅',
    'review.note': '沿用现有固定 GPT 路由，独立材料上下文、无执行权限，不是第三个执行脑。外部客户端接入暂缓。',
    'review.configOnly': '这里只读宿主配置，不探测中转站；模型已注册不等于审阅通过。',
    'review.provider': '模型服务', 'review.model': '模型', 'review.protocol': '实际配置协议', 'review.endpoint': '中转站来源（仅域名）',
    'review.unknown': '未记录 / 未确认', 'review.registered': '宿主已注册模型服务（非在线探测）', 'review.unregistered': '宿主尚未注册模型服务',
    'review.duty.ready': '独立审阅接缝已装载（非审阅验收）', 'review.duty.initializing': '独立审阅接缝装载中', 'review.duty.not-mounted': '独立审阅接缝未装载',
    'review.fixed': '与唯一GPT行动器使用同一路由', 'review.routeMismatch': '当前配置未确认与固定GPT行动器一致',
    'review.record': '独立审阅记录', 'review.noExecution': '审阅意见不是执行效果、Bot验收、生产发布或平台回执。',
    'review.state.queued': '已接纳 / 排队', 'review.state.running': '审阅中', 'review.state.reviewed': '模型交回审阅意见',
    'review.state.failed': '审阅未正常结算', 'review.state.suspended': '宿主重启暂停（不重跑）',
    'review.decision.approve': '建议可接受', 'review.decision.changes': '建议修改', 'review.decision.block': '建议阻塞',
    'review.decision.unstructured': '未交回规范决定', 'review.decision.pending': '尚无审阅决定',
    'review.handover.character_read': 'Bot已核对审阅回流', 'review.handover.queued_for_character': '已排队交回Bot',
    'review.handover.handback_failed': 'Bot回流回合未正常结束', 'review.handover.deferred': '回流暂缓（意见保留）', 'review.handover.pending': '尚未交回Bot',
    'review.validation': '宿主审阅凭据状态', 'review.native': '原生审阅证据',
    'development.tab': '工程与GPT审阅', 'development.aria': 'Bot工程与独立GPT审阅', 'development.refresh': '刷新工程记录',
    'development.note': '只读实际候选/测试/中转站GPT意见/Bot决定/commit/版本账；浏览不创建任务、不启动模型、不发平台。',
    'development.notBound': '当前场景没有owner工程来源；不借用其他作者的工作。', 'development.empty': '尚无候选工程或独立审阅记录。',
    'development.choose': '选择候选工程', 'development.loading': '正在读取工程记录', 'development.stale': '刷新未完成；下方为上次读取记录，不作为当前状态。',
    'development.notCreated': '这条行动还没有创建候选工程；不为浏览创建空工程。',
    'development.work': '稳定候选与版本', 'development.test': '实际沙箱测试记录', 'development.review': '当前审阅凭据',
    'development.author': 'Bot验收决定', 'development.commit': '本地候选提交（非push/部署）', 'development.release': '冻结版本选择 / 回退',
    'development.absent': '尚无记录', 'development.raw': '展开保留的实际证据',
    'development.storedOnly': '下方为保留的回执与决定；是否匹配当前候选，执行时仍须复核树指纹。',
    'development.recovery': '未结算操作 / 保留的恢复证据',
    'development.selectionOnly': '版本选择不等于服务激活或健康；UNKNOWN 不自动重发，旧版本保留。',
    'development.queued': '行动已持久接纳并排队；尚无native child工具或报告，不等于已执行。',
  });
  Object.assign(DICTIONARY.en, {
    'memory.aria': 'Bot memory', 'memory.guide': 'Native memory, source records and real action reports for this scene',
    'memory.kind.all': 'Native memory overview', 'memory.notBound': 'This session has no QQ scene binding; another scene’s private memory will not be borrowed.',
    'memory.kind.documents': 'Structured memory', 'memory.kind.summary': 'Native turn records', 'memory.kind.legacy': 'Legacy private knowledge (read-only)',
    'memory.kind.cognition': 'Source-bound cognition', 'memory.category.cognition': 'Source-bound record',
    'memory.kind.goals': 'Persistent goals', 'memory.category.goal': 'Persistent goal',
    'memory.status.open': 'Open', 'memory.status.done': 'Close decision recorded (check effect evidence)', 'memory.status.cancelled': 'Cancelled', 'memory.status.blocked': 'Blocked', 'memory.status.snoozed': 'Snoozed',
    'goal.edit': 'Goal controls', 'goal.note': 'Update only this stable goal. No model, work or platform execution. Completion needs executor-linked native effects.',
    'goal.reason': 'Goal decision reason', 'goal.cancel': 'Cancel goal', 'goal.open': 'Reopen goal', 'goal.block': 'Mark blocked',
    'memory.provenance.model': 'Model interpretation origin', 'memory.provenance.operator': 'Operator correction (not model output)',
    'memory.provenance.own': 'Own affect: grounded in native role expression, not a QQ participant’s emotion.',
    'memory.provenance.note': 'Internal note origin (not local user input, review advice or a platform receipt)',
    'memory.provenance.noteLegacy': 'The legacy note has no new origin fields; native calls and permissions are not fabricated.',
    'memory.edit.latest': 'Latest stored revision (draft below is unchanged)',
    'memory.status.candidate': 'Candidate', 'memory.status.promoted': 'Promoted', 'memory.status.withdrawn': 'Source withdrawn',
    'memory.status.forgotten': 'Forgotten (history retained)', 'memory.status.expired': 'Expired',
    'memory.edit': 'Operator correction / forgetting', 'memory.edit.body': 'Corrected content', 'memory.edit.reason': 'Reason',
    'memory.edit.sources': 'Linked source sequences (comma separated)', 'memory.edit.correct': 'Save correction revision', 'memory.edit.forget': 'Forget (remove from context)',
    'memory.edit.reload': 'Check latest revision (keep draft)', 'memory.edit.note': 'No model call. Linked quotes are audit references, not proof of the new statement. Forgetting retains old revisions and source records.',
    'memory.edit.audit': 'Recorded operator operations', 'memory.edit.conflict': 'Not completed; draft retained. Check revision and sources before submitting.',
    'memory.kind.notes': 'Cross-session notes', 'memory.kind.deliveries': 'Platform receipts', 'memory.kind.events': 'Platform events', 'memory.kind.qzone': 'Qzone publications',
    'memory.category.fact': 'Structured memory', 'memory.category.turn': 'Native turn', 'memory.category.legacy': 'Legacy private knowledge',
    'memory.category.event': 'Platform event', 'memory.category.delivery': 'Delivery receipt', 'memory.category.qzone': 'Qzone publication',
    'memory.category.note': 'Cross-session note', 'memory.category.jobs': 'Native action report', 'memory.status.completed': 'Action turn ended',
    'memory.status.recalled': 'Recalled', 'memory.status.platform_accepted': 'Accepted by platform', 'memory.status.unknown': 'Receipt unconfirmed',
    'memory.status.failed': 'Not completed normally', 'memory.status.paused': 'Paused (records retained)', 'memory.status.running': 'Running',
    'settings.aria': 'Bot character settings', 'settings.status': 'Business Host: {state} · Data: {database}',
    'settings.note': 'DSH stores route drafts. Apply queues a background restart; check after reconnecting. Session model selections take precedence. API keys remain in native provider settings and are never shown here.',
    'settings.activated': 'Background apply requested; check status after reconnecting.', 'settings.selfSource.native': 'Native Bot data; no legacy-context import',
    'settings.state.applying': 'Applying in background', 'settings.state.failed': 'Apply did not complete; original configuration retained',
    'settings.transport.aria': 'Gateway observation', 'settings.transport.note': 'Persisted heartbeat only; not a fresh connection probe or delivery receipt.',
    'settings.transport.connected': 'Recent heartbeat: connected', 'settings.transport.connecting': 'Recent heartbeat: connecting',
    'settings.transport.disconnected': 'Recent heartbeat: disconnected', 'settings.transport.stale': 'Heartbeat stale; current connection unconfirmed',
    'settings.transport.unknown': 'Heartbeat state unknown', 'settings.transport.unavailable': 'Heartbeat read face unavailable',
    'settings.transport.age': 'Heartbeat about {seconds} seconds old',
    'trigger.gpt_result': 'GPT reported back', 'trigger.internal': 'Internal continuation', 'session.settings': 'Character settings',
    'brain.helper': 'GPT · Legacy assistant session', 'brain.reviewer': 'Relay GPT · Independent review', 'ui.scope': 'Bot business controls',
    'trigger.review': 'GPT received independent review material', 'trigger.review_result': 'GPT returned independent review advice',
    'review.aria': 'Relay GPT review source', 'review.title': 'Relay GPT · Independent review',
    'review.note': 'Existing fixed GPT route, fresh explicit-material context, no executable tools; not a third execution brain. External client integration is deferred.',
    'review.configOnly': 'Host configuration only, without contacting the relay. A registered model is not an approved review.',
    'review.provider': 'Provider', 'review.model': 'Model', 'review.protocol': 'Configured protocol', 'review.endpoint': 'Relay origin (no credentials or path)',
    'review.unknown': 'Not recorded / unconfirmed', 'review.registered': 'Provider registered in Host (not a connectivity check)', 'review.unregistered': 'Provider not registered in Host',
    'review.duty.ready': 'Review seam loaded (not review acceptance)', 'review.duty.initializing': 'Review seam initializing', 'review.duty.not-mounted': 'Review seam not mounted',
    'review.fixed': 'Same route as the single GPT executor', 'review.routeMismatch': 'Configuration does not confirm the fixed executor route',
    'review.record': 'Independent review record', 'review.noExecution': 'Advice is not execution evidence, Bot acceptance, production activation or a platform receipt.',
    'review.state.queued': 'Accepted / queued', 'review.state.running': 'Reviewing', 'review.state.reviewed': 'Model returned review advice',
    'review.state.failed': 'Review not settled normally', 'review.state.suspended': 'Suspended at Host restart (not replayed)',
    'review.decision.approve': 'Advisory approval', 'review.decision.changes': 'Changes recommended', 'review.decision.block': 'Block recommended',
    'review.decision.unstructured': 'No structured decision', 'review.decision.pending': 'No review decision yet',
    'review.handover.character_read': 'Bot read the review hand-back', 'review.handover.queued_for_character': 'Queued for Bot',
    'review.handover.handback_failed': 'Bot hand-back turn did not complete', 'review.handover.deferred': 'Hand-back deferred (advice retained)', 'review.handover.pending': 'Not handed back yet',
    'review.validation': 'Host review receipt state', 'review.native': 'Native review evidence',
    'development.tab': 'Development and GPT review', 'development.aria': 'Bot development and independent GPT review', 'development.refresh': 'Refresh work records',
    'development.note': 'Actual candidate/tests/relay GPT advice/Bot decisions/commit/release records only. Browsing starts no work, model or platform send.',
    'development.notBound': 'This scene has no owner development source; other authors’ work is not borrowed.', 'development.empty': 'No candidate work or independent reviews yet.',
    'development.choose': 'Select candidate work', 'development.loading': 'Reading work records', 'development.stale': 'Refresh failed; the last read is shown, not current state.',
    'development.notCreated': 'No candidate work has been created for this action; browsing does not create an empty one.',
    'development.work': 'Stable candidate and revision', 'development.test': 'Actual sandbox test receipt', 'development.review': 'Current review fence',
    'development.author': 'Bot acceptance decision', 'development.commit': 'Local candidate commit (not push/deployment)', 'development.release': 'Frozen release selection / rollback',
    'development.absent': 'No record yet', 'development.raw': 'Expand retained actual evidence',
    'development.storedOnly': 'Stored receipts and decisions below. Execution still rechecks that they match the current candidate fingerprint.',
    'development.recovery': 'Unsettled operations / retained recovery evidence',
    'development.selectionOnly': 'Selection is not activation or health. UNKNOWN is not automatically retried; old releases are retained.',
    'development.queued': 'Action durably accepted and queued; no native child tools or report yet, not evidence of execution.',
  });
  const memoryKinds = ['all', 'cognition', 'goals', 'documents', 'self', 'relation', 'summary', 'source', 'affect', 'jobs', 'notes', 'deliveries', 'qzone', 'events', 'legacy'];

  const sourceStage = source => {
    if (source?.kind === 'soyo-action-brain') return { lane: 'executor', phase: 'EXECUTE', trigger: 'brief' };
    if (source?.kind === 'soyo-schedule-occurrence') return { lane: 'character', phase: 'TURN', trigger: 'schedule' };
    if (source?.kind === 'soyo-public-note-home') return { lane: 'character', phase: 'TURN', trigger: 'note' };
    if (source?.kind === 'soyo-action-report') return { lane: 'character', phase: 'TURN', trigger: 'task_result' };
    if (source?.kind === 'soyo-gpt-review-report') return { lane: 'character', phase: 'TURN', trigger: 'review_result' };
    if (source?.kind === 'soyo-gpt-review') return { lane: 'reviewer', phase: 'REVIEW', trigger: 'review' };
    if (source?.channel !== 'soyo-qq' || source.current !== true) return null;
    const trigger = source.review_id ? 'review_result' : source.kind !== 'soyo-consultation' ? 'message'
      : source.internal_source === 'action-report' ? 'task_result'
      : source.internal_source === 'gpt-consultation' ? 'gpt_result'
      : source.internal_source === 'scene-note' ? 'note' : 'internal';
    return { lane: 'character', phase: 'TURN', trigger, operation: source.receipt };
  };
  const textSeen = event => event.type === 'assistant/message'
    ? (event.data.message?.content ?? []).some(block => block.type === 'text' && block.text.trim())
    : event.type === 'assistant/live-chunk' && event.data.chunk?.type === 'text-delta' && !!event.data.chunk.text.trim();
  const stageAt = (match, reader) => {
    const prior = reader.previous('soyo-stage-source')?.state;
    return { stage: prior?.turn === match.event.data.turn ? prior.stage : null,
      turn: match.event.data.turn, step: match.event.data.step, anchor: match.event.seq - 0.2,
      textSeen: !!textSeen(match.event) };
  };
  const stageDefinitions = [{ kind: 'soyo-stage-source',
    match: event => event.type === 'user/message' && sourceStage(event.data.source) ? { id: String(event.seq), role: 'start' } : null,
    start: (_context, match) => ({ stage: sourceStage(match.event.data.source), turn: match.location.turn?.turn ?? match.event.data.turn }),
    update: context => context.state,
  }, { kind: 'asuna-stage',
    match: event => ['assistant/message', 'assistant/live-chunk'].includes(event.type) && Number.isInteger(event.data.turn) && Number.isInteger(event.data.step)
      ? { id: event.data.turn + ':' + event.data.step, role: 'start' } : null,
    start: (_context, match, reader) => stageAt(match, reader),
    update: context => context.state,
    buildLocationData: (context, scope) => scope === 'step' && context.state?.stage ? { kind: 'step', turn: context.state.turn,
      step: context.state.step, key: 'asuna-stage', value: context.state.stage } : null,
  }, { kind: 'soyo-brain-marker', target: 'chat',
    match: event => ['assistant/message', 'assistant/live-chunk'].includes(event.type) && Number.isInteger(event.data.turn)
      ? { id: String(event.data.turn), role: 'start' } : null,
    start: (_context, match, reader) => stageAt(match, reader),
    update: (context, match) => ({ ...context.state, textSeen: context.state.textSeen || !!textSeen(match.event) }),
    publication: match => match.event.type === 'assistant/live-chunk' ? 'animation-frame' : 'immediate',
    buildViewNode: context => context.state?.stage && context.state.textSeen ? { key: context.key, kind: 'asuna-stage', id: context.id,
      target: 'chat', anchorSeq: context.state.anchor, location: { kind: 'session' }, visibility: 'visible', data: context.state.stage } : null,
  }];

  function delegatedTask(event) {
    if (event.type !== 'tool/result' || event.data.message?.isError) return null;
    const blocks = event.data.message?.content ?? [];
    const text = blocks.filter(block => block.type === 'text').map(block => block.text).join('\n');
    let value; try { value = JSON.parse(text); } catch { return null; }
    return value.state === 'accepted' && /^action-[0-9a-f-]{36}$/.test(value.id ?? '') &&
      /^soyo-action-[0-9a-f-]{36}$/.test(value.child_session_id ?? '') ? value : null;
  }
  const actionDefinition = {
    kind: 'soyo-action-thread', target: 'chat',
    match: event => event.type === 'tool/call' && ['soyo_action_brain', 'soyo_consult'].includes(event.data.name)
      ? { id: event.data.callId, role: 'start' }
      : delegatedTask(event) ? { id: event.data.message.toolCallId, role: 'update' } : null,
    start: (_context, match) => ({ callSeq: match.event.seq, taskId: null }),
    update: (context, match) => {
      const value = delegatedTask(match.event);
      return value ? { ...context.state, taskId: value.id, anchor: match.event.seq } : context.state;
    },
    buildViewNode: context => !context.state?.taskId ? null : ({ key: context.key, kind: 'soyo-action-thread', id: context.id,
      target: 'chat', anchorSeq: context.state.anchor, location: { kind: 'session' }, visibility: 'visible', data: context.state }),
  };
  function apply(ctx) {
    ctx.effect(() => ctx.locale.register(NS, DICTIONARY));
    const t = ctx.locale.bind(NS);
    const rpc = async (method, payload = {}, signal) => {
      const brains = ['brainContext', 'thread'].includes(method);
      const fields = method === 'brainContext' ? { request: { session_id: payload.sessionId } }
        : ['memory', 'identity', 'development', 'memoryMutation', 'goalMutation'].includes(method) ? { request: payload.request ?? payload }
        : method === 'saveSettings' ? payload : brains ? { request: payload } : {};
      const result = await ctx.connection.rpc.call('/api', (brains ? 'soyoBrains/' : 'soyoUi/') + method, { args: fields }, signal);
      if (!result.ok) throw Error(result.error?.message || 'Native Bot record unavailable');
      return result.value;
    };
    // Native form revisions/overrides remain native. Only merge the existing
    // Bot routes into the redacted view; never mirror private gateway secrets.
    const describe = ctx.configForms.describe(); describe.ensure();
    const subscribers = new Set(); let describedValue = { status: 'loading', writable: false };
    let settingsLoad, settingsRerun = false;
    const reloadSettings = () => {
      if (settingsLoad) { settingsRerun = true; return settingsLoad; }
      settingsLoad = Promise.resolve().then(async () => {
        do {
          settingsRerun = false;
          try { describedValue = await rpc('settingsView'); }
          catch { describedValue = { ...describedValue, status: 'unavailable', writable: false }; }
          for (const fn of subscribers) fn();
        } while (settingsRerun);
      }).finally(() => { settingsLoad = undefined; });
      return settingsLoad;
    };
    ctx.effect(() => describe.subscribe(reloadSettings));
    const subscribe = fn => { subscribers.add(fn); return () => subscribers.delete(fn); };
    const snapshot = () => describedValue;
    reloadSettings();
    function ReviewSource({ value, t }) {
      return h('section', { 'aria-label': t('review.aria'), style: stack }, h('h4', {}, value?.label ?? t('review.title')),
        h('p', { style: small }, t('review.note')),
        h('dl', {}, ...[['provider', value?.provider], ['model', value?.model], ['protocol', value?.wire_protocol], ['endpoint', value?.endpoint_origin]]
          .flatMap(([key, text]) => [h('dt', { key: key + '-label' }, t('review.' + key)),
            h('dd', { key, style: { marginInlineStart: 0, overflowWrap: 'anywhere' } }, text ?? t('review.unknown'))])),
        value && h('p', { style: small }, t(value.provider_registered ? 'review.registered' : 'review.unregistered')),
        value?.duty_state && h('p', { style: small }, word(t, 'review.duty.', value.duty_state)),
        value && h('p', { style: small }, t(value.fixed_executor_route ? 'review.fixed' : 'review.routeMismatch')),
        h('p', { style: small }, t('review.configOnly')));
    }
    function EvidenceRecord({ title, value, t }) {
      return h('section', { style: stack }, h('h4', {}, t(title)),
        value && Object.keys(value).length ? h(React.Fragment, {},
          h('p', { style: small }, String(value.phase ?? value.decision ?? value.state ?? value.commit ?? (value.revision ? 'revision=' + value.revision : ''))),
          h('details', {}, h('summary', {}, t('development.raw')),
            h('pre', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontSize: 12 } }, JSON.stringify(value, null, 2))))
          : h('p', { style: small }, t('development.absent')));
    }
    function ReviewRecord({ row, t }) {
      const source = row.source;
      return h('article', { 'aria-label': t('review.record'), style: { ...stack, borderTop: '1px solid var(--dsw-alias-border-l1)', paddingTop: 8 } },
        h('h4', {}, t('review.record')), h('code', { style: { overflowWrap: 'anywhere' } }, row.id),
        h('p', {}, word(t, 'review.state.', row.state) + ' · ' + word(t, 'review.decision.', row.decision ?? 'pending')),
        h('p', { style: small }, [source?.provider, source?.model, source?.wire_protocol, source?.endpoint_origin].filter(Boolean).join(' · ') || t('review.unknown')),
        h('p', { style: small }, t('review.noExecution')),
        row.handover && h('p', { style: small }, word(t, 'review.handover.', row.handover)),
        row.validation && h('p', { style: small }, t('review.validation') + ': ' + (row.validation.review_state ?? row.validation.state)),
        row.result?.text && h(MarkdownText, { text: row.result.text, labels: markdownLabels(t) }),
        row.reason && h('p', { role: 'alert' }, row.reason),
        row.result && h(EvidenceRecord, { title: 'review.native', value: Object.fromEntries(Object.entries(row.result).filter(([key]) => key !== 'text')), t }));
    }
    function Development(props) {
      const [sample, setSample] = React.useState(null), [selection, setSelection] = React.useState(null);
      const [refresh, setRefresh] = React.useState(0), [failure, setFailure] = React.useState(null), [loading, setLoading] = React.useState(false);
      const sessionId = props.sessionId, work = selection?.sessionId === sessionId ? selection.work : '';
      const key = JSON.stringify([sessionId, work]), value = sample?.key === key ? sample.value : null;
      const error = failure?.key === key ? failure.message : '';
      React.useEffect(() => {
        if (!sessionId) return;
        const controller = new AbortController(); setFailure(null); setLoading(true);
        rpc('development', { session_id: sessionId, ...(work ? { work_id: work } : {}) }, controller.signal)
          .then(next => { if (!controller.signal.aborted) setSample({ key, value: next }); })
          .catch(error => { if (!controller.signal.aborted) setFailure({ key, message: error.message }); })
          .finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
      }, [key, refresh]);
      const detail = value?.detail;
      return h('section', { 'aria-label': t('development.aria'), style: stack }, h('h3', {}, t('development.tab')),
        h('p', { style: small }, t('development.note')),
        h(Button, { disabled: loading || !sessionId, onClick: () => setRefresh(x => x + 1) }, t('development.refresh')),
        loading && h('p', { role: 'status' }, t('development.loading')),
        error && h('p', { role: 'alert' }, error + (value ? ' · ' + t('development.stale') : '')),
        (!sessionId || value && !value.bound) && h('p', {}, t('development.notBound')),
        value && h(ReviewSource, { value: value.reviewer, t }),
        value?.bound && h('select', { 'aria-label': t('development.choose'), value: work, disabled: loading,
          onChange: event => setSelection({ sessionId, work: event.target.value }) },
          h('option', { value: '' }, t('development.choose')),
          ...value.works.map(row => h('option', { key: row.id, value: row.id }, row.objective.slice(0, 100)))),
        value?.bound && !value.works.length && !value.reviews.length && h('p', {}, t('development.empty')),
        detail?.state === 'not-created' && h('p', {}, t('development.notCreated')),
        detail?.work && h(React.Fragment, {},
          h('p', { style: small }, t('development.storedOnly')),
          ...[['development.work', detail.work], ['development.test', detail.test], ['development.review', detail.review],
            ['development.author', detail.work.acceptance], ['development.commit', detail.commit], ['development.release', detail.publication]]
            .map(([title, body]) => h(EvidenceRecord, { key: title, title, value: body, t })),
          h('p', { style: small }, t('development.selectionOnly')),
          detail.recovery_required && h(EvidenceRecord, { title: 'development.recovery', value: {
            unsettled_operations: detail.unsettled_operations, orphan_revision_audit: detail.orphan_revision_audit, automatic_replay: false }, t })),
        ...(value?.reviews ?? []).filter(row => !work || row.work_id === work).map(row => h(ReviewRecord, { key: row.id, row, t })));
    }
    function GatewayStatus({ initial, t }) {
      const [sample,setSample]=React.useState({ value: initial, at: performance.now() }),[now,setNow]=React.useState(performance.now());
      React.useEffect(()=>{
        const controller=new AbortController();let busy=false;
        const load=async()=>{
          if (busy) return;busy=true;
          try { const value=await rpc('gatewayStatus',{},controller.signal);if (!controller.signal.aborted) setSample({value,at:performance.now()}); }
          catch { if (!controller.signal.aborted) setSample({value:{state:'unavailable'},at:performance.now()}); }
          finally { busy=false; }
        };
        load();const read=setInterval(load,15000),clock=setInterval(()=>setNow(performance.now()),1000);
        return ()=>{controller.abort();clearInterval(read);clearInterval(clock);};
      },[]);
      const value=sample.value,age=typeof value?.status_age_seconds==='number' ? value.status_age_seconds+Math.max(0,now-sample.at)/1000 : null;
      const state=age!==null && age>value.max_age_seconds ? 'stale' : value?.state ?? 'unavailable';
      return h('section',{'aria-label':t('settings.transport.aria'),style:small},
        h('p',{},t('settings.transport.'+state)),age!==null && h('p',{},t('settings.transport.age',{seconds:Math.floor(age)})),
        h('p',{},t('settings.transport.note')));
    }
    function MemoryProvenance({ detail, t }) {
      if (detail.note_provenance) return h('div', { style: small }, h('p', {}, t('memory.provenance.note')),
        !detail.note_origin && h('p', {}, t('memory.provenance.noteLegacy')),
        h('details', {}, h('summary', {}, t('development.raw')),
          h('pre', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' } }, JSON.stringify({ origin: detail.note_origin, receipt: detail.note_provenance }, null, 2))));
      if (!detail.memory_kind) return null;
      return h('div', { style: small }, h('p', {}, detail.model === 'owner-ui-verbatim-correction' ? t('memory.provenance.operator')
        : t('memory.provenance.model') + ': ' + (detail.model ?? 'unknown')),
        detail.attribution?.subject === 'soyo' ? h('p', {}, t('memory.provenance.own')) : null);
    }
    function GoalControl({ detail, sessionId, t, onSaved }) {
      const [base,setBase]=React.useState(detail),[reason,setReason]=React.useState(''),[busy,setBusy]=React.useState(false),[notice,setNotice]=React.useState('');
      const intent=React.useRef(null);
      if (!detail.goal_mutation?.allowed) return null;
      const submit=async status=>{
        if(busy || !reason.trim())return;setBusy(true);setNotice('');
        try {
          const request={session_id:sessionId,id:base.goal_mutation.id,policy_epoch:base.goal_mutation.policy_epoch,expected_revision:base.revision,status,reason};
          const key=JSON.stringify(request);
          if(intent.current?.key!==key)intent.current={key,request:{...request,request_id:[...crypto.getRandomValues(new Uint8Array(16))].map(value=>value.toString(16).padStart(2,'0')).join('')}};
          await rpc('goalMutation',{request:intent.current.request});onSaved();
        }catch(error){setNotice(t('memory.edit.conflict')+' '+error.message);}finally{setBusy(false);}
      };
      const reload=async()=>{if(busy)return;setBusy(true);try{const latest=await rpc('memory',{request:{session_id:sessionId,id:detail.goal_mutation.id}});setBase(latest);setNotice('revision='+latest.revision+' · '+t('goal.note'));}catch(error){setNotice(error.message);}finally{setBusy(false);}};
      return h('section',{'aria-label':t('goal.edit'),style:stack},h('p',{style:small},t('goal.note')+' · revision='+base.revision),
        base.revision!==detail.revision && h('div',{},h('p',{style:small},t('memory.edit.latest')),h(MarkdownText,{text:base.body,labels:markdownLabels(t)})),
        h(Input,{'aria-label':t('goal.reason'),value:reason,maxLength:500,disabled:busy,onChange:event=>setReason(event.target.value)}),
        h('div',{style:{display:'flex',flexWrap:'wrap',gap:8}},...['cancelled','open','blocked'].map(status=>h(Button,{key:status,disabled:busy||!reason.trim(),onClick:()=>submit(status)},t(status==='cancelled'?'goal.cancel':status==='open'?'goal.open':'goal.block'))),
          h(Button,{disabled:busy,onClick:reload},t('memory.edit.reload'))),notice&&h('p',{role:'alert'},notice));
    }
    function MemoryCorrection({ detail, sessionId, t, onSaved }) {
      const [base, setBase] = React.useState(detail);
      const [body, setBody] = React.useState(detail.body), [reason, setReason] = React.useState('');
      const [sources, setSources] = React.useState((detail.source_seqs ?? []).join(', '));
      const [busy, setBusy] = React.useState(false), [notice, setNotice] = React.useState('');
      const intent = React.useRef(null);
      if (!detail.mutation?.allowed) return null;
      const submit = async operation => {
        if (busy) return;
        setBusy(true); setNotice('');
        try {
          const seqs = sources.split(',').map(value => Number(value.trim()));
          if (!reason.trim() || operation === 'correct' && (!body.trim() || seqs.length > 64 || seqs.some(value => !Number.isSafeInteger(value) || value < 1)))
            throw Error(t('memory.edit.conflict'));
          const request = { session_id: sessionId, id: base.mutation.id, policy_epoch: base.mutation.policy_epoch,
            expected_revision: base.revision, operation, reason, ...(operation === 'correct' ? { body, sources: seqs } : {}) };
          const key = JSON.stringify(request);
          if (intent.current?.key !== key) {
            const requestId = [...crypto.getRandomValues(new Uint8Array(16))].map(value => value.toString(16).padStart(2,'0')).join('');
            intent.current = { key, request: { ...request, request_id: requestId } };
          }
          await rpc('memoryMutation', { request: intent.current.request });
          onSaved();
        } catch (error) { setNotice(t('memory.edit.conflict') + ' ' + error.message); }
        finally { setBusy(false); }
      };
      const reload = async () => {
        if (busy) return;
        setBusy(true);
        try { const latest = await rpc('memory', { request: { session_id: sessionId, id: detail.mutation.id } });
          setBase(latest); setNotice('revision=' + latest.revision + ' · ' + t('memory.edit.note')); }
        catch (error) { setNotice(error.message); }
        finally { setBusy(false); }
      };
      return h('section', { 'aria-label': t('memory.edit'), style: { ...stack, marginTop: 12 } },
        h('p', { style: small }, t('memory.edit.note') + ' · revision=' + base.revision),
        base.revision !== detail.revision && h('div', null, h('p', { style: small }, t('memory.edit.latest')),
          h(MarkdownText, { text: base.body, labels: markdownLabels(t) })),
        h('textarea', { 'aria-label': t('memory.edit.body'), value: body, maxLength: 4000, rows: 4, disabled: busy,
          onChange: event => setBody(event.target.value), style: { width: '100%', boxSizing: 'border-box' } }),
        h(Input, { 'aria-label': t('memory.edit.sources'), value: sources, maxLength: 1000, disabled: busy, onChange: event => setSources(event.target.value) }),
        h(Input, { 'aria-label': t('memory.edit.reason'), value: reason, maxLength: 500, disabled: busy, onChange: event => setReason(event.target.value) }),
        h('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8 } },
          h(Button, { disabled: busy || !reason.trim(), onClick: () => submit('correct') }, t('memory.edit.correct')),
          h(Button, { disabled: busy || !reason.trim(), onClick: () => submit('forget') }, t('memory.edit.forget')),
          h(Button, { disabled: busy, onClick: reload }, t('memory.edit.reload'))),
        notice && h('p', { role: 'alert' }, notice),
        base.operator_corrections?.length > 0 && h('p', { style: small }, t('memory.edit.audit') + ': ' + base.operator_corrections.map(row => row.operation + ' r' + row.revision).join(' · ')));
    }
/* UPSTREAM_COMPONENTS */
    for (const definition of stageDefinitions) ctx.effect(() => ctx.uiConversation.events.register(definition));
    function SoyoTrigger(props) {
      const stage = sourceStage(props.node?.data?.source);
      return h(AsunaTrigger, stage ? { ...props, node: { ...props.node, data: { ...props.node.data,
        source: { ...props.node.data.source, soyo_ui_trigger: true, trigger: stage.trigger } } } } : props);
    }
    ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({ name: 'conversation.chat.node', key: 'turn-trigger',
      priority: -2, locale: 'chat' }, SoyoTrigger));
    ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@soyo/asuna-memory', kind: 'soyo-asuna-memory', title: () => t('memory.tab'),
      guide: [{ id: 'soyo-asuna-memory', order: 40, title: () => t('memory.tab'), description: () => t('memory.guide') }] }));
    ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab',
      key: '@soyo/asuna-memory', locale: NS }, Memory));
    ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@soyo/asuna-settings', kind: 'soyo-asuna-settings', title: () => t('session.settings') }));
    ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({ name: 'sidebar.right.pane.tab',
      key: '@soyo/asuna-settings', locale: NS }, Settings));
    ctx.effect(()=>ctx.sidebarRightTabs.register({id:'@soyo/asuna-development',kind:'soyo-asuna-development',title:()=>t('development.tab')}));
    ctx.slots.inject('sidebar.right.pane.tab',()=>ctx.slots.register({name:'sidebar.right.pane.tab',key:'@soyo/asuna-development',locale:NS},Development));
    ctx.slots.inject('plugins.bundle.config', () => ctx.slots.register({ name: 'plugins.bundle.config',
      key: '@soyo/dsh-asuna-ui', locale: NS }, Settings));
    function SessionBrainHeader(props) {
      const [identity, setIdentity] = React.useState(null);
      React.useEffect(() => {
        const controller = new AbortController(); setIdentity(null);
        rpc('identity', { session_id: props.sessionId }, controller.signal).then(value => {
          if (!controller.signal.aborted) setIdentity(value);
        }).catch(() => {});
        return () => controller.abort();
      }, [props.sessionId]);
      return identity && h('span', { 'data-soyo-author-ui': true, title: t('ui.scope'), style: { display: 'flex', alignItems: 'center', gap: 6 } },
        h(Pill, { className: brainClass(identity.lane) }, identity.label),
        h(Button, { size: 'sm', variant: 'ghost', onClick: () => ctx.sidebarRight.openTab('soyo-asuna-memory') }, t('memory.tab')),
         h(Button, { size: 'sm', variant: 'ghost', onClick: () => { reloadSettings(); ctx.sidebarRight.openTab('soyo-asuna-settings'); } }, t('session.settings')),
         h(Button,{size:'sm',variant:'ghost',onClick:()=>ctx.sidebarRight.openTab('soyo-asuna-development')},t('development.tab')));
    }
    ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({ name: 'conversation.session.header.actions',
      id: 'soyo-scene-identity', order: 40, locale: NS }, SessionBrainHeader));
    function SoyoThread(props) {
      const [value, setValue] = React.useState(null), [error, setError] = React.useState('');
      React.useEffect(() => {
        let live = true, busy = false;
        setValue(null); setError('');
        const controller = new AbortController();
        const load = async () => {
          if (busy) return; busy = true;
          try {
            const next = await rpc('thread', { session_id: props.sessionId, id: props.node.data.taskId }, controller.signal);
            if (live) { setValue(next); setError(''); }
          } catch (failure) { if (live) setError(failure.message); }
          finally { busy = false; }
        };
        load(); const timer = setInterval(load, 3000);
        return () => { live = false; controller.abort(); clearInterval(timer); };
      }, [props.sessionId, props.node.data.taskId]);
      if (!value) return h('p', { role: error ? 'alert' : 'status' }, error || props.t('collab.loading'));
       return h(React.Fragment, null, error && h('p', { role: 'alert' }, error),
         value.native_child_created === false
           ? h('p', { role: 'status' }, value.state === 'queued' ? t('development.queued') : word(t, 'collab.state.', value.state))
           : h(CollabThread, { ...props, node: { ...props.node, data: { entries: value.entries } } }),
         ...(value.reviews ?? []).map(row => h(ReviewRecord, { key: row.id, row, t })));
    }
    function SoyoToolRow(props) {
      const [name, map] = aliases[props.toolName];
      const raw = props.phase === 'start' ? props.block.argsRaw : props.phase === 'result' ? props.block.call?.argsRaw : '';
      const args = map(parseArgs(raw));
      const argsRaw = JSON.stringify(args);
      const block = props.phase === 'result' ? { ...props.block, call: { ...props.block.call, argsRaw } } : { ...props.block, argsRaw };
      return h(RoleToolRow, { ...props, toolName: name, block });
    }
    ctx.effect(() => {
      const style = document.createElement('style'); style.textContent = brainPalette + '\n' +
        'body .asuna-brain-reviewer { color: var(--dsw-static-green-600, #15803d); background: color-mix(in srgb, #15803d 10%, var(--dsw-alias-bg-base)); }\n' +
        'body[data-ds-dark-theme] .asuna-brain-reviewer { color: #86efac; background: color-mix(in srgb, #86efac 10%, var(--dsw-alias-bg-base)); }';
      document.head.append(style); return () => style.remove();
    });
    ctx.effect(() => ctx.uiConversation.events.register(actionDefinition));
    ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
      name: 'conversation.chat.node', key: 'soyo-action-thread', locale: NS,
      children: { 'asuna.collab.work': { kind: 'single', scope: 'session' } },
    }, SoyoThread));
    ctx.slots.inject('asuna.collab.work', () => ctx.slots.register({ name: 'asuna.collab.work' }, WorkFragment));
    for (const name of Object.keys(aliases)) ctx.slots.inject('tool.call.toolview', () => ctx.slots.register({
      name: 'tool.call.toolview', key: name, locale: NS }, SoyoToolRow));
  }
  return { apply, inject: ['slots', 'locale', 'sidebarRight', 'sidebarRightTabs', 'connection', 'remote', 'remote.settings',
    'remote.credentials', 'configForms', 'sessions', 'uiConversation'] };
} });
