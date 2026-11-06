// SPDX-License-Identifier: MIT
// Notification, not a destructive claim. Repeated reads keep the same attempt.
export class ReadyOutbox {
  constructor() { this.items = new Map(); this.waiters = new Set(); this.version = 0; this.closed = false; }
  put(item) { this.items.set(item.publication_id, item); this.changed(); }
  remove(id) { if (this.items.delete(id)) this.changed(); }
  changed() { this.version++; for (const wake of [...this.waiters]) wake(); }
  async read({ waitMs = 0, signal, valid = () => true } = {}) {
    const select = () => [...this.items.values()].filter(valid).slice(0, 16);
    let result = select();
    if (result.length || !waitMs || this.closed || signal?.aborted) return result;
    const version = this.version;
    await new Promise(resolve => {
      let timer;
      const done = () => { clearTimeout(timer); this.waiters.delete(done); signal?.removeEventListener('abort', done); resolve(); };
      this.waiters.add(done); signal?.addEventListener('abort', done, { once: true });
      timer = setTimeout(done, Math.min(15000, Math.max(0, waitMs)));
      if (this.closed || signal?.aborted || version !== this.version || select().length) done();
    });
    return select();
  }
  close() { this.closed = true; this.changed(); }
}
