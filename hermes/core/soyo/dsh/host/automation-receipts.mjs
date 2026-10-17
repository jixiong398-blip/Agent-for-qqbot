// SPDX-License-Identifier: MIT
// Effect receipts, not Schedule delivery acknowledgements or model prose.
import { constants } from 'node:fs';
import { open, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { openPrivate } from './platform.mjs';

// Existing automation publications use SHA256(JSON.stringify(publication_id)).
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const receiptIdentity = value => typeof value === 'string' && value.length > 0 && value.length <= 160 && /^[!-~]+$/.test(value);
export const platformMessageIdentity = value => receiptIdentity(value) || Number.isSafeInteger(value) && value !== 0;

async function privateJSON(path, max = 512 * 1024) {
  const file = await openPrivate(path, max);
  try {
    return JSON.parse(await file.readFile('utf8'));
  } finally { await file.close(); }
}

function feishuBase(config) {
  const value = new URL(config.feishu_api_base ?? 'https://open.feishu.cn');
  const fixture = config.automation_fixture_allow_loopback === true && value.protocol === 'http:' && value.hostname === '127.0.0.1';
  if ((!fixture && (value.protocol !== 'https:' || value.hostname !== 'open.feishu.cn')) ||
      value.username || value.password || value.search || value.hash || value.pathname !== '/') throw Error('Feishu endpoint outside deployment policy');
  return value.origin;
}

async function boundedJSON(response) {
  const chunks = []; let bytes = 0;
  for await (const chunk of response.body ?? []) {
    bytes += chunk.byteLength;
    if (bytes > 64 * 1024) throw Error('Platform response exceeds receipt budget');
    chunks.push(Buffer.from(chunk));
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

export async function notifyFeishu(config, text) {
  if (!config.feishu_key_file || !config.feishu_chat_id || !text || text.trim() === '[SILENT]') return { state: 'not_configured_or_silent' };
  let dispatched = false;
  try {
    const base = feishuBase(config), credentials = await privateJSON(config.feishu_key_file, 8192);
    if (!credentials.app_id || !credentials.app_secret) return { state: 'blocked', reason: 'feishu_credentials_incomplete', message_attempted: false };
    const response = await fetch(base + '/open-apis/auth/v3/tenant_access_token/internal', {
      method: 'POST', redirect: 'error', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ app_id: credentials.app_id, app_secret: credentials.app_secret }),
      signal: AbortSignal.timeout(15000) });
    const token = await boundedJSON(response);
    if (!response.ok || token.code !== 0 || !token.tenant_access_token) return { state: 'failed', reason: 'feishu_auth_failed', message_attempted: false };
    dispatched = true;
    const sent = await fetch(base + '/open-apis/im/v1/messages?receive_id_type=chat_id', {
      method: 'POST', redirect: 'error', headers: { 'Authorization': 'Bearer ' + token.tenant_access_token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ receive_id: config.feishu_chat_id, msg_type: 'text', content: JSON.stringify({ text: text.slice(0, 8000) }) }),
      signal: AbortSignal.timeout(15000) });
    const result = await boundedJSON(sent);
    if (sent.ok && result.code === 0 && receiptIdentity(result.data?.message_id))
      return { state: 'platform_accepted', message_id: result.data.message_id, message_attempted: true };
    if (sent.ok && result.code === 0) return { state: 'unknown', reason: 'feishu_message_id_missing', message_attempted: true };
    return { state: 'failed', code: typeof result.code === 'number' ? result.code : null, message_attempted: true };
  } catch (error) {
    return { state: dispatched ? 'unknown' : 'failed', reason: dispatched ? 'feishu_send_unconfirmed' : 'feishu_pre_dispatch_failed',
      error_type: error.name ?? 'Error', message_attempted: dispatched };
  }
}

export function publicationOutcome(work, publication) {
  const expected = work.publication;
  if (!expected || !publication || typeof publication !== 'object' || Array.isArray(publication) ||
      publication.publication_id !== expected.publication_id || publication.attempt_id !== expected.attempt_id)
    return { state: 'unknown', reason: 'external_publication_binding_mismatch' };
  const receipt = publication.receipt;
  if (!receipt) return null;
  if (receipt.publication_id !== expected.publication_id || receipt.attempt_id !== expected.attempt_id)
    return { state: 'unknown', reason: 'external_receipt_binding_mismatch' };
  if (receipt.status === 'platform_accepted' && platformMessageIdentity(receipt.platform_message_id))
    return { state: 'completed', platform_receipt: receipt, completion_evidence: 'actual-qq-platform-receipt' };
  if (receipt.status === 'failed') return { state: 'failed', platform_receipt: receipt, reason: receipt.reason ?? 'external_publication_failed' };
  return { state: 'unknown', platform_receipt: receipt, reason: 'external_delivery_unconfirmed' };
}

export async function reconcileQueuedRuns(runsRoot, publicationRoot, save) {
  const changed = [], retained_errors = [];
  for (const name of await readdir(runsRoot)) {
    if (!/^[a-f0-9]{64}\.json$/.test(name)) continue;
    let work;
    try { work = await privateJSON(join(runsRoot, name)); }
    catch (error) { retained_errors.push({ file: name, reason: error.name ?? 'Error' }); continue; }
    if (!work || work.state !== 'queued_external' || work.publication?.kind !== 'message') continue;
    if (work.id !== name.slice(0, -5)) { retained_errors.push({ file: name, reason: 'ledger_identity_mismatch' }); continue; }
    if (!receiptIdentity(work.publication.publication_id) || !receiptIdentity(work.publication.attempt_id)) {
      await save({ ...work, state: 'unknown', reason: 'external_work_binding_invalid' }); changed.push(work.id); continue;
    }
    let publication;
    try { publication = await privateJSON(join(publicationRoot, hash(work.publication.publication_id) + '.json')); }
    catch (error) {
      await save({ ...work, state: 'unknown', reason: error.code === 'ENOENT' ? 'external_publication_file_missing' : 'external_receipt_source_invalid' }); changed.push(work.id); continue;
    }
    const result = publicationOutcome(work, publication);
    if (result) { await save({ ...work, ...result, receipt_reconciled_at: Date.now() }); changed.push(work.id); }
  }
  return { changed, retained_errors, side_effects_replayed: false, model_woken: false };
}
