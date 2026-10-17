// SPDX-License-Identifier: MIT
// Mount the actual DSH tools on an Agent. A tool name in a restriction or a
// prompt does not register it; factory-created Agents need these plugins too.
import * as bash from '@deepseek-ai/dsh-tool-bash';
import * as files from '@deepseek-ai/dsh-tool-fs';
import * as search from '@deepseek-ai/dsh-tool-fs-search';
import * as jobs from '@deepseek-ai/dsh-tool-jobs';
import { setSandboxMode } from '@deepseek-ai/dsh-sandbox-policy';
import { setApprovalPolicy } from '@deepseek-ai/dsh-user-approval';

const mounted = new WeakSet();

export async function mountNativeImageTool(scope, agent) {
  if (!scope.tools.get('read_image', agent)) await scope.plugin(files, {});
}

export async function mountNativeHostTools(scope, agent) {
  if (mounted.has(agent)) return;
  const suites = [
    ['bash', bash, { enableRunInBackground: true, promoteOnTimeout: true }],
    ['read', files, {}],
    ['glob', search, { sampleOverCapGlobResults: false }],
    ['job_output', jobs, { completionDelivery: 'quiet' }],
  ];
  for (const [name, plugin, settings] of suites) {
    // A resident standard-preset Agent already has these. Do not double
    // register its own tools, and do not mount the whole coding persona on GPT.
    if (!scope.tools.get(name, agent)) await scope.plugin(plugin, settings);
  }
  const permission = scope.get('permissionPresets');
  if (!permission) throw Error('Native Host permissionPresets service is not ready');
  const mode = process.env.SOYO_HOST_PERMISSION_MODE || 'workspace-write';
  if (!['workspace-write', 'danger-full-access', 'read-only'].includes(mode)) throw Error('Invalid configured Host permission mode');
  if (mode === 'read-only') {
    setSandboxMode(agent.session, 'read-only');
    setApprovalPolicy(agent.session, 'never');
    scope.tools.guard(exec => ['read', 'read_image', 'glob', 'grep', 'job_output', 'job_list'].includes(exec.name) ||
      !['bash', 'write', 'edit', 'job_kill'].includes(exec.name) ? undefined : 'Configured read-only Host mode');
  } else permission.set(agent.session, mode);
  // An already fully authorized Host has no wider mode to request. Advertising
  // these optional controls caused real GPT calls to invent workspace-write +
  // an empty justification instead of executing a read-only date command.
  // Narrow only the model-facing schema; keep the original tool dispatcher,
  // arguments and permission checks intact, including for unadvertised fields.
  scope.on('system-prompt/assemble', async (_assembly, { agent: current }, next) => {
    const assembly = await next();
    if (current?.id !== agent.id || !Array.isArray(assembly.tools) ||
        scope.get('sandboxPolicy')?.resolve({ session: agent.session }).mode !== 'danger-full-access') return assembly;
    return { ...assembly, tools: assembly.tools.map(tool => {
      const parameters = tool.parameters, properties = parameters?.properties;
      if (!properties || !('sandbox_permissions' in properties)) return tool;
      const visible = Object.fromEntries(Object.entries(properties).filter(([name]) =>
        !['sandbox_permissions', 'justification'].includes(name)));
      return { ...tool, parameters: { ...parameters, properties: visible,
        ...(Array.isArray(parameters.required) ? { required: parameters.required.filter(name =>
          !['sandbox_permissions', 'justification'].includes(name)) } : {}) } };
    }) };
  });
  mounted.add(agent);
}
