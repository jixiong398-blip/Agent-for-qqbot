// SPDX-License-Identifier: MIT
// One host-owned outbound image per final reply. Model text names a path, but
// only a real image inside the deployment media root or an action task
// workspace is staged; delivery still goes through the single outbox writer.
import { createHash, randomUUID } from 'node:crypto';
import { lstat, mkdir, open, readFile, readdir, realpath, rename } from 'node:fs/promises';
import { extname, isAbsolute, join, sep } from 'node:path';

const TYPES = [
  { type: 'image/png', ext: '.png', test: b => b.subarray(0, 8).equals(Buffer.from('89504e470d0a1a0a', 'hex')) },
  { type: 'image/jpeg', ext: '.jpg', test: b => b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff },
  { type: 'image/gif', ext: '.gif', test: b => ['GIF87a', 'GIF89a'].includes(b.subarray(0, 6).toString('ascii')) },
  { type: 'image/webp', ext: '.webp', test: b => b.subarray(0, 4).toString('ascii') === 'RIFF' && b.subarray(8, 12).toString('ascii') === 'WEBP' },
];

export function imageType(bytes) {
  return TYPES.find(candidate => candidate.test(bytes)) ?? null;
}

const within = (path, root) => root && (path === root || path.startsWith(root.endsWith(sep) ? root : root + sep));

export async function stageOutboundImage({ path, mediaRoot, developmentRoot, maxBytes = 20 * 1024 * 1024 }) {  if (typeof path !== 'string' || !isAbsolute(path)) throw Error('OUTBOUND_IMAGE_PATH: 需要本机绝对路径');
  if (!mediaRoot || !isAbsolute(mediaRoot)) throw Error('OUTBOUND_IMAGE_ROOT: 媒体目录未配置');
  await mkdir(mediaRoot, { recursive: true, mode: 0o700 });
  const media = await realpath(mediaRoot);
  let development = null;
  if (developmentRoot) {
    try { development = await realpath(developmentRoot); } catch { development = null; }
  }
  let source;
  try { source = await realpath(path); } catch { throw Error('OUTBOUND_IMAGE_MISSING: 找不到这张图片'); }
  const info = await lstat(source);
  if (!info.isFile() || info.isSymbolicLink()) throw Error('OUTBOUND_IMAGE_FILE: 只接受普通图片文件');
  if (info.size <= 0 || info.size > maxBytes) throw Error('OUTBOUND_IMAGE_SIZE: 图片超出大小限制');
  if (!within(source, media) && !within(source, development))
    throw Error('OUTBOUND_IMAGE_SCOPE: 只能取媒体目录或行动任务目录里的图片');
  const bytes = await readFile(source);
  const kind = imageType(bytes);
  if (!kind) throw Error('OUTBOUND_IMAGE_TYPE: 不是可识别的 PNG/JPEG/WebP/GIF 图片');
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  const target = join(media, 'outbound-' + sha256.slice(0, 32) + kind.ext);
  if (source !== target) {
    const temporary = join(media, '.outbound-' + randomUUID() + '.tmp');
    const file = await open(temporary, 'wx', 0o600);
    try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
    await rename(temporary, target);
  }
  return { path: target, sha256, bytes: bytes.length, media_type: kind.type };
}

const EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif']);

/**
 * Recent images the character may attach, newest first. Listing is read-only
 * and never validates by itself: stageOutboundImage checks magic and bytes.
 */
export async function recentImages({ mediaRoot, developmentRoot, limit = 8, maxBytes = 20 * 1024 * 1024 }) {
  const rows = [];
  for (const root of [mediaRoot, developmentRoot].filter(Boolean)) {
    let entries;
    try { entries = await readdir(root, { recursive: true, withFileTypes: true }); } catch { continue; }
    for (const entry of entries) {
      if (!entry.isFile() || entry.isSymbolicLink()) continue;
      if (!EXTENSIONS.has(extname(entry.name).toLowerCase())) continue;
      const path = join(entry.parentPath ?? root, entry.name);
      try {
        const info = await lstat(path);
        if (!info.isFile() || info.isSymbolicLink() || info.size <= 0 || info.size > maxBytes) continue;
        rows.push({ path, name: entry.name, bytes: info.size, modified_at: info.mtimeMs });
      } catch { /* A concurrent removal is simply not offered. */ }
    }
  }
  rows.sort((left, right) => right.modified_at - left.modified_at);
  return rows.slice(0, Math.max(1, Math.min(24, Number(limit) || 8)));
}

// Built-in chibi stickers restored from the pre-migration Soyo adapter. The
// names are the same `[sticker:name]` labels the character already uses; the
// resolver never reads outside the sticker root.
const STICKER_FILES = Object.freeze({
  tea: 'soyo_chibi_tea.jpg',
  excited: 'soyo_chibi_excited.gif',
  sad: 'soyo_chibi_sad.jpg',
  speechless: 'soyo_chibi_speechless.jpg',
  clasp: 'soyo_chibi_clasp.jpg',
});
const STICKER_NAMES = Object.freeze({
  '喝茶': 'tea', '茶': 'tea',
  '兴奋': 'excited', '开心': 'excited',
  '难过': 'sad', '伤心': 'sad',
  '无语': 'speechless',
  '拜托': 'clasp', '撒娇': 'clasp',
});
const STICKER_HINTS = [
  ['excited', ['excite', 'happy', '开心', '兴奋', '激动', '耶', 'wink', '笑', '乐']],
  ['sad', ['sad', 'cry', '难过', '伤心', '哭', '委屈', '泪']],
  ['speechless', ['speechless', '无语', 'shy', '尴尬', '汗', '……', '害羞', '脸红']],
  ['clasp', ['clasp', '拜托', '求', 'please', '撒娇', '嘛', '讨']],
];

export function resolveSticker(name, root) {
  const raw = String(name ?? '').trim();
  if (!raw) return null;
  const key = raw.toLowerCase();
  const canonical = STICKER_FILES[key] ? key : STICKER_NAMES[raw];
  if (canonical) return join(root, STICKER_FILES[canonical]);
  for (const [emotion, words] of STICKER_HINTS)
    if (words.some(word => key.includes(word))) return join(root, STICKER_FILES[emotion]);
  return join(root, STICKER_FILES.tea);
}

/** Remove every sticker marker, including a truncated one at the end. */
export function stripStickerMarkers(text) {
  return String(text ?? '').replace(/\[sticker:[^\]]*(?:\]|$)/gi, '').trim();
}
