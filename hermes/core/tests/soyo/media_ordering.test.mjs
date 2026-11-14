// SPDX-License-Identifier: MIT
// Group chats send several pictures with several messages. An unordered pile
// makes the model answer about the wrong image: a real turn replied with PCB
// soldering talk to a screenshot of a ban notice. These contracts pin ordering
// and source attribution so deictic references ("that last picture") resolve.
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  orderSceneMedia, describeMediaSources, mediaNoteFor,
  DEFAULT_MEDIA_LIMIT, DEFAULT_MEDIA_WINDOW_SECONDS,
} from '../../soyo/dsh/host/scene-media.mjs';

const image = ref => ({ kind: 'image', ref, metadata: {} });
const envelope = over => ({ event_id: 'cur', occurred_at: 1_000, sender_id: '1', text: '@bot 你看这个', ...over });

test('explicit old quotes and recalled sources bypass recency, not source order or the image cap', () => {
  const result=orderSceneMedia({envelope:envelope(),batchInputs:[],
    replyContext:{state:'resolved',message_id:'quoted',occurred_at:1,media:[image('a'),image('b')]},
    recalled:[{event_id:'recalled',occurred_at:2,media:[image('c')]}]});
  assert.deepEqual(result.media.map(v=>v.ref),['a','b','c']);
  assert.deepEqual(result.media.map(v=>v.from),['quoted','quoted','recalled']);
});
test('newest message first never reverses pictures inside one message', () => {
  const result=orderSceneMedia({envelope:envelope(),recent:[
    {event_id:'old',occurred_at:900,media:[image('a'),image('b')]},
    {event_id:'new',occurred_at:950,media:[image('c'),image('d')]}]});
  assert.deepEqual(result.media.map(v=>v.ref),['c','d','a','b']);
});

test('the current message\u2019s own pictures always come first', () => {
  const { media } = orderSceneMedia({
    envelope: envelope(),
    batchInputs: [{ event_id: 'cur', occurred_at: 1_000, sender_id: '1', text: '@bot 你看这个', media: [image('cur.jpg')] }],
    recent: [{ event_id: 'old', occurred_at: 900, sender_id: '2', text: '旧图', media: [image('old.jpg')] }],
    config: {},
  });
  assert.equal(media[0].ref, 'cur.jpg');
  assert.equal(media[0].from, 'current');
  assert.equal(media[1].ref, 'old.jpg');
  assert.equal(media[1].from, 'recent');
});

test('recent pictures are newest-first, not oldest-first', () => {
  const { media } = orderSceneMedia({
    envelope: envelope(),
    batchInputs: [],
    recent: [
      { event_id: 'a', occurred_at: 800, sender_id: '2', text: 'a', media: [image('a.jpg')] },
      { event_id: 'b', occurred_at: 950, sender_id: '2', text: 'b', media: [image('b.jpg')] },
      { event_id: 'c', occurred_at: 900, sender_id: '2', text: 'c', media: [image('c.jpg')] },
    ],
    config: {},
  });
  assert.deepEqual(media.map(m => m.ref), ['b.jpg', 'c.jpg', 'a.jpg'],
    'the most recent picture must be nearest, so "the last image" is unambiguous');
});

test('every attached picture names its source message and time', () => {
  const now = Math.floor(Date.now() / 1000);
  const { media } = orderSceneMedia({
    envelope: envelope({ occurred_at: now }),
    batchInputs: [],
    recent: [{ event_id: 'a', occurred_at: now - 30, sender_id: '2', text: '群主发的板子', media: [image('a.jpg')] }],
    config: {},
  });
  const noted = media.map((m, i) => ({ ...m, index: i + 1 }));
  const note = describeMediaSources(noted);
  assert.match(note, /#1/);
  assert.match(note, /群主发的板子/);
  assert.match(note, /更早的消息/, 'a recent picture must not claim to be the current message');
});

test('the note tells the model not to treat an older picture as the current topic', () => {
  const note = mediaNoteFor({ attached: [{ ref: 'old.jpg', from: 'recent', occurred_at: 900, message_text: 'x', index: 1 }] });
  assert.match(note, /不要拿更早的图当作当前话题/);
  assert.match(note, /按顺序/);
});

test('an old picture ages out instead of piling in', () => {
  const { media } = orderSceneMedia({
    envelope: envelope(),
    batchInputs: [],
    recent: [
      { event_id: 'stale', occurred_at: 1_000 - 2_400, sender_id: '2', text: '很久以前', media: [image('stale.jpg')] },
      { event_id: 'near', occurred_at: 1_000 - 60, sender_id: '2', text: '刚发的', media: [image('near.jpg')] },
    ],
    config: {},
  });
  assert.deepEqual(media.map(m => m.ref), ['near.jpg']);
});

test('the picture budget is small and reported, never silently truncated', () => {
  assert.equal(DEFAULT_MEDIA_LIMIT, 4);
  assert.equal(DEFAULT_MEDIA_WINDOW_SECONDS, 900);
  const recent = Array.from({ length: 9 }, (_, i) => ({
    event_id: 'm' + i, occurred_at: 900 + i, sender_id: '2', text: 'p' + i, media: [image(i + '.jpg')],
  }));
  const { media, dropped } = orderSceneMedia({ envelope: envelope(), batchInputs: [], recent, config: {} });
  assert.equal(media.length, DEFAULT_MEDIA_LIMIT);
  assert.equal(dropped, 5, 'the caller must be able to tell the model what was left out');
  assert.match(mediaNoteFor({ attached: media.map((m, i) => ({ ...m, index: i + 1 })), dropped }), /另有 5 张/);
});

test('faces and stickers never consume the picture budget', () => {
  const { media } = orderSceneMedia({
    envelope: envelope(),
    batchInputs: [],
    recent: [
      { event_id: 'f', occurred_at: 900, sender_id: '2', text: '[表情包]', media: [{ kind: 'face', ref: 'face1' }] },
      { event_id: 's', occurred_at: 950, sender_id: '2', text: '[表情包]', media: [{ kind: 'sticker', ref: 'st1' }] },
      { event_id: 'p', occurred_at: 980, sender_id: '2', text: '[图片]', media: [{ kind: 'image', ref: 'photo.jpg' }] },
    ],
    config: {},
  });
  assert.deepEqual(media.map(m => m.ref), ['photo.jpg'],
    'decorative faces/stickers must not displace the real photo being discussed');
});

test('current voice and video still reach materialization without consuming the picture budget', () => {
  const result = orderSceneMedia({ envelope: envelope(), config: { qq_media_max_images: 1 },
    batchInputs: [{ event_id: 'cur', media: [
      { kind: 'record', ref: 'voice.ogg' }, { kind: 'video', ref: 'clip.mp4' }, image('photo.png'),
    ] }], recent: [{ event_id: 'old', occurred_at: 950, media: [image('older.png')] }] });
  assert.deepEqual(result.media.map(item => item.ref), ['voice.ogg', 'clip.mp4', 'photo.png']);
  assert.equal(result.dropped, 1, 'only excluded pictures count as dropped pictures');
  assert.equal(result.imageLimit, 1, 'video frames must share the image attachment budget');
});

test('source selection matches the bounded worker input, including non-picture media', () => {
  const result = orderSceneMedia({ envelope: envelope(), config: { qq_media_max_images: 40 },
    batchInputs: [{ event_id: 'cur', media: [
      { kind: 'audio', ref: 'voice.ogg' }, ...Array.from({ length: 12 }, (_, i) => image('image-' + i)),
    ] }] });
  assert.equal(result.media.length, 8);
  assert.equal(result.media[0].kind, 'audio');
  assert.equal(result.dropped, 5);
});

test('internal turns never attach scene pictures', () => {  const { media } = orderSceneMedia({
    envelope: envelope(), internal: true,
    batchInputs: [{ event_id: 'cur', media: [image('cur.jpg')] }],
    recent: [{ event_id: 'x', occurred_at: 900, media: [image('x.jpg')] }], config: {},
  });
  assert.deepEqual(media, []);
});

test('no pictures produces no note at all', () => {
  assert.equal(mediaNoteFor({ attached: [] }), '');
});

test('the host input assembly uses this module, not an ad-hoc pile', () => {
  // Guard against the fix silently disappearing in a later refactor.
  return import('node:fs/promises').then(async ({ readFile }) => {
    const source = await readFile(new URL('../../soyo/dsh/host/qq-native.mjs', import.meta.url), 'utf8');
    assert.match(source, /import \{ orderSceneMedia, mediaNoteFor \} from '\.\/scene-media\.mjs'/);
    assert.match(source, /const ordered = orderSceneMedia\(/);
    assert.match(source, /const mediaNote = mediaNoteFor\(/);
  });
});
