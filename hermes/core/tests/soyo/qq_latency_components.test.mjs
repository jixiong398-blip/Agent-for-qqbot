// Local contracts for the low-loss QQ scheduling components.
// These tests do not start DSH, OneBot, a memory worker or a model.
import test from 'node:test';
import assert from 'node:assert/strict';
import { modelRoute } from '../../soyo/dsh/host/model-route.mjs';
import { inputIntent, SceneScheduler } from '../../soyo/dsh/host/scene-scheduler.mjs';
import { ReadyOutbox } from '../../soyo/dsh/host/ready-outbox.mjs';
import { DurableEffects } from '../../soyo/dsh/host/durable-effects.mjs';

const envelope = (eventId, text = 'message') => ({
  route_id: 'qq-private-owner', sender_id: 'owner', event_id: eventId, text,
});

const eventually = async (predicate, timeout = 1000) => {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    if (Date.now() >= deadline) throw Error('component contract timed out');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
};

test('model routes keep implicit cognition on the role and explicit work on action', () => {
  const config = {
    agent_options: { provider: 'character-provider', model: 'character-model' },
    action_agent_options: { provider: 'action-provider', model: 'action-model' },
  };
  assert.deepEqual(modelRoute(config, 'character'), config.agent_options);
  assert.deepEqual(modelRoute(config, 'action'), config.action_agent_options);
  assert.throws(() => modelRoute({}), /GLOBAL_MODEL_ROUTE_REQUIRED/);
});

test('control intent recognizes only the bounded control forms', () => {
  assert.equal(inputIntent({ text: '停止回复' }), 'stop');
  assert.equal(inputIntent({ text: '停止当前任务' }), 'stop-action');
  assert.equal(inputIntent({ text: '补充：别忘了标题' }), 'supplement');
  assert.equal(inputIntent({ text: '不对，改成蓝色' }), 'correct');
  assert.equal(inputIntent({ text: '停止回复，但继续说' }), 'message');
  assert.equal(inputIntent({ text: '补充：看图', media: [{ kind: 'image' }] }), 'message');
});

test('scene scheduler batches same-scene bursts and preserves every source event', async () => {
  const saved = [];
  const started = [];
  const scheduler = new SceneScheduler({
    quietMs: 0, maxWaitMs: 0, limit: 1, owner: () => true,
    save: async job => saved.push({ key: job.key, state: job.state, covered_by: job.covered_by }),
    run: async job => { started.push(job); },
  });
  const queuedAt = Date.now();
  const first = { key: 'a', envelope: envelope('event-a'), policy_epoch: 1, queued_at: queuedAt };
  const second = { key: 'b', envelope: envelope('event-b'), policy_epoch: 1, queued_at: queuedAt };
  scheduler.enqueue(first); scheduler.enqueue(second);
  await eventually(() => started.length === 1);
  assert.equal(started[0].key, 'a');
  assert.deepEqual(started[0].input_keys, ['a', 'b']);
  assert.deepEqual(started[0].covered_event_ids, ['event-a', 'event-b']);
  assert.deepEqual(started[0].batch_inputs.map(item => item.event_id), ['event-a', 'event-b']);
  assert.deepEqual(saved.find(item => item.key === 'b'), { key: 'b', state: 'coalesced', covered_by: 'a' });
  scheduler.close();
});

test('scene scheduler can cancel a queued job without starting it', async () => {
  const saved = [];
  const started = [];
  const scheduler = new SceneScheduler({
    quietMs: 10000, maxWaitMs: 10000, save: async job => saved.push(job),
    run: async job => started.push(job),
  });
  const job = { key: 'queued', envelope: envelope('queued-event'), policy_epoch: 1 };
  scheduler.enqueue(job);
  const cancelled = await scheduler.cancel(candidate => candidate.key === 'queued');
  assert.deepEqual(cancelled, [job]);
  assert.equal(job.state, 'cancelled');
  assert.equal(started.length, 0);
  scheduler.close();
});

test('ready outbox wakes a bounded waiter without claiming the publication', async () => {
  const outbox = new ReadyOutbox();
  const item = { publication_id: 'publication-1', attempt_id: 'attempt-1' };
  const pending = outbox.read({ waitMs: 500, valid: value => value.publication_id === item.publication_id });
  await new Promise(resolve => setTimeout(resolve, 5));
  outbox.put(item);
  assert.deepEqual(await pending, [item]);
  assert.deepEqual(await outbox.read(), [item]);
  outbox.remove(item.publication_id);
  assert.deepEqual(await outbox.read(), []);
  outbox.close();
});

test('durable effects keep same-domain side effects ordered', async () => {
  const applied = [];
  const saved = [];
  const effects = new DurableEffects({
    save: async record => saved.push(record.key),
    apply: async effect => applied.push(effect.name),
  });
  effects.schedule({ key: 'first', envelope: { route_id: 'scene' }, effects: [{ name: 'first-effect' }] });
  effects.schedule({ key: 'second', envelope: { route_id: 'scene' }, effects: [{ name: 'second-effect' }] });
  await effects.barrier('scene');
  assert.deepEqual(applied, ['first-effect', 'second-effect']);
  assert.deepEqual(saved, ['first', 'second']);
  await effects.close();
});
