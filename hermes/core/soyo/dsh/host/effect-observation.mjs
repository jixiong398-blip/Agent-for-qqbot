// SPDX-License-Identifier: MIT
// Interpret the actual frozen tools/result value, never model prose or isError alone.
export function effectObservation(name, result) {
  if (result.isError) return { verified: false, state: 'tool-error' };
  const value = result.value;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { verified: false, state: 'no-canonical-value' };
  if (name === 'bash') return { verified: value.kind === 'foreground' && value.exitCode === 0 && value.signal === null &&
      !value.timedOut && !value.aborted && !value.sandbox?.denied && !value.sandbox?.runnerFailed,
    state: value.kind === 'foreground' ? 'process-ended' : 'background-not-settled',
    exit_code: Number.isInteger(value.exitCode) ? value.exitCode : null };
  if (['read', 'write', 'edit'].includes(name)) return { verified: typeof value.path === 'string' && value.path.length > 0,
    state: name === 'read' ? 'file-observed' : 'file-mutation-returned' };
  if (name === 'soyo_development') return { verified: value.state === 'completed' && value.exit_code === 0,
    state: 'candidate-only', exit_code: value.exit_code ?? null };
  if (name === 'soyo_review_candidate') return { verified: false,
    state: value.state === 'reviewed' ? 'independent-review-returned' : 'review-not-accepted', review_id: value.review_id ?? null };
  if (name.startsWith('qq_') || name === 'soyo_qq_action' || name === 'soyo_qq_forward')
    return { verified: value.success === true, state: value.success === true ? 'platform-action-accepted' : 'platform-action-not-accepted' };
  return { verified: false, state: 'not-a-goal-effect' };
}
