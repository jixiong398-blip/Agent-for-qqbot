// SPDX-License-Identifier: MIT
// Deployment-owned identity anchor that survives a dropped system prompt.
//
// Why this exists: every persona/identity instruction in this deployment lives
// in the system prompt. A model gateway in a degraded or retry state can drop
// every client-supplied system message while still answering normally, and then
// the model has no name to answer to. It falls back to guessing from whatever
// strings surround it -- and this deployment is full of internal "soyo" tokens
// (package scope, preset ids, service names), so the guess is both wrong and
// confident.
//
// The fix belongs at the turn boundary, not in one channel: `agent/pre-step` is
// the waterfall every agent (character, action, scheduled, review, consultation)
// passes through, and its `messages` are the conversation itself. Injecting the
// persona there means identity survives even when the system prompt does not,
// and no per-channel code has to remember to do it.
//
// The persona file is the single source of truth. This plugin never derives,
// guesses or normalises a name: a derived name is a second, weaker authority
// that can silently disagree with what the deployment owner actually wrote.
// It replays the owner's own words instead. If no persona is readable the
// plugin stays inert -- asserting an invented identity is worse than none.
//
// Dosing matters as much as content: pre-step messages are appended to the
// session surface, so anchoring every turn would copy the persona body into the
// history dozens of times. See `needsAnchor` for the exact rule.
import { createMessage } from '@deepseek-ai/dsh-llm';
import { readFile } from 'node:fs/promises';
import z from '@deepseek-ai/schemastery';
import { ANCHOR_SOURCE, anchorText, needsAnchor, personaDigest } from './identity-anchor-text.mjs';

export const name = 'soyo-identity-anchor';

// The persona is read from disk, not from the system prompt service. Declaring
// `systemPrompt` here would make a gateway that drops system sections also block
// this plugin from mounting -- exactly the failure it exists to survive.
export const inject = [];

export const Config = z.object({
  configFile: z.string().required(),
  // Upper bound on replayed persona characters. The identity-bearing opening of
  // a persona is short; this only guards against pathological files costing
  // tokens on every turn.
  maxChars: z.number().default(6000),
});

/** Read the deployment's own persona text, or '' when none is readable. */
async function readPersona(configFile) {
  let raw = {};
  try { raw = JSON.parse(await readFile(configFile, 'utf8')); } catch { return ''; }
  const soulPath = String(raw?.soul_file || '');
  if (!soulPath) return '';
  try {
    return String(await readFile(soulPath, 'utf8')).trim();
  } catch { return ''; }
}

export async function apply(ctx, config) {
  const persona = await readPersona(config.configFile);
  if (!persona) {
    // No readable persona: stay inert rather than inventing an identity.
    return;
  }
  const digest = personaDigest(persona);
  const text = anchorText(persona, config.maxChars);
  if (!text) return;

  ctx.on('agent/pre-step', async (payload, next) => {
    const decision = await next();
    if (decision.kind !== 'enter') return decision;
    // Only the opening step of a turn needs the anchor. Repeating it on every
    // tool step would add tokens without adding information.
    if (Number(payload.step ?? 1) > 1) return decision;
    const messages = decision.messages ?? [];
    // Re-entrant safety: never stack anchors if another plugin already added one
    // for this very step.
    if (messages.some(message => message.source?.kind === ANCHOR_SOURCE)) return decision;
    // Durable check: keep exactly one anchor per compacted window instead of one
    // per turn. Compaction is the only thing that can drop it from the surface.
    let events;
    try {
      events = payload.agent.session.snapshotEvents();
    } catch {
      // An unreadable log must not silently switch identity protection off. Fall
      // back to the opening turn only: cheaper than anchoring every turn, and
      // still enough for a dropped system prompt, which happens on turn entry.
      events = undefined;
    }
    const anchored = events === undefined
      ? Number(payload.turn ?? 1) > 1
      : !needsAnchor(events, digest);
    if (anchored) return decision;
    const anchor = createMessage({
      role: 'user',
      source: { kind: ANCHOR_SOURCE, form: 'notice', digest, summary: '身份锚（人格文件原文）' },
      content: [{ type: 'text', text }],
    });
    return { ...decision, messages: [...messages, anchor] };
  }, { global: true });
}
