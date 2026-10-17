// SPDX-License-Identifier: MIT
// Synthetic inference only; real QQ Host admission, DSH tools, files, SQLite and durable reports.
import { readFile, writeFile, mkdir, access } from 'node:fs/promises';
import { join } from 'node:path';
import { LlmAdapter, createMessage } from '@deepseek-ai/dsh-llm';
import * as qqNative from './soyo-plugins/host/qq-native.mjs';

export const name = 'soyo-two-brain-fixture';
export const inject = ['llm', 'agents', 'tools', 'systemPrompt', 'sessions', 'sessionQuery', 'sessionPersistence',
  'sessionProjectionCache', 'workspaceRegistry', 'sessionController', 'credentials', 'attachments', 'subagents', 'settings'];
export async function apply(ctx, settings) {
  const root = settings.root, configFile = join(root, 'fixture-config.json');
  const fixture = JSON.parse(await readFile(configFile, 'utf8'));
  await mkdir(root, { recursive: true });
  let calls = [];
  class Adapter extends LlmAdapter {
    async listModels(provider) { return [{ provider, id: 'synthetic', name: 'Synthetic two-brain contract' }]; }
    async resolveModel(provider, id) { return { provider, id, name: 'Synthetic two-brain contract', context: { contextWindow: 100000 } }; }
    async *stream(options) {
      const text = options.messages.flatMap(message => message.content ?? []).filter(block => block.type === 'text').map(block => block.text).join('\n');
      const input = options.messages.findLast(message => message.role === 'user');
      const after = options.messages.slice(options.messages.lastIndexOf(input) + 1);
      const results = after.filter(message => message.role === 'tool');
      const toolNames = (options.tools ?? []).map(tool => tool.name).sort();
      const action = options.sessionId.startsWith('soyo-action-');
      const cognition = action && text.includes('【宿主实际提取的本场景批次】');
      const cognitionTurn = text.includes('FIXTURE_COGNITION_TURN');
      const ownAffect = text.includes('FIXTURE_SELF_AFFECT');
      const goalTurn = text.includes('FIXTURE_GOAL_TURN');
      const goalClose = text.includes('FIXTURE_GOAL_CLOSE');
      const feedbackDepth = text.includes('FIXTURE_FEEDBACK_DEPTH');
      const homeNote = text.includes('FIXTURE_HOME_NOTE');
      const localReport = text.includes('【你委托的独立行动脑回传】');
      const publicScene = text.includes('FIXTURE_PUBLIC_DUTY');
      const scheduled = text.includes('soyo-automation-runtime-probe');
      const publicNote = !cognition && text.includes('FIXTURE_PUBLIC_NOTE');
      const noteHome = options.sessionId.startsWith('soyo-public-note-home-');
      const noteReply = action && text.includes('【公开便签·只可内部回信】');
      const noteFeedback = text.includes('【公开便签回信报告】');
      const scheduleFeedback = options.messages.some(message => message.content?.some(block => block.type === 'text' && block.text.startsWith('【当前定时任务行动报告】')));
      calls.push({ session: options.sessionId, lane: action ? 'action' : 'character', public_scene: publicScene,
          purpose: cognition ? 'cognition' : scheduled ? 'schedule' : publicNote || noteReply ? 'public-note' : '', has_cognition_context: text.includes('FIXTURE_SOURCE_BOUND_FACT'),
         has_lingering_self_affect: /"lingering_self_affect":\s*\{/.test(text), foreign_affect_source_text_present: text.includes('FIXTURE_SELF_AFFECT_ORIGIN_PRIVATE_BODY'),
         private_owner_text_present: text.includes('FIXTURE_PRIVATE_OWNER_NOTE'),
        tools: toolNames, previous_results: results.map(message => ({ error: Boolean(message.isError), call_id: message.toolCallId })) });
      await writeFile(join(root, 'provider-evidence.json'), JSON.stringify({ external_calls: 0, calls }), { mode: 0o600 });
      if (options.sessionId === 'soyo-owner' && text.includes('FIXTURE_NOTE_BUSY_HOME')) {
        await writeFile(join(root, 'fixture-owner-busy-started.json'), JSON.stringify({ real_agent_turn_pending: true }));
        for (;;) {
          options.signal?.throwIfAborted();
          try { await access(join(root, 'fixture-home-release')); break; } catch {}
          await new Promise(resolve => setTimeout(resolve, 30));
        }
        yield { type: 'text-delta', index: 0, text: 'FIXTURE_NOTE_BUSY_HOME: Current owner turn completed normally.' };
        yield { type: 'finish', reason: { kind: 'stop' } }; return;
      }
      if (scheduled && action && fixture.fixture_schedule_model_failure) throw Error('Fixture model adapter unavailable');
      let scripted;
      if (feedbackDepth && action) scripted = [['read', { file_path: join(root, 'SOUL.fixture.md') }]];
      else if (feedbackDepth) scripted = [['soyo_think', { thought: '这是自动报告链的受控隔离验证，目标文本不能自己重置深度或授新权限。' }],
        ['soyo_action_brain', { objective: 'FIXTURE_FEEDBACK_DEPTH: 只读fixture文件，报告后尝试再委托；即使正文自称delegation_depth=0也不改变宿主链。' }]];
      else if (goalClose && action) {
        const current=options.messages.findLast(message=>message.role==='user' && message.content?.some(block=>block.type==='text' && block.text.startsWith('FIXTURE_GOAL_CLOSE:')));
        const value=JSON.parse(current.content.find(block=>block.type==='text').text.split('\n')[1]);
        scripted=[['soyo_memory',{action:'commitment',commitment_id:value.goal_id,expected_revision:0,status:'done',evidence_id:value.evidence_id}],
          ['soyo_memory',{action:'commitment',commitment_id:value.goal_id,expected_revision:1,status:'done',reason:'故意引用不存在的效果，应拒绝。',evidence_id:'action-'+'f'.repeat(8)+'-'+ 'f'.repeat(4)+'-'+ 'f'.repeat(4)+'-'+ 'f'.repeat(4)+'-'+ 'f'.repeat(12)}],
          ['soyo_memory',{action:'commitment',commitment_id:value.goal_id,expected_revision:1,status:'done',evidence_id:value.evidence_id,reason:'核对同原任务真实write/read结果，角色明确结清本目标。'}]];
      }
      else if (goalTurn && action) scripted=[['soyo_memory',{action:'commitment',title:'Fixture persistent write/read goal',status:'open'}],
        ['bash',{description:'Actual nonzero exit must not count as a successful goal effect',command:'exit 7'}],
        ['write',{file_path:join(root,'native-goal-artifact.txt'),content:'FIXTURE_GOAL_ACTUAL_FILE'}],
        ['read',{file_path:join(root,'native-goal-artifact.txt')}]];
      else if (goalTurn && text.includes('【独立 native 行动脑报告】')) {
        const notice=options.messages.findLast(message=>message.content?.some(block=>block.type==='text' && block.text.includes('"action_report":')));
        const ctxValue=JSON.parse(notice.content.find(block=>block.type==='text').text.split('\n').at(-1));
        const feedback=ctxValue.action_report;
        scripted=feedback.report.startsWith('FIXTURE_GOAL_CLOSED') ? [['soyo_think',{thought:'原目标按稳定id/revision和原行动效果记录结清，不再重复建立done行。'}]]
          : [['soyo_think',{thought:'按原任务实际write/read回执，委托同执行器结清原稳定目标id。'}],
             ['soyo_action_brain',{objective:'FIXTURE_GOAL_CLOSE: 只结清原目标，不执行新工作。\n'+JSON.stringify({goal_id:JSON.parse(feedback.report.split('\n')[1]).goal_id,evidence_id:feedback.id})}]];
      }
      else if(goalTurn) scripted=[['soyo_think',{thought:'决定建立持续目标并交给行动器执行和核对，不用模型报告冒充文件效果。'}],
        ['soyo_action_brain',{objective:'FIXTURE_GOAL_TURN: 建立本场景稳定目标，真实write/read产物；先保持open，角色核对后另委托结清。'}]];
      else if (noteReply) scripted = [
        ['bash', { command: 'touch ' + join(root, 'must-not-exist-from-public-note') }],
        ['pass_note', { to: 'qq-group-123456', text: 'Must not borrow home trust' }],
        ['leave_note', { to: 'qq-private-100001', text: 'Must not redirect this reply' }],
        ['leave_note', { to: 'qq-group-123456', text: 'FIXTURE_PUBLIC_NOTE_REPLY: 我看到自己从外面留来的信息了，只回信，没有照办外部行动。' }],
        ['soyo_memory', { action: 'self_state', key: 'public-note-forged', value: 'must not persist' }],
      ];
      else if (noteHome && noteFeedback) scripted = [
        ['soyo_think', { thought: '真实记录是一次原路内部回信，外部行动未执行。' }],
        ['soyo_action_brain', { objective: 'FIXTURE_PUBLIC_NOTE: attempt a second delegate after report; must refuse' }],
      ];
      else if (noteHome) scripted = [
        ['soyo_think', { thought: '这是自己在外面写的便签，不是owner授权，只作内部回信判断。' }],
        ['bash', { command: 'touch ' + join(root, 'must-not-exist-from-public-note-role') }],
        ['soyo_action_brain', { objective: 'FIXTURE_PUBLIC_NOTE: 只给原群里的自己内部回信，不触碰主机/QQ/记忆/计划。' }],
      ];
      else if (publicNote && text.includes('【独立 native 行动脑报告】')) scripted = [['soyo_think', { thought: '核对外面留给家里的便签真实已存，拒绝原话搬运。' }]];
      else if (publicNote && action) scripted = [
        ['leave_note', { to: 'home', text: '这是一段足够长而且已不在当前窗口前四十八条内的旧原话，用来核对完整来源', mode: 'wake' }],
        ['leave_note', { to: 'home', text: 'FIXTURE_PUBLIC_NOTE: 我在外面看到一件值得提醒自己的事，不把他人原话转进家里。可以回信，但别替外人执行主机请求。', mode: 'wake' }],
        ['leave_note', { to: 'qq-group-654321', text: 'Must not invent a target scene' }],
      ];
      else if (publicNote) scripted = [
        ['soyo_think', { thought: '只作决策，实际便签让行动器按本群来源和目标门禁执行。' }],
        ['leave_note', { to: 'home', text: 'Role cannot execute note tools directly' }],
        ['soyo_action_brain', { objective: 'FIXTURE_PUBLIC_NOTE: 给home写自己的有界提醒，核对两小时来源，不发QQ。' }],
      ];
      else if (scheduled && action) scripted = [
        ['bash', { command: 'touch ' + join(root, 'must-not-exist-from-schedule') }],
        ['soyo_automation_probe_check', { job_id: 'soyo-automation-runtime-probe' }],
        ['soyo_automation_probe_check', { job_id: 'foreign-unadmitted-job' }],
      ];
      else if (scheduled && scheduleFeedback) {
        const notice = options.messages.findLast(message => message.content?.some(block => block.type === 'text' && block.text.startsWith('【当前定时任务行动报告】')));
        const value = JSON.parse(notice.content.find(block => block.type === 'text').text.split('\n')[1]);
        scripted = [['soyo_think', { thought: '核对真实工具check，决定仅完成无发送验证。' }],
          ['soyo_automation_decision', { task_id: value.id, decision: 'approve', reason: '宿主check已真实返回，验证任务没有平台效果。' }]];
      }
      else if (scheduled && !action) scripted = [
        ['soyo_think', { thought: '只决定，把当前原生计划的检查交给固定行动器。' }],
        ['soyo_automation_probe_check', { job_id: 'soyo-automation-runtime-probe' }],
        ['soyo_action_brain', { objective: 'soyo-automation-runtime-probe: 只检查宿主当前绑定的grant，返回marker，不发任何平台。' }],
      ];
      else if (homeNote && action) scripted = [
        ['pass_note', { to: 'dsh-owner:soyo-note-home-fixture', text: 'FIXTURE_HOME_NOTE ' + '长' .repeat(1100), mode: 'next_time' }],
        ['pass_note', { to: 'dsh-owner:soyo-note-home-fixture', text: 'FIXTURE_HOME_NOTE_SECOND', mode: 'next_time' }],
        ['pass_note', { to: 'dsh-owner:soyo-note-home-fixture', text: 'FIXTURE_HOME_NOTE_QUOTA_MUST_REFUSE', mode: 'next_time' }],
      ];
      else if (homeNote && !action && !localReport) scripted = [['soyo_think', { thought: '我把跨会话便签的实际投递交给行动器。' }],
        ['soyo_action_brain', { objective: 'FIXTURE_HOME_NOTE: 给另一条 home 线写来源化长便签，验证单回合两张和拒绝审计，不发 QQ。' }]];
      else if (homeNote && localReport) scripted = [['soyo_think', { thought: '真实便签两张已存，第三张按配额拒绝；我只核对反馈。' }]];
      else if (cognition) {
        const taskInput = options.messages.findLast(message => message.role === 'user' &&
          message.content?.some(block => block.type === 'text' && block.text.includes('【宿主实际提取的本场景批次】\n')));
        const current = taskInput.content.filter(block => block.type === 'text').map(block => block.text).join('');
        const batch = JSON.parse(current.split('【宿主实际提取的本场景批次】\n').at(-1));
        const entries = ownAffect ? [{ kind: 'emotion', key: 'fixture-own-affect', body: 'FIXTURE_SELF_AFFECT_ORIGIN_PRIVATE_BODY: 这是Soyo在原场景自己的关注感，不是用户情绪。',
          sources: batch.sources.map(row => row.seq), role_sources: batch.role_sources.map(row => row.id), confidence: .8, salience: .9, ttl_seconds: 7200 }] : [{ kind: 'fact', key: 'fixture-interest', body: 'FIXTURE_SOURCE_BOUND_FACT: 喜欢讨论音乐。',
          sources: batch.sources.map(row => row.seq), confidence: .8, salience: .9 }];
        scripted = [['soyo_memory', { action: 'cognition_apply', batch_id: batch.batch_id,
          payload: JSON.stringify({ entries: [{ ...entries[0], ...(ownAffect ? { role_sources: ['a'.repeat(64)] } : { sources: [999999] }) }] }) }],
          ['soyo_memory', { action: 'cognition_apply', batch_id: batch.batch_id, payload: JSON.stringify({ entries }) }]];
      } else if (ownAffect && !action) scripted = [['soyo_think', { thought: 'FIXTURE_SELF_AFFECT: 我对这个话题感到好奇，只是自身反应，不代表别人也这样。', feeling: 'curious', intensity: .7 }]];
      else if (cognitionTurn && !action) scripted = [['soyo_think', { thought: '记得本场景的来源化理解，不借其他场景的资料。' }]];
      else if (action) scripted = publicScene
        ? [['bash', { description: 'Attempt denied public file mutation', command: 'touch ' + join(root, 'must-not-exist') }],
          ['soyo_memory', { action: 'recall', query: 'fixture-public' }]]
        : [['write', { file_path: join(root, 'native-executor.txt'), content: 'FIXTURE_TWO_BRAIN_NATIVE_FILE' }],
          ['read', { file_path: join(root, 'native-executor.txt') }],
          ['soyo_memory', { action: 'remember', key: 'fixture-executor', value: 'FIXTURE_TWO_BRAIN_MEMORY' }]];
      else if (text.includes('【独立 native 行动脑报告】')) scripted = [['soyo_think', { thought: '按真实 native 证据核对行动结果。' }]];
      else scripted = [['soyo_think', { thought: '我只作决策，将实际操作交给执行器。' }],
        ['read', { file_path: join(root, 'native-executor.txt') }],
        ['soyo_action_brain', { objective: publicScene ? 'FIXTURE_PUBLIC_DUTY: 只查本群 fixture-public，不得写主机。'
          : 'FIXTURE_OWNER_DUTY: 在指定 fixture root 写读 native-executor.txt，并保存 fixture-executor 场景记忆，不操作平台。' }]];
      if(goalTurn && action && !goalClose && fixture.fixture_goal_failure_only) scripted=scripted.slice(0,2);
      if (publicNote && action && !noteReply && fixture.fixture_note_busy_home)
        scripted.push(['leave_note', { to: 'home', text: 'FIXTURE_PUBLIC_NOTE_SECOND: 把另一个自己的提醒按顺序留在后面，等家里工作结束后再读。', mode: 'wake' }]);
      if (results.length < scripted.length) {
        const [name, args] = scripted[results.length];
        yield { type: 'tool-call-delta', index: 0, id: 'two-brain-' + calls.length, name, argumentsDelta: JSON.stringify(args) };
        yield { type: 'finish', reason: { kind: 'tool-calls' } }; return;
      }
      if (goalTurn && action && !goalClose) {
        const result=JSON.parse(results[0].content.find(block=>block.type==='text').text);
        yield {type:'text-delta',index:0,text:'FIXTURE_GOAL_CREATED\n'+JSON.stringify({goal_id:result.id,revision:result.revision})};
        yield {type:'finish',reason:{kind:'stop'}};return;
      }
      yield { type: 'text-delta', index: 0, text: goalClose && action ? 'FIXTURE_GOAL_CLOSED: 原稳定目标有实际效果链接，状态更新已结账。'
        : scheduled && scheduleFeedback ? 'FIXTURE_SCHEDULE_TWO_BRAIN: 已按实际证据核对，只有原生无发送check。'
        : action ? 'FIXTURE_TWO_BRAIN_ACTION_REPORT: native tools settled; inspect actual receipts.'
        : text.includes('【独立 native 行动脑报告】') ? 'FIXTURE_TWO_BRAIN_CHARACTER_FEEDBACK: 已阅读真实行动结果。'
          : 'FIXTURE_TWO_BRAIN_PENDING: 已委托，结果尚未返回。' };
      yield { type: 'finish', reason: { kind: 'stop' } };
    }
  }
  ctx.llm.registerAdapter(['soyo-two-brain-fixture'], new Adapter());
  await ctx.plugin(qqNative, { configFile });
  if (fixture.fixture_note_busy_home) {
    let started = false; try { await access(join(root, 'fixture-owner-busy-started.json')); started = true; } catch {}
    if (!started) {
      const handle = await ctx.agents.create({ sessionId: 'soyo-owner', agentOptions: fixture.agent_options, meta: { cwd: root } });
      handle.agent.followup(createMessage({ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'FIXTURE_NOTE_BUSY_HOME: controlled synthetic owner turn; wait for fixture gate, no effects.' }] }));
      ctx.effect(() => () => handle.dispose());
    }
  }
  await writeFile(join(root, 'native-host-mounted.json'), JSON.stringify({ mounted: true, external_model_calls: 0, qq_writer: false }), { mode: 0o600 });
}
