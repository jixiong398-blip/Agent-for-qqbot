// SPDX-License-Identifier: MIT
import { realpath } from 'node:fs/promises';

export function imageMayGenerate(config, { owner = false, envelope = {}, internal = false } = {}) {
  const policy = config.image_permissions ?? {};
  if (policy.enabled === false || internal) return false;
  if (owner) return true;
  const groups = Array.isArray(policy.group_ids) ? policy.group_ids.map(String) : [];
  return policy.allow_group_members === true && envelope.message_type === 'group' &&
    envelope.route_id === 'qq-group-' + String(envelope.target_id) &&
    (!groups.length || groups.includes(String(envelope.target_id)));
}

export async function sceneImagePaths(paths, allowed, owner = false) {
  if (!Array.isArray(paths) || paths.length > 4 || paths.some(p => typeof p !== 'string' || !p.trim()))
    throw Error('IMAGE_SOURCE: up to four explicit image paths are required');
  const resolved = [];
  for (const path of paths) {
    const real = await realpath(path);
    if (!owner && !allowed?.has(real)) throw Error('IMAGE_SOURCE: reference must belong to this admitted scene/task');
    resolved.push(real);
  }
  return resolved;
}
