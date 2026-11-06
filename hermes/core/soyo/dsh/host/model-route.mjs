// SPDX-License-Identifier: MIT
// No utility-specific model or credentials. Explicit execution stays on action;
// implicit language work (including memory settlement) prefers the global role.
export function modelRoute(config, purpose = 'character') {
  const legacy = config.collaborator && { provider: config.collaborator.provider,
    model: config.collaborator.model, maxTokens: config.collaborator.max_tokens,
    ...(config.collaborator.reasoning_effort ? { reasoningEffort: config.collaborator.reasoning_effort } : {}) };
  const role = config.agent_options;
  const action = config.action_agent_options ?? legacy;
  const selected = purpose === 'action' ? action ?? role : role ?? action;
  if (!selected?.provider || !selected?.model) throw Error('GLOBAL_MODEL_ROUTE_REQUIRED');
  return { ...selected };
}
