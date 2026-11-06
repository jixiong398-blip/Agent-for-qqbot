// SPDX-License-Identifier: MIT
// Guards a silent-sync hazard: an over-broad ignore rule can drop a whole
// source directory or a new manifest without any error, so the Win checkout
// (and any public snapshot exported from here) is quietly incomplete.
import assert from 'node:assert/strict';
import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const inWorktree = existsSync(resolve(root, '.git'));
const skip = inWorktree ? false : 'not a git worktree (deployed bundle)';
const BUILD_ONLY = /(__pycache__|\.pytest_cache|node_modules|\.pyc$)/;
// Generated on the target machine (platform-specific optional deps), not source.
const GENERATED = new Set(['core/soyo/dsh/host/runtime-lock.json']);

test('no source directory under core/ is silently ignored', { skip }, () => {
  const out = execFileSync(
    'git', ['ls-files', '--others', '--ignored', '--exclude-standard', '--directory', 'core'],
    { cwd: root, encoding: 'utf8' },
  );
  const ignored = out.split('\n').map(line => line.trim()).filter(Boolean)
    .filter(path => !BUILD_ONLY.test(path) && !GENERATED.has(path));
  assert.deepEqual(ignored, [], `ignored source paths would not sync: ${ignored.join(', ')}`);
});

test('gitignore keeps no global *.json rule', { skip }, () => {
  const lines = readFileSync(resolve(root, '.gitignore'), 'utf8').split(/\r?\n/).map(line => line.trim());
  assert.equal(lines.includes('*.json'), false, 'a global *.json rule hides new manifests');
});
