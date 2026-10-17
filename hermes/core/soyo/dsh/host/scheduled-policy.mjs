// SPDX-License-Identifier: MIT
// A character decision is not a platform receipt and cannot create an artifact.
export function scheduledDecision(work, task, args, phase, now = Date.now()) {
  if (phase !== 'feedback' || args.task_id !== work.action_task_id || task?.parent_session !== work.role_session_id ||
      task.actor?.occurrence_id !== work.id || typeof args.reason !== 'string' || !args.reason.trim() || args.reason.length > 500 ||
      !['approve', 'silent', 'blocked'].includes(args.decision)) throw Error('Current reported task decision required');
  if (work.role_decision) throw Error('The current report already has a durable character decision');
  if (args.decision === 'approve' && (task.state !== 'completed' || !(work.publication || work.probe === true && work.probe_checked === true)))
    throw Error('No completed executor artifact to approve');
  return { decision: args.decision, reason: args.reason, task_id: args.task_id, at: now };
}
export const scheduledEffectApproved = (work, roleCompleted) => roleCompleted === true &&
  work.initial_role_completed === true && work.role_decision?.decision === 'approve';
