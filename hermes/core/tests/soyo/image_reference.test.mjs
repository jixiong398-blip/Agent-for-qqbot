// SPDX-License-Identifier: MIT
// Reference-image generation (image-to-image / image-edit) and the character's
// own picture shelf. Local stub provider only: no network, no provider key, no cost.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import {
  generateImage, loadReferenceImages, collectImage, shelfImages, shelfRoot,
} from '../../soyo/dsh/host/image-generation.mjs';

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const USB = PNG; // A second identical-but-distinct buffer for dedupe checks.

async function stub(handler) {
  const requests = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => {
      const body = Buffer.concat(chunks);
      requests.push({ url: req.url, method: req.method, headers: req.headers, body });
      handler(req, res, body);
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, requests, base: 'http://127.0.0.1:' + server.address().port,
    close: () => new Promise(r => server.close(r)) };
}

async function world() {
  const home = await mkdtemp(join(tmpdir(), 'soyo-refimg-'));
  const media = join(home, 'media'); await mkdir(media, { recursive: true });
  const shelf = join(media, 'shelf');
  const keyFile = join(home, 'image-gen-key');
  await writeFile(keyFile, 'sk-fixture-drawing-key\n', { mode: 0o600 });
  if (process.platform === 'win32') {
    // The image reader checks real DACLs; a POSIX mode on writeFile is not one.
    process.env.SOYO_PYTHON ||= 'python';
    process.env.SOYO_WORKER_ROOT ||= fileURLToPath(new URL('../../', import.meta.url));
    execFileSync(process.env.SOYO_PYTHON, ['-B', '-c',
      'from pathlib import Path; import sys; from soyo.platform import protect; protect(Path(sys.argv[1]))', keyFile],
    { cwd: process.env.SOYO_WORKER_ROOT, windowsHide: true });
  }
  const refPath = join(media, 'reference.png');
  await writeFile(refPath, PNG, { mode: 0o600 });
  const drawing = base => ({ enabled: true, base_url: base, model: 'gpt-image-2.5',
    size: '1024x1024', timeout_ms: 20000, key_file: keyFile, shelf_dir: shelf });
  return { home, media, shelf, keyFile, refPath, drawing };
}

test('reference images are uploaded to /images/edits as real multipart parts', async () => {
  const { media, refPath, drawing } = await world();
  const { base, requests, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ b64_json: PNG.toString('base64') }] }));
  });
  try {
    const loaded = await loadReferenceImages({ paths: [refPath], mediaRoot: media });
    assert.deepEqual(loaded.error, undefined);
    assert.equal(loaded.images.length, 1);
    assert.equal(loaded.images[0].mediaType, 'image/png');
    assert(loaded.images[0].bytes.length > 0);

    const result = await generateImage({ config: { image_gen: drawing(base) }, prompt: 'keep it, make it blue',
      referenceImages: loaded.images, mediaRoot: media, logger: {} });
    assert.equal(result.state, 'created', JSON.stringify(result));

    const sent = requests[0];
    assert.equal(sent.method, 'POST');
    assert.match(sent.url, /\/images\/edits$/);
    assert.match(sent.headers['content-type'], /^multipart\/form-data; boundary=/);
    assert.equal(sent.headers.authorization, 'Bearer sk-fixture-drawing-key');
    assert.ok(sent.headers.origin && sent.headers.referer);
    assert.match(sent.body.toString("latin1"), /name="prompt"/);
    assert.match(sent.body.toString("latin1"), /name="image"; filename="reference-1\.png"/);
    assert.match(sent.body.toString("latin1"), /name="model"/);
    assert.match(sent.body.toString("latin1"), /name="size"/);
    // The raw PNG bytes travel as-is, not base64-inflated.
    assert(sent.body.includes(PNG), 'the uploaded part must carry the original image bytes');
  } finally { await close(); }
});

test('no reference images keeps the plain generations endpoint', async () => {
  const { media, drawing } = await world();
  const { base, requests, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ b64_json: PNG.toString('base64') }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base) }, prompt: 'a cat',
      mediaRoot: media, logger: {} });
    assert.equal(result.state, 'created');
    assert.match(requests[0].url, /\/images\/generations$/);
    assert.match(requests[0].headers['content-type'], /^application\/json/);
  } finally { await close(); }
});

test('a reference image outside the trusted roots is refused before any request', async () => {
  const { media, home } = await world();
  const outside = join(home, 'outside.png');
  await writeFile(outside, PNG, { mode: 0o600 });
  const loaded = await loadReferenceImages({ paths: [outside], mediaRoot: media });
  assert.equal(loaded.error.code, 'IMAGE_GEN_REFERENCE');
  assert.match(loaded.error.message, /不在允许的图片目录内/);
});

test('a reference that is not a real image is refused', async () => {
  const { media, home } = await world();
  const fake = join(media, 'fake.png');
  await writeFile(fake, Buffer.from('<html>not an image</html>'), { mode: 0o600 });
  const loaded = await loadReferenceImages({ paths: [fake], mediaRoot: media });
  assert.equal(loaded.error.code, 'IMAGE_GEN_REFERENCE');
  assert.match(loaded.error.message, /不是可识别的/);
});

test('more than four reference images is refused', async () => {
  const { media, refPath } = await world();
  const loaded = await loadReferenceImages({ paths: Array(5).fill(refPath), mediaRoot: media });
  assert.equal(loaded.error.code, 'IMAGE_GEN_REFERENCE');
  assert.match(loaded.error.message, /最多 4 张/);
});

test('the action workspace is an accepted reference root, nothing else is', async () => {
  const { media, home } = await world();
  const actionDir = join(home, 'action'); await mkdir(actionDir, { recursive: true });
  const inside = join(actionDir, 'shot.png'); await writeFile(inside, PNG, { mode: 0o600 });
  const ok = await loadReferenceImages({ paths: [inside], mediaRoot: media, extraRoots: [actionDir] });
  assert.equal(ok.images.length, 1);
  const denied = await loadReferenceImages({ paths: [inside], mediaRoot: media });
  assert.equal(denied.error.code, 'IMAGE_GEN_REFERENCE');
});

test('a picture the owner sent over QQ can be used as a reference', async () => {
  // Real defect: the owner sent the official portrait over QQ, it was stored in
  // the attachment store, and soyo_image_collect refused it. She then drew from
  // her own drifted self-portrait and the result stopped resembling the
  // character. The attachment store must be a legal reference root.
  const { media, home } = await world();
  const attachments = join(home, 'attachments/v1/objects/ab');
  await mkdir(attachments, { recursive: true });
  const portrait = join(attachments, 'official-portrait.png');
  await writeFile(portrait, PNG, { mode: 0o400 });

  const denied = await loadReferenceImages({ paths: [portrait], mediaRoot: media,
    extraRoots: [join(home, 'development')] });
  assert.equal(denied.error.code, 'IMAGE_GEN_REFERENCE', 'the old roots refuse the portrait');

  const ok = await loadReferenceImages({ paths: [portrait], mediaRoot: media,
    extraRoots: [join(home, 'development'), join(home, 'attachments')] });
  assert.equal(ok.images.length, 1);
  assert.deepEqual(ok.images[0].bytes, PNG);
});

test('an owner-sent picture can be collected into the shelf', async () => {
  const { media, home, shelf, drawing } = await world();
  const attachments = join(home, 'attachments/v1/objects/ab');
  await mkdir(attachments, { recursive: true });
  const portrait = join(attachments, 'official-portrait.png');
  await writeFile(portrait, PNG, { mode: 0o400 });
  const config = { image_gen: drawing('http://127.0.0.1:1') };
  const collected = await collectImage({ config, path: portrait, label: 'official',
    mediaRoot: media, extraRoots: [join(home, 'attachments')] });
  assert.equal(collected.state, 'collected', JSON.stringify(collected));
  assert(collected.path.startsWith(shelf));
});

test('widening the roots still refuses files outside every root', async () => {
  // The attachment store must not become a way to read arbitrary files.
  const { media, home } = await world();
  const outside = join(home, 'private/channel.json');
  await mkdir(join(home, 'private'), { recursive: true });
  await writeFile(outside, '{"token":"secret"}', { mode: 0o600 });
  const loaded = await loadReferenceImages({ paths: [outside], mediaRoot: media,
    extraRoots: [join(home, 'attachments')] });
  assert.equal(loaded.error.code, 'IMAGE_GEN_REFERENCE');
  assert.match(loaded.error.message, /不在允许的图片目录内/);
});

test('a collected favourite survives as a reusable reference', async () => {
  const { media, shelf, refPath, drawing } = await world();
  const config = { image_gen: drawing('http://127.0.0.1:1') };
  assert.equal(shelfRoot(config), shelf);

  const collected = await collectImage({ config, path: refPath, label: 'Soyo official', mediaRoot: media });
  assert.equal(collected.state, 'collected', JSON.stringify(collected));
  assert(collected.path.startsWith(shelf));
  assert.match(collected.name, /^Soyo-official-[a-f0-9]{16}\.png$/);
  assert.deepEqual(await readFile(collected.path), PNG);

  const listed = await shelfImages({ config });
  assert.equal(listed.state, 'listed');
  assert.equal(listed.total, 1);
  assert.equal(listed.items[0].path, collected.path);

  // The saved copy is now a legal reference input.
  const loaded = await loadReferenceImages({ paths: [collected.path], mediaRoot: media });
  assert.equal(loaded.images.length, 1);
});

test('collecting the same picture twice dedupes instead of duplicating', async () => {
  const { media, shelf, refPath, drawing } = await world();
  const config = { image_gen: drawing('http://127.0.0.1:1') };
  const first = await collectImage({ config, path: refPath, mediaRoot: media });
  const copy = join(media, 'copy.png'); await writeFile(copy, USB, { mode: 0o600 });
  const second = await collectImage({ config, path: copy, mediaRoot: media });
  assert.equal(second.sha256, first.sha256);
  const names = (await readdir(shelf)).filter(n => !n.startsWith('.'));
  assert.equal(names.length, 1, 'identical bytes must not create two shelf entries');
});

test('collecting refuses a source outside the trusted roots', async () => {
  const { media, home, drawing } = await world();
  const outside = join(home, 'private-source.png');
  await writeFile(outside, PNG, { mode: 0o600 });
  const result = await collectImage({ config: { image_gen: drawing('http://127.0.0.1:1') },
    path: outside, mediaRoot: media });
  assert.equal(result.code, 'IMAGE_SHELF_PATH');
});

test('the host hands the attachment store to the drawing tools', async () => {
  // The roots live in one helper so load and collect cannot drift apart, and so
  // the attachment store cannot be dropped by a later refactor.
  const source = await readFile(new URL('../../soyo/dsh/host/qq-native.mjs', import.meta.url), 'utf8');
  assert.match(source, /const referenceRoots = config => \[config\.development_home, config\.action_workdir,/);
  assert.match(source, /config\.attachment_root/);
  assert.match(source, /extraRoots: referenceRoots\(config\)/);
  const uses = source.match(/extraRoots: referenceRoots\(config\)/g) || [];
  assert.equal(uses.length, 1, 'collection keeps the same root helper');
  assert.match(source, /roots: referenceRoots/);
  const drawing = await readFile(new URL('../../soyo/dsh/host/drawing-tools.mjs', import.meta.url), 'utf8');
  assert.match(drawing, /extraRoots: roots\(config\)/);
  assert.match(drawing, /sceneImagePaths/);
});

test('the deployment renders an attachment root for those tools', async () => {
  const source = await readFile(new URL('../../soyo/app/render.py', import.meta.url), 'utf8');
  assert.match(source, /"attachment_root": str\(home \/ "attachments"\)/);
});

test('an unconfigured shelf reports that plainly instead of inventing one', async () => {
  const status = await shelfImages({ config: {} });
  assert.equal(status.state, 'unconfigured');
  assert.deepEqual(status.items, []);
  const collected = await collectImage({ config: {}, path: '/tmp/x.png', mediaRoot: '/tmp' });
  assert.equal(collected.code, 'IMAGE_SHELF_UNCONFIGURED');
});
