// SPDX-License-Identifier: MIT
// The character's own drawing channel. It uses a dedicated image-slot
// credential (deployment `image_gen`, materialized as its own private key
// file) and never borrows models.action / models.character: a text-only key
// cannot draw, so sharing one would turn a clear refusal into a confusing
// upstream error.
//
// The channel is a browser-facing HTTPS endpoint behind Cloudflare, so the
// request carries an ordinary Chrome header set. A missing header set is
// rejected with HTTP 403 / error 1010 before the provider ever runs.
//
// Every outcome is one of three explicit states: `created` (real image bytes
// verified), `refused` (provider answered with text instead of an image) or
// `failed` (transport, HTTP or decoding error). Nothing here reports success
// without verified image bytes.
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, open, readdir, realpath, rename, stat } from 'node:fs/promises';
import { join, sep } from 'node:path';
import { imageType } from './outbound-image.mjs';
import { openPrivate, syncDirectory } from './platform.mjs';

// A reference-image edit takes ~183s on this channel, measured end to end, so a
// 180s default sat exactly on the failure boundary and turned a slow success
// into a paid timeout. 300s leaves real headroom; the 10 minute cap still
// bounds a stuck request.
const DEFAULT_TIMEOUT_MS = 300000;
const MAX_TIMEOUT_MS = 600000;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const MAX_REFERENCE_IMAGES = 4;
const MAX_REFERENCE_BYTES = 20 * 1024 * 1024;
const DEFAULT_SIZE = '1024x1024';

/** Browser-shaped headers; the Cloudflare front rejects a bare JSON client. */
export const IMAGE_BROWSER_HEADERS = Object.freeze({
  'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*',
  'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
  'Content-Type': 'application/json',
});

function originOf(baseUrl) {
  try { return new URL(baseUrl).origin; } catch { return ''; }
}

export function imageGenerationConfig(config) {
  const drawing = config?.image_gen;
  if (!drawing || typeof drawing !== 'object') return null;
  if (!drawing.enabled) return null;
  if (drawing.enabled !== true) return null;
  for (const key of ['base_url', 'model', 'key_file']) {
    if (typeof drawing[key] !== 'string' || !drawing[key]) return null;
  }
  return drawing;
}

/** Build the provider request without mutating the caller's arguments. */
export function imageRequest({ config, prompt, size }) {
  const origin = originOf(config.base_url);
  const body = { model: config.model, prompt, n: 1, size: size || config.size || DEFAULT_SIZE };
  return { url: config.base_url.replace(/\/+$/, '') + '/images/generations',
    headers: { ...IMAGE_BROWSER_HEADERS, ...(origin ? { Origin: origin, Referer: origin + '/' } : {}) },
    body };
}

/**
 * The channel's actual reference-image contract (probed, not guessed):
 * `POST /images/edits` with a *multipart* body. The same JSON `image` field on
 * `/images/generations` is rejected with `unexpected_image_input`, and a JSON
 * body on `/images/edits` is rejected with `images[].image_url is required`.
 * So drawing with reference images must migrate to multipart here.
 */
export function imageEditRequest({ config, prompt, size, images }) {
  const origin = originOf(config.base_url);
  return { url: config.base_url.replace(/\/+$/, '') + '/images/edits',
    headers: { ...IMAGE_BROWSER_HEADERS, ...(origin ? { Origin: origin, Referer: origin + '/' } : {}) },
    fields: { model: config.model, prompt, n: 1, size: size || config.size || DEFAULT_SIZE },
    images };
}

/** Build a multipart body with real binary image parts; no base64 inflation. */
function multipartBody({ fields, images }) {
  const boundary = '----soyo' + randomUUID().replace(/-/g, '');
  const chunks = [];
  const push = text => chunks.push(Buffer.from(text, 'utf8'));
  for (const [name, value] of Object.entries(fields)) {
    push('--' + boundary + '\r\n');
    push('Content-Disposition: form-data; name="' + name + '"\r\n\r\n');
    push(String(value) + '\r\n');
  }
  for (const image of images) {
    push('--' + boundary + '\r\n');
    push('Content-Disposition: form-data; name="image"; filename="' + image.name + '"\r\n');
    push('Content-Type: ' + image.mediaType + '\r\n\r\n');
    chunks.push(image.bytes);
    push('\r\n');
  }
  push('--' + boundary + '--\r\n');
  return { body: Buffer.concat(chunks), contentType: 'multipart/form-data; boundary=' + boundary };
}

/** Logging is diagnostics only: it must never turn a clear failure into a crash. */
function note(logger, level, ...args) {
  try { logger?.[level]?.(...args); } catch { /* A logger fault cannot fail the call. */ }
}

function safeProviderDetail(value, key) {
  let text = String(value ?? '');
  if (key) text = text.replaceAll(key, '<redacted>');
  return text.replace(/Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}/g, '<redacted>')
    .replace(/https?:\/\/\S+/g, '[endpoint]');
}

function describeHttp(status, text) {
  const detail = String(text ?? '').replace(/\s+/g, ' ').trim().slice(0, 300);
  if (status === 403 && /(^|\D)1010(\D|$)/.test(detail))
    return 'IMAGE_GEN_BLOCKED: 渠道拒绝了请求（HTTP 403 / 1010），通常是缺少完整浏览器请求头';
  if (status === 401 || status === 403) return 'IMAGE_GEN_AUTH: 画图凭据被渠道拒绝（HTTP ' + status + '）' + (detail ? '：' + detail : '');
  if (status === 429) return 'IMAGE_GEN_QUOTA: 渠道限流或额度不足（HTTP 429）' + (detail ? '：' + detail : '');
  if (status >= 500) return 'IMAGE_GEN_UPSTREAM: 渠道服务端错误（HTTP ' + status + '）' + (detail ? '：' + detail : '');
  return 'IMAGE_GEN_HTTP: 生图请求失败（HTTP ' + status + '）' + (detail ? '：' + detail : '');
}

async function writeImage({ bytes, mediaRoot, extension }) {
  const digest = createHash('sha256').update(bytes).digest('hex');
  const target = join(mediaRoot, 'generated-' + digest.slice(0, 32) + extension);
  const temporary = join(mediaRoot, '.generated-' + randomUUID() + '.tmp');
  const file = await open(temporary, 'wx', 0o600);
  try { await file.writeFile(bytes); await file.sync(); } finally { await file.close(); }
  await rename(temporary, target);
  await syncDirectory(mediaRoot);
  return { path: target, sha256: digest, bytes: bytes.length };
}

/**
 * Load reference images from the places this deployment already trusts: the
 * media root and the action workspace. A caller-supplied path is never trusted
 * as an arbitrary read: it must resolve inside one of those roots, be a regular
 * file, and carry real image magic bytes.
 */
export async function loadReferenceImages({ paths, mediaRoot, extraRoots = [], maxBytes = MAX_REFERENCE_BYTES }) {
  const list = Array.isArray(paths) ? paths.filter(item => typeof item === 'string' && item.trim()) : [];
  if (!list.length) return { images: [] };
  if (list.length > MAX_REFERENCE_IMAGES)
    return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
      message: 'IMAGE_GEN_REFERENCE: 参考图最多 ' + MAX_REFERENCE_IMAGES + ' 张' } };
  const roots = [];
  for (const root of [mediaRoot, ...extraRoots]) {
    if (typeof root !== 'string' || !root) continue;
    try { roots.push(await realpath(root)); } catch { /* An absent root grants nothing. */ }
  }
  const images = [];
  for (const [index, value] of list.entries()) {
    let real;
    try { real = await realpath(value); }
    catch { return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
      message: 'IMAGE_GEN_REFERENCE: 参考图不存在：' + String(value).slice(0, 200) } }; }
    if (!roots.some(root => real === root || real.startsWith(root + sep)))
      return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
        message: 'IMAGE_GEN_REFERENCE: 参考图不在允许的图片目录内，拒绝读取' } };
    let info;
    try { info = await stat(real); }
    catch { return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE', message: 'IMAGE_GEN_REFERENCE: 读不到参考图' } }; }
    if (!info.isFile() || info.size <= 0 || info.size > maxBytes)
      return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
        message: 'IMAGE_GEN_REFERENCE: 参考图必须是小于 ' + maxBytes + ' 字节的普通文件' } };
    const file = await open(real, 'r');
    let bytes;
    try { bytes = await file.readFile(); } finally { await file.close(); }
    const kind = imageType(bytes);
    if (!kind)
      return { error: { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
        message: 'IMAGE_GEN_REFERENCE: 参考图不是可识别的 PNG/JPEG/WebP/GIF' } };
    images.push({ name: 'reference-' + (index + 1) + kind.ext, mediaType: kind.type, bytes });
  }
  return { images };
}

/**
 * Generate one image and stage it inside the deployment media root so the
 * character's own attach tool can send it. Returns an explicit state; a
 * provider text answer is `refused`, never a fake success.
 */
export async function generateImage({ config, prompt, size, referenceImages = [], mediaRoot, signal, logger = console }) {
  const drawing = imageGenerationConfig(config);
  if (!drawing) return { state: 'failed', code: 'IMAGE_GEN_UNCONFIGURED',
    message: 'IMAGE_GEN_UNCONFIGURED: 还没有配置画图用的独立凭据（image_gen），不能画图' };
  if (typeof prompt !== 'string' || !prompt.trim()) return { state: 'failed', code: 'IMAGE_GEN_PROMPT', message: 'IMAGE_GEN_PROMPT: 需要一段明确的画面描述' };
  if (prompt.length > 4000) return { state: 'failed', code: 'IMAGE_GEN_PROMPT', message: 'IMAGE_GEN_PROMPT: 画面描述过长（上限 4000 字）' };
  const requested = size || drawing.size || DEFAULT_SIZE;
  if (!/^[1-9][0-9]{1,4}x[1-9][0-9]{1,4}$/.test(String(requested)))
    return { state: 'failed', code: 'IMAGE_GEN_SIZE', message: 'IMAGE_GEN_SIZE: 尺寸要写成 宽x高，例如 1024x1024' };
  const references = Array.isArray(referenceImages) ? referenceImages.filter(Boolean) : [];
  if (references.length > MAX_REFERENCE_IMAGES)
    return { state: 'failed', code: 'IMAGE_GEN_REFERENCE',
      message: 'IMAGE_GEN_REFERENCE: 参考图最多 ' + MAX_REFERENCE_IMAGES + ' 张' };
  const media = await realpath(mediaRoot);
  let key, keyFile;
  try {
    keyFile = await openPrivate(drawing.key_file, 4096);
    key = (await keyFile.readFile('utf8')).trim();
  } catch {
    return { state: 'failed', code: 'IMAGE_GEN_KEY', message: 'IMAGE_GEN_KEY: 读不到画图凭据文件，未发起生图请求' };
  } finally { await keyFile?.close(); }
  if (!key || !/^[\x21-\x7e]+$/.test(key)) return { state: 'failed', code: 'IMAGE_GEN_KEY', message: 'IMAGE_GEN_KEY: 画图凭据为空或含非 ASCII 字符，未发起生图请求' };
  const request = imageRequest({ config: drawing, prompt, size: requested });
  const budget = Number(drawing.timeout_ms) > 0 ? Math.min(Number(drawing.timeout_ms), MAX_TIMEOUT_MS) : DEFAULT_TIMEOUT_MS;
  const deadline = AbortSignal.timeout(budget);
  const combined = signal ? AbortSignal.any([signal, deadline]) : deadline;
  let response;
  const startedAt = Date.now();
  try {
    if (references.length) {
      const edit = imageEditRequest({ config: drawing, prompt, size: requested, images: references });
      const encoded = multipartBody({ fields: edit.fields, images: references });
      response = await fetch(edit.url, { method: 'POST', signal: combined,
        headers: { ...edit.headers, Authorization: 'Bearer ' + key, 'Content-Type': encoded.contentType },
        body: encoded.body });
    } else {
      response = await fetch(request.url, { method: 'POST', headers: { ...request.headers, Authorization: 'Bearer ' + key },
        body: JSON.stringify(request.body), signal: combined });
    }
  } catch (error) {
    const timeout = error?.name === 'TimeoutError' || deadline.aborted;
    const code = timeout ? 'IMAGE_GEN_TIMEOUT' : 'IMAGE_GEN_TRANSPORT';
    // A timeout is genuinely unknown upstream: the provider may still have
    // generated and billed the image, so never auto-retry it here.
    return { state: 'failed', code, message: code + ': ' + (timeout
      ? '等待渠道超时（' + budget + 'ms）；上游可能仍在生成，不自动重试以免重复计费'
      : '连不上生图渠道：' + safeProviderDetail(error?.message ?? error, key).slice(0, 200)) };
  }
  const text = await response.text().catch(() => '');
  if (!response.ok) {
    note(logger, 'warn', '[soyo-image] generation HTTP %d after %dms', response.status, Date.now() - startedAt);
    return { state: 'failed', code: 'IMAGE_GEN_HTTP', http_status: response.status, message: describeHttp(response.status, safeProviderDetail(text, key)) };
  }
  let payload;
  try { payload = JSON.parse(text); }
  catch { return { state: 'failed', code: 'IMAGE_GEN_RESPONSE', http_status: response.status,
    message: 'IMAGE_GEN_RESPONSE: 渠道返回了非 JSON 内容，没有拿到图片：' + safeProviderDetail(text, key).replace(/\s+/g, ' ').trim().slice(0, 200) }; }
  if (payload?.error) return { state: 'failed', code: 'IMAGE_GEN_PROVIDER', http_status: response.status,
    message: 'IMAGE_GEN_PROVIDER: 渠道返回错误：' + safeProviderDetail(payload.error.message ?? payload.error, key).slice(0, 300) };
  const entry = Array.isArray(payload?.data) ? payload.data[0] : null;
  if (!entry || typeof entry !== 'object') return { state: 'failed', code: 'IMAGE_GEN_EMPTY', http_status: response.status,
    message: 'IMAGE_GEN_EMPTY: 渠道没有返回图片数据（可能只回了文字说明）' };
  let bytes;
  if (typeof entry.b64_json === 'string' && entry.b64_json) {
    try { bytes = Buffer.from(entry.b64_json, 'base64'); }
    catch { bytes = null; }
  } else if (typeof entry.url === 'string' && entry.url) {
    let download;
    try { download = await fetch(entry.url, { headers: { 'User-Agent': IMAGE_BROWSER_HEADERS['User-Agent'] }, signal: combined }); }
    catch (error) { return { state: 'failed', code: 'IMAGE_GEN_DOWNLOAD', http_status: response.status,
      message: 'IMAGE_GEN_DOWNLOAD: 图片已生成但下载失败：' + safeProviderDetail(error?.message ?? error, key).slice(0, 200) }; }
    if (!download.ok) return { state: 'failed', code: 'IMAGE_GEN_DOWNLOAD', http_status: download.status,
      message: 'IMAGE_GEN_DOWNLOAD: 图片已生成但下载返回 HTTP ' + download.status };
    bytes = Buffer.from(await download.arrayBuffer());
  } else if (typeof entry.text === 'string' && entry.text.trim() || typeof payload?.message === 'string' && payload.message.trim()) {
    // The provider sometimes answers with prose instead of an image. That is a
    // refusal to draw, not a generated picture.
    const prose = safeProviderDetail(entry.text ?? payload.message, key).replace(/\s+/g, ' ').trim().slice(0, 300);
    return { state: 'refused', code: 'IMAGE_GEN_UPSTREAM_TEXT', http_status: response.status,
      message: 'IMAGE_GEN_UPSTREAM_TEXT: 渠道只回了文字、没有出图：' + prose };
  } else {
    return { state: 'failed', code: 'IMAGE_GEN_EMPTY', http_status: response.status,
      message: 'IMAGE_GEN_EMPTY: 响应里既没有图片数据也没有可读的错误说明' };
  }
  if (!bytes?.length) return { state: 'failed', code: 'IMAGE_GEN_EMPTY', http_status: response.status,
    message: 'IMAGE_GEN_EMPTY: 渠道返回的图片是空的' };
  if (bytes.length > MAX_IMAGE_BYTES) return { state: 'failed', code: 'IMAGE_GEN_SIZE_LIMIT', http_status: response.status,
    message: 'IMAGE_GEN_SIZE_LIMIT: 生成的图片超过 ' + MAX_IMAGE_BYTES + ' 字节上限' };
  const kind = imageType(bytes);
  if (!kind) return { state: 'failed', code: 'IMAGE_GEN_TYPE', http_status: response.status,
    message: 'IMAGE_GEN_TYPE: 返回内容不是可识别的 PNG/JPEG/WebP/GIF 图片（没有把错误响应当成图片保存）' };
  const staged = await writeImage({ bytes, mediaRoot: media, extension: kind.ext });
  note(logger, 'info', '[soyo-image] created %s bytes=%d model=%s in %dms',
    staged.path, staged.bytes, drawing.model, Date.now() - startedAt);
  return { state: 'created', ...staged, media_type: kind.type, model: drawing.model, size: requested,
    message: '图片已生成并存入媒体目录，可以用 soyo_attach_image 附在回复上。' };
}

/** Read-only details for the character: never returns the credential. */
export function imageGenerationStatus(config) {
  const drawing = imageGenerationConfig(config);
  if (!drawing) return { configured: false, base_url: '', model: '', size: '',
    note: '还没有配置独立的画图凭据（image_gen）；现在调用画图会明确失败，不会借用行动脑的 key。' };
  return { configured: true, base_url: drawing.base_url, model: drawing.model,
    size: drawing.size || DEFAULT_SIZE, timeout_ms: Number(drawing.timeout_ms) > 0 ? Number(drawing.timeout_ms) : DEFAULT_TIMEOUT_MS,
    key_file_exists: true,
    note: '使用独立的画图凭据；与行动脑、角色脑的 key 无关。' };
}

export async function imageKeyFilePresent(config) {
  const drawing = imageGenerationConfig(config);
  if (!drawing) return false;
  try { const info = await stat(drawing.key_file); return info.isFile() && info.size > 0; } catch { return false; }
}

/** The character's own long-term picture shelf, kept beside the native root. */
export function shelfRoot(config) {
  const root = config?.image_gen?.shelf_dir;
  return typeof root === 'string' && root ? root : null;
}

/**
 * Copy one already-local picture into the shelf under its content digest, so a
 * favourite survives the media-cache TTL and can be reused as a reference later.
 * The source must already live in an allowed root; nothing is downloaded here.
 */
export async function collectImage({ config, path, label, mediaRoot, extraRoots = [], maxBytes = MAX_REFERENCE_BYTES }) {
  const shelf = shelfRoot(config);
  if (!shelf) return { state: 'failed', code: 'IMAGE_SHELF_UNCONFIGURED', message: 'IMAGE_SHELF_UNCONFIGURED: 收藏目录没有配置' };
  if (typeof path !== 'string' || !path.trim())
    return { state: 'failed', code: 'IMAGE_SHELF_PATH', message: 'IMAGE_SHELF_PATH: 需要一个本机图片路径' };
  const roots = [];
  for (const root of [mediaRoot, ...extraRoots]) {
    if (typeof root !== 'string' || !root) continue;
    try { roots.push(await realpath(root)); } catch { /* absent root grants nothing */ }
  }
  let real;
  try { real = await realpath(path); }
  catch { return { state: 'failed', code: 'IMAGE_SHELF_PATH', message: 'IMAGE_SHELF_PATH: 图片不存在：' + path.slice(0, 200) } };
  if (!roots.some(root => real === root || real.startsWith(root + sep)))
    return { state: 'failed', code: 'IMAGE_SHELF_PATH', message: 'IMAGE_SHELF_PATH: 图片不在允许的目录内，拒绝收藏' };
  const info = await stat(real);
  if (!info.isFile() || info.size <= 0 || info.size > maxBytes)
    return { state: 'failed', code: 'IMAGE_SHELF_PATH', message: 'IMAGE_SHELF_PATH: 只能收藏小于 ' + maxBytes + ' 字节的普通图片文件' };
  const file = await open(real, 'r');
  let bytes;
  try { bytes = await file.readFile(); } finally { await file.close(); }
  const kind = imageType(bytes);
  if (!kind) return { state: 'failed', code: 'IMAGE_SHELF_TYPE', message: 'IMAGE_SHELF_TYPE: 不是可识别的 PNG/JPEG/WebP/GIF' };
  const digest = createHash('sha256').update(bytes).digest('hex');
  await mkdir(shelf, { recursive: true, mode: 0o700 });
  const safe = String(label ?? '').replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  const name = (safe ? safe + '-' : '') + digest.slice(0, 16) + kind.ext;
  const target = join(shelf, name), temporary = join(shelf, '.' + randomUUID() + '.tmp');
  const handle = await open(temporary, 'wx', 0o600);
  try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
  await rename(temporary, target);
  await syncDirectory(shelf);
  return { state: 'collected', path: target, name, sha256: digest, bytes: bytes.length, media_type: kind.type,
    message: '已收进收藏目录，可直接作为 reference_images 使用。' };
}

/** Read-only list of the shelf; never sends or spends anything. */
export async function shelfImages({ config, limit = 20 }) {
  const shelf = shelfRoot(config);
  if (!shelf) return { state: 'unconfigured', items: [], note: '收藏目录没有配置' };
  let names;
  try { names = await readdir(shelf); }
  catch (error) { return { state: error.code === 'ENOENT' ? 'empty' : 'unavailable', items: [], note: '收藏目录还不可读' }; }
  const bound = Math.max(1, Math.min(100, Number(limit) > 0 ? Number(limit) : 20));
  const items = [];
  for (const name of names.sort()) {
    if (!/\.(png|jpe?g|webp|gif)$/i.test(name) || name.startsWith('.')) continue;
    try {
      const full = join(shelf, name), info = await stat(full);
      if (!info.isFile()) continue;
      items.push({ name, path: full, bytes: info.size, modified_at: info.mtimeMs });
    } catch { /* A file that vanished mid-scan is simply absent. */ }
  }
  items.sort((a, b) => b.modified_at - a.modified_at);
  return { state: items.length ? 'listed' : 'empty', items: items.slice(0, bound), total: items.length };
}
