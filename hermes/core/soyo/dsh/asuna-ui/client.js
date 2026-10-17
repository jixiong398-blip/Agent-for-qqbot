// SPDX-License-Identifier: GPL-3.0-only
// Generated from pinned AsunaCognitionCore controls; see vendor/source.json.
// Verbatim and adapted upstream sections are distinguished in BUILD_MANIFEST.json.
window.__ModuleLoader__.load({ id: '@soyo/dsh-asuna-ui', factory: require => {
  const React = require('react');
  const primitives = require('@deepseek-ai/dsh-client-ui-primitives');
  const { Button, Input, Menu, Pill, IconChevronDownOutlineRegular, DisclosureRow, MarkdownText,
    SettingsForm, SettingsFormModel, SettingsValueField, SettingsSecretField } = primitives;
  const h = React.createElement;
  const NS = 'soyo-asuna-ui';
  const DICTIONARY = {
    zh: {
      'date.locale': 'zh-CN',
      'brain.character': '角色脑', 'brain.executor': '行动脑',
      'trigger.message': '收到消息', 'trigger.task_result': '行动脑交回了结果', 'trigger.question': '行动脑在问角色',
      'trigger.internal': '角色的内部时间', 'trigger.visit': '角色自己来看看', 'trigger.note': '角色自己留的便条', 'trigger.schedule': '到了安排的时间', 'trigger.brief': '角色的交代',
      'trigger.follow-up': '角色的补充',
      'collab.header': '{character} ⇄ {action}', 'collab.untitled': '一件事',
      'collab.state.queued': '排队中', 'collab.state.running': '进行中', 'collab.state.waiting': '等角色回答',
      'collab.state.done': '已完成', 'collab.state.failed': '没做成', 'collab.state.stopped': '已叫停',
      'collab.state.paused': '已暂停', 'collab.paused': '宿主重启时暂停了；要接着做，在本机私聊里请角色继续。',
      'collab.outcome.done': '做完了', 'collab.outcome.failed': '没做成',
      'collab.handback.handing': '{outcome} · 正在交给角色', 'collab.handback.taken': '{outcome} · 角色看过了',
      'collab.handback.missed': '{outcome} · 没交到角色手上',
      'collab.missed.report': '报告在上面，但交回给角色时程序出错（{error}）。',
      'collab.missed.turn': '报告交回了，但角色读它的那一轮没走完（{error}）。',
      'collab.missed.restart': '报告在上面，宿主重启前没来得及交给角色。', 'collab.missed.retry': '程序会再交给角色。',
      'collab.missed.final': '全文和短版都没交成，已经告诉开发者；报告还存着。', 'collab.handback.handingShort': '{outcome} · 正在补交短版',
      'workspace.local': '本机', 'session.group': '群聊', 'session.dm': '私聊',
      'collab.state.continued': '下面接着', 'collab.working': '正在做 {duration}', 'collab.watch': '展开看实时过程',
      'collab.stopped': '已叫停：{reason}', 'collab.open': '在侧栏打开完整过程',
      'collab.work': '工作了 {duration}', 'collab.call': '{n} 次工具调用', 'collab.calls': '{n} 次工具调用', 'collab.loading': '读取行动脑记录…',
      'collab.more': '展开全文', 'collab.less': '收起', 'collab.progress': '进展',
      'duration.seconds': '{n} 秒', 'duration.minutes': '{n} 分钟', 'duration.hours': '{h} 小时 {m} 分钟',
      'tool.think': '心里话', 'tool.recall': '回想', 'tool.delegate': '交给行动脑', 'tool.message_action': '给行动脑补话',
      'tool.stop_action': '叫停', 'tool.answer_action': '回答行动脑', 'tool.stay_silent': '不说话',
      'tool.attach_image': '配图', 'tool.write_document': '写文档', 'tool.update_self': '更新自我',
      'tool.understand_person': '理解这个人', 'tool.set_policy': '调参数',
      'tool.feel': '心情', 'tool.plan': '安排', 'tool.group_action': '群管理', 'tool.promote_memory': '沉淀记忆',
      'tool.visit': '出门', 'tool.note_idea': '记想法', 'tool.read_ideas': '读想法本', 'tool.read_report': '翻读报告', 'tool.review_idea': '处理想法', 'tool.ask_character': '问角色', 'tool.report_progress': '报进展',
      'tool.refused': '被退回', 'tool.preparing': '正在写…', 'repair.title': '草稿退回重写',
      'input.checking': '正在确认会话输入权限…', 'input.internal': '这是内部工作会话，请回到本地私聊。',
      'input.schedules': '这是定时提醒的投递会话，只用来送达角色的计划和闹钟，在这里写的话角色收不到；跟角色说话请回到本地私聊。',
      'input.readOnly': '{platform} 会话仅供查看，请在 {platform} 中回复。', 'input.readOnlyLocal': '这个会话仅供查看。',
      'markdown.copy': '复制', 'markdown.copied': '已复制', 'markdown.footnotes': '来源',
      'memory.tab': '记忆', 'memory.guide': '当前角色、场景与授权来源', 'memory.aria': 'Bot 记忆',
      'memory.category': '记忆类型', 'memory.search': '搜索记忆', 'memory.searchPlaceholder': '搜索当前类型的全部记录',
      'memory.refresh': '刷新记忆', 'memory.subject': '当前交谈对象：{name}', 'memory.linked': '也能读到：{titles}',
      'memory.notBound': '当前会话尚无 Bot 场景绑定。完成角色交互后可查看。', 'memory.loading': '读取当前场景…',
      'memory.detailLoading': '读取详情…', 'memory.revision': '版本 {n}', 'memory.compiled': '整理于 {time}',
      'memory.sourcesTruncated': '以下显示前 12 条来源。', 'memory.noMatch': '未找到匹配的记录。',
      'memory.empty': '当前范围暂无记录。', 'memory.previous': '上一页', 'memory.next': '下一页',
      'memory.corrected': '这条记录之后出现了更正；请结合后续原话查看。', 'memory.separator': '、',
      'memory.kind.all': '全部', 'memory.kind.documents': '文档', 'memory.kind.affect': '情感', 'memory.kind.jobs': '作业报告',
      'memory.kind.ideas': '改进想法', 'memory.category.idea': '改进想法',
      'memory.idea.state.open': '待处理', 'memory.idea.state.adopted': '已采纳', 'memory.idea.state.deferred': '暂缓',
      'memory.idea.state.dropped': '已放弃', 'memory.idea.why': '为什么：{text}', 'memory.idea.from.character': '角色自己记下的 · {where}',
      'memory.idea.from.action': '行动脑做事时记下的 · {where}', 'memory.idea.decision.adopt': '采纳：{why}',
      'memory.idea.decision.defer': '暂缓：{why}', 'memory.idea.decision.drop': '放弃：{why}',
      'memory.status.idea.open': '待处理', 'memory.status.idea.adopted': '已采纳', 'memory.status.idea.deferred': '暂缓',
      'memory.status.idea.dropped': '已放弃',
      'memory.kind.self': '自我', 'memory.kind.relation': '对人的认识', 'memory.kind.summary': '交流摘要',
      'memory.kind.interpretation': '当时的理解', 'memory.kind.source': '原始来源',
      'memory.category.self': '自我', 'memory.category.relation': '对人的认识', 'memory.category.derived_summary': '交流摘要',
      'memory.category.character_interpretation': '当时的理解', 'memory.category.public_statement': '角色的发言',
      'memory.category.reported_speech': '他人的原话', 'memory.category.observed_fact': '事实记录',
      'memory.category.source': '原始消息', 'memory.category.document': '文档', 'memory.category.affect': '情感',
      'memory.category.affect_event': '情感', 'memory.category.persona_job_report': '作业报告', 'memory.category.other': '记忆',
      'memory.status.empty': '还没有写过', 'memory.status.recorded': '已记录',
      'memory.hint.self': '角色只在每天一次的内部自省时间里决定要不要写下或改写。',
      'memory.hint.relation': '角色在对话中觉得对这个人的理解有了变化时才会写下。',
      'memory.title.character_core': '核心自我', 'memory.title.current_self': '当前自我', 'memory.title.relation': '关系与偏好',
      'memory.title.peer': '对方身份资料', 'memory.title.mood': '此刻的心情', 'memory.title.moved': '触动 · {feeling}',
      'memory.title.job': '作业报告', 'memory.title.said': '原话 · {speaker}', 'memory.title.blank': '无正文的记忆',
      'memory.title.document': '{kind}', 'memory.title.documentNamed': '{kind} · {name}',
      'memory.doc.persona': '人格设定', 'memory.doc.voice': '说话方式', 'memory.doc.ledger': '承诺与挂账',
      'memory.doc.working': '工作笔记', 'memory.doc.other': '文档',
      'memory.doc.sections': '{label} {n} 节', 'memory.doc.overBudget': '超出渲染预算',
      'memory.visibility.public': '公开', 'memory.visibility.owner_private': '仅主人可见',
      'memory.inject.always': '每轮都用', 'memory.inject.on_demand': '相关时才用', 'memory.inject.never': '不放进对话',
      'memory.mood.calm': '平静', 'memory.mood.line': '{label} · 心情 {val} · 激动 {arl}{open}', 'memory.mood.open': ' · {n} 件事还挂着',
      'memory.mood.head': '**{label}**（心情 {val}，范围 −100～100；激动 {arl}，范围 0～100）',
      'memory.mood.policy': '此刻的倾向：{text}', 'memory.mood.tendencies': '主要的情绪带来：{text}', 'memory.mood.from': '来自：',
      'memory.mood.contribution': '- {feeling} · 心情 {val} · 激动 {arl} · {ago}{held}：{why}', 'memory.mood.held': '（还挂着，不会淡去）',
      'memory.mood.fade': '每件触动会随时间淡去（各种情绪淡得快慢不同）；还挂着的事要等了结后才开始淡。',
      'memory.event.line': '心情 {val} · 激动 {arl}{held} · {why}', 'memory.event.held': ' · 还挂着',
      'memory.event.kind': '种类：{feeling} · 心情 {val} · 激动 {arl}', 'memory.event.cost': '代价：{text}',
      'memory.event.open': '这是一件还挂着的事：了结之前不会淡去。', 'memory.event.noReason': '（未写原因）',
      'memory.amendment.close': '已了结：{why}', 'memory.amendment.void': '作废（前提不成立）：{why}', 'memory.amendment.fix_ts': '更正时间：{why}',
      'memory.amendment.fix_kind': '更正种类：{why}', 'memory.doc.meta': '*{visibility} · {inject}{date}*',
      'memory.report.status': '状态：{status} · 作业 {job} · {run}',
      'memory.ago.now': '刚才', 'memory.ago.minutes': '{n} 分钟前', 'memory.ago.hours': '{n} 小时前', 'memory.ago.days': '{n} 天前',
      'memory.scene.shared': '所有对话共用', 'memory.scene.local': '本地聊天', 'memory.scene.group': '群聊 · {name}',
      'memory.scene.dm': '私聊 · {name}',
      'memory.usage.none': '这个对话还没有可核对的一轮', 'memory.usage.used': '最近一轮（{time}）用到了这一版',
      'memory.usage.older': '最近一轮（{time}）用的还是旧版本', 'memory.usage.formed': '最近一轮形成的理解，保存在该轮原生会话中',
      'memory.usage.input': '是最近一轮（{time}）的输入', 'memory.usage.unused': '最近一轮（{time}）没有用到',
      'memory.readback': '——回读（{path} 第 {from}–{to} 行，导入时快照）——',
      'settings.loading': '读取设置…', 'settings.unavailable': '配置暂不可用。', 'settings.aria': 'Bot 设置',
      'settings.persona': '当前角色', 'settings.channelAdmission': '外部渠道接入策略', 'settings.python': 'Python',

      'settings.route': '{brain} · {field}', 'settings.route.provider': '模型服务', 'settings.route.model': '模型',
      'settings.route.reasoningEffort': '推理强度', 'settings.route.maxTokens': '最大输出 token',
      'settings.route.attendEffort': '要不要接话时的推理强度', 'settings.route.groupEffort': '群聊里的推理强度',
      'settings.routeEffort': '同这个脑的推理强度',
      'settings.newSecrets': '新增或更新凭据（JSON）', 'settings.overridden': '已覆盖', 'settings.reset': '恢复默认',
      'settings.choose': '请选择', 'settings.unavailableValue': '{value}（当前不可用）',
      'settings.admission.automatic': '自动接入私聊、群及新成员', 'settings.admission.explicit': '仅接入已配置身份',
      'settings.providerDefault': '使用模型服务默认值', 'settings.routeHint': '选项来自 DSH 已配置的模型服务及其能力。',
      'settings.secretMapHint': '例如 {"ASUNA_CHANNELS_NEW_TOKEN":"值"}：存进凭据库，设置里只写引用。只更新列出的名称；留空不修改。', 'settings.secretHint': '留空保留现有凭据。',
      'settings.secretAdd': '可添加凭据引用', 'settings.secretSet': '已配置', 'settings.secretUnset': '未配置',
      'settings.jsonHint': 'JSON 配置；凭据使用 {"$secret":"名称"} 引用。', 'settings.pythonHint': '留空：首次启动时在数据目录里按包里的锁文件建好 Python 环境（需要 uv 或 Python 3.12+）。', 'settings.invalidNumber': '请输入正整数',
      'settings.invalidJson': '请输入有效的 JSON 值', 'settings.form.unavailable': '配置暂不可用', 'settings.form.readOnly': '当前配置只读',
      'settings.form.saveFailed': '保存失败，草稿已保留。', 'settings.form.save': '保存设置', 'settings.form.saving': '保存中…',
      'settings.status': '业务进程：{state} · Mongo：{database}', 'settings.disconnected': '未连接',
      'settings.restartWaiting': '{project} 的已发布改动（{time}）要重启宿主后才生效；在那之前夜里的自我开发会跳过。',
      'settings.readingStatus': '读取状态…',
      'settings.note': '配置由 DSH 保存；凭据只写不回显。模型与 API key 在 DSH 原生 provider 设置管理。会话中的模型选择优先于下方默认路由。',
      'settings.savedPending': '已保存，尚未应用。', 'settings.savedApplied': '已保存，与当前应用配置一致。',
      'settings.activated': '已应用到业务 worker 与后续模型请求。',
      'settings.selfSource': '自我来源：{source}', 'settings.waiting': '等待连接', 'settings.channelsFallback': '外部渠道',
      'settings.deployment.database': "数据库名", 'settings.deployment.allowed_databases': "允许的数据库",
      'settings.deployment.legacy_database': "旧数据库", 'settings.deployment.mongo_uri': "Mongo 连接",
      'settings.deployment.embedding': "向量模型",
      'settings.deployment.workflow_timeout_seconds': "阶段超时（秒）",
      'settings.deployment.provider_idle_timeout_seconds': "模型空闲超时（秒）",
      'settings.deployment.publish_adapter': "发布适配器", 'settings.deployment.prompts_dir': "提示词目录",
      'settings.deployment.chat': "本机对话", 'settings.deployment.self_development': "自我改进",
      'settings.deployment.timezone': "时区", 'settings.deployment.persona_runtime': "人格运行参数",
      'settings.deployment.integration': "设备集成", 'settings.deployment.channels': "外部渠道",
      'settings.deployment.channel_port': "渠道端口", 'settings.deployment.context_links': "关联对话",
      'settings.deployment.canonical_persons': "同一个人的账号", 'settings.deployment.vision': "看图",
      'settings.deployment.search': "网页搜索", 'settings.deployment.active_groups': "常驻群（平常的数目）",
      'settings.state.unconfigured': "未配置", 'settings.state.inert': "未启用", 'settings.state.starting': "启动中",
      'settings.state.ready': "就绪", 'settings.state.failed': "失败", 'settings.state.preparing': "准备中",
      'settings.state.restarting': "重启中", 'settings.step.uv': "用 uv 建 Python 环境",
      'settings.step.python': "用本机 Python 建环境", 'settings.step.ready': "Python 环境就绪",
      'settings.database.connected': "已连接", 'settings.database.unavailable': "不可用",
      'settings.selfSource.mongo': "Mongo 里已有的自我状态", 'settings.integration.RUNNING': "运行中",
      'settings.integration.STARTING': "启动中", 'settings.integration.STOPPED': "已停止",
      'settings.integration.EXITED': "已退出", 'settings.integration.DISABLED': "未启用", 'settings.sandbox.dsh': "DSH 沙箱",
      'settings.sandboxReason.off': "设置里关掉了", 'settings.sandboxReason.no_host': "宿主没有沙箱",
      'settings.channels': '{titles}：{state}', 'settings.channelOn': '本机入口已启动；适配器 {state}；平台连接未验证',
      'settings.channelOff': '未启用', 'settings.schedule': '定时：{state}', 'settings.sandbox': '沙箱：{state}', 'settings.sandboxNone': '无（{reason}）：跑代码、自开发与集成已关闭', 'settings.scheduleOn': '原生调度',
      'settings.pending': '已保存的配置尚未应用。', 'settings.applied': '保存配置与当前应用配置一致。',
      'settings.apply': '应用已保存设置', 'settings.refresh': '刷新状态',
      'persona.aria': '人格数据', 'persona.title': '人格数据 · {persona}',
      'persona.render': '人格渲染估算 {estimate} / 上限 {limit}', 'persona.unlimited': '未设', 'persona.overBudget': '超出预算',
      'persona.sources': '源根：{list}', 'persona.source': '{id}（{state}，{path}）', 'persona.noSources': '未配置源根（本机配置 persona_sources）。',
      'persona.job': '作业 {id} · 源根 {sources}', 'persona.dryRun': '试运行', 'persona.run': '运行',
      'persona.runs': '最近运行：{list}', 'persona.runDry': '（试）', 'persona.export': '导出文档',
      'persona.exportUnset': '导出（未配置 export_dir）', 'persona.exported': '已导出 {n} 份文档。',
      'persona.jobResult': '作业 {job}{dry}：{status}{code}{reason} · 报告在「记忆 → 作业报告」中查看。',
      'persona.exitCode': ' · 退出码 {code}',
    },
    en: {
      'date.locale': 'en-US',
      'brain.character': 'Character brain', 'brain.executor': 'Action brain',
      'trigger.message': 'Message received', 'trigger.task_result': 'The action brain reported back',
      'trigger.question': 'The action brain asks them', 'trigger.internal': 'Their inner time', 'trigger.visit': 'Their own visit', 'trigger.note': 'A note from themselves', 'trigger.schedule': 'A plan came due',
      'trigger.brief': 'Their brief', 'trigger.follow-up': 'Their follow-up',
      'collab.header': '{character} ⇄ {action}', 'collab.untitled': 'A task',
      'collab.state.queued': 'Queued', 'collab.state.running': 'In progress', 'collab.state.waiting': 'Waiting for their answer',
      'collab.state.done': 'Done', 'collab.state.failed': 'Not finished', 'collab.state.stopped': 'Stopped',
      'collab.state.paused': 'Paused', 'collab.paused': 'Paused when the Host restarted; ask them in the local chat to continue.',
      'collab.outcome.done': 'Done', 'collab.outcome.failed': 'Not finished',
      'collab.handback.handing': '{outcome} · Handing it to them', 'collab.handback.taken': '{outcome} · They have read it',
      'collab.handback.missed': '{outcome} · Never reached them',
      'collab.missed.report': 'The report is above, but handing it back to them failed ({error}). ',
      'collab.missed.turn': 'The report was handed back, but their turn reading it did not finish ({error}). ',
      'collab.missed.restart': 'The report is above; the Host restarted before it reached them. ',
      'collab.missed.retry': 'The program will hand it back again.',
      'collab.missed.final': 'Neither the full nor the short version reached them; the developer has been told. The report is still stored.',
      'collab.handback.handingShort': '{outcome} · Handing them a short version',
      'workspace.local': 'Local', 'session.group': 'Group chat', 'session.dm': 'Direct message',
      'collab.state.continued': 'Continued below', 'collab.working': 'Working {duration}', 'collab.watch': 'Expand to watch it live',
      'collab.stopped': 'Stopped: {reason}', 'collab.open': 'Open the full record in the sidebar',
      'collab.work': 'Worked {duration}', 'collab.call': '{n} tool call', 'collab.calls': '{n} tool calls', 'collab.loading': 'Loading the action brain’s record…',
      'collab.more': 'Show all', 'collab.less': 'Show less', 'collab.progress': 'Progress',
      'duration.seconds': '{n}s', 'duration.minutes': '{n} min', 'duration.hours': '{h} h {m} min',
      'tool.think': 'Thought', 'tool.recall': 'Recall', 'tool.delegate': 'Hand to the action brain',
      'tool.message_action': 'Message the action brain', 'tool.stop_action': 'Stop a task', 'tool.answer_action': 'Answer the action brain',
      'tool.stay_silent': 'Stay silent', 'tool.attach_image': 'Attach a picture', 'tool.write_document': 'Write document',
      'tool.update_self': 'Update self', 'tool.understand_person': 'Understand this person', 'tool.set_policy': 'Adjust a setting',
      'tool.feel': 'Feeling', 'tool.plan': 'Plan', 'tool.group_action': 'Group action',
      'tool.promote_memory': 'Keep a memory', 'tool.visit': 'Go and see a group', 'tool.note_idea': 'Note an idea', 'tool.read_ideas': 'Read their ideas', 'tool.read_report': 'Read on in a report', 'tool.review_idea': 'Review an idea', 'tool.ask_character': 'Ask them',
      'tool.report_progress': 'Report progress', 'tool.refused': 'Refused', 'tool.preparing': 'Writing…',
      'repair.title': 'Draft sent back',
      'input.checking': 'Checking who may write here…', 'input.internal': 'This is an internal work conversation; go back to the local chat.',
      'input.schedules': 'This conversation only delivers their plans and alarms; nothing written here reaches them. Talk to them in the local chat.',
      'input.readOnly': '{platform} conversations are read-only here; reply in {platform}.', 'input.readOnlyLocal': 'This conversation is read-only.',
      'markdown.copy': 'Copy', 'markdown.copied': 'Copied', 'markdown.footnotes': 'Sources',
      'memory.tab': 'Memory', 'memory.guide': 'The character, this scene and its authorized sources', 'memory.aria': 'Bot memory',
      'memory.category': 'Kind of memory', 'memory.search': 'Search memory', 'memory.searchPlaceholder': 'Search every record of this kind',
      'memory.refresh': 'Refresh', 'memory.subject': 'Talking with: {name}', 'memory.linked': 'Also reads: {titles}',
      'memory.notBound': 'This conversation has no Bot scene yet. It appears after they have taken part.',
      'memory.loading': 'Loading this scene…', 'memory.detailLoading': 'Loading…', 'memory.revision': 'Revision {n}',
      'memory.compiled': 'Compiled {time}', 'memory.sourcesTruncated': 'Showing the first 12 sources.',
      'memory.noMatch': 'No matching records.', 'memory.empty': 'Nothing here yet.', 'memory.previous': 'Previous', 'memory.next': 'Next',
      'memory.corrected': 'This record was corrected later; read it with the later messages.', 'memory.separator': ', ',
      'memory.kind.all': 'All', 'memory.kind.documents': 'Documents', 'memory.kind.affect': 'Feelings', 'memory.kind.jobs': 'Job reports',
      'memory.kind.ideas': 'Improvement ideas', 'memory.category.idea': 'Improvement idea',
      'memory.idea.state.open': 'Open', 'memory.idea.state.adopted': 'Adopted', 'memory.idea.state.deferred': 'Deferred',
      'memory.idea.state.dropped': 'Dropped', 'memory.idea.why': 'Why: {text}', 'memory.idea.from.character': 'Noted by them · {where}',
      'memory.idea.from.action': 'Noted by the action brain while working · {where}', 'memory.idea.decision.adopt': 'Adopted: {why}',
      'memory.idea.decision.defer': 'Deferred: {why}', 'memory.idea.decision.drop': 'Dropped: {why}',
      'memory.status.idea.open': 'Open', 'memory.status.idea.adopted': 'Adopted', 'memory.status.idea.deferred': 'Deferred',
      'memory.status.idea.dropped': 'Dropped',
      'memory.kind.self': 'Self', 'memory.kind.relation': 'People', 'memory.kind.summary': 'Summaries',
      'memory.kind.interpretation': 'Their readings', 'memory.kind.source': 'Sources',
      'memory.category.self': 'Self', 'memory.category.relation': 'People', 'memory.category.derived_summary': 'Summary',
      'memory.category.character_interpretation': 'Their reading', 'memory.category.public_statement': 'What they said',
      'memory.category.reported_speech': 'What others said', 'memory.category.observed_fact': 'Recorded fact',
      'memory.category.source': 'Original message', 'memory.category.document': 'Document', 'memory.category.affect': 'Feelings',
      'memory.category.affect_event': 'Feelings', 'memory.category.persona_job_report': 'Job report', 'memory.category.other': 'Memory',
      'memory.status.empty': 'Not written yet', 'memory.status.recorded': 'Recorded',
      'memory.hint.self': 'They decide whether to write or rewrite this only in their daily time for reflection.',
      'memory.hint.relation': 'They write this when, in a conversation, their understanding of the person changes.',
      'memory.title.character_core': 'Core self', 'memory.title.current_self': 'Current self', 'memory.title.relation': 'Relationship and preferences',
      'memory.title.peer': 'Their profile', 'memory.title.mood': 'Their mood now', 'memory.title.moved': 'Moved · {feeling}',
      'memory.title.job': 'Job report', 'memory.title.said': 'Said · {speaker}', 'memory.title.blank': 'A memory without text',
      'memory.title.document': '{kind}', 'memory.title.documentNamed': '{kind} · {name}',
      'memory.doc.persona': 'Persona', 'memory.doc.voice': 'Voice', 'memory.doc.ledger': 'Promises and open items',
      'memory.doc.working': 'Working notes', 'memory.doc.other': 'Document',
      'memory.doc.sections': '{label}: {n} sections', 'memory.doc.overBudget': 'over the render budget',
      'memory.visibility.public': 'Public', 'memory.visibility.owner_private': 'Owner only',
      'memory.inject.always': 'used every turn', 'memory.inject.on_demand': 'used when relevant', 'memory.inject.never': 'never in conversation',
      'memory.mood.calm': 'Calm', 'memory.mood.line': '{label} · mood {val} · stirred {arl}{open}', 'memory.mood.open': ' · {n} things still open',
      'memory.mood.head': '**{label}** (mood {val}, from −100 to 100; stirred {arl}, from 0 to 100)',
      'memory.mood.policy': 'Leaning now: {text}', 'memory.mood.tendencies': 'Their main feelings bring: {text}', 'memory.mood.from': 'From:',
      'memory.mood.contribution': '- {feeling} · mood {val} · stirred {arl} · {ago}{held}: {why}', 'memory.mood.held': ' (still open, not fading)',
      'memory.mood.fade': 'Each thing that moved them fades with time (some feelings faster than others); open things fade only once settled.',
      'memory.event.line': 'mood {val} · stirred {arl}{held} · {why}', 'memory.event.held': ' · still open',
      'memory.event.kind': 'Kind: {feeling} · mood {val} · stirred {arl}', 'memory.event.cost': 'Cost: {text}',
      'memory.event.open': 'This is still open: it does not fade until settled.', 'memory.event.noReason': '(no reason written)',
      'memory.amendment.close': 'Settled: {why}', 'memory.amendment.void': 'Voided (its premise was wrong): {why}', 'memory.amendment.fix_ts': 'Time corrected: {why}',
      'memory.amendment.fix_kind': 'Kind corrected: {why}', 'memory.doc.meta': '*{visibility} · {inject}{date}*',
      'memory.report.status': 'Status: {status} · job {job} · {run}',
      'memory.ago.now': 'just now', 'memory.ago.minutes': '{n} min ago', 'memory.ago.hours': '{n} h ago', 'memory.ago.days': '{n} days ago',
      'memory.scene.shared': 'Shared by every conversation', 'memory.scene.local': 'Local chat', 'memory.scene.group': 'Group · {name}',
      'memory.scene.dm': 'Direct · {name}',
      'memory.usage.none': 'This conversation has no turn to check against yet', 'memory.usage.used': 'Used in the latest turn ({time})',
      'memory.usage.older': 'The latest turn ({time}) still used an older revision', 'memory.usage.formed': 'Formed in the latest turn; kept in that turn’s native conversation',
      'memory.usage.input': 'The input of the latest turn ({time})', 'memory.usage.unused': 'Not used in the latest turn ({time})',
      'memory.readback': '— read back ({path}, lines {from}–{to}, snapshot taken at import) —',
      'settings.loading': 'Loading settings…', 'settings.unavailable': 'Settings are unavailable.', 'settings.aria': 'Bot settings',
      'settings.persona': 'Character', 'settings.channelAdmission': 'Channel admission', 'settings.python': 'Python',

      'settings.route': '{brain} · {field}', 'settings.route.provider': 'Model service', 'settings.route.model': 'Model',
      'settings.route.reasoningEffort': 'Reasoning effort', 'settings.route.maxTokens': 'Max output tokens',
      'settings.route.attendEffort': 'Reasoning effort when deciding whether to reply', 'settings.route.groupEffort': 'Reasoning effort in groups',
      'settings.routeEffort': "Same as this brain's reasoning effort",
      'settings.newSecrets': 'Add or update credentials (JSON)', 'settings.overridden': 'Overridden', 'settings.reset': 'Reset to default',
      'settings.choose': 'Choose', 'settings.unavailableValue': '{value} (unavailable now)',
      'settings.admission.automatic': 'Admit direct chats, groups and new members automatically', 'settings.admission.explicit': 'Admit configured identities only',
      'settings.providerDefault': 'Model service default', 'settings.routeHint': 'Choices come from the model services configured in DSH and what they offer.',
      'settings.secretMapHint': 'For example {"ASUNA_CHANNELS_NEW_TOKEN":"value"}: stored in the credential store; the settings keep only the reference. Only the listed names change; leave empty for no change.',
      'settings.secretHint': 'Leave empty to keep the current credential.',
      'settings.secretAdd': 'Credential references can be added', 'settings.secretSet': 'Configured', 'settings.secretUnset': 'Not configured',
      'settings.jsonHint': 'JSON; refer to credentials as {"$secret":"name"}.', 'settings.pythonHint': 'Leave empty to build a Python environment from the package lock in the data folder on first start (needs uv or Python 3.12+).', 'settings.invalidNumber': 'Enter a positive whole number',
      'settings.invalidJson': 'Enter a valid JSON value', 'settings.form.unavailable': 'Settings are unavailable', 'settings.form.readOnly': 'Settings are read-only',
      'settings.form.saveFailed': 'Saving failed; your draft is kept.', 'settings.form.save': 'Save settings', 'settings.form.saving': 'Saving…',
      'settings.status': 'Business process: {state} · Mongo: {database}', 'settings.disconnected': 'not connected',
      'settings.restartWaiting': 'A published change to {project} ({time}) takes effect after a Host restart; until then their night self-development stages are skipped.',
      'settings.readingStatus': 'Reading status…',
      'settings.note': 'DSH stores these settings; credentials are write-only. Models and API keys are managed in DSH’s own provider settings. A model chosen in a conversation takes precedence over the routes below.',
      'settings.savedPending': 'Saved, not applied yet.', 'settings.savedApplied': 'Saved; matches what is running.',
      'settings.activated': 'Applied to the business worker and later model requests.',
      'settings.selfSource': 'Self from: {source}', 'settings.waiting': 'waiting for connection', 'settings.channelsFallback': 'Channels',
      'settings.deployment.database': "Database name", 'settings.deployment.allowed_databases': "Allowed databases",
      'settings.deployment.legacy_database': "Legacy database", 'settings.deployment.mongo_uri': "Mongo connection",
      'settings.deployment.embedding': "Embedding model",
      'settings.deployment.workflow_timeout_seconds': "Stage timeout (seconds)",
      'settings.deployment.provider_idle_timeout_seconds': "Model idle timeout (seconds)",
      'settings.deployment.publish_adapter': "Publish adapter", 'settings.deployment.prompts_dir': "Prompts folder",
      'settings.deployment.chat': "Local chat", 'settings.deployment.self_development': "Self-improvement",
      'settings.deployment.timezone': "Time zone", 'settings.deployment.persona_runtime': "Persona runtime",
      'settings.deployment.integration': "Device integration", 'settings.deployment.channels': "Channels",
      'settings.deployment.channel_port': "Channel port",
      'settings.deployment.context_links': "Linked conversations",
      'settings.deployment.canonical_persons': "One person's accounts", 'settings.deployment.vision': "Vision",
      'settings.deployment.search': "Web search", 'settings.deployment.active_groups': "Active groups (the usual number)",
      'settings.state.unconfigured': "not configured", 'settings.state.inert': "inactive",
      'settings.state.starting': "starting", 'settings.state.ready': "ready", 'settings.state.failed': "failed",
      'settings.state.preparing': "preparing", 'settings.state.restarting': "restarting",
      'settings.step.uv': "building the Python environment with uv",
      'settings.step.python': "building the Python environment with the local Python",
      'settings.step.ready': "Python environment ready", 'settings.database.connected': "connected",
      'settings.database.unavailable': "unavailable", 'settings.selfSource.mongo': "the self state already in Mongo",
      'settings.integration.RUNNING': "running", 'settings.integration.STARTING': "starting",
      'settings.integration.STOPPED': "stopped", 'settings.integration.EXITED': "exited",
      'settings.integration.DISABLED': "off", 'settings.sandbox.dsh': "DSH sandbox",
      'settings.sandboxReason.off': "turned off in the settings",
      'settings.sandboxReason.no_host': "the Host has no sandbox",
      'settings.channels': '{titles}: {state}', 'settings.channelOn': 'local entry running; adapter {state}; platform connection not verified',
      'settings.channelOff': 'off', 'settings.schedule': 'Schedules: {state}', 'settings.sandbox': 'Sandbox: {state}', 'settings.sandboxNone': 'none ({reason}): running code, self-development and integration are off', 'settings.scheduleOn': 'native scheduler',
      'settings.pending': 'Saved settings are not applied yet.', 'settings.applied': 'Saved settings match what is running.',
      'settings.apply': 'Apply saved settings', 'settings.refresh': 'Refresh status',
      'persona.aria': 'Persona data', 'persona.title': 'Persona data · {persona}',
      'persona.render': 'Persona render estimate {estimate} / limit {limit}', 'persona.unlimited': 'none', 'persona.overBudget': 'over budget',
      'persona.sources': 'Source roots: {list}', 'persona.source': '{id} ({state}, {path})', 'persona.noSources': 'No source roots (configure persona_sources locally).',
      'persona.job': 'Job {id} · sources {sources}', 'persona.dryRun': 'Dry run', 'persona.run': 'Run',
      'persona.runs': 'Recent runs: {list}', 'persona.runDry': ' (dry)', 'persona.export': 'Export documents',
      'persona.exportUnset': 'Export (export_dir not configured)', 'persona.exported': 'Exported {n} documents.',
      'persona.jobResult': 'Job {job}{dry}: {status}{code}{reason} · the report is under Memory → Job reports.',
      'persona.exitCode': ' · exit code {code}',
    },
  };

  const stack = { display: 'flex', flexDirection: 'column', gap: 12, padding: 16, minWidth: 0,
    overflowWrap: 'anywhere', fontSize: 14, lineHeight: 1.6 };
  const small = { fontSize: 12, color: 'var(--dsw-alias-label-tertiary)' };
  const markdownLabels = t => ({ code: { copyLabel: t('markdown.copy'), copiedLabel: t('markdown.copied') }, footnotes: t('markdown.footnotes') });
  const formatDate = (t, value, compact = false) => {
    const date = new Date(value);
    return value && Number.isFinite(date.getTime()) ? date.toLocaleString(t('date.locale'), {
      ...(compact ? {} : { year: 'numeric' }), month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }) : '';
  };
  const duration = (t, ms) => {
    const seconds = Math.max(0, Math.round(ms / 1000));
    if (seconds < 60) return t('duration.seconds', { n: seconds });
    const minutes = Math.round(seconds / 60);
    return minutes < 60 ? t('duration.minutes', { n: minutes })
      : t('duration.hours', { h: Math.floor(minutes / 60), m: minutes % 60 });
  };
  const ago = (t, hours) => hours * 60 < 5 ? t('memory.ago.now') : hours < 1 ? t('memory.ago.minutes', { n: Math.round(hours * 60) })
    : hours < 48 ? t('memory.ago.hours', { n: Math.round(hours) }) : t('memory.ago.days', { n: Math.round(hours / 24) });
  const signed = value => (value >= 0 ? '+' : '') + Math.round(Number(value) || 0);
  // A platform person id (qq:<account>) reads as `QQ · <account>`; local ids read as themselves.
  const memoryAuthor = value => typeof value === 'string'
    ? value.replace(/^([a-z][a-z0-9_]{0,15}):/, (_, kind) => kind.toUpperCase() + ' · ') : '';
  // A server label: a locale key with its parameters, or content text shown as it is.
  // A list of parts is concatenated (the server puts its own paragraph breaks in).
  const say = (t, label) => !label ? '' : typeof label === 'string' ? label
    : Array.isArray(label) ? label.map(part => say(t, part)).join('')
    : t(label.key, Object.fromEntries(Object.entries(label.params ?? {}).map(([name, value]) =>
      [name, value && typeof value === 'object' ? say(t, value) : value])));

  // A program value (a state, a code) in the viewer's words; one this version has no words for is shown as it is.
  const EFFORTS = ['reasoningEffort', 'attendEffort', 'groupEffort'];
  const DEPLOYMENT_KEYS = new Set(['database', 'allowed_databases', 'legacy_database', 'mongo_uri', 'embedding', 'workflow_timeout_seconds', 'provider_idle_timeout_seconds', 'publish_adapter', 'prompts_dir', 'chat', 'self_development', 'timezone', 'persona_runtime', 'integration', 'channels', 'channel_port', 'context_links', 'canonical_persons', 'vision', 'search']);
  const word = (t, prefix, value) => { const key = prefix + value, text = t(key); return text && text !== key ? text : String(value); };
  const deploymentLabel = key => DEPLOYMENT_KEYS.has(key) ? { key: 'settings.deployment.' + key } : key;

  const stageLabel = (t, stage) => ['character', 'executor', 'reviewer', 'helper'].includes(stage?.lane) ? t('brain.' + stage.lane) : null;
  const brainClass = lane => ['character', 'executor', 'reviewer'].includes(lane) ? 'asuna-brain-' + lane : undefined;

  // Pill's static branch forwards className, but not style. Scope just the
  // palette to these existing labels; native Pill still owns their geometry.
  const brainPalette = `
    body .asuna-brain-character { color: #7e22ce; background: color-mix(in srgb, #7e22ce 10%, var(--dsw-alias-bg-base)); }
    body .asuna-brain-executor { color: var(--dsw-static-blue-600); background: color-mix(in srgb, var(--dsw-static-blue-600) 10%, var(--dsw-alias-bg-base)); }
    body[data-ds-dark-theme] .asuna-brain-character { color: #c4b5fd; background: color-mix(in srgb, #c4b5fd 10%, var(--dsw-alias-bg-base)); }
    body[data-ds-dark-theme] .asuna-brain-executor { color: var(--dsw-static-blue-300); background: color-mix(in srgb, var(--dsw-static-blue-300) 10%, var(--dsw-alias-bg-base)); }
    body .asuna-collab { border: .5px solid var(--dsw-alias-border-l1); border-radius: var(--dsw-radius-lg, 12px);
      padding: 10px 12px; margin: 8px 0; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
    body .asuna-collab-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px;
      color: var(--dsw-alias-label-secondary); }
    body .asuna-collab-title { font-weight: 500; color: var(--dsw-alias-label-primary); min-width: 0; overflow-wrap: anywhere; }
    body .asuna-collab-bubble { border-left: 3px solid; border-radius: 4px; padding: 4px 10px; min-width: 0;
      background: color-mix(in srgb, currentColor 4%, transparent); }
    body .asuna-collab-character { border-color: #7e22ce; }
    body .asuna-collab-executor { border-color: var(--dsw-static-blue-600); }
    body[data-ds-dark-theme] .asuna-collab-character { border-color: #c4b5fd; }
    body[data-ds-dark-theme] .asuna-collab-executor { border-color: var(--dsw-static-blue-300); }
    body .asuna-collab-bubble .asuna-collab-text { color: var(--dsw-alias-label-primary); }
    body .asuna-collab-clipped { max-height: 9.6em; overflow: hidden; }
    body .asuna-collab-cut { -webkit-mask-image: linear-gradient(to bottom, #000 65%, transparent);
      mask-image: linear-gradient(to bottom, #000 65%, transparent); }
    body .asuna-collab-missed { color: var(--dsw-alias-status-danger, #c00);
      background: color-mix(in srgb, var(--dsw-alias-status-danger, #c00) 10%, var(--dsw-alias-bg-base)); }
    body .asuna-collab-missed-note { margin: 0; font-size: 12px; color: var(--dsw-alias-status-danger, #c00); }
  `;
  // Palette only (pinned DSH version's class): DSH's meter is the character-brain purple, the second
  // instance of the same meter (the action session) the action-brain blue.
  const meterPalette = `
    .JObwrW_fill { stroke: #7e22ce; }
    body[data-ds-dark-theme] .JObwrW_fill { stroke: #c4b5fd; }
    .asuna-action-meter { display: contents; }
    .asuna-action-meter .JObwrW_fill { stroke: var(--dsw-static-blue-600); }
    body[data-ds-dark-theme] .asuna-action-meter .JObwrW_fill { stroke: var(--dsw-static-blue-300); }
  `;
  /** DSH's own ContextMeter, read from the meter it already renders next to this dock. DSH does not
   * export it; when the lookup fails (another DSH revision) the action meter is simply absent. */
  function shippedContextMeter(anchor) {
    for (const element of anchor?.parentElement?.parentElement?.children ?? []) {
      const key = Object.keys(element).find(name => name.startsWith('__reactFiber$'));
      for (let fiber = key && element[key], depth = 0; fiber && depth < 4; fiber = fiber.return, depth++)
        if (typeof fiber.type === 'function' && fiber.type.name === 'ContextMeter' && fiber.memoizedProps?.t)
          return { Meter: fiber.type, t: fiber.memoizedProps.t };
    }
    return null;
  }
  function collabDefinitions() {
    return [{ kind: 'asuna-collab', target: 'chat',
      match: event => event.type === 'asuna/collab' && event.data?.thread
        ? { id: String(event.data.block ?? event.data.thread), role: 'start' } : null,
      start: (_context, match) => ({ anchor: match.event.seq, entries: [match.event.data] }),
      update: (context, match) => context.state.entries.some(entry => entry.id === match.event.data.id) ? context.state
        : { ...context.state, entries: [...context.state.entries, match.event.data] },
      buildViewNode: context => !context.state ? null : ({ key: context.key, kind: 'asuna-collab', id: context.id,
        target: 'chat', anchorSeq: context.state.anchor, location: { kind: 'session' }, visibility: 'visible',
        data: context.state }),
    }];
  }
  /** What a block of a thread reads as: its title, its sessions, its state, how long it has run, and the
   * action brain's work still going on (`live`: the range after its last work row). */
  function threadOf(entries) {
    const open = entries.findLast(entry => entry.kind === 'open');
    const title = entries.find(entry => entry.title)?.title;
    const statuses = entries.filter(entry => entry.kind === 'status');
    const last = entries.at(-1);
    const asked = entries.findLast(entry => entry.kind === 'question');
    const answered = asked && entries.slice(entries.indexOf(asked)).some(entry => entry.kind === 'answer');
    let state = statuses.at(-1)?.state ?? (open ? 'running' : 'queued');
    if (asked && !answered && !['done', 'failed', 'stopped', 'paused'].includes(state)) state = 'waiting';
    // A continuation runs again after a finished or paused run.
    if (['done', 'failed', 'paused'].includes(state) && last && last !== statuses.at(-1) && ['message', 'open'].includes(last.kind)) state = 'queued';
    // The thread went on in a later block, below.
    if (entries.some(entry => entry.kind === 'continued')) state = 'continued';
    // A finished run's result on its way back to her: handing, taken (her turn on it finished) or missed. It may
    // stand in a block of its own (her conversation moved to a new session after the run), so it carries the outcome.
    const lastHandback = entries.findLast(entry => entry.kind === 'handback');
    const after = lastHandback ? entries.slice(entries.indexOf(lastHandback) + 1) : [];
    const handback = lastHandback && state !== 'continued' && entries.indexOf(lastHandback) > entries.indexOf(statuses.at(-1))
      && !after.some(entry => ['message', 'open'].includes(entry.kind)) ? lastHandback : null;
    const outcome = handback?.outcome ?? statuses.findLast(entry => ['done', 'failed'].includes(entry.state))?.state ?? 'done';
    if (handback && !['done', 'failed', 'paused'].includes(state)) state = outcome;
    const started = Date.parse(entries[0]?.at), ended = Date.parse(last?.at);
    const child = open?.child_session_id ?? entries.findLast(entry => entry.child_session_id)?.child_session_id;
    const work = open && entries.slice(entries.indexOf(open)).findLast(entry => entry.kind === 'work');
    const live = state === 'running' && child && (work?.through_seq ?? open?.after_seq) !== undefined
      ? { child, after: work?.through_seq ?? open.after_seq, since: Date.parse(work?.at ?? open.at) } : null;
    return { title, open, child, live, state, handback, outcome, stopped: statuses.findLast(entry => entry.state === 'stopped'),
      // A block of hand-back entries alone holds none of the run, so it has no run time to show.
      elapsed: entries.every(entry => entry.kind === 'handback') ? null
        : Number.isFinite(started) ? (['done', 'failed', 'stopped', 'paused', 'continued'].includes(state) && Number.isFinite(ended) ? ended : Date.now()) - started : null };
  }

  const TOOL_ICONS = { think: 'IconThinkOutlineRegular', recall: 'IconSearchOutlineRegular', delegate: 'IconSendOutlineRegular',
    message_action: 'IconPaperPlaneOutlineRegular', stop_action: 'IconPauseOutlineRegular', answer_action: 'IconQuestionOutlineRegular',
    stay_silent: 'IconMicrophoneOutlineRegular', attach_image: 'IconPaperclipOutlineRegular', write_document: 'IconEditOutlineRegular',
    update_self: 'IconPersonalizationOutlineRegular', understand_person: 'IconUserOutlineRegular', set_policy: 'IconSlidersTwoOutlineRegular',
    feel: 'IconLikeOutlineRegular', plan: 'IconAlarmClockOutlineRegular',
    group_action: 'IconUsersOutlineRegular', promote_memory: 'IconArchiveOutlineRegular', note_idea: 'IconLightOutlineRegular',
    read_ideas: 'IconListPenOutlineRegular', read_report: 'IconFlatListOutlineRegular', review_idea: 'IconChecklistOutlineRegular', visit: 'IconRightUpOutlineRegular',
    ask_character: 'IconQuestionOutlineRegular', report_progress: 'IconInfoOutlineRegular' };
  // The argument that says what a call was about (her own words), and the one shown in full when opened.
  const TOOL_SUMMARY = { think: 'thought', recall: 'query', delegate: 'title', message_action: 'message', stop_action: 'reason',
    answer_action: 'answer', stay_silent: 'reason', attach_image: 'why', write_document: 'doc', update_self: 'target',
    understand_person: 'body', set_policy: 'key', feel: 'why', plan: 'intent', group_action: 'who',
    promote_memory: 'fact', note_idea: 'idea', review_idea: 'why', ask_character: 'question', report_progress: 'note',
    visit: 'topic' };
  const TOOL_BODY = { think: 'thought', delegate: 'brief', message_action: 'message', answer_action: 'answer',
    write_document: 'body', update_self: 'body', understand_person: 'body', note_idea: 'idea', ask_character: 'question',
    report_progress: 'note', promote_memory: 'fact' };
  const parseArgs = raw => { try { const value = JSON.parse(raw ?? ''); return value && typeof value === 'object' ? value : {}; } catch { return {}; } };
  const firstSentence = text => String(text ?? '').split(/(?<=[。！？!?.\n])/)[0].trim();
  const resultText = block => (block?.content ?? []).filter(part => part.type === 'text').map(part => part.text).join('\n');
  const ROLE_TOOLS = Object.keys(TOOL_ICONS);

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
    function Select({ id, label, value, options, onChange, disabled, overridden, onReset, hint, t }) {
      const [open, setOpen] = React.useState(false);
      const selected = options.find(option => option[0] === value);
      return h('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
          h('label', { htmlFor: id }, label), overridden && h(Pill, null, t('settings.overridden')),
          overridden && h(Button, { size: 'sm', disabled, onClick: onReset }, t('settings.reset'))),
        h(Menu, { open: open && !disabled, portal: true, selectedId: value,
          items: options.map(([id, label]) => ({ id, label })), onClose: () => setOpen(false),
          onSelect: value => { onChange(value); setOpen(false); },
          anchor: h(Button, { id, variant: 'outline', 'aria-label': label, 'aria-haspopup': 'menu',
            'aria-expanded': open && !disabled, disabled: disabled || !options.length,
            onClick: () => setOpen(value => !value) },
          selected?.[1] ?? (value ? t('settings.unavailableValue', { value }) : t('settings.choose')),
          h(IconChevronDownOutlineRegular, null)) }),
        hint && h('p', { style: small }, hint));
    }

    const categoryLabel = (t, category) => t('memory.category.' + (DICTIONARY.en['memory.category.' + category] ? category : 'other'));
    function Memory(props) {
      const t = props.t;
      const visible = props.useTabInfo().tab.visible;
      const [category, setCategory] = React.useState('summary'), [offset, setOffset] = React.useState(0);
      const [search, setSearch] = React.useState(''), [query, setQuery] = React.useState('');
      const [composing, setComposing] = React.useState(false);
      const [page, setPage] = React.useState(null), [error, setError] = React.useState('');
      const [selected, setSelected] = React.useState(null), [detail, setDetail] = React.useState(null);
      const [refresh, setRefresh] = React.useState(0);
      React.useEffect(() => {
        if (!visible || composing) return;
        const timer = setTimeout(() => { setQuery(search.trim()); setOffset(0); }, 250);
        return () => clearTimeout(timer);
      }, [visible, search, composing]);
      React.useEffect(() => {
        if (!visible) return;
        const controller = new AbortController(); setPage(null); setError(''); setSelected(null); setDetail(null);
        rpc('memory', { request: { session_id: props.sessionId, category, offset, search: query } }, controller.signal)
          .then(value => { if (!controller.signal.aborted) setPage(value); })
          .catch(error => { if (!controller.signal.aborted) setError(error.message); });
        return () => controller.abort();
      }, [visible, props.sessionId, category, offset, query, refresh]);
      React.useEffect(() => {
        setDetail(null);
        if (!visible || !selected) return;
        const controller = new AbortController();
        rpc('memory', { request: { session_id: props.sessionId, id: selected } }, controller.signal)
          .then(value => { if (!controller.signal.aborted) setDetail(value); })
          .catch(error => { if (!controller.signal.aborted) setError(error.message); });
        return () => controller.abort();
      }, [visible, props.sessionId, selected]);
      const labels = markdownLabels(t);
      const usage = detail => detail.usage && t('memory.usage.' + detail.usage, { time: formatDate(t, detail.context_at, true) });
      return h('section', { style: { ...stack, height: '100%', minHeight: 0, overflow: 'hidden' }, 'aria-label': t('memory.aria') },
        h('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0 } },
        h(Select, { t, label: t('memory.category'), value: category,
          options: memoryKinds
            .map(kind => [kind, t('memory.kind.' + kind)]),
          onChange: value => { setCategory(value); setOffset(0); } }),
        h(Input, { 'aria-label': t('memory.search'), placeholder: t('memory.searchPlaceholder'), value: search, maxLength: 160,
          onChange: event => setSearch(event.target.value),
          onCompositionStart: () => setComposing(true), onCompositionEnd: () => setComposing(false) }),
        h(Button, { size: 'sm', onClick: () => setRefresh(x => x + 1) }, t('memory.refresh')),
        page && h('p', { style: { ...small, margin: 0 } }, say(t, page.scene_title),
          category === 'relation' ? ' · ' + t('memory.subject', { name: page.subject_name }) : '',
          page.linked_scene_titles?.length ? ' · ' + t('memory.linked', { titles: page.linked_scene_titles.map(title => say(t, title)).join(t('memory.separator')) }) : '')),
        h('div', { style: { display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0, overflowY: 'auto' } },
        error && h('p', { role: 'alert' }, error.includes('NOT_BOUND') ? t('memory.notBound') : error),
        !page && !error && h('p', null, t('memory.loading')),
        page?.rows.map(row => h('article', { key: row.id },
          h(DisclosureRow, { icon: h(IconChevronDownOutlineRegular), previewChevron: false,
            title: formatDate(t, row.updated_at, true) || (row.status ? t('memory.status.' + row.status) : categoryLabel(t, row.kind)),
            collapsedContent: h('span', { style: { marginLeft: 8, minWidth: 0, overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--dsw-alias-label-primary)' } }, say(t, row.title)),
            keepContentWhenOpen: true,
            open: selected === row.id, expandable: true,
            expandOnRowClick: true, onToggle: () => setSelected(selected === row.id ? null : row.id) },
            selected === row.id && (detail ? h('div', { style: { padding: '8px 0', color: 'var(--dsw-alias-label-primary)' } },
              h('p', { style: small }, [categoryLabel(t, detail.category), detail.status && t('memory.status.' + detail.status)].filter(Boolean).join(' · ')),
              h(MarkdownText, { text: say(t, detail.body), labels }),
               h(MemoryProvenance, { detail, t }),
               h(GoalControl, { key: 'goal-' + row.id, detail, sessionId: props.sessionId, t, onSaved: () => setRefresh(x => x + 1) }),
               h(MemoryCorrection, { key: row.id, detail, sessionId: props.sessionId, t, onSaved: () => setRefresh(x => x + 1) }),
              usage(detail) && h('p', { style: small }, usage(detail)),
              detail.corrected && h('p', null, t('memory.corrected')),
              h('p', { style: small }, [typeof detail.revision === 'number' ? t('memory.revision', { n: detail.revision }) : '',
                memoryAuthor(detail.speaker || detail.author),
                detail.generated_at ? t('memory.compiled', { time: formatDate(t, detail.generated_at) }) : formatDate(t, detail.occurred_at)].filter(Boolean).join(' · ')),
              detail.sources_truncated && h('p', { style: small }, t('memory.sourcesTruncated')),
              ...detail.sources.map(source => h('blockquote', { key: source._id },
                h('p', { style: small }, [categoryLabel(t, source.category ?? 'source'), memoryAuthor(source.author), say(t, source.scene_title),
                  formatDate(t, source.occurred_at)].filter(Boolean).join(' · ')),
                h(MarkdownText, { text: source.text, labels })))) : h('p', null, t('memory.detailLoading')))),
          selected !== row.id && row.excerpt && h('p', { style: { margin: '4px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, say(t, row.excerpt)),
          (category === 'all' || (row.scene_title && say(t, row.scene_title) !== say(t, page.scene_title))) && h('p', { style: { ...small, margin: 0 } },
            [category === 'all' ? categoryLabel(t, row.kind) : '',
              row.scene_title && say(t, row.scene_title) !== say(t, page.scene_title) ? say(t, row.scene_title) : ''].filter(Boolean).join(' · ')))),
        page && !page.rows.length && h('p', null, query ? t('memory.noMatch') : t('memory.empty'))),
        page && h('div', { style: { display: 'flex', gap: 8, flexShrink: 0 } },
          h(Button, { disabled: offset === 0, onClick: () => setOffset(Math.max(0, offset - 24)) }, t('memory.previous')),
          h(Button, { disabled: page.next_offset === null, onClick: () => setOffset(page.next_offset) }, t('memory.next'))));
    }

    function Settings(props) {
      const saved = React.useSyncExternalStore(subscribe, snapshot);
      return saved.value ? h(SettingsEditor, { initial: saved.value, t: props.t })
        : h('p', null, saved.status === 'unavailable' ? props.t('settings.unavailable') : props.t('settings.loading'));
    }

    function SettingsEditor({ initial, t }) {
      const [status, setStatus] = React.useState(null);
      // Whether each credential the card shows has a value: asked of DSH's credential store, never the value.
      const [credentialState, setCredentialState] = React.useState({});
      const describeCredentials = async refs => {
        if (!refs.length) return {};
        const response = await ctx.remote.credentials.describe(refs);
        const states = response?.ok ? Object.fromEntries(refs.map(ref => [ref, response.value[ref]?.configured === true])) : {};
        setCredentialState(previous => ({ ...previous, ...states }));
        return states;
      };
      const [notice, setNotice] = React.useState(''), [busy, setBusy] = React.useState(false);
      const [persona, setPersona] = React.useState(null);
      const loadPersona = () => rpc('personaSources').then(setPersona).catch(() => setPersona(null));
      React.useEffect(() => { loadPersona(); }, []);
      const runJob = async (job, dryRun) => { setBusy(true); setNotice('');
        try { const result = await rpc('personaJob', { request: { job, dry_run: dryRun } });
          setNotice(t('persona.jobResult', { job, dry: dryRun ? t('persona.runDry') : '', status: result.status,
            code: result.exit_code !== undefined ? t('persona.exitCode', { code: result.exit_code }) : '',
            reason: result.reason ? ' · ' + result.reason : '' }));
          loadPersona(); } catch (error) { setNotice(error.message); } finally { setBusy(false); } };
      const exportDocs = async () => { setBusy(true); setNotice('');
        try { const result = await rpc('personaExport'); setNotice(t('persona.exported', { n: result.exported.length })); }
        catch (error) { setNotice(error.message); } finally { setBusy(false); } };
      const [editor] = React.useState(() => {
        // Labels are read at render (the language may change); fields carry keys and parameters.
        const fields = [], add = (path, label, type = 'text') => fields.push({ path, label, type, field: JSON.stringify(path) });
        // The character route also carries the effort of her relevance gate and of her group turns.
        for (const lane of ['character', 'action']) for (const key of ['provider', 'model', 'reasoningEffort', 'maxTokens',
          ...[]])
          add(['routes', lane, key], { key: 'settings.route', params: { brain: { key: 'brain.' + (lane === 'character' ? 'character' : 'executor') },
            field: { key: 'settings.route.' + key } } }, key === 'maxTokens' ? 'number' : 'choice');
        // Business values use the shipped settings fields. Structured settings
        // retain their JSON type; no second schema editor or settings store.
        for (const [key, value] of Object.entries(initial.deployment ?? {}))
          add(['deployment', key], deploymentLabel(key), typeof value === 'string' ? 'text' : 'json');
        // A new profile has no deployment yet: its required sections appear with a starting value staged
        // (the Mongo URI already pointing at a credential), so the page alone can configure it (ADR-010 M1).
        const starters = [];
        const secretNames = new Set();
        const collect = value => { if (!value || typeof value !== 'object') return;
          if (typeof value.$secret === 'string') secretNames.add(value.$secret);
          else Object.values(value).forEach(collect); };
        collect(initial.deployment);
        // Credentials are write-only controls into DSH's credential store, never settings (ADR-010 D6): one per
        // reference the settings name, and one that stores values for references a new section names.
        for (const key of secretNames) add(['credentials', key], key, 'secret');
        const byId = new Map(fields.map(field => [field.field, field]));
        const flatten = value => Object.fromEntries(fields.flatMap(field => {
          const entry = field.path.reduce((value, key) => value?.[key], value);
          return entry === undefined || field.type.startsWith('secret') ? [] : [[field.field, entry]];
        }));
        const scope = { subscribe, getSnapshot: () => {
          const saved = snapshot();
          return { ...saved, value: flatten(saved.value), base: flatten(saved.base), user: flatten(saved.user) };
        }, mutate: async (ops, revision) => {
          try {
            const edits = ops.map(op => ({ ...op, path: byId.get(op.path[0]).path }));
            await rpc('saveSettings', { ops: edits, revision });
            const response = await ctx.remote.settings.describe();
            if (response.ok) {
              const view = response.value.namespaces.find(row => row.ns === 'soyo-asuna-ui');
              if (view) ctx.configForms.describe().acceptView(view);
            }
            await reloadSettings();
            const current = await rpc('status');
            setStatus(current); setNotice(current.pending ? t('settings.savedPending') : t('settings.savedApplied')); return true;
          } catch (error) { await reloadSettings(); setNotice(error.message); return false; }
        } };
        const store = async values => {
          for (const [ref, value] of Object.entries(values)) {
            const response = await ctx.remote.credentials.set(ref, value);
            if (response && response.ok === false) throw new Error(response.error?.message ?? 'CREDENTIAL_NOT_STORED');
          }
          const states = await describeCredentials(Object.keys(values));
          return Object.keys(values).every(ref => states[ref]);
        };
        const secrets = fields.filter(field => field.type.startsWith('secret')).map(field => ({ field: field.field,
          write: async text => { try {
            if (field.type === 'secret') return await store({ [field.path[1]]: text });
            const value = JSON.parse(text);
            if (!value || Array.isArray(value) || typeof value !== 'object' || Object.entries(value).some(([ref, item]) =>
              typeof item !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(ref))) throw new Error(t('settings.secretMapHint'));
            return await store(value);
          } catch (error) { setNotice(error.message); return false; } } }));
        const model = new SettingsFormModel(scope, fields.filter(field => !field.type.startsWith('secret')).map(field => ({ field: field.field,
          format: value => value === undefined ? '' : field.type === 'json' ? JSON.stringify(value) : String(value),
          parse: text => { try {
            // An empty reasoning choice explicitly uses the provider default;
            // clearing an override would instead re-inherit a previous effort.
            if (EFFORTS.includes(field.path[2])) return { kind: 'set', value: text };
            if (field.type === 'choice') return text ? { kind: 'set', value: text } : undefined;
            if (!text.trim()) return { kind: 'clear' };
            const value = ['json', 'number'].includes(field.type) ? JSON.parse(text) : text;
            if (field.type === 'number' && (!Number.isSafeInteger(value) || value < 1)) return undefined;
            return { kind: 'set', value };
          } catch { return undefined; } } })), secrets);
        return { fields, model, starters, actions: model.actions(), store: model.bind(() => ({ shell: model.shell(),
          fields: Object.fromEntries(fields.map(field => [field.field, model.field(field.field)])) })) };
      });
      const state = React.useSyncExternalStore(editor.store.subscribe, editor.store.getSnapshot);
      const routeValue = (lane, key) => state.fields[JSON.stringify(['routes', lane, key])].text;
      const choices = field => {
        if (field.path[0] === 'channelAdmission') return [['automatic', t('settings.admission.automatic')], ['explicit', t('settings.admission.explicit')]];
        if (field.path[0] === 'persona') return (status?.personas ?? []).map(persona => [persona.id, persona.name || persona.id]);
        const [, lane, key] = field.path, providers = status?.providers ?? [];
        if (key === 'provider') return providers.map(provider => [provider.id, provider.name || provider.id]);
        const provider = providers.find(provider => provider.id === routeValue(lane, 'provider'));
        if (key === 'model') return (provider?.models ?? []).map(model => [model.id, model.name || model.id]);
        const model = provider?.models.find(model => model.id === routeValue(lane, 'model'));
        // DSH's levels for this model, under DSH's own names.
        return model ? [['', t(key === 'reasoningEffort' ? 'settings.providerDefault' : 'settings.routeEffort')],
          ...(model.reasoning?.efforts ?? []).map(effort => [effort.id, effort.name])] : [];
      };
      const choose = (field, value) => {
        editor.actions.edit(field.field, value);
        const [, lane, key] = field.path;
        if (field.path[0] !== 'routes' || !['provider', 'model'].includes(key)) return;
        const provider = status?.providers.find(provider => provider.id === (key === 'provider' ? value : routeValue(lane, 'provider')));
        let model = provider?.models.find(model => model.id === (key === 'model' ? value : routeValue(lane, 'model')));
        if (key === 'provider') {
          if (!model && provider?.models.length === 1) model = provider.models[0];
          editor.actions.edit(JSON.stringify(['routes', lane, 'model']), model?.id ?? '');
        }
        for (const effort of EFFORTS) if (state.fields[JSON.stringify(['routes', lane, effort])]
            && !model?.reasoning?.efforts.some(offered => offered.id === routeValue(lane, effort)))
          editor.actions.edit(JSON.stringify(['routes', lane, effort]), '');
      };
      React.useEffect(() => () => editor.model.dispose(), [editor]);
      React.useEffect(() => {
        const refs = editor.fields.filter(field => field.type === 'secret').map(field => field.path[1]);
        describeCredentials(refs).catch(error => setNotice(error.message));
        return ctx.remote.$on('credentials/reference-updated', ref => {
          if (refs.includes(ref)) describeCredentials([ref]).catch(() => {});
        });
      }, [editor]);
      React.useEffect(() => { for (const [field, text] of editor.starters) editor.actions.edit(field, text); }, [editor]);
      React.useEffect(() => { const controller = new AbortController();
        rpc('status', {}, controller.signal).then(setStatus).catch(error => { if (!controller.signal.aborted) setNotice(error.message); });
        return () => controller.abort(); }, []);
      const activate = async () => { setBusy(true); setNotice('');
        try { setStatus(await rpc('applySettings')); setNotice(t('settings.activated')); }
        catch (error) { setNotice(error.message); } finally { setBusy(false); } };
      const worker = status?.worker;
      return h('section', { style: stack, 'aria-label': t('settings.aria') },
        h('h3', null, 'Bot'),
        h('p', null, status ? t('settings.status', { state: word(t, 'settings.state.', status.lifecycle.state)
            + (status.lifecycle.step ? ' · ' + word(t, 'settings.step.', status.lifecycle.step) : ''),
          database: worker?.database ? word(t, 'settings.database.', worker.database) : t('settings.disconnected') })
          : t('settings.readingStatus')),
        status?.lifecycle.error && h('p', { role: 'alert' }, status.lifecycle.error),
        h(GatewayStatus, { initial: worker?.transport_observation, t }),
        h(ReviewSource, { value: status?.reviewer, t }),
        // A publication that only a Host restart puts into effect is said, never left silent (ADR-021 D4).
        ...(status?.publications ?? []).filter(p => p.state === 'HOST_RESTART_REQUIRED').map(p => h('p', { key: 'restart-' + p.project,
          role: 'status' }, t('settings.restartWaiting', { project: p.project,
            time: p.published_at ? new Date(p.published_at).toLocaleString() : '?' }))),
        h('p', { style: small }, t('settings.note')),
        h(SettingsForm, { state: state.shell, onSave: editor.actions.save, onDiscard: editor.actions.discard,
          labels: { unavailable: t('settings.form.unavailable'), readOnly: t('settings.form.readOnly'),
            saveFailed: t('settings.form.saveFailed'), save: t('settings.form.save'), saving: t('settings.form.saving') } },
          ...editor.fields.map(field => {
            // A valid element id (the field key is JSON, which no selector or label-for can address).
            const props = { key: field.field, id: 'asuna-setting-' + field.path.join('-').replace(/[^A-Za-z0-9_-]/g, '_'), label: say(t, field.label),
              ...state.fields[field.field], disabled: busy || state.shell.saving || !state.shell.writable || status?.lifecycle.state === 'applying' || (status?.reviewer?.route_locked && field.path[0] === 'routes' && field.path[1] === 'action' && ['provider', 'model'].includes(field.path[2])),
              overriddenLabel: t('settings.overridden'), resetLabel: t('settings.reset'),
              invalidLabel: field.type === 'number' ? t('settings.invalidNumber') : t('settings.invalidJson'),
              onEdit: text => editor.actions.edit(field.field, text), onReset: () => editor.actions.resetField(field.field) };
            if (field.type === 'choice') return h(Select, { ...props, t, value: props.text, options: choices(field),
              onChange: value => choose(field, value),
              hint: field.path[0] === 'routes' ? t('settings.routeHint') : undefined });
            return field.type.startsWith('secret') ? h(SettingsSecretField, { ...props, configured: credentialState[field.path[1]] ?? false,
              hint: field.type === 'secret-map' ? t('settings.secretMapHint') : t('settings.secretHint'),
              stateLabel: field.type === 'secret-map' ? t('settings.secretAdd') : credentialState[field.path[1]] ? t('settings.secretSet') : t('settings.secretUnset') })
              : h(SettingsValueField, { ...props, numeric: field.type === 'number',
                hint: field.type === 'json' ? t('settings.jsonHint') : field.path[0] === 'python' ? t('settings.pythonHint') : undefined });
          })),
        status && h('p', { style: small }, [
          t('settings.selfSource', { source: worker?.self_source ? word(t, 'settings.selfSource.', worker.self_source) : t('settings.waiting') }),
          t('settings.channels', { titles: worker?.channel_titles?.join(t('memory.separator')) || t('settings.channelsFallback'),
            state: worker?.integration_state === 'STALE' ? t('settings.transport.stale') : worker?.integration_state === 'UNKNOWN' ? t('settings.transport.unknown') : worker?.channels_active ? t('settings.channelOn', { state: word(t, 'settings.integration.', worker.integration_state) }) : t('settings.channelOff') })
            + (worker?.integration_error ? ' · ' + worker.integration_error : ''),
          t('settings.schedule', { state: worker?.schedules_active ? t('settings.scheduleOn') : t('settings.channelOff') }),
          ...(worker?.sandbox ? [t('settings.sandbox', { state: worker.sandbox.backend === 'none'
            ? t('settings.sandboxNone', { reason: worker.sandbox.reason_code ? word(t, 'settings.sandboxReason.', worker.sandbox.reason_code)
              : worker.sandbox.reason }) : word(t, 'settings.sandbox.', worker.sandbox.backend) })] : [])].join(' · ')),
        status && h('p', { role: 'status' }, status.pending ? t('settings.pending') : t('settings.applied')),
        h('div', { style: { display: 'flex', gap: 8, flexWrap: 'wrap' } },
          h(Button, { disabled: busy || !state.shell.writable || state.shell.dirty || state.shell.saving || status?.lifecycle.state === 'applying', onClick: activate, variant: 'outline' }, t('settings.apply')),
          h(Button, { disabled: busy, onClick: () => rpc('status').then(setStatus).catch(error => setNotice(error.message)) }, t('settings.refresh'))),
        persona && h('section', { style: stack, 'aria-label': t('persona.aria') },
          h('h4', null, t('persona.title', { persona: persona.persona })),
          persona.render && h('p', { role: persona.render.over_budget ? 'alert' : 'status',
            style: persona.render.over_budget ? { color: 'var(--dsw-alias-status-danger, #c00)' } : small },
            t('persona.render', { estimate: persona.render.estimate_tokens, limit: persona.render.limit_tokens ?? t('persona.unlimited') })
              + (persona.render.over_budget ? ' · ' + t('persona.overBudget') : '')),
          h('p', { style: small }, persona.sources.length
            ? t('persona.sources', { list: persona.sources.map(source => t('persona.source', source)).join(t('memory.separator')) })
            : t('persona.noSources')),
          ...persona.jobs.map(job => h('div', { key: job.id, style: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' } },
            h('span', null, t('persona.job', { id: job.id, sources: job.sources.join(t('memory.separator')) })),
            h(Button, { size: 'sm', disabled: busy, onClick: () => runJob(job.id, true) }, t('persona.dryRun')),
            h(Button, { size: 'sm', disabled: busy, variant: 'outline', onClick: () => runJob(job.id, false) }, t('persona.run')))),
          persona.runs.length > 0 && h('p', { style: small }, t('persona.runs', { list: persona.runs.map(run =>
            run.job + ' ' + run.status + (run.dry_run ? t('persona.runDry') : '')).join(t('memory.separator')) })),
          h(Button, { size: 'sm', disabled: busy || !persona.export_configured, onClick: exportDocs },
            persona.export_configured ? t('persona.export') : t('persona.exportUnset'))),
        notice && h('p', { role: 'status' }, notice));
    }

    function AsunaTrigger(props) {
      const source = props.node?.data?.source;
      const shipped = ctx.slots.entries('conversation.chat.node')
        .find(entry => entry.options.key === 'turn-trigger' && entry.component !== AsunaTrigger && entry.component !== SoyoTrigger);
      if (!shipped) return null;
      if (!source?.soyo_ui_trigger || !source.trigger) return h(shipped.component, props);
      const title = t('trigger.' + source.trigger);
      return h(shipped.component, { ...props, t: (key, params) => key === 'message.trigger.request' ? title : props.t(key, params) });
    }
    ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({
      name: 'conversation.chat.node', key: 'asuna-stage', locale: NS,
    }, props => stageLabel(props.t, props.node.data)
      ? h(Pill, { className: brainClass(props.node.data.lane) }, stageLabel(props.t, props.node.data)) : null));
    const injectChat = sessionId => ({ hooks: { chat: ctx.uiConversation.binding(ctx.sessions.binding(sessionId)).target('chat') } });
    function ActiveStage(props) {
      const stage = props.useChat(snapshot => {
        const timeline = snapshot?.timeline;
        const turn = timeline?.turns.get(timeline.turnOrder.at(-1));
        return turn?.status === 'open' ? turn.steps.at(-1)?.data.get('asuna-stage') : undefined;
      });
      return stageLabel(props.t, stage) ? h(Pill, { className: brainClass(stage.lane) }, stageLabel(props.t, stage)) : null;
    }
    ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({
      name: 'conversation.session.header.actions', id: 'asuna-active-stage', order: 50, inject: injectChat, locale: NS,
    }, ActiveStage));    function BrainMeters({ sessionId }) {
      const [state, setState] = React.useState(null), [shipped, setShipped] = React.useState(null);
      const anchor = React.useRef(null);
      React.useEffect(() => {
        if (!sessionId) return undefined;
        let alive = true;
        const load = () => rpc('brainContext', { sessionId }).then(value => {
          if (!alive) return;
          setState(value);
          setShipped(current => current ?? shippedContextMeter(anchor.current));
        }).catch(() => {});
        load();
        const timer = setInterval(load, 5000);
        return () => { alive = false; clearInterval(timer); setState(null); };
      }, [sessionId]);
      const action = state?.action;
      return h('span', { ref: anchor, className: 'asuna-action-meter' },
        state && h('style', null, meterPalette),
        action && shipped && h(shipped.Meter, { useProjection: key => action[key], t: shipped.t }));
    }
    ctx.slots.inject('conversation.composer.dock', () => ctx.slots.register({
      name: 'conversation.composer.dock', id: 'asuna-brain-meters', order: 100 }, BrainMeters));

    const inlineChat = () => ctx.slots.snapshot('factory:conversation.chat.content').length > 0;
    const openSubagent = (child, parent) => ctx.sidebarRight.openResource('dsh-resource://subagentchat/session/'
      + encodeURIComponent(child) + '?' + new URLSearchParams({ parent, mode: 'one-shot' }),
      { kind: 'subagentchat', preferNewPane: true });
    function Work(props) {
      if (inlineChat()) return h(InlineWork, props);
      const { entry, parent, t } = props;
      return h(Button, { size: 'sm', variant: 'ghost', onClick: () => openSubagent(entry.child_session_id, parent) },
        t('collab.open'));
    }
    /** The action session's own records for one stretch of work, as DSH renders them (a fragment). */
    function InlineWork(props) {
      const { entry, parent } = props;
      const [reference, setReference] = React.useState(null), [error, setError] = React.useState('');
      React.useEffect(() => {
        const controller = new AbortController();
        const target = { parentSessionId: parent, childSessionId: entry.child_session_id, mode: 'unknown' };
        const ref = ctx.sessions.retain(target, { source: 'asunaCollab', signal: controller.signal });
        ref.ready.then(() => { if (!controller.signal.aborted) setReference(ref); })
          .catch(error => { if (!controller.signal.aborted) setError(error.message); });
        return () => { controller.abort(); ref.release(); };
      }, [entry.child_session_id, parent]);
      return reference ? h(props.SessionProvider, { session: reference },
        props.renderSlot('asuna.collab.work', { owner: { node: { data: entry } } }))
        : h('p', { role: error ? 'alert' : 'status', style: small }, error || props.t('collab.loading'));
    }
    const workKinds = ['turn-process', 'assistant-step', 'tool-call', 'turn-error', 'turn-max-tokens',
      'model-retry', 'compaction', 'manual-compaction', 'command'];
    function WorkFragment(props) {
      const range = props.owner.node.data;
      return props.renderFactorySlot('conversation.chat.content', { variant: 'fragment', kinds: workKinds,
        after: range.after_seq, through: range.through_seq });
    }
    /** Whether an element's text is really cut off as rendered (vertically or on one line), measured again when its
     * size changes. A length guessed from characters is wrong at some width: it offered a toggle with nothing more to
     * show, or hid text with no way to read it. */
    function useCut(ref, deps, active = true) {
      const [cut, setCut] = React.useState(false);
      React.useLayoutEffect(() => {
        const element = ref.current;
        if (!element || !active) return undefined;
        const measure = () => setCut(element.scrollHeight > element.clientHeight + 1 || element.scrollWidth > element.clientWidth + 1);
        measure();
        const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null;
        observer?.observe(element);
        return () => observer?.disconnect();
      }, [...deps, active]);
      return cut;
    }
    function Bubble({ entry, t }) {
      const lane = entry.from === 'action' ? 'executor' : 'character';
      const [all, setAll] = React.useState(false);
      const text = String(entry.text ?? '');
      // The button shows only when the clipped text is really cut off, as rendered.
      const box = React.useRef(null);
      const cut = useCut(box, [text], !all);
      return h('div', { className: 'asuna-collab-bubble asuna-collab-' + lane },
        h('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
          h(Pill, { className: brainClass(lane) }, t('brain.' + lane)),
          entry.kind === 'progress' && h('span', { style: small }, t('collab.progress'))),
        // A cut can fall between paragraphs and look complete: the clipped text fades out where it is cut.
        h('div', { ref: box, className: 'asuna-collab-text' + (all ? '' : ' asuna-collab-clipped' + (cut ? ' asuna-collab-cut' : '')) },
          h(MarkdownText, { text, labels: markdownLabels(t) })),
        (cut || all) && h(Button, { size: 'sm', variant: 'ghost', onClick: () => setAll(value => !value) },
          all ? t('collab.less') : t('collab.more')));
    }
    function WorkRow(props) {
      const { entry, t } = props;
      const [open, setOpen] = React.useState(false);
      return h(DisclosureRow, { icon: h(IconChevronDownOutlineRegular), previewChevron: false,
        title: t('collab.work', { duration: duration(t, entry.duration_ms ?? 0) }),
        collapsedContent: h('span', { style: { marginLeft: 8, ...small } },
          t(entry.tool_calls === 1 ? 'collab.call' : 'collab.calls', { n: entry.tool_calls ?? 0 })),
        keepContentWhenOpen: true, open, expandable: true, expandOnRowClick: true, onToggle: () => setOpen(value => !value) },
        open && h(Work, { ...props }));
    }
    /** The action brain's work still going on: its native records after the last work row, as they come. */
    function LiveWorkRow(props) {
      const { live, t } = props;
      const [open, setOpen] = React.useState(false), now = Date.now();      // the thread re-renders while running
      return h(DisclosureRow, { icon: h(IconChevronDownOutlineRegular), previewChevron: false,
        title: t('collab.working', { duration: duration(t, Math.max(0, now - (Number.isFinite(live.since) ? live.since : now))) }),
        collapsedContent: h('span', { style: { marginLeft: 8, ...small } }, t('collab.watch')),
        keepContentWhenOpen: true, open, expandable: true, expandOnRowClick: true, onToggle: () => setOpen(value => !value) },
        open && h(Work, { ...props, entry: { child_session_id: live.child, after_seq: live.after } }));
    }
    function CollabThread(props) {
      const t = props.t, { entries } = props.node.data;
      const thread = threadOf(entries);
      // While the thread goes on, its clock and the live work row's tick together.
      const [, tick] = React.useState(0);
      React.useEffect(() => {
        if (!['running', 'queued', 'waiting'].includes(thread.state)) return undefined;
        const timer = setInterval(() => tick(count => count + 1), 15000);
        return () => clearInterval(timer);
      }, [thread.state]);
      const parent = thread.open?.parent_session_id ?? props.sessionId;
      const child = thread.child;
      const openAside = child && parent ? () => openSubagent(child, parent) : null;
      return h('section', { className: 'asuna-collab', 'aria-label': t('collab.header', {
        character: t('brain.character'), action: t('brain.executor') }) },
        h('div', { className: 'asuna-collab-head' },
          h('span', null, t('collab.header', { character: t('brain.character'), action: t('brain.executor') }), ' · '),
          h('span', { className: 'asuna-collab-title' }, thread.title || t('collab.untitled')),
          thread.handback
            ? h(Pill, { className: thread.handback.state === 'missed' ? 'asuna-collab-missed' : undefined },
              t('collab.handback.' + thread.handback.state + (thread.handback.state === 'handing' && thread.handback.short ? 'Short' : ''),
                { outcome: t('collab.outcome.' + thread.outcome) }))
            : h(Pill, null, t('collab.state.' + thread.state)),
          thread.elapsed !== null && h('span', { style: small }, duration(t, thread.elapsed)),
          openAside && h(Button, { size: 'sm', variant: 'ghost', onClick: openAside }, t('collab.open'))),
        ...entries.filter(entry => entry.kind !== 'open' && entry.kind !== 'continued').map(entry =>
          entry.kind === 'handback' ? entry === thread.handback && entry.state === 'missed'
              && h('p', { key: entry.id, role: 'status', className: 'asuna-collab-missed-note' },
                entry.final ? t('collab.missed.final')
                  : t('collab.missed.' + (entry.cause ?? 'report'), { error: entry.error ?? '' }) + t('collab.missed.retry'))
            : entry.kind === 'work' ? h(WorkRow, { key: entry.id, entry, t, parent, SessionProvider: props.SessionProvider,
              renderSlot: props.renderSlot })
            : entry.kind === 'status' ? (entry.state === 'stopped' ? h('p', { key: entry.id, style: small },
              t('collab.stopped', { reason: entry.reason ?? '' }))
              : entry.state === 'paused' && entry === entries.at(-1) && h('p', { key: entry.id, style: small }, t('collab.paused')))
            : h(Bubble, { key: entry.id, entry, t })),
        thread.live && h(LiveWorkRow, { key: 'live:' + thread.live.after, live: thread.live, t, parent,
          SessionProvider: props.SessionProvider, renderSlot: props.renderSlot }));
    }
    function RoleToolRow(props) {
      const t = props.t, name = props.toolName;
      const disclosure = props.useDisclosure();
      const raw = props.phase === 'start' ? props.block.argsRaw : props.phase === 'result' ? props.block.call?.argsRaw : '';
      const args = parseArgs(raw);
      const refused = props.phase === 'result' && props.block.isError;
      const said = args[TOOL_SUMMARY[name]];
      const summary = name === 'think' ? firstSentence(said) : typeof said === 'string' ? said : said === undefined ? '' : JSON.stringify(said);
      // A call whose only text is its summary (stay_silent's reason, feel's why…) opens to that text in full when
      // the one-line row really cuts it off at this width; a call with a body opens to the body.
      const line = React.useRef(null);
      const cut = useCut(line, [summary], !disclosure.expanded);       // measured while closed; kept while open
      const body = typeof args[TOOL_BODY[name]] === 'string' ? args[TOOL_BODY[name]]
        : name !== 'think' && typeof said === 'string' && cut ? said : '';
      const result = props.phase === 'result' ? resultText(props.block) : '';
      const Icon = primitives[TOOL_ICONS[name]] ?? primitives.IconInfoOutlineRegular;
      const detail = [body && h(MarkdownText, { key: 'body', text: body, labels: markdownLabels(t) }),
        refused && h('p', { key: 'refused', style: { ...small, color: 'var(--dsw-alias-state-error-primary)' } }, t('tool.refused') + ' · ' + result)]
        .filter(Boolean);
      return h(DisclosureRow, { icon: h(Icon), previewChevron: false,
        title: t('tool.' + name),
        // DSH's own row text: the secondary size, a dot between the title and what the call was about.
        collapsedContent: h('span', { ref: line, style: { minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          fontSize: 'var(--dsh-content-font-size-secondary, 13px)',
          ...(refused ? { color: 'var(--dsw-alias-state-error-primary)' } : {}) } },
          h('span', { 'aria-hidden': true, style: { margin: '0 6px', opacity: .6 } }, '·'),
          props.phase === 'preparing' ? t('tool.preparing') : refused ? t('tool.refused') : summary),
        keepContentWhenOpen: true, open: disclosure.expanded, expandable: detail.length > 0,
        expandOnRowClick: true, onToggle: disclosure.toggle }, ...detail);
    }

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
