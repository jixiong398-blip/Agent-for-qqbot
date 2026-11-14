# SPDX-License-Identifier: MIT
"""Per-model compaction budgets for the pinned DSH request-pressure contract."""
from __future__ import annotations

SUMMARY_CEILING = 65536


def model_policy(provider, model):
    # Input and output share a window. DSH also subtracts headroom before
    # deciding to compact; its default 64K cannot fit every small model.
    window, output = model['context_window'], model['max_tokens']
    available = window - output
    if available < 1024:
        raise ValueError('Model output reservation leaves too little room for safe automatic compaction')
    headroom = min(SUMMARY_CEILING, max(256, available // 4))
    threshold = min(window // 2, available - headroom)
    return {'provider': provider, 'model': model['name'],
            'headroomTokens': headroom,
            'maxTokens': min(SUMMARY_CEILING, output, headroom),
            'retainTokens': min(available // 4, max(0, (threshold - 1) // 2))}


def configure_plugins(plugins, policies):
    """Cover QQ/action and the owner's standard preset, without adding tools."""
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        if plugin.get('name') == '@deepseek-ai/dsh-compaction-basic':
            plugin.setdefault('config', {}).update(maxTokens=SUMMARY_CEILING, modelPolicies=policies)
        nested = plugin.get('config')
        if isinstance(nested, list):
            configure_plugins(nested, policies)
