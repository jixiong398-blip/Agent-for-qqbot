# SPDX-License-Identifier: MIT
"""Rebuild the reviewed UI fragment in a private copy without touching sources."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def test_pinned_vendor_rebuild_is_deterministic_across_newline_handling(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'soyo/dsh/asuna-ui'
    destination = tmp_path / 'client'
    shutil.copytree(source, destination)
    result = subprocess.run([sys.executable, '-B', str(destination / 'build_client.py')], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert (destination / 'client.js').read_bytes() == (source / 'client.js').read_bytes()
    manifest = json.loads((destination / 'BUILD_MANIFEST.json').read_text())
    assert manifest['build_executed_this_round'] is True
    assert hashlib.sha256((destination / 'client.js').read_bytes()).hexdigest() == manifest['client_artifact_sha256']
    dictionary = (destination / 'client.js').read_text(encoding='utf-8').split('  const DICTIONARY = {', 1)[1].split('  const stack = ', 1)[0]
    assert 'Asuna' not in dictionary and '她' not in dictionary
