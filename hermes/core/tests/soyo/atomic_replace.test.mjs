// SPDX-License-Identifier: MIT
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { replaceFile } from '../../soyo/dsh/host/atomic-replace.mjs';

test('transient Windows replacement denial retries the same local rename only', async () => {
  const waits = [], calls = [];
  await replaceFile('pending', 'selected', { windows: true, wait: async ms => waits.push(ms),
    move: async (...args) => { calls.push(args); if (calls.length < 3) throw Object.assign(Error('busy'), { code: 'EPERM' }); } });
  assert.deepEqual(calls, Array.from({ length: 3 }, () => ['pending', 'selected']));
  assert.deepEqual(waits, [10, 20]);
});

test('non-Windows failures and non-sharing errors fail immediately unchanged', async () => {
  for (const [windows, code] of [[false, 'EPERM'], [true, 'ENOSPC'], [true, 'ENOENT']]) {
    const fault = Object.assign(Error('fixture'), { code });
    let attempts = 0;
    await assert.rejects(replaceFile('pending', 'selected', { windows,
      wait: async () => assert.fail('must not retry'), move: async () => { attempts++; throw fault; } }), error => error === fault);
    assert.equal(attempts, 1);
  }
});

test('permanent sharing denial has a finite budget and does not delete either file', async () => {
  const waits = [], fault = Object.assign(Error('fixture'), { code: 'EACCES' });
  let attempts = 0;
  await assert.rejects(replaceFile('pending', 'selected', { windows: true, wait: async ms => waits.push(ms),
    move: async () => { attempts++; throw fault; } }), error => error === fault);
  assert.equal(attempts, 6);
  assert.deepEqual(waits, [10, 20, 40, 80, 160]);
});

test('actual NTFS replacement settles after an incompatible reader closes', {
  skip: process.platform !== 'win32' ? 'Windows delete-sharing contract' : false, timeout: 10000,
}, async () => {
  const root = await mkdtemp(join(tmpdir(), 'atomic-replace-'));
  const target = join(root, 'receipt.json'), pending = join(root, 'pending.json');
  await writeFile(target, 'old'); await writeFile(pending, 'new');
  const child = spawn(process.env.SOYO_PYTHON || 'python', ['-B', '-u', '-c',
    'import sys;f=open(sys.argv[1],"rb");print("ready",flush=True);sys.stdin.read(1);f.close()', target],
    { stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
  let timer;
  try {
    await Promise.race([once(child.stdout, 'data'), once(child, 'error').then(([error]) => { throw error; })]);
    assert.equal(await readFile(target, 'utf8'), 'old');
    timer = setTimeout(() => child.stdin.end('x'), 50);
    await replaceFile(pending, target);
    assert.equal(await readFile(target, 'utf8'), 'new');
  } finally {
    clearTimeout(timer);
    if (!child.stdin.destroyed && !child.stdin.writableEnded) child.stdin.end('x');
    child.kill();
  }
});
