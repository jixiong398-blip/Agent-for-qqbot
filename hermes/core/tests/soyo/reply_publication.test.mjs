// SPDX-License-Identifier: MIT
import test from 'node:test';
import assert from 'node:assert/strict';
import { committedStage, replyText, publishableText, StagePublications } from '../../soyo/dsh/host/reply-publication.mjs';

const event = (kind = 'tool-calls', extra = {}) => ({ type: 'assistant/message', seq: 12, data: {
  turn: 3, step: 1, message: { content: [{ type: 'reasoning', text: 'PRIVATE_REASONING' },
    { type: 'text', text: '我去看看，等我一下。' }, { type: 'tool-call', name: 'bounded_tool' }] },
  stream: [{ chunk: { type: 'finish', reason: { kind } } }], ...extra,
} });
test('a committed text + tool step is speech; reasoning is not included', () => {
  assert.deepEqual(committedStage(event()), { seq: 12, turn: 3, text: '我去看看，等我一下。' });
});
test('repeated committed events are claimed exactly once without re-emitting into SDK persistence', () => {
  const stages=new StagePublications();
  assert(stages.claim(event()));
  assert.equal(stages.claim(event()),null);
  const truncated=event('max-tokens');truncated.seq=13;
  assert.equal(stages.claim(truncated),null);
  const completed=event();completed.seq=13;
  assert(stages.claim(completed));
});
test('cancelled, truncated, failed and unsettled attempts never become stages', () => {
  for (const kind of ['max-tokens','error','aborted']) assert.equal(committedStage(event(kind)), null);
  assert.equal(committedStage(event('stop', { interrupted: true })), null);
  assert.equal(committedStage(event('stop', { stream: [] })), null);
});
test('a plain message is left to final settlement unless another step follows it', () => {
  const plain = event('stop', { message: { content: [{ type: 'text', text: '完整正文' }] } });
  assert.equal(committedStage(plain), null);
  assert.equal(committedStage(plain, { requireTools: false }).text, '完整正文');
});
test('normal Markdown, multilingual text and thought-like words are not debris', () => {
  const value = 'Привет!\n\n---\n\nthink 是引用的单词。';
  assert.equal(replyText([{ type: 'text', text: value }]), value);
  assert.equal(publishableText(value), true);
});
test('only complete explicitly marked reasoning spans can be stripped', () => {
  assert.equal(replyText([{ type: 'text', text: '<think>private</think>回答' }]), '回答');
  assert.equal(replyText([{ type: 'text', text: 'private</think>回答' }]), '回答');
  assert.equal(publishableText(replyText([{ type: 'text', text: '<think>unclosed private' }])), false);
  assert.equal(committedStage(event('tool-calls', { message: { content: [{ type: 'reasoning', text: 'private' }, { type: 'tool-call' }] } })), null);
});

test('mixed-case unterminated reasoning and invalid sequence numbers cannot be published', () => {
  for (const text of ['<THINK>private', '<Analysis>private', '<ReAsOnInG>private', '<|DsMl|>private'])
    assert.equal(publishableText(replyText([{ type: 'text', text }])), false, text);
  for (const seq of [-1, Number.MAX_SAFE_INTEGER + 1, NaN, Infinity])
    assert.equal(committedStage({ ...event(), seq }), null);
});
