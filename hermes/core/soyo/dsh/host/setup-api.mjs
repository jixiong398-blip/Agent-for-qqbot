// SPDX-License-Identifier: MIT
// Native operator UI -> fixed private supervisor. No model tool or arbitrary URL/command.
import http from 'node:http';
import { Remote, TypertRemoteService } from '@deepseek-ai/dsh-typert-protocol';
import { openPrivate } from './platform.mjs';

export async function mountSetupApi(ctx, config) {
  const initializers = [];
  if (!config.setupApiURL) return;
  const url = new URL(config.setupApiURL);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.pathname !== '/' || url.search || url.hash || url.username || url.password)
    throw Error('Setup API must be the explicit private loopback root.');
  const file = await openPrivate(config.setupKeyFile, 129);
  let key;
  try { key = (await file.readFile('utf8')).trim(); } finally { await file.close(); }
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(key)) throw Error('Private setup credential missing.');
  const wire = (path, method = 'GET', body, csrf) => new Promise((resolve, reject) => {
    const raw = body === undefined ? undefined : Buffer.from(JSON.stringify(body));
    const request = http.request(new URL(path, url), { method, agent: false, headers: {
      Authorization: 'Bearer ' + key, Origin: url.origin,
      ...(raw ? { 'Content-Type': 'application/json', 'Content-Length': raw.length, 'X-Agent-CSRF': csrf } : {}),
    } }, response => {
      const chunks = []; let size = 0;
      response.on('data', chunk => { size += chunk.length; if (size > 1024 * 1024) response.destroy(Error('Setup response too large')); else chunks.push(chunk); });
      response.on('error', reject);
      response.on('end', () => {
        let value; try { value = JSON.parse(Buffer.concat(chunks).toString()); } catch { reject(Error('Setup response unavailable.')); return; }
        if (response.statusCode !== 200) reject(Error(value.error || 'Setup operation was not accepted.'));
        else resolve(value);
      });
    });
    request.setTimeout(30000, () => request.destroy(Error('Setup supervisor did not respond.')));
    request.on('error', () => reject(Error('Setup supervisor unavailable.'))); request.end(raw);
  });
  const post = async (path, value) => wire(path, 'POST', value, (await wire('/api/csrf')).csrf);
  class SetupApi extends TypertRemoteService {
    constructor() { super(ctx, 'botSetup'); for (const init of initializers) init.call(this); }
    view() { return wire('/api/setup'); }
    save(request) { return post('/api/setup/save', request); }
    napcat(request) { return post('/api/setup/napcat', request); }
    models(request) { return post('/api/models/list', request); }
    preset(request) { return post('/api/setup/preset', request); }
    status() { return wire('/api/status'); }
    logs(request) { return wire('/api/logs?service=' + encodeURIComponent(String(request?.service || 'manager'))); }
    service(request) {
      const operation = String(request?.operation || ''), service = String(request?.service || '');
      if (!['start', 'stop', 'restart'].includes(operation) || !['native', 'web', 'gateway', 'napcat', 'live2d'].includes(service))
        throw Error('Unsupported service operation.');
      return post('/api/services/' + operation, { service });
    }
  }
  for (const name of ['view', 'save', 'napcat', 'models', 'preset', 'status', 'logs', 'service'])
    Remote(SetupApi.prototype[name], { name, kind: 'method', static: false, private: false, addInitializer: init => initializers.push(init) });
  new SetupApi();
}
