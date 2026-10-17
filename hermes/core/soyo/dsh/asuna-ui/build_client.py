#!/usr/bin/env python3
"""Reuse reviewed upstream component bytes, with the Bot adapter kept separate."""
from pathlib import Path
import hashlib
import json
import re

root = Path(__file__).resolve().parent
vendor_bytes = (root / 'vendor/cognition-core-client.js').read_bytes()
pin = json.loads((root / 'vendor/source.json').read_text(encoding='utf-8'))
assert hashlib.sha256(vendor_bytes).hexdigest() == pin['client_sha256'], 'vendor bytes differ from pin'
# Hash the retained bytes before normalizing text. read_text's universal-newline
# conversion otherwise makes a valid CRLF vendor pin fail on every platform.
source = vendor_bytes.decode('utf-8').replace('\r\n', '\n')

def section(start, end):
    assert source.count(start) == 1 and source.count(end) == 1, (start, end)
    return source[source.index(start):source.index(end)]

dictionary_original = section('  const DICTIONARY = {', '  const stack = ')
# Adapt display strings only; retained vendor bytes, provenance and protocol IDs stay intact.
dictionary = dictionary_original.replace('Asuna', 'Bot').replace('她', '角色')
dictionary = re.sub(r'\bher(?= (?:answer|turn|plans|ideas|daily|understanding|night))', 'their', dictionary)
dictionary = re.sub(r'\bher\b', 'them', dictionary).replace('Her ', 'Their ').replace('herself', 'themselves')
dictionary = re.sub(r'\bshe\b', 'they', dictionary).replace('She ', 'They ')
for original, neutral in [('They has', 'They have'), ('they has', 'they have'), ('They decides', 'They decide'), ('They writes', 'They write')]:
    dictionary = dictionary.replace(original, neutral)
helpers = section('  const stack = ', '  // ── which brain')
stage_label = section('  const stageLabel = ', '  const brainClass = ')
stage_label = stage_label.replace("['character', 'executor']", "['character', 'executor', 'reviewer', 'helper']")
palette = section('  const brainClass = ', '  function stageIdentity(')
palette = palette.replace("const brainClass = lane => ['character', 'executor']", "const brainClass = lane => ['character', 'executor', 'reviewer']", 1)
# Input-policy subscriptions are a different business capability; keep only
# the original brain palette, meter palette and ContextMeter lookup here.
palette = palette[:palette.index('  function subscribeInputPolicies(')] + palette[palette.index('  // Pill\'s static branch'):]
thread = section('  function collabDefinitions()', '  // ── her tool rows (ADR-011 §7.2)')
tool_helpers = section('  const TOOL_ICONS = ', '  function apply(ctx)')
meters = section('    function BrainMeters(', '    // Add only Asuna business attribution')
controls = section('    const inlineChat = ', '    // ── her tool rows and the action brain')
controls = controls[:controls.index("    ctx.slots.inject('conversation.chat.node'")]
tool_row = section('    function RoleToolRow(', '    for (const name of ROLE_TOOLS)')
select = section('    function Select(', '    // ── memory')
memory_original = section('    const categoryLabel = ', '    // ── settings')
memory = memory_original.replace("['all', 'documents', 'affect', 'jobs', 'ideas', 'self', 'relation', 'summary', 'interpretation', 'source']", 'memoryKinds')
assert memory != memory_original
memory_detail_anchor = "h(MarkdownText, { text: say(t, detail.body), labels }),"
assert memory.count(memory_detail_anchor) == 1
memory = memory.replace(memory_detail_anchor, memory_detail_anchor + "\n               h(MemoryProvenance, { detail, t }),\n               h(GoalControl, { key: 'goal-' + row.id, detail, sessionId: props.sessionId, t, onSaved: () => setRefresh(x => x + 1) }),\n               h(MemoryCorrection, { key: row.id, detail, sessionId: props.sessionId, t, onSaved: () => setRefresh(x => x + 1) }),")
settings_original = section('    function Settings(', "    ctx.effect(() => ctx.sidebarRightTabs.register({ id: '@asuna/memory'")
settings = settings_original.replace("'asuna-cognition-core'", "'soyo-asuna-ui'").replace("'Asuna'", "'Bot'")
settings = settings.replace("        for (const key of ['persona', 'channelAdmission', 'python'])\n          add([key], { key: 'settings.' + key }, ['persona', 'channelAdmission'].includes(key) ? 'choice' : 'text');\n", '')
settings = settings.replace("...(lane === 'character' ? ['attendEffort', 'groupEffort'] : [])", '...[]')
begin = settings.index('        const starters = [];')
end = settings.index('        const collect = value =>', begin)
settings = settings[:begin] + '        const starters = [];\n        const secretNames = new Set();\n' + settings[end:]
settings = settings.replace("        add(['credentials'], { key: 'settings.newSecrets' }, 'secret-map');\n", '')
assert settings.count("            const current = await rpc('status');") == 1
settings = settings.replace("            const current = await rpc('status');", "            await reloadSettings();\n            const current = await rpc('status');")
save_failure = "          } catch (error) { setNotice(error.message); return false; }\n        } };"
assert settings.count(save_failure) == 1
settings = settings.replace(save_failure, "          } catch (error) { await reloadSettings(); setNotice(error.message); return false; }\n        } };")
settings = settings.replace("disabled: busy || state.shell.dirty || state.shell.saving, onClick: activate", "disabled: busy || !state.shell.writable || state.shell.dirty || state.shell.saving || status?.lifecycle.state === 'applying', onClick: activate")
settings = settings.replace("disabled: busy || state.shell.saving || !state.shell.writable", "disabled: busy || state.shell.saving || !state.shell.writable || status?.lifecycle.state === 'applying'")
locked_route = "disabled: busy || state.shell.saving || !state.shell.writable || status?.lifecycle.state === 'applying',"
assert settings.count(locked_route) == 1
settings = settings.replace(locked_route, locked_route[:-1] + " || (status?.reviewer?.route_locked && field.path[0] === 'routes' && field.path[1] === 'action' && ['provider', 'model'].includes(field.path[2])),")
heartbeat_anchor = "        status?.lifecycle.error && h('p', { role: 'alert' }, status.lifecycle.error),"
assert settings.count(heartbeat_anchor) == 1
settings = settings.replace(heartbeat_anchor, heartbeat_anchor + "\n        h(GatewayStatus, { initial: worker?.transport_observation, t }),\n        h(ReviewSource, { value: status?.reviewer, t }),")
channel_state = "state: worker?.channels_active ? t('settings.channelOn', { state: word(t, 'settings.integration.', worker.integration_state) }) : t('settings.channelOff')"
assert settings.count(channel_state) == 1
settings = settings.replace(channel_state, "state: worker?.integration_state === 'STALE' ? t('settings.transport.stale') : worker?.integration_state === 'UNKNOWN' ? t('settings.transport.unknown') : worker?.channels_active ? t('settings.channelOn', { state: word(t, 'settings.integration.', worker.integration_state) }) : t('settings.channelOff')")
trigger_original = section('    function AsunaTrigger(', '    // DSH\'s max-tokens notice')
trigger = trigger_original[:trigger_original.index("    ctx.slots.inject('conversation.chat.node'")]
trigger = trigger.replace("source?.kind !== 'asuna'", '!source?.soyo_ui_trigger')
trigger = trigger.replace('entry.component !== AsunaTrigger', 'entry.component !== AsunaTrigger && entry.component !== SoyoTrigger')
brain_mark = section("    ctx.slots.inject('conversation.chat.node', () => ctx.slots.register({\n      name: 'conversation.chat.node', key: 'asuna-stage'", '\n\n  }')
header = '''// SPDX-License-Identifier: GPL-3.0-only
// Generated from pinned AsunaCognitionCore controls; see vendor/source.json.
// Verbatim and adapted upstream sections are distinguished in BUILD_MANIFEST.json.
window.__ModuleLoader__.load({ id: '@soyo/dsh-asuna-ui', factory: require => {
  const React = require('react');
  const primitives = require('@deepseek-ai/dsh-client-ui-primitives');
  const { Button, Input, Menu, Pill, IconChevronDownOutlineRegular, DisclosureRow, MarkdownText,
    SettingsForm, SettingsFormModel, SettingsValueField, SettingsSecretField } = primitives;
  const h = React.createElement;
  const NS = 'soyo-asuna-ui';
'''
adapt = (root / 'adapter.js').read_text(encoding='utf-8')
before, after = adapt.split('/* UPSTREAM_COMPONENTS */')
output = header + dictionary + helpers + stage_label + palette + thread + tool_helpers + before + select + memory + settings + trigger + brain_mark + meters + controls + tool_row + after
(root / 'client.js').write_text(output, encoding='utf-8', newline='\n')
manifest = {**pin, 'client_artifact_sha256': hashlib.sha256(output.encode()).hexdigest(),
            'artifact_kind': 'generated-from-pinned-retained-vendor', 'build_executed_this_round': True,
            'adapter_sha256': hashlib.sha256((root / 'adapter.js').read_bytes()).hexdigest(),
            'upstream_sections_sha256': {key: hashlib.sha256(value.encode()).hexdigest()
                for key, value in {'thread': thread, 'meters': meters, 'controls': controls, 'tool_row': tool_row}.items()},
            'components_reused_verbatim': ['CollabThread', 'InlineWork', 'WorkFragment', 'RoleToolRow', 'BrainMeters', 'Select', 'ActiveStage'],
            'components_reused_with_documented_adapter_edits': ['Localization (neutral Bot labels without preset persona/gender)', 'Memory (Bot categories/operator revisions)', 'Settings/SettingsEditor (Bot routes, heartbeat and configured review source; no Mongo/persona jobs)', 'AsunaTrigger (native source with compatibility identifiers)', 'Stage labels (independent review duty; no third context wheel)'],
            'adapted_upstream_sections_sha256': {key: hashlib.sha256(value.encode()).hexdigest()
                for key, value in {'dictionary_original': dictionary_original, 'memory_original': memory_original, 'settings_original': settings_original, 'trigger_original': trigger_original}.items()},
            'whole_cognition_core_installed': False}
(root / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({'client_built': True, 'upstream_commit': pin['commit'],
                  'verbatim_components': manifest['components_reused_verbatim'],
                  'documented_adaptations': manifest['components_reused_with_documented_adapter_edits']}))
