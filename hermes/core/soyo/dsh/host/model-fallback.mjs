// SPDX-License-Identifier: MIT
// Deployment-owned ordered routes. Native request headers/attempts/retries remain the evidence.
import { randomUUID, createHash } from 'node:crypto';
import z from '@deepseek-ai/schemastery';

export const name = 'soyo-model-fallback';
export const inject = ['agents', 'llm'];
export const Config = z.object({
  routes: z.array(z.object({ provider: z.string().required(), model: z.string().required(),
    maxTokens: z.natural().min(1).required() })).required(),
  stepBudgetMs: z.natural().min(1000).max(300000).default(120000),
  fallbackOnContextOverflow: z.boolean().default(false),
});
const RECOVERABLE = new Set(['QUOTA', 'ACCOUNT_QUOTA', 'AUTH', 'RATE_LIMIT', 'SERVER',
  'TIMEOUT', 'TRANSPORT', 'STREAM_CLOSED', 'EMPTY_RESPONSE']);
const sameRoute = (a, b) => a?.provider === b?.provider && a?.model === b?.model;

// A started block, including reasoning/tool arguments, is already observable.
// Do not replay that attempt against another provider, even if its output was incomplete.
function emptyFailedAttempt(session, turn, step) {
  const attempt = session.snapshotEvents().findLast(event => event.type === 'assistant/attempt');
  return attempt?.data.turn === turn && attempt.data.step === step &&
    attempt.data.stream.every(record => record.type === 'chunk' &&
      (record.chunk.type === 'usage' || record.chunk.type === 'finish'));
}

export function apply(ctx, config) {
  const routes = config.routes.map(route => Object.freeze({ ...route }));
  if (!routes.length || new Set(routes.map(route => route.provider)).size !== routes.length) {
    throw new Error('Bot fallback needs distinct, explicitly configured provider routes.');
  }
  const policyKey = 'soyo-fallback:' + createHash('sha256').update(JSON.stringify(routes)).digest('hex');
  const states = new WeakMap();
  const lifetime = new AbortController();
  ctx.effect(() => () => lifetime.abort(new Error('Bot fallback disposed.')));

  ctx.on('agent/request', async ({ agent, turn, step, signal }, next) => {
    const proposed = await next();
    const requestedIndex = routes.findIndex(route => sameRoute(route, proposed));
    if (requestedIndex < 0) { states.delete(agent); return proposed; }
    let state = states.get(agent);
    if (!state || state.turn !== turn || !sameRoute(state.requested, proposed)) {
      state = { turn, requested: { provider: proposed.provider, model: proposed.model },
        index: requestedIndex, step: null, deadline: 0, visited: new Set() };
      states.set(agent, state);
    }
    if (state.step !== step) {
      state.step = step; state.deadline = Date.now() + config.stepBudgetMs; state.visited = new Set();
    }
    const selected = routes[state.index];
    state.visited.add(state.index);
    if (sameRoute(selected, proposed)) return { ...proposed,
      maxTokens: Math.min(proposed.maxTokens ?? selected.maxTokens, selected.maxTokens) };
    // Do not send the primary's output/reasoning settings to a different model.
    const { maxTokens: _tokens, reasoningEffort: _effort, ...rest } = proposed;
    return { ...rest, provider: selected.provider, model: selected.model, maxTokens: selected.maxTokens };
  }, { prepend: true });

  ctx.on('agent/request-error', async (payload, next) => {
    const { agent, turn, step, provider, failure, signal } = payload;
    const state = states.get(agent);
    if (!state || state.turn !== turn || state.step !== step || routes[state.index].provider !== provider) return next();
    if (signal.aborted || lifetime.signal.aborted || !emptyFailedAttempt(agent.session, turn, step)) return;
    if (!RECOVERABLE.has(failure.code) && !(config.fallbackOnContextOverflow &&
      failure.code === 'CONTEXT_WINDOW_EXCEEDED')) return next(); // Native handling remains the default.
    if (Date.now() >= state.deadline) return;
    const nextIndex = routes.findIndex((_route, index) => index > state.index && !state.visited.has(index));
    if (nextIndex < 0) return;
    const retryId = randomUUID(), retry = state.visited.size;
    // Known native event vocabulary; no credentials/endpoints or invented surface events.
    agent.session.append('llm/retry', { retryId, turn, step, provider, mode: 'normal', policyKey,
      retry, maxRetries: routes.length - 1, delayMs: 0,
      failure: { code: failure.code, message: 'Configured model route failed before producing content.' } });
    signal.throwIfAborted();
    if (lifetime.signal.aborted) return;
    state.index = nextIndex;
    agent.session.append('llm/retry-started', { retryId, turn, step, retry });
    ctx.logger.info('Bot model fallback: %s -> %s (%s)', provider, routes[nextIndex].provider, failure.code);
    return { kind: 'retry' };
  }, { prepend: true });

  // DSH's adapterStream already converts adapter throws to typed finish chunks.
  // Do not bypass its prepared-call/checkpoint boundary or mutate a frozen request.
}
