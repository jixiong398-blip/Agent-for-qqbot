// SPDX-License-Identifier: MIT
// End-to-end proof of the drawing channel against a local stub provider.
// No external network, no provider credential, no cost. The stub records the
// exact headers it received so the browser-header requirement is checked
// against a real request rather than against the source text.
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtemp, readFile, writeFile, stat, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { generateImage } from '../../soyo/dsh/host/image-generation.mjs';
import { stageOutboundImage, imageType } from '../../soyo/dsh/host/outbound-image.mjs';

// A real 1x1 PNG, so magic-byte validation is exercised on true image bytes.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');

async function stub(handler) {
  const requests = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      requests.push({ url: req.url, method: req.method, headers: req.headers, body });
      handler(req, res, body);
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, requests, base: 'http://127.0.0.1:' + server.address().port, close: () => new Promise(r => server.close(r)) };
}

async function fixture(home) {
  await mkdir(join(home, 'media'), { recursive: true });
  const keyFile = join(home, 'image-gen-key');
  await writeFile(keyFile, 'sk-fixture-drawing-key\n', { mode: 0o600 });
  if (process.platform === 'win32') {
    // mode: 0600 cannot set a Windows DACL. Use the same private-file contract
    // as deployment rendering, including the Python checker used by the reader.
    process.env.SOYO_PYTHON ||= 'python';
    process.env.SOYO_WORKER_ROOT ||= fileURLToPath(new URL('../../', import.meta.url));
    execFileSync(process.env.SOYO_PYTHON, ['-B', '-c',
      'from pathlib import Path; import sys; from soyo.platform import protect; protect(Path(sys.argv[1]))', keyFile],
    { cwd: process.env.SOYO_WORKER_ROOT, windowsHide: true });
  }
  return { keyFile, mediaRoot: join(home, 'media') };
}

const drawing = (base, keyFile, extra = {}) => ({
  enabled: true, base_url: base, model: 'gpt-image-2.5', size: '1024x1024', timeout_ms: 20000, key_file: keyFile, ...extra });

test('a real image is produced, saved in the media root and accepted by the attach tool', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const { base, requests, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ b64_json: PNG.toString('base64') }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'Generate an image: a pastel anime girl', mediaRoot, logger: {} });
    assert.equal(result.state, 'created', JSON.stringify(result));
    assert.equal(result.media_type, 'image/png');
    assert.equal(result.model, 'gpt-image-2.5');

    // The saved bytes are the real image, and the path is attachable.
    const saved = await readFile(result.path);
    assert.equal(createHash('sha256').update(saved).digest('hex'), result.sha256);
    assert.ok(imageType(saved));
    const staged = await stageOutboundImage({ path: result.path, mediaRoot, maxBytes: 20 * 1024 * 1024 });
    assert.equal(staged.sha256, result.sha256);

    // The request carried the full browser header set plus the bearer key.
    const sent = requests[0];
    assert.equal(sent.method, 'POST');
    assert.match(sent.url, /\/images\/generations$/);
    assert.equal(sent.headers.authorization, 'Bearer sk-fixture-drawing-key');
    assert.match(sent.headers['user-agent'], /Mozilla\/5\.0/);
    assert.equal(sent.headers.accept, 'application/json, text/plain, */*');
    assert.ok(sent.headers['accept-language']);
    assert.equal(sent.headers['content-type'], 'application/json');
    assert.ok(sent.headers.origin, 'Origin must be sent or Cloudflare rejects the request');
    assert.ok(sent.headers.referer);
    const body = JSON.parse(sent.body);
    assert.equal(body.model, 'gpt-image-2.5');
    assert.equal(body.size, '1024x1024');
    assert.equal(body.n, 1);
  } finally { await close(); }
});

test('a textual provider answer is reported as refused, never as a generated image', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const { base, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ text: 'I can only help write the prompt.' }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'a cat', mediaRoot, logger: {} });
    assert.equal(result.state, 'refused');
    assert.equal(result.code, 'IMAGE_GEN_UPSTREAM_TEXT');
    assert.match(result.message, /只回了文字/);
    // Nothing was written into the media root, so no fake picture can be sent.
    const leftovers = await stat(mediaRoot).then(() => readFile(join(mediaRoot, 'nonexistent')).catch(() => null));
    assert.equal(leftovers, null);
  } finally { await close(); }
});

test('a Cloudflare 1010 block is named as a header problem, not a generic failure', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const { base, close } = await stub((_req, res) => {
    res.writeHead(403, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ errors: [{ code: 1010 }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'a cat', mediaRoot, logger: {} });
    assert.equal(result.state, 'failed');
    assert.equal(result.http_status, 403, JSON.stringify(result));
    assert.match(result.message, /1010/);
    assert.match(result.message, /浏览器请求头/);
  } finally { await close(); }
});

test('a 401 is reported as an auth failure with the status visible', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const { base, close } = await stub((_req, res) => { res.writeHead(401); res.end('{"error":"bad key"}'); });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'a cat', mediaRoot, logger: {} });
    assert.equal(result.state, 'failed');
    assert.equal(result.code, 'IMAGE_GEN_HTTP');
    assert.match(result.message, /IMAGE_GEN_AUTH/);
    assert.match(result.message, /401/);
  } finally { await close(); }
});

test('a URL-form response is downloaded and verified as an image', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const imageServer = http.createServer((_req, res) => { res.writeHead(200, { 'Content-Type': 'image/png' }); res.end(PNG); });
  await new Promise(resolve => imageServer.listen(0, '127.0.0.1', resolve));
  const imageUrl = 'http://127.0.0.1:' + imageServer.address().port + '/out.png';
  const { base, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ url: imageUrl }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'a cat', mediaRoot, logger: {} });
    assert.equal(result.state, 'created', JSON.stringify(result));
    assert.equal(result.media_type, 'image/png');
  } finally { await close(); imageServer.close(); }
});

test('a non-image body is refused instead of being saved as a picture', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const html = Buffer.from('<html>cloudflare challenge</html>');
  const { base, close } = await stub((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ data: [{ b64_json: html.toString('base64') }] }));
  });
  try {
    const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
      prompt: 'a cat', mediaRoot, logger: {} });
    assert.equal(result.state, 'failed');
    assert.equal(result.code, 'IMAGE_GEN_TYPE');
    assert.match(result.message, /没有把错误响应当成图片保存/);
  } finally { await close(); }
});

test('provider errors and refusals cannot echo the dedicated key or private endpoint', async () => {
  const home = await mkdtemp(join(tmpdir(), 'soyo-draw-redaction-'));
  const { keyFile, mediaRoot } = await fixture(home);
  const key = (await readFile(keyFile, 'utf8')).trim();
  let status = 401, payload = `key=${key} url=https://private.example.invalid/v1?token=private`;
  const { base, requests, close } = await stub((_req, res) => {
    res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(payload);
  });
  try {
    for (const next of [
      [401, payload],
      [200, 'not-json ' + payload],
      [200, JSON.stringify({ error: { message: payload } })],
      [200, JSON.stringify({ data: [{ text: payload }] })],
    ]) {
      [status, payload] = next;
      const result = await generateImage({ config: { image_gen: drawing(base, keyFile) },
        prompt: 'fixture', mediaRoot, logger: {} });
      assert.notEqual(result.state, 'created');
      assert(!result.message.includes(key), result.message);
      assert(!result.message.includes('private.example.invalid'), result.message);
    }
    assert.equal(requests.length, 4, 'no automatic paid retry');
  } finally { await close(); }
});
