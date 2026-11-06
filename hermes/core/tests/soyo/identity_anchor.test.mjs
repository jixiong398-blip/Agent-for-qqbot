// SPDX-License-Identifier: MIT
// The identity anchor is the fix for "the model called itself something else
// when the gateway dropped system". These invariants matter more than the prose:
// identity must survive, it must not be duplicated into every turn, and it must
// never invent a persona the deployment did not write.
import test from 'node:test';
import assert from 'node:assert/strict';
import { anchorText, needsAnchor, personaDigest } from '../../soyo/dsh/host/identity-anchor-text.mjs';

const ANCHOR = 'soyo-identity-anchor';
const digest = personaDigest('# 人格\n\n我是测试角色。\n');

const anchorEvent = (seq, source = {}) => ({
  type: 'user/message', seq, time: seq,
  data: { role: 'user', source: { kind: ANCHOR, form: 'notice', digest, ...source, },
    content: [{ type: 'text', text: 'anchor' }] },
});
const userEvent = seq => ({
  type: 'user/message', seq, time: seq,
  data: { role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'hi' }] },
});
const compaction = (seq, start, end) => ({
  type: 'compaction/summary', seq, time: seq,
  data: { summary: 's', shadowedRange: { start, end }, shadowedSeqs: [] },
});

test('an empty persona produces no anchor rather than an invented identity', () => {
  assert.equal(anchorText('', 6000), '');
  assert.equal(anchorText('   \n\t ', 6000), '');
  assert.equal(anchorText(null, 6000), '');
});

test('the anchor replays persona text verbatim and names the internal tokens as non-identity', () => {
  const text = anchorText('# 人格\n\n我是测试角色。', 6000);
  assert.match(text, /人格文件开始/);
  assert.match(text, /人格文件结束/);
  assert.ok(text.includes('我是测试角色。'));
  // The surrounding context of this deployment is full of internal "soyo"
  // tokens; the anchor has to say they are not a name.
  assert.match(text, /soyo/);
  assert.match(text, /不是你的名字/);
});

test('oversized personas are bounded and marked as truncated', () => {
  const text = anchorText('x'.repeat(9000), 600);
  assert.ok(text.length < 9000);
  assert.match(text, /后续内容略/);
});

test('the first turn of a session is anchored', () => {
  assert.equal(needsAnchor([], digest), true);
  assert.equal(needsAnchor([userEvent(1)], digest), true);
  assert.equal(needsAnchor([userEvent(1), anchorEvent(2)], digest), false);
});

test('later turns reuse the surviving anchor instead of appending another one', () => {
  // Turn 1 anchored at seq 2; turns 2..5 add plain messages only.
  const events = [userEvent(1), anchorEvent(2), userEvent(3), userEvent(4), userEvent(5)];
  assert.equal(needsAnchor(events, digest), false);
});

test('compaction that swallows the anchor re-arms it', () => {
  const events = [
    userEvent(1), anchorEvent(2), userEvent(3), userEvent(4),
    compaction(5, 1, 4),
  ];
  assert.equal(needsAnchor(events, digest), true);
});

test('compaction that still shadows the anchor re-arms it', () => {
  const events = [
    userEvent(1), userEvent(2),
    compaction(3, 1, 2),
    anchorEvent(4),
    userEvent(5),
    compaction(6, 3, 5),
  ];
  // The second compaction shadows seq 3..5, taking the anchor at seq 4 with it.
  assert.equal(needsAnchor(events, digest), true);
});

test('an anchor shadowed by an earlier compaction but re-added later is enough', () => {
  const events = [
    userEvent(1), anchorEvent(2),
    compaction(3, 1, 2),
    anchorEvent(4),
    userEvent(5),
  ];
  assert.equal(needsAnchor(events, digest), false);
});

test('a persona edit invalidates the old anchor', () => {
  const events = [userEvent(1), anchorEvent(2)];
  const changed = personaDigest('# 人格\n\n我是另一个角色。\n');
  assert.notEqual(changed, digest);
  assert.equal(needsAnchor(events, changed), true);
});

test('an anchor written by another source kind is not trusted', () => {
  const foreign = anchorEvent(2, { kind: 'soyo-qq-context' });
  foreign.data.source.kind = 'soyo-qq-context';
  assert.equal(needsAnchor([userEvent(1), foreign], digest), true);
});

test('persona digest ignores line-ending rewrites', () => {
  assert.equal(personaDigest('a\nb\nc'), personaDigest('a\r\nb\r\nc'));
  assert.equal(personaDigest('a\nb'), personaDigest('a\rb'));
  assert.notEqual(personaDigest('a\nb'), personaDigest('a\nb\n'));
});
