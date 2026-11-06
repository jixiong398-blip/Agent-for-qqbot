// SPDX-License-Identifier: MIT
// Effect intents live in the SAME durable job/publication as their source.
// Only idempotent derived effects belong here; no model calls or platform sends.
export class DurableEffects {
  constructor({ save, apply, onError = () => {} }) {
    Object.assign(this, { save, apply, onError }); this.records = new Map(); this.tails = new Map(); this.closed = false;
    this.timer = setInterval(() => { for (const record of this.records.values()) this.schedule(record); }, 5000);
    this.timer.unref?.();
  }
  schedule(record) {
    const key = record.key ?? record.publication_id;
    this.records.set(key, record);
    if (this.closed || this.active?.has(key)) return;
    this.active ??= new Set(); this.active.add(key);
    const domain = record.envelope?.route_id ?? record.route_id;
    const work = (this.tails.get(domain) ?? Promise.resolve()).catch(() => {}).then(async () => {
      for (const effect of record.effects ?? []) {
        if (this.closed || effect.done) continue;
        if (effect.retry_at > Date.now()) break;
        try {
          await this.apply(effect, record); effect.done = true; effect.done_at = Date.now(); delete effect.retry_at;
          await this.save(record);
        } catch (error) {
          effect.failures = (effect.failures ?? 0) + 1;
          effect.retry_at = Date.now() + Math.min(60000, 1000 * 2 ** Math.min(6, effect.failures));
          await this.save(record).catch(this.onError); this.onError(error); break;
        }
      }
      if ((record.effects ?? []).every(effect => effect.done)) this.records.delete(key);
    });
    this.tails.set(domain, work);
    work.finally(() => { this.active.delete(key); if (this.tails.get(domain) === work) this.tails.delete(domain); }).catch(this.onError);
  }
  async barrier(domain) {
    for (const record of this.records.values()) if ((record.envelope?.route_id ?? record.route_id) === domain) this.schedule(record);
    await this.tails.get(domain);
    if ([...this.records.values()].some(record => (record.envelope?.route_id ?? record.route_id) === domain &&
      record.effects?.some(effect => !effect.done && effect.required))) throw Error('MEMORY_PROJECTION_PENDING');
  }
  async close() { this.closed = true; clearInterval(this.timer); await Promise.allSettled([...this.tails.values()]); }
}
