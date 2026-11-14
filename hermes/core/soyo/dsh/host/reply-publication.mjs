// SPDX-License-Identifier: MIT
// Typed, committed assistant text is speech. Reasoning is never a publication.
export const protocol = /(?:[<＜⟨]?[|｜]?(?:DSML|dsml)[|｜]|<\/?(?:think|analysis|reasoning|tool_call|function_calls)\b|\[CQ:)/i;
const PROVIDER_NOTICE = [
  /AI provider temporarily unavailable/i, /\bRequest ID:\s*[A-Za-z0-9_-]+/i,
  /\bUpstreamResponseCode\b/i, /\bHow to fix:\s*$/im, /\bRecommended tools\b/i,
  /\bDo not keep retrying the exact same request\b/i,
  /\bthis request still counts as a request and is billed\b/i, /\bstart a new session\/chat\b/i,
];
export const isProviderNotice = value => PROVIDER_NOTICE.some(pattern => pattern.test(String(value ?? '')));

export function replyText(blocks = []) {
  let text = blocks.filter(block => block.type === 'text').map(block => block.text).join('');
  // Only a complete, explicitly delimited span can be removed. An unmatched
  // opening tag is withheld by protocol, never treated as the start of speech.
  text = text.replace(/<(think|analysis|reasoning)\b[^>]*>[\s\S]*?<\/\1>/gi, '');
  const closing = /<\/(?:think|analysis|reasoning)>/i.exec(text);
  if (closing) text = text.slice(closing.index + closing[0].length);
  return text.replace(/<\|endoftext\|>/g, '').replace(/<\/?(?:response|answer|output)>/gi, '')
    .replace(/[ \t]{2,}/g, ' ').replace(/\s+([，。！？、；：])/g, '$1').trim();
}

export function publishableText(text) {
  return Boolean(text && text.length <= 16000 && !protocol.test(text) && !isProviderNotice(text) &&
    !/^\[(?:SILENT|GO_QUIET|END_EPISODE)\]$/.test(text));
}

export function committedStage(event, { requireTools = true } = {}) {
  if (event?.type !== 'assistant/message' || event.data?.interrupted || !Number.isSafeInteger(event.seq) || event.seq < 0) return null;
  const blocks = event.data.message?.content ?? [];
  if (blocks.some(block => !['text', 'reasoning', 'tool-call'].includes(block.type)) ||
      (requireTools && !blocks.some(block => block.type === 'tool-call'))) return null;
  const finish = event.data.stream?.findLast(frame => frame.chunk?.type === 'finish')?.chunk?.reason?.kind;
  if (!['stop', 'tool-calls'].includes(finish)) return null;
  const text = replyText(blocks);
  return publishableText(text) ? { seq: event.seq, turn: event.data.turn, text } : null;
}

export class StagePublications {
  constructor() { this.seen = new Set(); }
  claim(event, options) {
    const stage = committedStage(event, options);
    if (!stage || this.seen.has(stage.seq)) return null;
    this.seen.add(stage.seq);
    return stage;
  }
}
