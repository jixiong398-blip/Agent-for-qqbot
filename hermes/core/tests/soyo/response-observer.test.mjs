// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import test from 'node:test';
import { createResponseObserver, recordSseText } from './response-observer.mjs';

const stream = events => new Response(events.map(event => `data: ${JSON.stringify(event)}\n\n`).join(''), {
  status: 200, headers: { 'content-type': 'text/event-stream' },
});

test('fetch instrumentation returns the same Response and never reads its body', async () => {
  const expected = stream([
    { type: 'response.function_call_arguments.done', arguments: '{"thought":"ok"}' },
    { type: 'response.output_item.done', item: { type: 'function_call' } },
    { type: 'response.completed', response: { status: 'completed' } },
  ]);
  const observer = createResponseObserver({ fetch: async () => expected });
  const actual = await observer.fetch('https://fixture.invalid/v1/responses');
  assert.equal(actual, expected);
  const raw = await actual.text();
  assert.equal(raw, await (async () => stream([
    { type: 'response.function_call_arguments.done', arguments: '{"thought":"ok"}' },
    { type: 'response.output_item.done', item: { type: 'function_call' } },
    { type: 'response.completed', response: { status: 'completed' } },
  ]).text())());
  assert.equal('sse_types' in observer.records[0], false);
  const parsed = {};
  recordSseText(raw, parsed);
  assert.deepEqual(parsed.sse_types, [
    'response.function_call_arguments.done', 'response.output_item.done', 'response.completed',
  ]);
  assert.equal(parsed.function_arguments_done.arguments_length, 16);
});

test('a 503 response is returned unchanged and its body remains readable by the adapter', async () => {
  const expected = new Response(JSON.stringify({ error: { code: 'UPSTREAM', message: 'temporarily unavailable' } }), {
    status: 503, headers: { 'content-type': 'application/json' },
  });
  const observer = createResponseObserver({ fetch: async () => expected });
  const actual = await observer.fetch('https://fixture.invalid/v1/responses');
  assert.equal(actual, expected);
  assert.equal(actual.status, 503);
  assert.deepEqual(await actual.json(), { error: { code: 'UPSTREAM', message: 'temporarily unavailable' } });
  assert.equal(observer.records[0].http_status, 503);
});

test('request-observer exceptions do not block the provider request', async () => {
  const expected = new Response('ok');
  const observer = createResponseObserver({ fetch: async () => expected, onRequest: () => { throw Error('observer failed'); } });
  assert.equal(await observer.fetch('https://fixture.invalid', { method: 'POST', body: '{}' }), expected);
  assert.equal(observer.records[0].observer_request_error, 'observer failed');
});

test('response body is neither cloned nor consumed by fetch instrumentation', async () => {
  const response = new Response('ok');
  response.clone = () => { throw Error('clone must not be called'); };
  const observer = createResponseObserver({ fetch: async () => response });
  assert.equal(await observer.fetch('https://fixture.invalid'), response);
  assert.equal(await response.text(), 'ok');
});

test('SSE parse errors are contained in the dedicated post-capture parser', async () => {
  const record = {};
  recordSseText('data: {not-json}\n\n', record);
  assert.equal(record.sse_parse_errors.length, 1);
});

test('a fetch failure is rethrown unchanged and safely recorded', async () => {
  const failure = new TypeError('fetch failed', { cause: Error('socket closed') });
  const observer = createResponseObserver({ fetch: async () => { throw failure; } });
  await assert.rejects(observer.fetch('https://fixture.invalid'), error => error === failure);
  assert.equal(observer.records[0].fetch_error, 'fetch failed');
});
