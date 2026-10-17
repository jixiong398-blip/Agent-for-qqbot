"""Native DSH tests must not bootstrap the retired Hermes runtime as setup.

Keep cache invalidation when a test actually imported that runtime. All parent
credential/home isolation, event-loop and 30-second deadline fixtures still run.
"""
import sys
from pathlib import Path

# The Hermes parent package was archived; keep the Soyo test package directly
# importable from the trimmed repository without relying on an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest


@pytest.fixture(autouse=True)
def _private_fixture_directory(tmp_path):
    # chmod is not an ACL on Windows. Fixture evidence must meet the same
    # private-file boundary as a real instance, rather than weakening the reader.
    from soyo.platform import protect
    protect(tmp_path, directory=True)


@pytest.fixture(autouse=True)
def _reset_tool_registry_caches():
    for name, clear in (("tools.registry", "invalidate_check_fn_cache"),
                        ("model_tools", "_clear_tool_defs_cache")):
        module = sys.modules.get(name)
        if module is not None:
            getattr(module, clear)()
    yield
