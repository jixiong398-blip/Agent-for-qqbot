// SPDX-License-Identifier: MIT
// Ordering and attribution for scene media. Pure data in, pure data out, so the
// rules that decide "which picture is the last one" can be tested without a Host.
//
// Why this exists: a group chat sent several pictures with several messages, and
// the Host handed the model one undifferentiated pile. The model then answered a
// question about the newest screenshot by talking about an older PCB photo.
// A picture is only usable if the model knows which message it belongs to and
// how recent it is relative to the current one.

/** Default: pictures older than this are not attached at all. */
export const DEFAULT_MEDIA_WINDOW_SECONDS = 900;
/** Default: how many pictures may be attached to a single turn. */
export const DEFAULT_MEDIA_LIMIT = 4;
// Keep source indexes aligned with native_media.py's eight-source input bound.
const MAX_MEDIA_SOURCES = 8;

const stamp = value => (Number.isFinite(value) ? value : 0);

/**
 * Collect the pictures for one turn in the order they will be attached.
 *
 * The current message's own pictures lead, because they are what triggered the
 * turn. Recent pictures follow newest-first, so "the last image" is the nearest
 * one rather than an arbitrary older one. Anything outside the window is
 * dropped instead of piling in.
 *
 * @param {object} input
 * @param {object} input.envelope - the current event (event_id, occurred_at, sender_id, text)
 * @param {Array} input.batchInputs - admitted inputs for this turn
 * @param {Array} input.recent - recent scene rows from memory
 * @param {boolean} input.internal - internal turns never attach scene media
 * @param {object} input.config - host config (window / limit overrides)
 * @returns {{ media: Array, dropped: number }}
 */
export function orderSceneMedia({ envelope = {}, batchInputs = [], recent = [], recalled = [], replyContext = {}, internal = false, config = {} }) {
  const window = Number(config.qq_media_window_seconds ?? 0) || DEFAULT_MEDIA_WINDOW_SECONDS;
  const configured = Number(config.qq_media_max_images ?? DEFAULT_MEDIA_LIMIT);
  const limit = Number.isFinite(configured) ? Math.max(1, Math.min(40, Math.floor(configured))) : DEFAULT_MEDIA_LIMIT;
  if (internal) return { media: [], dropped: 0, imageLimit: limit };
  // Faces and stickers are decorative: attaching them as real pictures both
  // wastes the picture budget and distracts from the photo being discussed.
  const picture = item => item && ['image', 'mface'].includes(String(item.kind || '').toLowerCase());
  // Picture ordering must not silently disable the existing voice/video worker.
  const useful = item => picture(item) || item && ['record', 'audio', 'video'].includes(String(item.kind || '').toLowerCase());
  const currentEvent = envelope.event_id;
  const currentAt = stamp(envelope.occurred_at);
  const rows = (Array.isArray(recent) ? recent : [])
    .filter(row => row && row.event_id !== currentEvent)
    .filter(row => !window || Math.abs(stamp(row.occurred_at) - currentAt) < window)
    .sort((a, b) => stamp(a.occurred_at) - stamp(b.occurred_at));
  const currentMedia = (Array.isArray(batchInputs) ? batchInputs : [])
    .flatMap((input, index) => (input.media || []).filter(useful).map(item => ({
      ...item,
      from: 'current',
      batch_index: index,
      message_event_id: input.event_id ?? currentEvent,
      occurred_at: input.occurred_at ?? envelope.occurred_at,
      sender_id: input.sender_id ?? envelope.sender_id,
      message_text: input.text ?? '',
    })));
  const nearbyMedia = [...rows].reverse().flatMap(row => (row.media || []).filter(useful).map(item => ({
    ...item,
    from: 'recent',
    message_event_id: row.event_id,
    occurred_at: row.occurred_at,
    sender_id: row.sender_id,
    message_text: row.text ?? '',
  })));
  const referenced = replyContext.state === 'resolved' && Array.isArray(replyContext.media) ? [{
    event_id: replyContext.message_id, occurred_at: replyContext.occurred_at, text: replyContext.text,
    sender_id: replyContext.sender_id, media: replyContext.media, from: 'quoted',
  }] : [];
  const selected = [...referenced, ...(Array.isArray(recalled) ? recalled : []).map(row => ({ ...row, from: 'recalled' }))]
    .flatMap(row => (row.media || []).filter(picture).map(item => ({ ...item, from: row.from,
      message_event_id: row.event_id, occurred_at: row.occurred_at, sender_id: row.sender_id, message_text: row.text ?? '' })));
  const seen = new Set();
  const ordered = [...currentMedia, ...selected, ...nearbyMedia].filter(item => {
    const key = JSON.stringify([item.message_event_id, item.kind, item.ref]);
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });
  const media = [];
  let pictures = 0, dropped = 0;
  for (const item of ordered) {
    if (media.length >= MAX_MEDIA_SOURCES || picture(item) && pictures >= limit) {
      if (picture(item)) dropped++;
      continue;
    }
    media.push(item);
    if (picture(item)) pictures++;
  }
  return { media, dropped, imageLimit: limit };
}

/**
 * Render the attachment map shown to the model. Indexes are 1-based and must
 * match the attachment order, so the model can connect "#2" to a message.
 */
export function describeMediaSources(list) {
  return (Array.isArray(list) ? list : []).map(row => {
    const when = row.occurred_at ? new Date(row.occurred_at * 1000).toTimeString().slice(0, 5) : '';
    const who = row.from === 'current' ? '本轮这条消息' : row.from === 'quoted' ? '本轮引用的消息'
      : row.from === 'recalled' ? '检索召回的消息' : '更早的消息';
    const text = String(row.message_text || '').replace(/\s+/g, ' ').trim().slice(0, 40);
    return '  #' + row.index + ' ← ' + who + (when ? ' ' + when : '') + (text ? '「' + text + '」' : '');
  }).join('\n');
}

/** The complete note appended to the turn input, or '' when nothing attached. */
export function mediaNoteFor({ attached = [], dropped = 0 }) {
  if (!attached.length) return '';
  return '\n【宿主已把以下原图按顺序作为图片附件附在这条输入后面】\n' + describeMediaSources(attached) +
    '\n占位文字“未解析”只表示没有文字描述，不代表看不到图片。' +
    (dropped > 0 ? '（另有 ' + dropped + ' 张因数量上限未附上）' : '') +
    '\n如果对方说的是“最后那张”“刚才那个图”，按上面标出的来源时间对应，不要拿更早的图当作当前话题。】';
}
