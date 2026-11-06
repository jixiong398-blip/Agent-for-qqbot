// SPDX-License-Identifier: MIT
// One live Agent per scene, bounded global model concurrency. Inputs are durable
// jobs owned by the caller; this queue never deletes sources or writes transcripts.
export function inputIntent(envelope) {
  if (envelope.reply_to || envelope.forward_refs?.length || envelope.media?.length) return 'message';
  const text = String(envelope.text ?? '').trim();
  if (/^(?:\/stop|停一下|停止回复|先别回复了|先别回了|别说了|不用回复了)[。！!\s]*$/i.test(text)) return 'stop';
  if (/^(?:停止这个任务|停止当前任务|停止任务|别画了|先别做了)[。！!\s]*$/.test(text)) return 'stop-action';
  if (/^(?:不是这个|不对[，,：:]|不是[，,：:]|改成|换成|不要这个)/.test(text)) return 'correct';
  if (/^(?:补充[：:，,]|再注意|注意一下|刚才还漏了)/.test(text)) return 'supplement';
  return 'message';
}

export class SceneScheduler {
  constructor({ run, save, owner = () => false, quietMs = 250, maxWaitMs = 900, limit = 2, onError = () => {} }) {
    Object.assign(this, { run, save, owner, quietMs, maxWaitMs, limit, onError });
    this.queue = []; this.running = new Map(); this.closed = false;
  }
  /** Per-job debounce window: private chat waits for the burst, groups answer at once. */
  windowOf(job) {
    const quiet = Number.isFinite(job.quiet_ms) ? job.quiet_ms : this.quietMs;
    const wait = Number.isFinite(job.max_wait_ms) ? job.max_wait_ms : this.maxWaitMs;
    return { quiet: Math.max(0, quiet), maxWait: Math.max(0, wait) };
  }
  enqueue(job) {
    if (this.closed) return;
    job.queued_at ??= Date.now();
    job.state = 'queued';
    this.queue.push(job); this.wake();
  }
  priority(job, now) {
    const base = job.internal_source === 'action-question' ? 2 : job.internal ? 20 : this.owner(job) ? 0 : 8;
    return base - Math.floor((now - job.queued_at) / 1500);
  }
  wake() {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.pump(), 0); this.timer.unref?.();
  }
  async takeSupplements(job) {
    const selected = this.queue.filter(next => next.state === 'queued' && !next.internal &&
      next.intent === 'supplement' && next.envelope.route_id === job.envelope.route_id &&
      next.envelope.sender_id === job.envelope.sender_id && next.policy_epoch === job.policy_epoch);
    for (const next of selected) {
      this.queue.splice(this.queue.indexOf(next), 1);
      next.state = 'coalesced'; next.covered_by = job.key; await this.save(next);
    }
    return selected;
  }
  async pump() {
    if (this.pumping || this.closed) return;
    this.pumping = true;
    try {
      this.queue = this.queue.filter(job => job.state === 'queued');
      while (this.running.size < this.limit) {
        const now = Date.now();
        const eligible = this.queue.filter(job => !this.running.has(job.envelope.route_id));
        const ready = eligible.filter(job => {
          if (job.internal) return true;
          const { quiet, maxWait } = this.windowOf(job);
          const burst = this.queue.filter(next => !next.internal && next.envelope.route_id === job.envelope.route_id &&
            next.envelope.sender_id === job.envelope.sender_id && next.policy_epoch === job.policy_epoch);
          const newest = burst.length ? Math.max(...burst.map(next => next.queued_at), job.queued_at) : job.queued_at;
          return now >= Math.min(job.queued_at + maxWait, newest + quiet);
        });
        ready.sort((a, b) => this.priority(a, now) - this.priority(b, now) || a.queued_at - b.queued_at);
        const job = ready[0]; if (!job) break;
        this.queue.splice(this.queue.indexOf(job), 1);
        const batch = job.internal ? [] : this.queue.filter(next => !next.internal && next.state === 'queued' &&
          next.envelope.route_id === job.envelope.route_id && next.envelope.sender_id === job.envelope.sender_id &&
          next.policy_epoch === job.policy_epoch && next.queued_at - job.queued_at <= this.windowOf(job).maxWait);
        for (const next of batch) {
          this.queue.splice(this.queue.indexOf(next), 1); next.state = 'coalesced'; next.covered_by = job.key;
          await this.save(next);
        }
        job.batch_inputs = [job.envelope, ...batch.flatMap(next => next.batch_inputs ?? [next.envelope])];
        job.input_keys = [...new Set([job.key, ...batch.flatMap(next => next.input_keys ?? [next.key])])];
        job.covered_event_ids = [...new Set(job.batch_inputs.map(input => input.event_id))];
        await this.save(job);
        this.running.set(job.envelope.route_id, job);
        Promise.resolve().then(() => this.run(job)).catch(this.onError).finally(() => {
          this.running.delete(job.envelope.route_id); this.wake();
        });
      }
    } catch (error) { this.onError(error); }
    finally {
      this.pumping = false;
      if (this.queue.length && !this.closed) {
        clearTimeout(this.timer); this.timer = setTimeout(() => this.pump(), 40); this.timer.unref?.();
      }
    }
  }
  async cancel(predicate, reason = 'cancelled') {
    const cancelled = [];
    for (const job of [...this.queue]) {
      if (!predicate(job)) continue;
      this.queue.splice(this.queue.indexOf(job), 1);
      job.state = reason === 'superseded' ? 'superseded' : 'cancelled';
      job.reason = reason; await this.save(job); cancelled.push(job);
    }
    return cancelled;
  }
  close() { this.closed = true; clearTimeout(this.timer); }
}
