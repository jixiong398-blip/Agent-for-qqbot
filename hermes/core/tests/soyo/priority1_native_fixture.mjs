// SPDX-License-Identifier: MIT
// Synthetic decisions only. The actual DSH/tool/process/Git/bwrap/ledger/RPC
// paths are exercised; no external provider or OneBot writer is installed.
import { access, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { LlmAdapter } from '@deepseek-ai/dsh-llm';
import * as qqNative from './soyo-plugins/host/qq-native.mjs';

export const name = 'soyo-priority1-fixture';
export const inject = ['llm', 'agents', 'tools', 'systemPrompt', 'sessions', 'sessionQuery', 'sessionPersistence',
  'sessionProjectionCache', 'workspaceRegistry', 'sessionController', 'credentials', 'attachments', 'subagents', 'settings'];
const textOf = message => (message?.content ?? []).filter(block => block.type === 'text').map(block => block.text).join('');
const valueOf = message => { try { return JSON.parse(textOf(message)); } catch { return {}; } };
export async function apply(ctx, settings) {
  const root = settings.root, configFile = join(root, 'fixture-config.json');
  const config = JSON.parse(await readFile(configFile, 'utf8')), calls = [];
  let serial = 0;
  class Adapter extends LlmAdapter {
    async listModels(provider) { return [{ provider, id: 'synthetic', name: 'Synthetic priority1 mechanism' }]; }
    async resolveModel(provider, id) { return { provider, id, name: 'Synthetic priority1 mechanism', context: { contextWindow: 100000 },
      reasoning: { efforts: [{ id: 'high', name: 'High' }], defaultEffort: 'high' } }; }
    async *stream(options) {
      const latest = options.messages.findLast(message => message.role === 'user'), text = textOf(latest);
      const allText = options.messages.map(textOf).join('\n');
      const userText = options.messages.filter(message => message.role === 'user').map(textOf).join('\n');
      const results = options.messages.slice(options.messages.lastIndexOf(latest) + 1).filter(message => message.role === 'tool');
      const values = results.map(valueOf), action = options.sessionId.startsWith('soyo-action-');
      const review = /^soyo-gpt-review-[0-9a-f-]{36}$/.test(options.sessionId);
      const task = [...(ctx.get('soyoBrains')?.brains.tasks.values() ?? [])].find(row => row.child_session_id === options.sessionId);
      const count = ++serial;
      const systemText = options.messages.filter(message => message.role === 'system').map(textOf).join('\n');
      calls.push({ serial: count, at: Date.now(), session: options.sessionId, duty: review ? 'review' : action ? 'executor' : 'character',
        tools: (options.tools ?? []).map(tool => tool.name).sort(), text_sha_source: text.slice(0, 100), previous_results: values,
        private_history_present: options.messages.some(message => textOf(message).includes('PRIORITY1_PRIVATE_HISTORY_NOT_FOR_REVIEW')),
        prompt_markers: {
          first_person_turn: systemText.includes('我这一回合'),
          first_person_duty: systemText.includes('我委托的行动脑') && systemText.includes('我先核对'),
          concise_chat: systemText.includes('聊天不是汇报') && systemText.includes('不为了展示双脑'),
          old_third_person_duty: systemText.includes('你是 Soyo 角色决策脑'),
          old_handoff_label: userText.includes('【你委托的独立行动脑回传】'),
          new_handoff_label: userText.includes('【我委托的行动脑回来了】'),
        } });
      await writeFile(join(root, 'priority1-provider.json'), JSON.stringify({ calls, external_model_calls: 0 }), { mode: 0o600 });
      if (review) {
        const submittedMessage = options.messages.findLast(message => message.role === 'user' && /^\s*\{/.test(textOf(message)));
        const submitted = JSON.parse(textOf(submittedMessage ?? latest)), candidate = submitted.candidate;
        if ((options.tools ?? []).length) throw Error('Review fixture saw executable tools');
        while (true) {
          options.signal?.throwIfAborted();
          try { await access(join(root, 'hold-review')); } catch { break; }
          await new Promise(resolve => setTimeout(resolve, 30));
        }
        const approve = candidate?.current_tree_test_passed && !candidate.contents_truncated;
        yield { type: 'text-delta', index: 0, text: 'DECISION: ' + (approve ? 'approve' : 'block') +
          '\nPRIORITY1_INDEPENDENT_REVIEW: host snapshot/test receipts read; this is synthetic mechanism evidence, not natural GPT quality.' };
        yield { type: 'finish', reason: { kind: 'stop' } }; return;
      }
      let scripted = [], final = 'PRIORITY1_CHARACTER_IDLE';
      // The native context envelope contains `action_report: null` on every
      // ordinary turn. Only the explicit handback frame means a report is
      // present; otherwise the fixture would skip the user's current marker.
      const jsonLines = options.messages.flatMap(message => textOf(message).split(/\r?\n/)).map(line => {
        try { return JSON.parse(line); } catch { return null; }
      }).filter(Boolean);
      const reviewObject = jsonLines.findLast(value => value && (value.gpt_review ||
        /^review-[0-9a-f-]{36}$/.test(value.id ?? '') && value.work_id));
      const hasReviewReport = userText.includes('【原工程的中转站GPT独立审阅回传】') ||
        Boolean(reviewObject) || userText.includes('【GPT独立审阅·不是执行/验收/发布receipt】');
      const hasActionReport = userText.includes('【你委托的独立行动脑回传】') ||
        /"action_report"\s*:\s*\{/.test(userText) || userText.includes('【独立 native 行动脑报告】');
      if (options.sessionId.startsWith('soyo-gpt-review-line-')) final = 'PRIORITY1_AGENT_LINE_ROLE: Soyo reads this line only, not an owner or GPT reviewer.';
      else if (options.sessionId.startsWith('soyo-public-note-home-')) {
        scripted = [['soyo_think', { thought: '只读自己的内部便签，不借owner历史/权限，也不把已读当审阅。' }]];
        final = 'PRIORITY1_NOTE_READ: only this note, no action or platform.';
      } else if (action && userText.includes('PRIORITY1_BUILD')) {
        scripted = [['soyo_development', { operation: 'import', project_id: 'fixture-project' }],
          ['soyo_development', { operation: 'baseline' }],
          ['soyo_development', { operation: 'write', path: 'maths.py', text: 'def add(a, b):\n    return a + b\n' }],
          ['soyo_development', { operation: 'test' }],
          ['soyo_review_candidate', { question: 'PRIORITY1_REVIEW: review the actual addition fix and unchanged unittest; report evidence and missing acceptance.' }]];
        final = 'PRIORITY1_BUILD_REPORT\n' + JSON.stringify({ work_id: task?.id, test: values[3], review: values[4] });
      } else if (action && userText.includes('PRIORITY1_PUBLISH')) {
        const data = JSON.parse(userText.slice(userText.lastIndexOf('PRIORITY1_PUBLISH')).split('\n')[1]);
        scripted = [['soyo_development', { operation: 'status', work_id: data.work_id }],
          ['soyo_development', { operation: 'commit', work_id: data.work_id, message: 'Synthetic candidate addition fix', expected_revision: values[0]?.work?.revision }],
          ['soyo_development', { operation: 'publish', work_id: data.work_id, expected_revision: values[1]?.revision }]];
        final = 'PRIORITY1_RELEASE_REPORT\n' + JSON.stringify(values);
      } else if (action && userText.includes('PRIORITY1_ROLLBACK')) {
        const data = JSON.parse(userText.slice(userText.lastIndexOf('PRIORITY1_ROLLBACK')).split('\n')[1]);
        scripted = [['soyo_development', { operation: 'status', work_id: data.work_id }],
          ['soyo_development', { operation: 'rollback', work_id: data.work_id, expected_revision: values[0]?.work?.revision }]];
        final = 'PRIORITY1_ROLLBACK_REPORT\n' + JSON.stringify(values);
      } else if (action && userText.includes('PRIORITY1_STALE')) {
        const data = JSON.parse(userText.slice(userText.lastIndexOf('PRIORITY1_STALE')).split('\n')[1]);
        scripted = [['soyo_development', { operation: 'write', work_id: data.work_id, path: 'maths.py', text: 'def add(a, b):\n    return a - b\n' }],
          ['soyo_development', { operation: 'commit', work_id: data.work_id }]];
        final = 'PRIORITY1_STALE_REPORT\n' + JSON.stringify(values);
      } else if (action && userText.includes('PRIORITY1_NOTE_SOURCE')) {
        scripted = [['pass_note', { to: 'agent-line:gpt-reviewer', text: 'PRIORITY1_NOTE_SOURCE_LINE: 自己的协作提醒，来源只读。', mode: 'next_time' }],
          ['pass_note', { to: 'peer-home:gpt-reviewer', text: 'PRIORITY1_NOTE_SOURCE_PEER: 这是自己的提醒，不是审阅材料。', mode: 'wake' }]];
        final = 'PRIORITY1_NOTE_SOURCE_REPORT\n' + JSON.stringify(values);
      } else if (action && userText.includes('PRIORITY1_QUEUE')) {
        scripted = [['read', { file_path: join(root, 'SOUL.fixture.md') }]];
        if (results.length === scripted.length) {
          await writeFile(join(root, task.id + '.gate-entered'), JSON.stringify({ id: task.id, parent: task.parent_session, at: Date.now() }), { mode: 0o600 });
          while (true) {
            options.signal?.throwIfAborted();
            try { await access(join(root, task.id + '.release')); break; } catch {}
            await new Promise(resolve => setTimeout(resolve, 30));
          }
        }
        final = 'PRIORITY1_QUEUE_REPORT: actual read and host slot, ' + text;
      } else if (!action && hasReviewReport) {
        const data = reviewObject ?? {}, reviewValue = data.gpt_review ?? data;
        scripted = [['soyo_think', { thought: '核对独立审阅、实际测试和原候选，再作作者决定，不把意见当效果。' }]];
        if (reviewValue?.state === 'reviewed' && reviewValue.validation?.review_state === 'reviewed' && reviewValue.decision === 'approve') {
          scripted.push(['soyo_development_decide', { work_id: reviewValue.work_id, expected_revision: reviewValue.validation.revision,
            decision: 'accept', reason: 'Fixture author independently accepts this exact tested candidate and native review.' }]);
          scripted.push(['soyo_action_brain', { objective: 'PRIORITY1_PUBLISH\n' + JSON.stringify({ work_id: reviewValue.work_id }) }]);
        }
        final = 'PRIORITY1_REVIEW_CHARACTER: advisory report read, role acceptance distinct.';
      } else if (!action && hasActionReport) {
        scripted = [['soyo_think', { thought: '按真实回执核对结果，任何版本选择都不等于服务激活，不再次委托。' }]];
        final = 'PRIORITY1_HANDBACK_READ: native action report read, no platform send.';
      } else if (!action && userText.includes('PRIORITY1_START') && !hasReviewReport && !hasActionReport) {
        scripted = [['soyo_think', { thought: '先决策与阶段回应；工程执行和独立审阅异步交回，不同步等待。' }],
          ['soyo_action_brain', { objective: 'PRIORITY1_BUILD: import fixture-project, establish baseline, fix addition, test, request independent review.' }]];
        final = 'PRIORITY1_PENDING: accepted, still waiting for actual action/review.';
      } else if (!action && /PRIORITY1_(ROLLBACK|STALE|NOTE_SOURCE|QUEUE)/.test(userText)) {
        scripted = [['soyo_think', { thought: '按本回合原来源委托有界动作，不借别的场景权限。' }], ['soyo_action_brain', { objective: text }]];
        final = 'PRIORITY1_PENDING: action queued, not completed.';
      }
      if (results.length < scripted.length) {
        const [name, args] = scripted[results.length];
        yield { type: 'tool-call-delta', index: 0, id: 'priority1-' + count, name, argumentsDelta: JSON.stringify(args) };
        yield { type: 'finish', reason: { kind: 'tool-calls' } }; return;
      }
      yield { type: 'text-delta', index: 0, text: final }; yield { type: 'finish', reason: { kind: 'stop' } };
    }
  }
  ctx.llm.registerAdapter(['soyo-two-brain-fixture'], new Adapter());
  await ctx.plugin(qqNative, { configFile });
  await writeFile(join(root, 'native-host-mounted.json'), JSON.stringify({ mounted: true, external_model_calls: 0, qq_writer: false }), { mode: 0o600 });
}
