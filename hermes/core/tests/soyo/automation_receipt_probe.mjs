// SPDX-License-Identifier: MIT
// Real HTTP and durable ledger files, loopback stand-in only for the external platform.
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, isAbsolute } from 'node:path';
import { notifyFeishu, reconcileQueuedRuns } from '../../soyo/dsh/host/automation-receipts.mjs';

const root = process.argv[2]; assert(root && isAbsolute(root)); await mkdir(root, { mode: 0o700 });
const runs = join(root, 'runs'), publications = join(root, 'publications');
await mkdir(runs, { mode: 0o700 }); await mkdir(publications, { mode: 0o700 });
await writeFile(join(root, 'feishu-key.json'), JSON.stringify({ app_id: 'fixture-app', app_secret: 'fixture-not-a-secret' }), { mode: 0o600 });
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
let calls = 0, missing = false;
const server = http.createServer(async (req, res) => {
  const chunks = []; for await (const chunk of req) chunks.push(chunk);
  const value = JSON.parse(Buffer.concat(chunks).toString()); calls++;
  const body = req.url.includes('/auth/') ? { code: 0, tenant_access_token: 'fixture-only-token' }
    : missing ? { code: 0, data: {} } : { code: 0, data: { message_id: 'om_fixture_real_http_receipt' } };
  if (!req.url.includes('/auth/')) { assert.equal(req.headers.authorization, 'Bearer fixture-only-token'); assert.equal(value.receive_id, 'fixture-chat'); }
  res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const config = { feishu_key_file: join(root, 'feishu-key.json'), feishu_chat_id: 'fixture-chat', automation_fixture_allow_loopback: true,
  feishu_api_base: 'http://127.0.0.1:' + server.address().port };
const proof = { status: 'unverified', real_platform_sends: 0, external_model_calls: 0, platform: 'loopback-only' };
try {
  const accepted = await notifyFeishu(config, 'fixture platform receipt');
  assert.equal(accepted.state, 'platform_accepted'); assert.equal(accepted.message_id, 'om_fixture_real_http_receipt');
  missing = true; const unknown = await notifyFeishu(config, 'fixture missing id');
  assert.equal(unknown.state, 'unknown'); assert.equal(unknown.reason, 'feishu_message_id_missing');
  const pub = { publication_id: 'automation-fixture', attempt_id: 'automation-fixture-attempt', kind: 'message' };
  const id = hash('fixture-run'), work = { id, state: 'queued_external', publication: pub };
  await writeFile(join(runs, id + '.json'), JSON.stringify(work), { mode: 0o600 });
  const mismatched = join(runs, hash('mismatched-ledger') + '.json');
  const preserved = JSON.stringify({ ...work, id: 'must-not-overwrite-a-different-ledger' });
  await writeFile(mismatched, preserved, { mode: 0o600 });
  await writeFile(join(publications, hash(pub.publication_id) + '.json'), JSON.stringify({ ...pub, receipt: {
    publication_id: pub.publication_id, attempt_id: pub.attempt_id, status: 'platform_accepted', platform_message_id: 'fixture-qq-message-id' } }), { mode: 0o600 });
  const save = value => writeFile(join(runs, value.id + '.json'), JSON.stringify(value), { mode: 0o600 });
  const first = await reconcileQueuedRuns(runs, publications, save);
  assert.deepEqual(first.changed, [id]); assert.equal(first.side_effects_replayed, false);
  assert.equal(first.retained_errors[0].reason, 'ledger_identity_mismatch'); assert.equal(await readFile(mismatched, 'utf8'), preserved);
  const settled = JSON.parse(await readFile(join(runs, id + '.json'), 'utf8'));
  assert.equal(settled.state, 'completed'); assert.equal(settled.platform_receipt.platform_message_id, 'fixture-qq-message-id');
  const second = await reconcileQueuedRuns(runs, publications, save); assert.deepEqual(second.changed, []);
  assert.equal(calls, 4); // No additional HTTP/model calls during either ledger reconciliation.
  Object.assign(proof, { status: 'verified_http_and_durable_receipt_path', feishu_id_required: true, empty_id_not_success: true,
    qq_run_settled_from_exact_receipt: true, repeat_reconcile_no_send: true, loopback_http_requests: calls });
} catch (error) { proof.error = error.name + ': ' + error.message; throw error; }
finally {
  server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
  await writeFile(join(root, 'probe.json'), JSON.stringify(proof, null, 2) + '\n', { mode: 0o600 });
  console.log(JSON.stringify(proof));
}
