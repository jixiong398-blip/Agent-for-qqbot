// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdir, readFile, realpath, symlink, utimes, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { mkdtemp } from 'node:fs/promises';
import { stageOutboundImage } from '../../soyo/dsh/host/outbound-image.mjs';

const PNG = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');

async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'soyo-outbound-image-'));
  const media = join(root, 'media'); const development = join(root, 'development');
  await mkdir(media); await mkdir(development);
  return { root, media, development };
}

test('one real image inside the media root is staged by content hash', async () => {
  const { media } = await fixture();
  const source = join(media, 'source.png'); await writeFile(source, PNG);
  const staged = await stageOutboundImage({ path: source, mediaRoot: media });
  assert.equal(staged.media_type, 'image/png');
  assert.equal(staged.bytes, PNG.length);
  assert.match(staged.path, /outbound-[0-9a-f]{32}\.png$/);
  assert.deepEqual(await readFile(staged.path), PNG);
});

test('an action workspace image is copied into the media root, never sent in place', async () => {
  const { media, development } = await fixture();
  const source = join(development, 'action-fixture', 'draft.png');
  await mkdir(join(development, 'action-fixture')); await writeFile(source, PNG);
  const staged = await stageOutboundImage({ path: source, mediaRoot: media, developmentRoot: development });
  assert.notEqual(staged.path, source);
  // realpath expands an 8.3 short name on Windows, so compare resolved roots.
  assert.equal(staged.path.startsWith(await realpath(media)), true);
  assert.deepEqual(await readFile(staged.path), PNG);
});

test('paths outside the two roots, fake images, links and missing files are refused', async () => {
  const { root, media, development } = await fixture();
  const outside = join(root, 'secret.png'); await writeFile(outside, PNG);
  await assert.rejects(stageOutboundImage({ path: outside, mediaRoot: media, developmentRoot: development }), /SCOPE/);
  const fake = join(media, 'fake.png'); await writeFile(fake, Buffer.from('not an image'));
  await assert.rejects(stageOutboundImage({ path: fake, mediaRoot: media }), /TYPE/);
  await assert.rejects(stageOutboundImage({ path: join(media, 'missing.png'), mediaRoot: media }), /MISSING/);
  const link = join(media, 'link.png'); await symlink(outside, link);
  await assert.rejects(stageOutboundImage({ path: link, mediaRoot: media }), /SCOPE|FILE/);
  await assert.rejects(stageOutboundImage({ path: 'relative.png', mediaRoot: media }), /PATH/);
});

test('oversized images are refused before any publication', async () => {
  const { media } = await fixture();
  const big = join(media, 'big.png'); await writeFile(big, PNG);
  await assert.rejects(stageOutboundImage({ path: big, mediaRoot: media, maxBytes: 8 }), /SIZE/);
});

test('recent images are newest-first, extension-bounded and root-confined', async () => {
  const { media, development } = await fixture();
  const { recentImages } = await import('../../soyo/dsh/host/outbound-image.mjs');
  await mkdir(join(development, 'action-a'), { recursive: true });
  const older = join(media, 'older.png'); await writeFile(older, PNG);
  // The ordering contract is mtime-based; two writes inside the same
  // filesystem timestamp tick would otherwise tie, so pin distinct times.
  await utimes(older, new Date(1_600_000_000_000), new Date(1_600_000_000_000));
  const newer = join(development, 'action-a', 'newer.jpg');
  await writeFile(newer, Buffer.concat([Buffer.from('ffd8ffe0', 'hex'), PNG]));
  await utimes(newer, new Date(1_700_000_000_000), new Date(1_700_000_000_000));
  await writeFile(join(media, 'notes.txt'), 'not an image');
  const rows = await recentImages({ mediaRoot: media, developmentRoot: development });
  assert.deepEqual(rows.map(row => row.path).sort(), [newer, older].sort());
  assert.equal(rows[0].path, newer);
  assert(rows.every(row => row.bytes === PNG.length || row.bytes === PNG.length + 4));
});
test('built-in sticker names resolve inside the sticker root and unknown names fall back to tea', async () => {
  const { resolveSticker, stripStickerMarkers } = await import('../../soyo/dsh/host/outbound-image.mjs');
  // Platform-neutral: the contract is ''inside the given root'', not a POSIX path.
  const root = join(tmpdir(), 'stickers');
  assert.equal(resolveSticker('excited', root), join(root, 'soyo_chibi_excited.gif'));
  assert.equal(resolveSticker('兴奋', root), join(root, 'soyo_chibi_excited.gif'));
  assert.equal(resolveSticker('难过', root), join(root, 'soyo_chibi_sad.jpg'));
  assert.equal(resolveSticker('拜托', root), join(root, 'soyo_chibi_clasp.jpg'));
  assert.equal(resolveSticker('something-else', root), join(root, 'soyo_chibi_tea.jpg'));
  assert.equal(resolveSticker('', root), null);
  assert.equal(stripStickerMarkers('濂界殑\n\n[sticker:excited]'), '濂界殑');
  assert.equal(stripStickerMarkers('濂界殑 [sticker:excited'), '濂界殑');
  assert.equal(stripStickerMarkers('鍙湁琛ㄦ儏 [sticker:寮€蹇僝'), '鍙湁琛ㄦ儏');
});
