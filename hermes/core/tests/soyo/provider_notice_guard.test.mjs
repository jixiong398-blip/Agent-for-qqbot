// SPDX-License-Identifier: MIT
// A provider diagnostic is not the character's reply. These contracts pin the
// exact banner that reached a real QQ chat so it can never be published again,
// while ordinary role-play prose (which may mention errors in her own voice)
// still travels.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { isProviderNotice } from '../../soyo/dsh/host/reply-publication.mjs';

// The guard lives in qq-native.mjs, which imports DSH packages. Read the
// predicate rather than importing the whole Host plugin.
const source = await readFile(new URL('../../soyo/dsh/host/qq-native.mjs', import.meta.url), 'utf8');


test('the exact banner that leaked into a real chat is refused', () => {
  const leaked = `AI provider temporarily unavailable
----
Request ID: req_ba25f381
Ref: 0.1794214234610
UpstreamResponseCode: N/A
Model: deepseek-v4.1-flash
----
- The AI provider failed to process your request (temporary server issue or oversized prompt).
- This was retried automatically.
How to fix:
- Send "Continue" to resume from where it stopped. If that does not work, start a new session/chat.
- Wait a moment and retry with a shorter or simpler prompt.
- Do not keep retrying the exact same request.
**Billing:**
- This request still counts as a request and is billed based on its input (minimum 1,000 prompt / 1,000 completion / 1,000 cached tokens).
- Do not resend the same request — it will keep failing and keep consuming your quota.
**Recommended tools:**
- These responses are optimized for opencode, Claude Code, and Codex.
- If you are using a non-standard client and keep hitting errors, switch to one of the supported tools above.`;
  assert.equal(isProviderNotice(leaked), true);
});

test('each unambiguous vendor marker is enough on its own', () => {
  for (const line of [
    'AI provider temporarily unavailable',
    'Request ID: req_9f8e7d6c',
    'UpstreamResponseCode: 502',
    '**Recommended tools:**',
    'Do not keep retrying the exact same request.',
    'This request still counts as a request and is billed based on its input.',
    '- Send "Continue" to resume from where it stopped. If that does not work, start a new session/chat.',
  ]) assert.equal(isProviderNotice(line), true, line);
});

test('her own words about a failure are still published', () => {
  for (const line of [
    '这次没画出来，渠道那边报了超时。我先停在这里，不再空转。',
    '对不起，连着试了两次都没成，我不想糊弄你。',
    'The image failed again, so I stopped instead of burning more credits.',
    '我刚才那个请求被拒了，说是上下文太长。',
    '正文\n\n---\n\n另一个段落',
    '',
    '   ',
  ]) assert.equal(isProviderNotice(line), false, JSON.stringify(line));
});

test('the final publication path actually consults the guard', () => {
  // Regression: the guard must be wired into the suppression branch, not merely
  // defined. Without this, the definition is dead code.
  const branch = source.slice(source.indexOf('} else if (trace.end?.data?.reason?.kind'),
    source.indexOf('provider_notice_withheld') + 40);
  assert.match(branch, /isProviderNotice\(text\)/);
  assert.match(branch, /provider_notice_withheld/);
});
