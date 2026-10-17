# SPDX-License-Identifier: MIT
"""Authenticated private HTTP over POSIX UDS or explicit Windows loopback."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def private_client(config, name="host", *, key=None, timeout=30):
    address = config.get(name + "_url") or (config.get("agent_line", {}).get("url") if name == "agent_line" else None)
    options = {"trust_env": False, "timeout": timeout,
               "headers": {"Authorization": "Bearer " + (key or config["host_key"])}}
    if address:
        url = urlsplit(address)
        if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or
                url.username or url.password or url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("Private endpoint must be explicit clean loopback")
        return httpx.Client(base_url=address, **options)
    socket = config.get(name + "_socket") or (config.get("agent_line", {}).get("socket") if name == "agent_line" else None)
    if os.name == "nt" or not socket or not Path(socket).is_absolute():
        raise ValueError("Private transport not configured for this platform")
    return httpx.Client(transport=httpx.HTTPTransport(uds=socket), base_url="http://localhost", **options)
