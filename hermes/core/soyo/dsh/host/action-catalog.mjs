// SPDX-License-Identifier: MIT
// A native child is discovered once, not once per task that reuses it.
export function ensureActionCatalog(parent, child, descriptor) {
  if (child.header.parentSession !== parent.id) throw Error('Action child belongs to a different parent');
  const cut = parent.inheritedEventCount ?? 0;
  const rows = parent.snapshotEvents().filter(event => event.seq >= cut &&
    event.type === 'subagent/catalog' && event.data.childId === child.id);
  if (rows.length > 1) throw Error('Parent action catalog needs explicit recovery before reuse');
  if (rows.length) {
    if (rows[0].data.childCreatedAt !== child.header.createdAt || rows[0].data.mode !== descriptor.mode)
      throw Error('Action child catalog identity changed');
    return false;
  }
  parent.append('subagent/catalog', { version: 0, mode: descriptor.mode, label: descriptor.label,
    childId: child.id, childCreatedAt: child.header.createdAt });
  return true;
}

/** Offline recovery only: preserve event coordinates/payloads, demote identical rediscovery to audit. */
export function recoverActionCatalogEvents(events, inheritedEventCount = 0) {
  const seen = new Map(), repairedSeqs = [];
  const recovered = events.map(event => {
    if (event.seq < inheritedEventCount || event.type !== 'subagent/catalog') return event;
    const first = seen.get(event.data.childId);
    if (!first) { seen.set(event.data.childId, event); return event; }
    if (first.data.childCreatedAt !== event.data.childCreatedAt || first.data.mode !== event.data.mode ||
        first.data.version !== event.data.version) throw Error('Conflicting child identity; automatic recovery refused');
    repairedSeqs.push(event.seq);
    return { ...event, type: 'plugin:soyo/action-catalog-reuse', ignorable: true };
  });
  return { events: recovered, repairedSeqs };
}

export function sameActionScope(previous, actor, parentId, sandboxOnly) {
  const sorted = values => [...(values ?? [])].sort();
  return Boolean(previous?.actor && actor && previous.parent_session === parentId && previous.actor.kind === actor.kind &&
    previous.actor.route_id === actor.route_id && previous.actor.sender_id === actor.sender_id &&
    previous.actor.policy_epoch === actor.policy_epoch && previous.actor.session_class === actor.session_class &&
    Boolean(previous.sandbox_only) === sandboxOnly && previous.purpose !== 'cognition' &&
    JSON.stringify(sorted(previous.actor.capabilities)) === JSON.stringify(sorted(actor.capabilities)));
}

/**
 * A QQ scene is not a project key: one private chat may contain unrelated
 * image, maintenance, and research requests.  Continuation therefore needs
 * an explicit bounded identifier instead of being inferred from the scene.
 */
export function normalizeActionWorkKey(value) {
  if (value === undefined || value === null || value === '') return null;
  if (typeof value !== 'string') throw Error('Action work key must be a string');
  const key = value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$/.test(key))
    throw Error('Action work key must be a bounded identifier');
  return key;
}

export function actionWorkRegistryKey(actor, continuationKey) {
  if (!continuationKey) return null;
  return [actor?.kind || 'unknown', actor?.route_id || actor?.sender_id || 'owner', continuationKey].join(':');
}

export function canReuseActionWork({ held, previous, actor, parentId, sandboxOnly, ttlMs, now = Date.now(), fresh = false, archived = false }) {
  return Boolean(held && !fresh && typeof held.session_id === 'string' &&
    held.session_id.startsWith('soyo-action-') && !held.session_archived && !held.reuse_ineligible &&
    !previous?.session_archived && !previous?.reuse_ineligible &&
    !archived &&
    sameActionScope(previous, actor, parentId, sandboxOnly) &&
    ['completed', 'failed'].includes(previous.state) && Number(ttlMs) > 0 &&
    now - (held.last_used_at || 0) < Number(ttlMs));
}
