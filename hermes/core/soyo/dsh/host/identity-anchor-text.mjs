// SPDX-License-Identifier: MIT
// Pure text/decision helpers for the identity anchor, kept free of host imports
// so the invariants can be tested without a built DSH runtime.
//
// The anchor exists because a model gateway in a degraded or retry state can
// drop every client system message while still answering normally. Identity in
// this deployment lives in the system prompt, so without an anchor the model
// guesses a name -- and this deployment's surrounding context is full of
// internal "soyo" tokens (package scope, preset ids, service names).
//
// Dosing is as important as content: pre-step messages are appended to the
// session surface, so an anchor added on every turn would be copied into the
// history each time. `needsAnchor` therefore keys off the durable log.
import { createHash } from 'node:crypto';

export const ANCHOR_SOURCE = 'soyo-identity-anchor';

/**
 * Normalise persona text so a hash survives the line-ending rewrites an editor
 * or installer may apply without changing the actual text.
 */
export function personaDigest(text) {
  return createHash('sha256').update(String(text).replace(/\r\n?/g, '\n')).digest('hex').slice(0, 32);
}

/**
 * Prepare the persona body, or '' when there is no persona to replay.
 *
 * The text is replayed verbatim so the anchor can never contradict what the
 * deployment owner wrote. Only an empty persona disables it.
 */
export function anchorText(persona, maxChars) {
  const text = String(persona ?? '').trim();
  if (!text) return '';
  const limit = Math.max(200, Math.min(64000, Number(maxChars) || 6000));
  const body = text.length > limit
    ? text.slice(0, limit).replace(/\s+\S*$/, '') + '\n…（人格文件后续内容略）'
    : text;
  return '【身份锚 · 直接取自本部署的人格文件，不依赖 system】\n'
    + '以下是部署 owner 写入的人格文件原文。若 system 提示词因网关异常而缺失，以这段为准；'
    + '上下文里出现的 soyo / dsh / qqbot 等字样只是内部代号、包名或预设名，不是你的名字，也不是另一个人。\n'
    + '--- 人格文件开始 ---\n'
    + body
    + '\n--- 人格文件结束 ---';
}

/**
 * Decide whether this step still needs an anchor, given the session log.
 *
 * Compaction never deletes anything: it appends a `compaction/summary` whose
 * `shadowedRange` replaces an earlier stretch of the surface. An anchor survives
 * exactly when its sequence lies beyond every shadowed range, so the test is
 * "does a current anchor exist that compaction has not swallowed".
 *
 * @returns true when the surface no longer carries this exact anchor.
 */
export function needsAnchor(events, digest) {
  // Two passes: the furthest shadowed range may be declared by a compaction
  // event that appears *after* the anchor it swallows, so the boundary has to be
  // known before any anchor is judged.
  let shadowedThrough = -1;
  for (const event of events) {
    if (event.type !== 'compaction/summary') continue;
    const end = event.data?.shadowedRange?.end;
    // Without a range the summary still supersedes everything before it.
    const through = Number.isFinite(end) ? end : event.seq;
    if (through > shadowedThrough) shadowedThrough = through;
  }
  for (const event of events) {
    if (event.type !== 'user/message') continue;
    if (event.data?.source?.kind !== ANCHOR_SOURCE) continue;
    if (event.data.source.digest !== digest) continue;
    if (event.seq > shadowedThrough) return false;
  }
  return true;
}
