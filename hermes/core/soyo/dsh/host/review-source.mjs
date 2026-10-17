// SPDX-License-Identifier: MIT
// Configured route metadata only. This does not fetch a model, read a key,
// probe the relay, or prove that an independent review has run.
export function gptReviewSource(ctx, config) {
  const synthetic = config.reviewer?.source_kind === 'synthetic-fixture' && config.direct_root !== true;
  const fixed = config.action_agent_options ?? config.collaborator ?? {};
  const provider = typeof fixed.provider === 'string' ? fixed.provider : null;
  const model = typeof fixed.model === 'string' ? fixed.model : null;
  let registered = false, profile, origin = null;
  try {
    registered = ctx.llm.listProviders().some(item => item.id === provider);
    const entry = ctx.llm.listConfigurableProviders().find(item => item.provider === provider);
    const section = entry && ctx.settings.describe({ redactSecrets: true }).find(item => item.ns === entry.settingsNs);
    profile = entry?.settingsPath.reduce((value, key) => value?.[key], section?.value);
    if (typeof profile?.baseURL === 'string') {
      const url = new URL(profile.baseURL);
      // Never project credentials, a query string, or arbitrary URL paths.
      if (['http:', 'https:'].includes(url.protocol)) origin = url.origin;
    }
  } catch { /* Missing plugin metadata is unknown, not a healthy relay. */ }
  const wire = ['openai-responses', 'openai-completions'].includes(profile?.api) ? profile.api : null;
  return {
    label: synthetic ? '隔离审阅机制（非真实模型）' : (config.reviewer?.label ?? config.collaborator?.label ?? '配置的行动模型 · 独立审阅'),
    source_kind: synthetic ? 'synthetic-fixture' : 'relay-gpt', provider, model,
    endpoint_origin: origin, wire_protocol: wire, provider_registered: registered,
    fixed_executor_route: Boolean(provider && model && provider === config.collaborator?.provider && model === config.collaborator?.model),
    context_policy: 'fresh-explicit-material-only', executable_tools: false,
    external_client_status: 'deferred', availability_checked: false,
    evidence_source: 'native-provider-configuration', model_woken: false, platform_sends: 0,
  };
}
