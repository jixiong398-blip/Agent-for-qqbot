// SPDX-License-Identifier: MIT
// Settlement opportunities, not a new clock, wake, permission, or historical replay.
export function canSettleCognition(config, job, reason, parent, tasks) {
  if (config.brain_mode !== 'character-action' || config.cognition_enabled !== true || job.probe || reason !== 'completed') return false;
  if (job.internal && !(job.internal_source === 'action-report' && job.binding?.task_continuation === true &&
      /^[a-f0-9]{64}$/.test(job.origin_job_key ?? ''))) return false;
  return ![...tasks].some(task => task.parent_session === parent && ['starting', 'running'].includes(task.state));
}
