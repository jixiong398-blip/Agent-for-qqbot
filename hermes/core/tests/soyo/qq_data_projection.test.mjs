// SPDX-License-Identifier: MIT
// Ambient QQ projection must remain in native corpus/data, not DSH history.
import assert from 'node:assert/strict';
import { copyFile, mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

// The source module is exercised from an isolated directory so its DSH peer
// imports resolve from the already-installed private runtime dependency tree;
// no service, model, session store, or QQ writer is started.
const sourceRoot = new URL('../../soyo/dsh/host/', import.meta.url);
const probeRoot = await mkdtemp(join(tmpdir(), 'soyo-qq-data-projection-'));
const hostRoot = join(probeRoot, 'host');
await mkdir(hostRoot, { recursive: true });
await copyFile(new URL('qq-data.mjs', sourceRoot), join(hostRoot, 'qq-data.mjs'));
await copyFile(new URL('platform.mjs', sourceRoot), join(hostRoot, 'platform.mjs'));
await copyFile(new URL('qq-composition.mjs', sourceRoot), join(hostRoot, 'qq-composition.mjs'));
// qq-data's project path does not call DSH message/decorator APIs. Provide
// only the import-level surface in the scratch runtime instead of borrowing a
// production release or requiring a full DSH dependency installation.
const llm = join(probeRoot, 'node_modules/@deepseek-ai/dsh-llm');
const typert = join(probeRoot, 'node_modules/@deepseek-ai/dsh-typert-protocol');
await mkdir(llm, { recursive: true });
await mkdir(typert, { recursive: true });
await writeFile(join(llm, 'package.json'), '{"type":"module","main":"index.mjs","exports":"./index.mjs"}\n');
await writeFile(join(typert, 'package.json'), '{"type":"module","main":"index.mjs","exports":"./index.mjs"}\n');
await writeFile(join(llm, 'index.mjs'), 'export const createMessage = value => value;\n');
await writeFile(join(typert, 'index.mjs'),
  'export class TypertRemoteService { constructor(ctx, name) { this.ctx = ctx; this.name = name; } }\n' +
  'export const Remote = () => {};\n');
const { QQData } = await import(`file://${join(hostRoot, 'qq-data.mjs')}`);

test('ambient projection advances native cursor without writing DSH session history', async () => {
  const path = join(probeRoot, 'scenes.json');
  const calls = [];
  const data = new QQData({}, {
    native_root: probeRoot,
    account_id: '900001',
  }, async args => {
    calls.push(args);
    return { rows: [
      { id: '41', event_id: 'ambient-41', sender_id: '100002', text: 'ambient one' },
      { id: '42', event_id: 'ambient-42', sender_id: '100003', text: 'ambient two' },
    ] };
  }, new Map());
  data.path = path;
  data.scenes.set('qq-group-123456', {
    route_id: 'qq-group-123456', message_type: 'group', target_id: '123456',
    session_id: 'soyo-qq-scratch', enabled: true, projected_through: 40,
  });

  await data.project('qq-group-123456');

  assert.deepEqual(calls, [{ action: 'projection', route: 'qq-group-123456', after: 40 }]);
  assert.equal(data.scenes.get('qq-group-123456').projected_through, 42);
  const persisted = JSON.parse(await readFile(path, 'utf8'));
  assert.equal(persisted[0].projected_through, 42);
  // No sessionQuery/sessionPersistence/session append methods are supplied to
  // this object. Reaching this assertion proves ambient projection did not
  // require or invoke a DSH transcript write boundary.
});
