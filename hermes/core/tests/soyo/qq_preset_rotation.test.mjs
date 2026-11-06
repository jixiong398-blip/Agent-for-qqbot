// SPDX-License-Identifier: MIT
// Upgrading an existing deployment must not brick QQ: a session that predates
// the Agent preset is rotated once, deterministically, and the old log is kept.
// The module under test is copied into a scratch tree with stub DSH packages,
// so no service, model, session store or real home is touched.
import assert from 'node:assert/strict';
import test from 'node:test';
import { copyFile, mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { QQ_AGENT_PRESET_ID } from '../../soyo/dsh/host/qq-composition.mjs';

// The scene's session id is derived from the account, route and epoch; a real
// deployment stores exactly that value, so the fixture must too.
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const ACCOUNT = '100001';
const ROUTE = 'qq-group-123456';
const liveSessionId = () => 'soyo-qq-' + hash([ACCOUNT, ROUTE, 'live']).slice(0, 32);

const sourceRoot = new URL('../../soyo/dsh/host/', import.meta.url);
const probeRoot = await mkdtemp(join(tmpdir(), 'soyo-qq-preset-rotation-'));
const hostRoot = join(probeRoot, 'host');
await mkdir(hostRoot, { recursive: true });
for (const name of ['qq-data.mjs', 'platform.mjs', 'qq-composition.mjs']) {
  await copyFile(new URL(name, sourceRoot), join(hostRoot, name));
}
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

// Minimal in-memory stand-in for the DSH services QQData touches.
const store = () => {
  const sessions = new Map();
  const archived = [];
  const warnings = [];
  // checkpoint() waits for a domain/changed notification keyed by the session
  // id and the last appended seq. The stub emits it synchronously after the
  // append so the test never waits on a real projection timer.
  const cache = new Map();
  const listeners = [];
  return {
    sessions, archived, warnings, cache, listeners,
    ctx: {
      logger: { warn: (...args) => warnings.push(args.join(' ')) },
      workspaceRegistry: {
        archiveSession: async id => { archived.push(id); },
        create: async (cwd, title) => ({ attachSession: async () => {}, cwd, title }),
      },
      sessionPersistence: {
        stat: async id => (sessions.has(id) ? { header: sessions.get(id).header } : undefined),
        open: async id => {
          const held = sessions.get(id);
          if (!held) throw Error('missing session');
          return { header: held.header,
            read: async (offset = 0, length = held.events.length) =>
              ({ eventState: 'shared', events: held.events.slice(offset, offset + length) }),
            close: async () => {} };
        },
        create: async header => {
          sessions.set(header.id, { header, events: [] });
          return { header, inheritedEventCount: 0,
            append: async events => {
              sessions.get(header.id).events.push(...events);
              for (const handler of listeners) handler({ key: header.id });
            },
            flush: async () => {}, close: async () => {} };
        },
      },
      sessions: { prepare: (id, options) => {
        const events = [];
        return { header: { id, isSeeded: false, cwd: options.meta.cwd },
          append: (type, data) => events.push({ type, data }),
          snapshotEvents: () => events };
      } },
      sessionProjectionCache: {
        // checkpoint() registers its listener first, then asks for a cold
        // snapshot and waits for the matching domain/changed notification.
        coldSnapshot: (header, _cut, events) => {
          cache.set(header.id, events.length - 1);
          for (const handler of listeners) handler({ key: header.id });
        },
        cachedSnapshot: header => (cache.has(header.id) ? { asOfSeq: cache.get(header.id) } : undefined),
      },
      on: (name, handler) => { listeners.push(handler); return () => { const at = listeners.indexOf(handler);
        if (at >= 0) listeners.splice(at, 1); }; },
    },
  };
};

const config = { account_id: '100001', native_root: join(probeRoot, 'root'),
  workspace: join(probeRoot, 'ws'), character_name: 'Bot' };
const route = { route_id: 'qq-group-123456', message_type: 'group', target_id: '123456', name: 'Fixture' };
const scene = (sessionId) => ({ route_id: route.route_id, message_type: 'group', target_id: '123456',
  name: 'Fixture', enabled: true, session_id: sessionId, session_epoch: 'live', policy_epoch: 1, members: [] });

test('a legacy QQ session without a preset is rotated once and keeps its log', async () => {
  const world = store();
  const value = new QQData(world.ctx, config, async () => ({}), new Map());
  value.path = join(probeRoot, 'scenes-a.json');
  const legacyId = liveSessionId();
  world.sessions.set(legacyId, { header: { id: legacyId, isSeeded: false, cwd: join(probeRoot, 'ws/qq') },
    events: [{ type: 'session/title', data: { title: '缇よ亰 路 Fixture' } },
             { type: 'turn/start', data: { turn: 1 } }] });
  value.scenes.set(route.route_id, scene(legacyId));

  await value.configure([route]);
  const updated = value.scenes.get(route.route_id);
  assert.notEqual(updated.session_id, legacyId, 'the upgraded scene must not reuse the pre-preset log');
  assert.deepEqual(updated.predecessor_sessions, [legacyId]);
  assert.equal(updated.recovery_reason, 'legacy_session_without_preset');
  assert.equal(updated.preset_rotation.to_preset, QQ_AGENT_PRESET_ID);
  assert.equal(updated.preset_rotation.previous_preset, null);
  assert.deepEqual(world.archived, [legacyId], 'the old log is archived, never deleted');
  assert.equal(updated.policy_epoch, 2);
});

test('a session bound to another preset rotates with a distinct reason', async () => {
  const world = store();
  const value = new QQData(world.ctx, config, async () => ({}), new Map());
  value.path = join(probeRoot, 'scenes-b.json');
  const standardId = liveSessionId();
  world.sessions.set(standardId, { header: { id: standardId, isSeeded: false,
    cwd: join(probeRoot, 'ws/qq'), agentPreset: 'standard' }, events: [] });
  value.scenes.set(route.route_id, scene(standardId));

  await value.configure([route]);
  const updated = value.scenes.get(route.route_id);
  assert.equal(updated.recovery_reason, 'agent_preset_conflict');
  assert.equal(updated.preset_rotation.previous_preset, 'standard');
  assert.notEqual(updated.session_id, standardId);
});

test('rotation is stable across restarts and does not churn the session id', async () => {
  const world = store();
  const value = new QQData(world.ctx, config, async () => ({}), new Map());
  value.path = join(probeRoot, 'scenes-c.json');
  const legacyId = liveSessionId();
  world.sessions.set(legacyId, { header: { id: legacyId, isSeeded: false, cwd: join(probeRoot, 'ws/qq') },
    events: [{ type: 'turn/start', data: { turn: 1 } }] });
  value.scenes.set(route.route_id, scene(legacyId));

  await value.configure([route]);
  const rotated = value.scenes.get(route.route_id).session_id;

  // Simulate a supervisor restart: a second QQData loads the persisted scenes
  // and configures the same routes again.
  const restarted = new QQData(world.ctx, config, async () => ({}), new Map());
  restarted.path = join(probeRoot, 'scenes-c.json');
  for (const row of value.scenes.values()) restarted.scenes.set(row.route_id, row);
  await restarted.configure([route]);
  assert.equal(restarted.scenes.get(route.route_id).session_id, rotated, 'rotation must be idempotent');
  assert.deepEqual(world.archived, [legacyId], 'the predecessor is archived exactly once');
});

test('a session already on the QQ preset is not rotated', async () => {
  const world = store();
  const value = new QQData(world.ctx, config, async () => ({}), new Map());
  value.path = join(probeRoot, 'scenes-d.json');
  const currentId = liveSessionId();
  world.sessions.set(currentId, { header: { id: currentId, isSeeded: false, cwd: join(probeRoot, 'ws/qq'),
    agentPreset: QQ_AGENT_PRESET_ID }, events: [{ type: 'turn/start', data: { turn: 1 } }] });
  value.scenes.set(route.route_id, scene(currentId));

  await value.configure([route]);
  const updated = value.scenes.get(route.route_id);
  assert.equal(updated.session_id, currentId);
  assert.equal(updated.preset_rotation, undefined);
  assert.deepEqual(world.archived, []);
});

test('an unreadable log is left to the QQ lane instead of being rotated blindly', async () => {
  const world = store();
  const value = new QQData(world.ctx, config, async () => ({}), new Map());
  value.path = join(probeRoot, 'scenes-e.json');
  const brokenId = liveSessionId();
  world.sessions.set(brokenId, { header: { id: brokenId, isSeeded: false, cwd: join(probeRoot, 'ws/qq') }, events: [] });
  world.ctx.sessionPersistence.open = async () => {
    throw Object.assign(Error('refused'), { name: 'SessionFormatUnsupportedError' });
  };
  value.scenes.set(route.route_id, scene(brokenId));

  await value.configure([route]);
  assert.equal(value.scenes.get(route.route_id).session_id, brokenId);
  assert.deepEqual(world.archived, []);
  assert(world.warnings.some(line => line.includes('preset check could not read the session log')));
});
