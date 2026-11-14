// SPDX-License-Identifier: MIT
// The drawing channel is a separate credential and a separate capability.
// These contracts do not call the provider, cost money or start DSH.
import test from 'node:test';
import assert from 'node:assert/strict';
import { SoyoRoleRuntime } from '../../soyo/dsh/host/role-runtime.mjs';
import { generateImage, imageRequest, imageGenerationStatus, IMAGE_BROWSER_HEADERS } from '../../soyo/dsh/host/image-generation.mjs';

const config = { brain_mode: 'character-action', account_id: '900001', admin_ids: ['100001'], owner_group_ids: ['123456'] };
const owner = { message_type: 'private', route_id: 'qq-private-100001', sender_id: '100001', target_id: '100001' };
const publicScene = { message_type: 'group', route_id: 'qq-group-123456', sender_id: '100002', target_id: '123456' };

function bound(envelope, lane = 'character') {
  const runtime = new SoyoRoleRuntime(config), agent = { id: 'fixture-' + lane + '-' + envelope.message_type };
  const job = { key: 'a'.repeat(64), envelope };
  runtime.admit(job); runtime.begin(agent, job, envelope, lane);
  return { runtime, agent };
}

test('owner character and action lanes may draw; public defaults still deny', () => {
  const { runtime, agent } = bound(owner);
  assert(runtime.exposed(agent).has('soyo_draw_image'));
  assert(runtime.exposed(agent).has('soyo_image_status'));
  const pub = bound(publicScene);
  assert(!pub.runtime.exposed(pub.agent).has('soyo_draw_image'));
  const action = bound(owner, 'action');
  assert(action.runtime.exposed(action.agent).has('soyo_draw_image'));
  assert(!action.runtime.exposed(action.agent).has('soyo_attach_image'), 'the executor is not another QQ writer');
});

test('the owner can draw in an owner-bound group, not only in a private chat', () => {
  // Real turn: the owner asked her to draw a picture of herself in a group.
  // Drawing was private-only, so the tool was not even offered and she
  // delegated the job to the action brain instead. The owner is the same
  // person in their own group.
  const ownerGroup = { message_type: 'group', route_id: 'qq-group-123456',
    sender_id: '100001', target_id: '123456', mentioned_account_ids: ['900001'] };
  const { runtime, agent } = bound(ownerGroup);
  const exposed = runtime.exposed(agent);
  assert(exposed.has('soyo_draw_image'), 'an owner group must offer the drawing tool');
  assert(exposed.has('soyo_image_shelf'));
  assert(exposed.has('soyo_image_collect'));
});

test('a group the owner merely belongs to is still not an owner scene', () => {
  // Group 999999 is not in owner_group_ids: the same sender id there is just a
  // member, so no paid drawing and no shelf access.
  const otherGroup = { message_type: 'group', route_id: 'qq-group-999999',
    sender_id: '100001', target_id: '999999', mentioned_account_ids: ['900001'] };
  const { runtime, agent } = bound(otherGroup);
  assert(!runtime.exposed(agent).has('soyo_draw_image'));
});

test('a non-owner in an owner group cannot draw', () => {
  const stranger = { message_type: 'group', route_id: 'qq-group-123456',
    sender_id: '100002', target_id: '123456', mentioned_account_ids: ['900001'] };
  const { runtime, agent } = bound(stranger);
  assert(!runtime.exposed(agent).has('soyo_draw_image'));
});

test('an owner-group report turn still cannot start a new paid drawing', () => {
  const ownerGroup = { message_type: 'group', route_id: 'qq-group-123456',
    sender_id: '100001', target_id: '123456', mentioned_account_ids: ['900001'] };
  const runtime = new SoyoRoleRuntime(config), agent = { id: 'group-report-turn' };
  const job = { key: 'c'.repeat(64), envelope: ownerGroup, internal: true, internal_source: 'action-report' };
  runtime.admit(job); runtime.begin(agent, job, ownerGroup);
  assert(!runtime.exposed(agent).has('soyo_draw_image'));
});

test('an internal report turn cannot start a new paid drawing', () => {
  const runtime = new SoyoRoleRuntime(config), agent = { id: 'report-turn' };
  const job = { key: 'b'.repeat(64), envelope: owner, internal: true, internal_source: 'gpt-consultation' };
  runtime.admit(job); runtime.begin(agent, job, owner);
  assert(!runtime.exposed(agent).has('soyo_draw_image'));
});

test('drawing is refused before any request when the section is unconfigured', async () => {
  const result = await generateImage({ config: {}, prompt: 'a cat', mediaRoot: '/tmp', logger: {} });
  assert.equal(result.state, 'failed');
  assert.equal(result.code, 'IMAGE_GEN_UNCONFIGURED');
  assert.match(result.message, /IMAGE_GEN_UNCONFIGURED/);
});

test('an unconfigured section never borrows a brain key', () => {
  // models.action carries a real key, but image_gen is absent: status must
  // still report "not configured" rather than falling back to that key.
  const withBrains = { brain_mode: 'character-action',
    models: { action: { api_key: 'sk-not-real', name: 'text-model' }, character: { api_key: 'sk-not-real' } } };
  const status = imageGenerationStatus(withBrains);
  assert.equal(status.configured, false);
  assert.equal(status.model, '');
});

test('browser headers are complete enough to pass the Cloudflare front', () => {
  const request = imageRequest({ config: { base_url: 'https://images.example.invalid/v1', model: 'fixture-image-model' }, prompt: 'Generate an image: a cat' });
  assert.equal(request.url, 'https://images.example.invalid/v1/images/generations');
  for (const header of ['User-Agent', 'Accept', 'Accept-Language', 'Content-Type', 'Origin', 'Referer'])
    assert.ok(request.headers[header], header + ' must be sent');
  assert.match(request.headers['User-Agent'], /Mozilla\/5\.0/);
  assert.equal(request.headers.Origin, 'https://images.example.invalid');
  assert.equal(request.headers.Referer, 'https://images.example.invalid/');
  assert.equal(request.body.model, 'fixture-image-model');
  assert.equal(request.body.size, '1024x1024');
  assert.equal(request.body.n, 1);
  assert.equal(IMAGE_BROWSER_HEADERS.Authorization, undefined, 'the key is added only at send time');
});

test('the default time budget leaves room for a real reference-image edit', () => {
  // Measured end to end on this channel: 183s for one reference-image edit.
  // The old 180s default sat on that boundary and turned a slow success into a
  // paid timeout, so the default must keep clear headroom above it.
  const status = imageGenerationStatus({ image_gen: { enabled: true, base_url: 'https://example.invalid/v1',
    model: 'gpt-image-2.5', size: '', timeout_ms: 0, api_key: 'sk-fixture', key_file: '/nonexistent' } });
  assert.equal(status.configured, true);
  assert.equal(status.timeout_ms, 300000);
  assert.ok(status.timeout_ms > 183000 * 1.3, 'default must exceed the observed edit duration with margin');
});

test('a bad size is rejected locally instead of spending a provider request', async () => {
  const configured = { image_gen: { enabled: true, base_url: 'https://example.invalid/v1', model: 'gpt-image-2.5', size: '', timeout_ms: 0, key_file: '/nonexistent' } };
  const result = await generateImage({ config: configured, prompt: 'a cat', size: 'huge', mediaRoot: '/tmp', logger: {} });
  assert.equal(result.state, 'failed');
  assert.equal(result.code, 'IMAGE_GEN_SIZE');
});

test('an unreadable key file fails before the network is touched', async () => {
  const configured = { image_gen: { enabled: true, base_url: 'https://example.invalid/v1', model: 'gpt-image-2.5', size: '', timeout_ms: 0, key_file: '/nonexistent/image-key' } };
  const result = await generateImage({ config: configured, prompt: 'a cat', mediaRoot: '/tmp', logger: {} });
  assert.equal(result.state, 'failed');
  assert.equal(result.code, 'IMAGE_GEN_KEY');
});
