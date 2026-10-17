// SPDX-License-Identifier: MIT
// Native Schedule is the only clock. Occurrences, effects and platform
// acknowledgements are separate durable records; no historical effects replay.
import { spawn } from 'node:child_process';
import { constants } from 'node:fs';
import { open, mkdir, rename, lstat, chmod, unlink, readFile } from 'node:fs/promises';
import { join, resolve, relative, isAbsolute } from 'node:path';
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import http from 'node:http';
import z from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { notifyFeishu, reconcileQueuedRuns } from './automation-receipts.mjs';
import { ScheduledBrains } from './automation-brains.mjs';
import { dualMode } from './role-runtime.mjs';
import { openPrivate, syncDirectory, workerEnvironment, listenPrivate } from './platform.mjs';

export const name = 'soyo-automation';
export const inject = ['agents', 'sessions', 'sessionPersistence', 'schedule', 'tools', 'workspaceRegistry', 'soyoBrains'];
export const Config = z.object({ configFile: z.string().required() });
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
const probeJob = 'soyo-automation-runtime-probe';
function configuredJobs(config) {
  const rows = config.automation_jobs ?? [];
  if (!Array.isArray(rows) || rows.some(row => !row || typeof row.id !== 'string' || !row.id ||
      !['watchdog', 'bandori', 'qzone', 'briefing', 'memory'].includes(row.kind))) throw Error('Invalid deployment automation jobs');
  if (new Set(rows.map(row => row.id)).size !== rows.length) throw Error('Duplicate automation job identity');
  const group = kinds => new Set(rows.filter(row => row.enabled !== false && kinds.includes(row.kind)).map(row => row.id));
  return { scriptJobs: group(['watchdog', 'bandori']), watchdogJobs: group(['watchdog']),
    qzoneJobs: group(['qzone']), briefingJobs: group(['briefing']), memoryJobs: group(['memory']),
    jobIds: group(['watchdog', 'bandori', 'qzone', 'briefing', 'memory']) };
}
async function privateJSON(path, max = 512 * 1024) {
  const file = await openPrivate(path, max);
  try {
    return JSON.parse(await file.readFile('utf8'));
  } finally { await file.close(); }
}
async function durable(path, value) {
  await mkdir(join(path, '..'), { recursive: true, mode: 0o700 });
  const tmp = path + '.' + randomUUID() + '.tmp', file = await open(tmp, 'wx', 0o600);
  try { await file.writeFile(JSON.stringify(value) + '\n'); await file.sync(); } finally { await file.close(); }
  await rename(tmp, path);
  await syncDirectory(join(path, '..'));
}
function runProcess(config, command, args, input, signal, timeout = 120000) {
  return new Promise((resolveResult, reject) => {
    const child = spawn(command, args, { cwd: config.workspace, signal,
      env: workerEnvironment({ ALL_PROXY: '', HTTP_PROXY: '', HTTPS_PROXY: '' }), windowsHide: true,
      stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '', bytes = 0, timedOut = false;
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGKILL'); }, timeout);
    child.stdout.on('data', chunk => { bytes += chunk.length; if (bytes > 256 * 1024) child.kill('SIGKILL'); else output += chunk; });
    child.stderr.resume(); child.stdin.on('error', () => {});
    child.on('error', error => { clearTimeout(timer); reject(error); });
    child.on('close', code => { clearTimeout(timer); resolveResult({ exit_code: code, timed_out: timedOut, output }); });
    child.stdin.end(input ? JSON.stringify(input) : undefined);
  });
}
function parseReminders(message) {
  if (message.source?.kind !== 'schedule') return [];
  const text = message.content.filter(block => block.type === 'text').map(block => block.text).join('\n');
  const batch = text.split('\n').find(line => line.startsWith('reminders_json: '));
  if (batch) { const values = JSON.parse(batch.slice('reminders_json: '.length)); return Array.isArray(values) ? values : []; }
  const idLine = text.split('\n').find(line => line.startsWith('schedule_id_json: '));
  const occurrence = text.split('\n').find(line => line.startsWith('occurrence_at: '));
  if (!idLine || !occurrence) return [];
  return [{ schedule_id: JSON.parse(idLine.slice('schedule_id_json: '.length)), occurrence_at: occurrence.slice('occurrence_at: '.length) }];
}
function requestFor(job, config) {
  const { scriptJobs, qzoneJobs, memoryJobs } = configuredJobs(config);
  const id = String(job.id);
  const goal = memoryJobs.has(id) ? '这是无模型记忆整理任务，由确定性 worker 处理。' : scriptJobs.has(id) ? '这是无模型脚本任务，由执行器处理。' : qzoneJobs.has(id)
    ? '只使用当前公开群聊生成一条日常 Qzone 动态；不要透露私聊、个人标识或敏感细节。先查最近动态避免重复。没有合适内容就沉默。'
    : '用可用 web 工具核验最新科技新闻和来源，整理中文 title/date/headline/deep/quick JSON，渲染图片并提交 owner 私聊图片草稿。不要用旧日期或编造新闻。';
  return { title: String(job.name || job.title || id).slice(0, 100),
    prompt: `Bot 自动化任务 ${id}。${goal}\n先调用 soyo_automation_context。发布工具仅准备草稿：只有本回合 completed final、日志 flush 后才允许出站。禁止 curl/token/任意 shell/旧 Hermes 工具链。`,
    cron: { expression: job.cron ?? job.schedule?.expr, time_zone: config.time_zone || 'UTC' } };
}

export async function apply(ctx, settings) {
  const config = await privateJSON(settings.configFile), startedAt = Date.now();
  const { scriptJobs, watchdogJobs, qzoneJobs, briefingJobs, memoryJobs, jobIds } = configuredJobs(config);
  const lookback = id => Math.max(1, Math.min(24, Number(config.automation_jobs?.find(row => row.id === id)?.lookback_hours ?? 6)));
  const sessionId = config.automation_session_id || 'soyo-automation';
  const root = config.automation_root || join(config.native_root, 'automation');
  const publicationRoot = config.publication_root || join(config.native_root, 'publications');
  const manifestPath = join(root, 'schedule-migration.json'), runsRoot = join(root, 'runs');
  await Promise.all([root, publicationRoot, runsRoot].map(path => mkdir(path, { recursive: true, mode: 0o700 })));
  let manifest = {};
  try { manifest = await privateJSON(manifestPath); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const actor = String(config.briefing_target_id || config.memory_private_peers?.[0] || '');
  const active = new Map();
  const worker = async (args, signal, script = config.memory_script, timeout = 10000) => {
    const result = await runProcess(config, config.python, ['-B', script, settings.configFile], args, signal, timeout);
    if (result.exit_code !== 0 || result.timed_out) throw Error('Automation worker did not complete');
    return JSON.parse(result.output);
  };
  const qzoneWorker = (args, signal, timeout = 60000) => worker(args, signal, config.qzone_script, timeout);
  const authorize = (jobId, exec) => {
    const work = active.get(exec.agent.id)?.find(work => work.job_id === jobId && work.state === 'running');
    if (exec.agent.id !== sessionId || !work) throw Error('Tool has no live scheduled occurrence grant');
    return work;
  };
  const saveRun = work => durable(join(runsRoot, work.id + '.json'), Object.fromEntries(Object.entries(work).filter(([key]) => !key.startsWith('_'))));
  let receiptTail = Promise.resolve();
  let receiptFlight = null, receiptObservation = { state: 'not_started', side_effects_replayed: false, model_woken: false };
  function reconcileReceipts() {
    if (receiptFlight) return receiptFlight; // Coalesce timer/catalog reads; never queue unbounded full scans.
    const work = receiptTail.catch(() => {}).then(() => reconcileQueuedRuns(runsRoot, publicationRoot, saveRun));
    receiptTail = work; receiptFlight = work; receiptObservation = { state: 'running', side_effects_replayed: false, model_woken: false };
    work.then(value => { receiptObservation = { state: 'ready', ...value }; }, error => {
      receiptObservation = { state: 'deferred', error_type: error.name ?? 'Error', side_effects_replayed: false, model_woken: false };
    }).finally(() => { if (receiptFlight === work) receiptFlight = null; });
    return work;
  }
  async function settleFeishu(work, text) {
    if (work.feishu?.state === 'effect_started' || work.feishu?.message_attempted) return work.feishu;
    work.feishu = { state: 'effect_started', started_at: Date.now() }; await saveRun(work);
    work.feishu = await notifyFeishu(config, text); await saveRun(work);
    return work.feishu;
  }
  const stagePublication = async (jobId, text, attachment, exec, authorizeFor = authorize) => {
    const work = authorizeFor(jobId, exec);
    if (watchdogJobs.has(jobId)) throw Error('Watchdog alerts are Feishu-only');
    if (work.publication) throw Error('An occurrence can prepare only one publication');
    if (typeof text !== 'string' || text.length > 5000 || /\b(?:sk-|access_token|api[_ -]?key)\b/i.test(text)) throw Error('Publication rejected');
    if (briefingJobs.has(jobId) && (!attachment || text)) throw Error('Briefing is image-only');
    if (qzoneJobs.has(jobId) && (!text.trim() || text.length > 1000 || attachment)) throw Error('Qzone needs a nonempty bounded text draft');
    if (!/^[1-9][0-9]{0,19}$/.test(actor)) throw Error('Deployment owner target unavailable');
    work.publication = qzoneJobs.has(jobId) ? { kind: 'qzone', text, occurrence_id: work.id } : {
      state: 'pending', kind: 'message', publication_id: 'automation-' + work.id, attempt_id: 'automation-attempt-' + work.id,
      account_id: config.account_id, route_id: 'qq-private-' + actor, target: { type: 'private', id: actor }, text,
      ...(attachment ? { attachment } : {}), source: 'native-automation', occurred_at: work.occurrence_at };
    await saveRun(work);
    return { state: 'prepared', occurrence_id: work.id, note: '草稿未发送；只有回合正常结束并 flush 后才能执行。' };
  };
  const commitEffect = async (work, signal) => {
    if (work.probe) {
      work.state = work.probe_checked && work.final_text?.includes(work.marker) ? 'completed' : 'failed';
      work.reason = work.state === 'completed' ? 'native_grant_probe' : 'native_grant_probe_incomplete';
      await saveRun(work); return; // No QQ, Qzone or Feishu side effects.
    }
    // Transport-health alerts are operational telemetry, not QQ content.  Keep
    // this fence here as well as in scriptRun so an old/injected occurrence
    // cannot turn a watchdog result into a QQ publication after restart.
    if (work.publication?.source === 'native-watchdog') {
      work.publication = undefined;
      work.state = 'blocked';
      work.reason = 'watchdog_alerts_feishu_only';
      await saveRun(work);
      return;
    }
    if (!work.publication) {
      work.state = work.final_text && work.final_text.trim() !== '[SILENT]' ? 'completed' : 'silent';
      if (work.final_text) await settleFeishu(work, work.final_text);
      await saveRun(work); return;
    }
    work.state = 'effect_started'; await saveRun(work); // durable fence BEFORE publisher invocation
    if (work.publication.kind === 'qzone') {
      const result = await qzoneWorker({ op: 'publish', occurrence_id: work.id, content: work.publication.text, image_path: work.publication.image_path || '' }, signal);
      work.result = result; work.state = result.state;
    } else {
      const path = join(publicationRoot, digest(work.publication.publication_id) + '.json');
      try { await privateJSON(path); } catch (error) { if (error.code !== 'ENOENT') throw error; await durable(path, work.publication); }
      work.state = 'queued_external';
    }
    const reportText = work.publication?.kind === 'qzone'
      ? `Qzone 任务 ${work.job_id}：${work.result?.state || work.state}`
      : (work.final_text || work.result?.alert || (work.result ? `任务 ${work.job_id}：${work.result.state || work.state}` : ''));
    if (reportText) await settleFeishu(work, reportText);
    await saveRun(work);
  };
  const scriptRun = async (work, signal) => {
    work.state = 'running'; await saveRun(work);
     const action = watchdogJobs.has(work.job_id) ? 'automation_watchdog' : memoryJobs.has(work.job_id) ? 'memory_maintenance' : 'bandori_sync';
     const result = await worker({ action,
        route_id: sessionId, sender_id: actor }, signal, (watchdogJobs.has(work.job_id) || memoryJobs.has(work.job_id)) ? config.memory_script : config.automation_script, 120000);
      work.result = result;
      work.state = result.state === 'completed' || watchdogJobs.has(work.job_id) && result.state === 'observed'
        ? 'completed' : ['failed', 'blocked', 'unknown'].includes(result.state) ? result.state : 'unknown';
      await saveRun(work);
     if (result.alert) {
       // Watchdog is a control-plane alarm.  It must never enter the QQ
       // publication root; QQ is reserved for admitted Soyo conversation
       // finals.  Feishu is the sole external alert channel.
       work.alert_channel = 'feishu_only';
        await settleFeishu(work, result.alert);
       work.state = work.feishu.state === 'platform_accepted' ? 'completed' : 'unknown';
       if (work.state !== 'completed') work.reason = 'watchdog_feishu_delivery_' + work.feishu.state;
       await saveRun(work);
     }
   };

   const registerTools = (scope, authorize) => {
     const output = { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] };
    scope.tools.register(defineTool({ name: 'soyo_automation_probe_check', description: '只读检查当前一次性 native Schedule 验证回合的 grant；不读取聊天，不发送任何平台。仅验证 occurrence 可用。',
      parameters: { job_id: { type: 'string', required: true } }, output,
      execute(args, exec) { const work = authorize(args.job_id, exec);
        if (!work.probe) throw Error('Not a native grant probe');
        work.probe_checked = true;
        return { state: 'observed', occurrence_id: work.id, marker: work.marker, platform_effects: 0 }; } }));
    scope.tools.register(defineTool({ name: 'soyo_automation_context', description: '读取当前任务的公开群聊和最近动态；不会读私聊/旧 Hermes 或调用模型。', parameters: { job_id: { type: 'string', required: true } }, output,
      execute(args, exec) { authorize(args.job_id, exec); return qzoneJobs.has(args.job_id)
        ? qzoneWorker({ op: 'context', hours: lookback(args.job_id) }, exec.signal)
        : worker({ action: 'automation_context', route_id: sessionId, sender_id: actor, job_id: args.job_id,
          hours: lookback(args.job_id) }, exec.signal); } }));
    scope.tools.register(defineTool({ name: 'soyo_automation_publish', description: '准备当前 Qzone 动态草稿，回合结束前不会发布。', parameters: { job_id: { type: 'string', required: true }, text: { type: 'string', required: true } }, output,
      execute(args, exec) { return stagePublication(args.job_id, args.text, null, exec, authorize); } }));
    scope.tools.register(defineTool({ name: 'soyo_automation_publish_image', description: '准备当前简报图片草稿，只接受 native media root 内已验证的图片。', parameters: { job_id: { type: 'string', required: true }, image_path: { type: 'string', required: true } }, output,
      async execute(args, exec) {
        authorize(args.job_id, exec); const path = resolve(args.image_path), rel = relative(resolve(config.media_root), path);
        if (!rel || rel.startsWith('..') || isAbsolute(rel) || !/\.(png|jpe?g|webp|gif)$/i.test(path)) throw Error('Media path outside grant');
        const stat = await lstat(path); if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 20 * 1024 * 1024) throw Error('Invalid media artifact');
        return stagePublication(args.job_id, '', { path, sha256: createHash('sha256').update(await readFile(path)).digest('hex'), bytes: stat.size }, exec, authorize);
      } }));
    scope.tools.register(defineTool({ name: 'soyo_automation_render_briefing', description: '渲染带可验证新闻来源的中文简报 JSON（title/date/headline/deep/quick）。不会发送。', parameters: { job_id: { type: 'string', required: true }, payload: { type: 'string', required: true } }, output,
      execute(args, exec) { authorize(args.job_id, exec); if (!briefingJobs.has(args.job_id) || args.payload.length > 32000) throw Error('Briefing grant missing');
       return worker(JSON.parse(args.payload), exec.signal, config.briefing_render_script, 30000); } }));
   };
   const scheduled = dualMode(config) ? new ScheduledBrains(ctx, config, ctx.soyoBrains.brains, {
     manifest, save: saveRun, commit: work => commitEffect(work, undefined), registerTools,
     allowedTools: jobId => jobId === probeJob ? ['soyo_automation_probe_check']
       : qzoneJobs.has(jobId) ? ['soyo_automation_context', 'soyo_automation_publish']
       : briefingJobs.has(jobId) ? ['web_search', 'web_fetch', 'soyo_automation_context', 'soyo_automation_publish_image', 'soyo_automation_render_briefing'] : [],
   }) : null;
   if (scheduled) await scheduled.initialize();
   const setup = agent => {
     const scope = agent.ctx, allowed = ['web_search', 'web_fetch', 'soyo_automation_context', 'soyo_automation_publish', 'soyo_automation_publish_image', 'soyo_automation_render_briefing', 'soyo_automation_probe_check'];
     scope.tools.restrict({ allow: scheduled ? [] : ['web_search', 'web_fetch'] });
     scope.tools.guard(exec => !scheduled && allowed.includes(exec.name) && active.has(agent.id) ? undefined : 'The clock has no model execution tools; use the bound role/action occurrence');
     if (!scheduled) registerTools(scope, authorize);
    scope.on('agent/pre-step', async (payload, next) => {
      if (payload.messages.some(message => message.source?.rpcId)) return { kind: 'reject' };
      const reminders = payload.messages.flatMap(parseReminders);
      if (!reminders.length) return active.has(agent.id) ? next() : { kind: 'reject' };
      const works = [];
      for (const reminder of reminders) {
        const jobId = Object.keys(manifest).find(id => manifest[id].schedule_id === reminder.schedule_id);
        if (!jobId || (!jobIds.has(jobId) && !(jobId === probeJob && manifest[jobId].probe))) continue;
        if (!Number.isFinite(Date.parse(reminder.occurrence_at))) throw Error('Invalid native occurrence');
        const work = { id: digest([jobId, reminder.occurrence_at]), job_id: jobId, occurrence_at: reminder.occurrence_at, state: 'admitted', created_at: Date.now(),
          ...(jobId === probeJob ? { probe: true, marker: manifest[jobId].marker } : {}) };
        try { await privateJSON(join(runsRoot, work.id + '.json')); continue; } catch (error) { if (error.code !== 'ENOENT') throw error; }
        // DSH emits latest-missed reminders after restart. A prior occurrence
        // is kept as evidence but never becomes a new model/effect obligation.
        if (Date.parse(work.occurrence_at) < startedAt || Date.now() - Date.parse(work.occurrence_at) > 90000) {
          work.state = 'skipped'; work.reason = 'no_catchup'; await saveRun(work); continue;
        }
        await saveRun(work);
        if (scriptJobs.has(jobId) || memoryJobs.has(jobId)) {
          try { await scriptRun(work, payload.signal); } catch { work.state = 'unknown'; work.reason = 'script_interrupted'; await saveRun(work); }
         } else if (scheduled) {
           work.goal = qzoneJobs.has(jobId)
             ? '只据当前公开群原话和最近动态，决定是否准备一条不含个人标识/私聊的日常Qzone草稿，无合适内容就沉默。'
             : '核验最新科技新闻与真实来源，制作中文title/date/headline/deep/quick简报JSON，渲染并准备当前owner图片草稿，不编造日期/新闻。';
           await scheduled.enqueue(work);
         } else { work.state = 'running'; await saveRun(work); works.push(work); }
      }
      if (!works.length) return { kind: 'reject' };
      active.set(agent.id, works);
      const timer = setTimeout(() => agent.cancel({ kind: 'hook', reason: 'Automation deadline' }), 180000);
      for (const work of works) work._timer = timer;
      return next();
    });
  };
  const assembled = new WeakSet();
  const assemble = agent => { if (agent.id === sessionId && !assembled.has(agent)) { assembled.add(agent); setup(agent); } };
  ctx.on('agent/created', ({ agent }) => assemble(agent), { global: true });
  const existingAgent = ctx.agents.get(sessionId); if (existingAgent) assemble(existingAgent);
  ctx.on('session/event', (session, event) => {
    if (session.id !== sessionId || !active.has(session.id)) return;
    const works = active.get(session.id);
    const agent = ctx.agents.get(session.id);
    if (event.type === 'assistant/message') {
      const text = (event.data.message?.content || []).filter(block => block.type === 'text').map(block => block.text).join('').trim();
      for (const work of works) if (text) work.final_text = text.slice(0, 12000);
      return;
    }
    if (event.type !== 'turn/end') return;
    active.delete(session.id); // Headers/step/tool events do not revoke a turn's grant.
    Promise.resolve().then(async () => {
      for (const work of works) { clearTimeout(work._timer); delete work._timer; }
      if (event.data.reason.kind !== 'completed') { for (const work of works) { work.state = 'cancelled'; work.reason = event.data.reason.kind; await saveRun(work); } return; }
      await agent?.whenIdle(); await ctx.sessions.flush(session);
      for (const work of works) await commitEffect(work, undefined);
    }).catch(() => console.error('Automation finalization unavailable; no unfenced retry'));
  }, { global: true });
  const stat = await ctx.sessionPersistence.stat(sessionId);
  if (!stat) {
    const cwd = join(config.workspace, 'automation'); await mkdir(cwd, { recursive: true, mode: 0o700 });
    const session = ctx.sessions.prepare(sessionId, { meta: { cwd } });
    session.append('session/title', { title: 'Bot · 自动化', source: { kind: 'user' }, messageSeqs: [] });
    const handle = await ctx.sessionPersistence.create(session.header); try { await handle.append(session.snapshotEvents()); await handle.flush(); } finally { await handle.close(); }
  }
  const workspace = await ctx.workspaceRegistry.create(join(config.workspace, 'automation'), 'Bot · 自动化与心跳'); await workspace.setTitle('Bot · 自动化与心跳'); await workspace.attachSession(sessionId);

  // Only explicitly configured future schedules are installed. No production
  // job IDs, remembered cron times, or automatic daily publication defaults.
  const catalogAtStart = await ctx.schedule.catalog();
  for (const job of config.automation_jobs ?? []) {
    if (!jobIds.has(job.id)) continue;
    const request = requestFor(job, config), signature = digest(request), previous = manifest[job.id];
    if (previous?.schedule_id && catalogAtStart.some(row => row.id === previous.schedule_id)) {
      if (previous.config_digest !== signature) throw Error('Configured schedule changed; explicitly remove its old native Schedule before recreating it');
      continue;
    }
    const record = await ctx.schedule.create(sessionId, request);
    manifest[job.id] = { state: 'native', schedule_id: record.id, session_id: sessionId, config_digest: signature,
      title: record.title, catchup: false, created_at: new Date().toISOString() };
    await durable(manifestPath, manifest);
  }

  let migrationTail = Promise.resolve();
  async function migrate(dryRun) {
    if (!config.legacy_cron_file) throw Error('Legacy schedule discovery file is not configured');
    const legacy = await privateJSON(config.legacy_cron_file, 4 * 1024 * 1024);
    const jobs = (legacy.jobs || []).filter(job => job.enabled !== false && jobIds.has(job.id));
    if (dryRun) return { state: 'planned', jobs: jobs.map(({ id, name, schedule }) => ({ legacy_id: id, name, schedule })), catchup: false };
    const catalog = await ctx.schedule.catalog();
    for (const job of jobs) {
      const existing = manifest[job.id];
      if (existing?.schedule_id && catalog.some(row => row.id === existing.schedule_id)) continue;
      const request = requestFor(job, config);
      const orphan = catalog.find(row => row.sessionId === sessionId && row.title === request.title);
      const record = orphan ?? await ctx.schedule.create(sessionId, request);
      manifest[job.id] = { state: 'migrated', schedule_id: record.id, session_id: sessionId, title: record.title, catchup: false, created_at: new Date().toISOString() };
      await durable(manifestPath, manifest); // persist EACH identity before the next creation
    }
    return { state: 'migrated', manifest, catchup: false, old_scheduler_changed: false };
  }
  async function handler(req, res) {
    const supplied = Buffer.from(req.headers.authorization || ''), expected = Buffer.from('Bearer ' + config.host_key);
    const answer = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); };
    if (req.method !== 'POST' || supplied.length !== expected.length || !timingSafeEqual(supplied, expected)) return answer({ kind: 'reject' }, 401);
    let size = 0, raw = ''; for await (const chunk of req) { size += chunk.length; if (size > 96 * 1024) throw Error('Body too large'); raw += chunk; }
    const input = JSON.parse(raw || '{}');
    if (req.url === '/automation-catalog') return answer({ session_id: sessionId, manifest, schedule_bundle: await ctx.schedule.catalog(),
      receipt_reconciliation: receiptObservation,
       brain_mode: scheduled ? 'character-action' : 'legacy-automation',
       active_occurrences: [...active.values()].flat().map(({ id, job_id, state }) => ({ id, job_id, state })).concat(scheduled?.catalog() ?? []) });
    if (req.url === '/automation-probe') {
      if (typeof input.marker !== 'string' || !/^[A-Za-z0-9_-]{1,120}$/.test(input.marker)) throw Error('Invalid probe marker');
       if (active.size || scheduled?.works.size) return answer({ state: 'busy' }, 409);
      const prior = manifest[probeJob];
      if (prior?.schedule_id && (await ctx.schedule.catalog()).some(row => row.id === prior.schedule_id && row.status === 'active'))
        return answer({ state: 'busy' }, 409);
      const record = await ctx.schedule.create(sessionId, { title: 'Bot · native grant probe', after_seconds: 15,
        prompt: `这是一次性、无平台副作用的原生 Schedule grant 验证。只调用一次 soyo_automation_probe_check，job_id=${probeJob}，读取返回的 marker 后最终只写 ${input.marker}。不能调用发布、web 或其他工具。` });
      manifest[probeJob] = { probe: true, marker: input.marker, schedule_id: record.id, session_id: sessionId, catchup: false };
      await durable(manifestPath, manifest);
      return answer({ state: 'accepted', schedule_id: record.id, job_id: probeJob, scheduled_at: record.scheduledAt });
    }
    if (req.url === '/automation-probe-status') {
      const record = manifest[probeJob];
      if (!record) return answer({ state: 'missing' });
      const key = digest([probeJob, input.occurrence_at]);
      try { return answer(await privateJSON(join(runsRoot, key + '.json'))); }
      catch (error) { if (error.code !== 'ENOENT') throw error; return answer({ state: 'pending' }); }
    }
    if (req.url === '/migrate-schedules') { const work = migrationTail.catch(() => {}).then(() => migrate(input.dry_run !== false)); migrationTail = work; return answer(await work); }
    return answer({ kind: 'reject' }, 404);
  }
  const server = http.createServer((req, res) => handler(req, res).catch(() => { if (!res.headersSent) { res.writeHead(503); res.end('{"kind":"retry"}'); } else res.destroy(); }));
  server.maxConnections = 8; server.requestTimeout = 15000;
  // Historical receipt reconciliation is model/effect-free and may scan a large
  // ledger. Do not hold appReady (and the Web mux) until that scan finishes.
  reconcileReceipts().catch(() => console.error('Automation receipt reconciliation deferred; no effects replayed'));
  const receiptTimer = setInterval(() => reconcileReceipts().catch(() => console.error('Automation receipt reconciliation deferred; no effects replayed')), 15000);
  receiptTimer.unref();
  ctx.effect(() => async () => { server.close(); clearInterval(receiptTimer); await receiptTail.catch(() => {});
    for (const works of active.values()) for (const work of works) clearTimeout(work._timer); });
  await listenPrivate(server, config, 'automation');
}
