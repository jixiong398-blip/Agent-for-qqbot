// SPDX-License-Identifier: MIT
// Host task lineage, not model-supplied depth or native Agent ancestry depth.
export const MAX_AUTOMATIC_FEEDBACK_DEPTH = 3;
export function nextFeedbackDepth(actor, tasks, parentId) {
  if (!actor.feedback_task_id) return { delegation_depth: 1, feedback_parent_id: null };
  const previous = tasks.get(actor.feedback_task_id);
  if (!previous || previous.parent_session !== parentId || !Number.isSafeInteger(previous.delegation_depth) || previous.delegation_depth < 1)
    throw Error('ACTION_FEEDBACK_DEPTH_UNKNOWN: retained legacy feedback cannot silently start a new chain');
  const depth = previous.delegation_depth + 1;
  if (depth > MAX_AUTOMATIC_FEEDBACK_DEPTH)
    throw Error('ACTION_FEEDBACK_DEPTH_LIMIT: automatic report/delegation chain is bounded; retain results, do not retry the same feedback');
  return { delegation_depth: depth, feedback_parent_id: previous.id };
}
