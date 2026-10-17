// SPDX-License-Identifier: MIT
// POSIX ownership/UDS and Windows DACL/loopback adapters. No authentication bypass.
import { constants } from 'node:fs';
import { open, lstat, unlink, chmod } from 'node:fs/promises';
import { isAbsolute, dirname } from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execute = promisify(execFile);
export const windows = process.platform === 'win32';
export const uid = () => typeof process.getuid === 'function' ? process.getuid() : null;
export const isRoot = () => uid() === 0;
export const publicMode = mode => !windows && Boolean(mode & 0o077);
export const operatorEnabled = config => Boolean(config.operator_ui_enabled || config.direct_root && isRoot());
const checkedACL = new Map();

export function workerEnvironment(extra = {}) {
  const keys = new Set(['PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
    'LOCALAPPDATA', 'APPDATA', 'USERPROFILE', 'HOME', 'LANG', 'LC_ALL', 'SOYO_PYTHON']);
  return { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => keys.has(key.toUpperCase()))),
    ...(process.env.SOYO_WORKER_ROOT ? { PYTHONPATH: process.env.SOYO_WORKER_ROOT } : {}),
    PYTHONDONTWRITEBYTECODE: '1', PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', ...extra };
}

export async function openPrivate(path, maxBytes = 2 * 1024 * 1024) {
  if (!isAbsolute(path)) throw Error('Explicit absolute private path required');
  const before = await lstat(path);
  if (!before.isFile() || before.isSymbolicLink()) throw Error('Private regular file required');
  const file = await open(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const info = await file.stat();
    if (!info.isFile() || info.ino !== before.ino || info.size > maxBytes ||
        publicMode(info.mode) || (!windows && !isRoot() && info.uid !== uid())) throw Error('Private file rejected');
    if (windows) {
      const stamp = `${info.ino}:${info.ctimeMs}:${info.size}`;
      if (checkedACL.get(path) !== stamp) {
        if (!process.env.SOYO_PYTHON) throw Error('Private-file ACL checker not configured');
        await execute(process.env.SOYO_PYTHON, ['-B', '-m', 'soyo.platform', 'check-private', path],
          { env: workerEnvironment(), timeout: 15000, maxBuffer: 4096, windowsHide: true });
        if (checkedACL.size > 4096) checkedACL.clear();
        checkedACL.set(path, stamp);
      }
    }
    return file;
  } catch (error) { await file.close(); throw error; }
}

export async function syncDirectory(path) {
  if (windows) return false; // File fsync + atomic rename; no POSIX directory-fsync claim on NTFS.
  const directory = await open(path, 'r');
  try { await directory.sync(); } finally { await directory.close(); }
  return true;
}

export function endpointOptions(config, name, path = '/') {
  const address = config[`${name}_url`];
  if (address) {
    const url = new URL(address);
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
        url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname))
      throw Error('Private endpoint must be an explicit clean loopback URL');
    return { hostname: '127.0.0.1', port: Number(url.port), path };
  }
  const socket = name === 'host' ? config.host_socket : config[`${name}_socket`];
  if (windows || !isAbsolute(socket ?? '')) throw Error('Private endpoint not configured');
  return { socketPath: socket, path };
}

export async function listenPrivate(server, config, name) {
  const endpoint = endpointOptions(config, name);
  if (endpoint.socketPath) {
    try {
      const info = await lstat(endpoint.socketPath);
      if (!info.isSocket() || (!isRoot() && info.uid !== uid())) throw Error('Unsafe socket');
      // A live listener must never be detached; clients fail closed on unknown state.
      const { createConnection } = await import('node:net');
      const live = await new Promise(resolve => {
        const socket = createConnection(endpoint.socketPath);
        socket.once('connect', () => { socket.destroy(); resolve(true); });
        socket.once('error', error => resolve(error.code !== 'ECONNREFUSED' && error.code !== 'ENOENT'));
        socket.setTimeout(1500, () => { socket.destroy(); resolve(true); });
      });
      if (live) throw Error('Private socket already owned or unavailable');
      await unlink(endpoint.socketPath);
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    const done = () => { server.off('error', reject); resolve(); };
    endpoint.socketPath ? server.listen(endpoint.socketPath, done) : server.listen(endpoint.port, endpoint.hostname, done);
  });
  if (endpoint.socketPath) await chmod(endpoint.socketPath, 0o600);
}
