// SPDX-License-Identifier: MIT
// Round-robin between author sessions, FIFO within one author's accepted work.
export class AuthorActionQueue {
  constructor(limit = 32) { this.limit = limit; this.groups = new Map(); this.order = []; }
  get size() { return [...this.groups.values()].reduce((count, rows) => count + rows.length, 0); }
  add(parent, id) {
    if (this.size >= this.limit) throw Error('ACTION_QUEUE_FULL: no work accepted');
    if (!this.groups.has(parent)) { this.groups.set(parent, []); this.order.push(parent); }
    this.groups.get(parent).push(id);
  }
  next() {
    const parent = this.order.shift(); if (!parent) return null;
    const rows = this.groups.get(parent), id = rows.shift();
    if (rows.length) this.order.push(parent); else this.groups.delete(parent);
    return id;
  }
  remove(id) {
    for (const [parent, rows] of this.groups) {
      const index = rows.indexOf(id); if (index < 0) continue;
      rows.splice(index, 1);
      if (!rows.length) { this.groups.delete(parent); this.order = this.order.filter(value => value !== parent); }
      return true;
    }
    return false;
  }
}
