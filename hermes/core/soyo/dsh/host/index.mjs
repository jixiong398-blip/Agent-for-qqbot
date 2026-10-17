// SPDX-License-Identifier: MIT
// Local carrier over the official Web app. Native cookies/Host fence stay in charge.
import http from 'node:http';
import { open } from 'node:fs/promises';
import { constants } from 'node:fs';
import { timingSafeEqual } from 'node:crypto';
import z from '@deepseek-ai/schemastery';
import { openPrivate } from './platform.mjs';
import { trustedUiHost, trustedUiPeer } from './ui-access.mjs';
import { mountSetupApi } from './setup-api.mjs';

export const name = 'soyo-host-boundary';
export const inject = ['webServer', 'connection'];
export const Config = z.object({
  host: z.string().required(),
  port: z.natural().min(1).max(65535).required(),
  accessKeyFile: z.string().required(),
  requireAccessKey: z.boolean().default(true),
  remoteSettings: z.boolean().default(false),
  setupApiURL: z.string().default(''),
  setupKeyFile: z.string().default(''),
});

const LOGIN = `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent-for-qqbot · DSH 登录</title><style>body{font-family:system-ui;background:#17191e;color:#eee;max-width:420px;margin:15vh auto;padding:24px}input,button{box-sizing:border-box;width:100%;padding:12px;margin-top:16px}small{display:block;margin-top:18px;color:#aab}</style>
<h1>Agent-for-qqbot · DSH</h1><p>请输入此实例的 DSH 独立访问密钥。远程访问须使用受限的加密网络。</p>
<form method="post" action="/soyo-login"><input type="password" name="key" autocomplete="current-password" required maxlength="128" aria-label="DSH 访问密钥"><button>进入 DSH 原生面板</button></form>
<small>登录后使用 DSH 原生签名会话，不把密钥放入地址。</small></html>`;

async function readKey(path) {
  const file = await openPrivate(path, 129);
  try {
    const stat = await file.stat();
    if (stat.size < 32) throw new Error('Unsafe DSH access-key file.');
    const key = (await file.readFile('utf8')).trim();
    if (!/^[A-Za-z0-9_-]{32,128}$/.test(key)) throw new Error('Invalid DSH access-key file.');
    return Buffer.from(key);
  } finally { await file.close(); }
}

function reply(res, status, body = '') {
  res.writeHead(status, {
    'Content-Type': status === 401 && body === LOGIN ? 'text/html; charset=utf-8' : 'text/plain; charset=utf-8',
    // no-referrer turns Chromium form-navigation Origin into "null", breaking strict same-origin POST.
    'Cache-Control': 'no-store', 'Referrer-Policy': body === LOGIN ? 'same-origin' : 'no-referrer',
    'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
  });
  res.end(body);
}

function carrierHeaders(original) {
  const headers = { ...original };
  for (const key of Object.keys(headers)) {
    if (key === 'forwarded' || key.startsWith('x-forwarded-') || key === 'proxy-authorization') delete headers[key];
  }
  // In particular preserve Host, Origin and Cookie; never forge admission or mint API auth here.
  return headers;
}

export async function apply(ctx, config) {
  await mountSetupApi(ctx, config);
  if (process.platform === 'win32') {
    const forwardBreak = () => process.emit('SIGINT');
    process.on('SIGBREAK', forwardBreak);
    ctx.effect(() => () => process.off('SIGBREAK', forwardBreak));
  }
  if (!trustedUiHost(config.host)) {
    throw new Error('DSH ingress must bind local loopback, never remote or all interfaces.');
  }
  if (ctx.webServer.host !== '127.0.0.1' || config.port === ctx.webServer.port) {
    throw new Error('DSH upstream must be the separate native loopback listener.');
  }
  const requireAccessKey = config.requireAccessKey !== false;
  const trustedPeer = address => trustedUiPeer(address, config.host);
  const key = requireAccessKey ? await readKey(config.accessKeyFile) : undefined;
  const authority = config.host + ':' + config.port;
  const origin = 'http://' + authority;
  const localPort = ctx.webServer.port;
  // Stock ui-settings intentionally disables Host persistence outside loopback.
  // Only the profile-scoped native client patch consumes this deployment opt-in.
  // It does not change Remote's host facts or replace native API admission.
  if (config.remoteSettings) ctx.effect(() => ctx.on('webserver/index-inject', rows => {
    rows.push({ kind: 'global', name: '__SOYO_DSH_REMOTE_SETTINGS__', value: { enabled: true, origin } });
  }));
  // This capability is kept inside the trusted host, never printed or placed in a network URL.
  const nativeLaunchPath = new URL(ctx.connection.authenticatedUrl('http://127.0.0.1/')).search;
  const sockets = new Set();
  let attempts = 0, windowStart = Date.now();

  const handler = async (req, res) => {
    if (!trustedPeer(req.socket.remoteAddress) || req.headers.host !== authority || req.url?.startsWith('/') !== true || req.url.startsWith('//')) {
      reply(res, 403, 'Forbidden authority.'); return;
    }
    const path = new URL(req.url, origin);
    // The upstream query-token bootstrap is deliberately not published at this ingress.
    if (path.searchParams.has('token')) { reply(res, 400, 'Credentials must not be placed in URLs.'); return; }
    if (path.pathname === '/soyo-login') {
      if (!requireAccessKey) { reply(res, 404); return; }
      if (req.method !== 'POST') { reply(res, 405); return; }
      if (req.headers.origin !== origin || req.headers['sec-fetch-site'] === 'cross-site') { reply(res, 403); return; }
      if (req.headers['content-type']?.split(';', 1)[0].trim().toLowerCase() !== 'application/x-www-form-urlencoded' || Number(req.headers['content-length'] || 0) > 1024) {
        reply(res, 415); return;
      }
      if (Date.now() - windowStart > 60000) { attempts = 0; windowStart = Date.now(); }
      if (++attempts > 30) { reply(res, 429, 'Retry later.'); return; }
      const chunks = [];
      let size = 0;
      req.setTimeout(5000, () => req.destroy());
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 1024) { reply(res, 413); req.destroy(); return; }
        chunks.push(chunk);
      }
      req.setTimeout(0);
      const form = new URLSearchParams(Buffer.concat(chunks).toString('utf8'));
      const candidate = Buffer.from(form.get('key') || '');
      if (form.size !== 1 || form.getAll('key').length !== 1 || candidate.length !== key.length || !timingSafeEqual(candidate, key)) {
        reply(res, 401, 'Invalid DSH access key.'); return;
      }
      // Only after a same-origin key POST, let native Connection mint its own authority-bound cookie.
      // Synthetic request stays in process: no token URL, no proxy log, no custom owner/session identity.
      ctx.connection.authorizeIndex({ method: 'GET', url: '/' + nativeLaunchPath, headers: req.headers }, res);
      return;
    }
    const rejection = ctx.connection.requestRejection(req);
    if (rejection !== undefined) {
      // Direct local entry: the native Host/Origin fence must already
      // have passed (401, never 403). Bootstrap only the index, never an API/WS.
      if (!requireAccessKey && rejection === 401 && req.method === 'GET' && path.pathname === '/') {
        ctx.connection.authorizeIndex({ method: 'GET', url: '/' + nativeLaunchPath, headers: req.headers }, res);
        return;
      }
      reply(res, rejection, rejection === 401 && req.method === 'GET' && path.pathname === '/' ? LOGIN : 'Authentication required.');
      return;
    }
    const upstream = http.request({ hostname: '127.0.0.1', port: localPort, path: req.url, method: req.method,
      headers: carrierHeaders(req.headers), agent: false }, response => {
      res.writeHead(response.statusCode, response.headers);
      response.on('error', () => res.destroy());
      response.pipe(res);
    });
    upstream.on('error', () => { if (res.headersSent) res.destroy(); else reply(res, 502, 'DSH unavailable.'); });
    req.on('aborted', () => upstream.destroy());
    res.on('close', () => upstream.destroy());
    req.pipe(upstream);
  };
  const server = http.createServer((req, res) => {
    handler(req, res).catch(() => { if (res.headersSent) res.destroy(); else reply(res, 400, 'Request rejected.'); });
  });
  // Native Typert streams use a shared authenticated mux WebSocket, not only HTTP/SSE.
  server.on('upgrade', (req, socket, head) => {
    if (!trustedPeer(req.socket.remoteAddress) || req.headers.host !== authority || req.url !== '/api/remote.mux' ||
        req.method !== 'GET' || ctx.connection.requestRejection(req) !== undefined) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return;
    }
    const upstream = http.request({ hostname: '127.0.0.1', port: localPort, path: req.url,
      method: 'GET', headers: carrierHeaders(req.headers), agent: false });
    upstream.on('upgrade', (response, peer, upstreamHead) => {
      if (socket.destroyed) { peer.destroy(); return; }
      const lines = ['HTTP/1.1 101 Switching Protocols'];
      for (let i = 0; i < response.rawHeaders.length; i += 2) lines.push(response.rawHeaders[i] + ': ' + response.rawHeaders[i + 1]);
      socket.write(lines.join('\r\n') + '\r\n\r\n');
      if (upstreamHead.length) socket.write(upstreamHead);
      if (head.length) peer.write(head);
      peer.on('error', () => socket.destroy());
      socket.on('error', () => peer.destroy());
      socket.on('close', () => peer.destroy());
      peer.on('close', () => socket.destroy());
      socket.pipe(peer).pipe(socket);
    });
    upstream.on('response', response => { response.resume(); socket.end('HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n'); });
    upstream.on('error', () => socket.destroy());
    socket.on('close', () => upstream.destroy());
    socket.on('error', () => upstream.destroy());
    upstream.end();
  });
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  server.maxConnections = 64;
  server.headersTimeout = 10000;
  server.requestTimeout = 30000;
  ctx.effect(() => async () => {
    const closed = new Promise(resolve => server.close(resolve));
    for (const socket of sockets) socket.destroy();
    await closed;
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(config.port, config.host, () => { server.off('error', reject); resolve(); });
  });
  server.on('error', () => ctx.logger.error('DSH local listener failed.'));
  ctx.logger.info('DSH native local ingress ready (credentials withheld).');
}
