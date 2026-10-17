# SPDX-License-Identifier: MIT
"""Explicit provider discovery: no default-provider scanning or inference calls."""
from __future__ import annotations

from .config import endpoint


def list_models(config, lane):
    if lane not in {"character", "action"}:
        raise ValueError("Choose the character or action model lane")
    item = config["models"][lane]
    base = endpoint(item.get("base_url"), {"http", "https"})
    import httpx
    headers = {"Authorization": "Bearer " + item["api_key"]} if item.get("auth_mode", "bearer") == "bearer" else {}
    try:
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            with client.stream("GET", base + "/models", headers=headers) as response:
                if response.status_code != 200:
                    raise ValueError("Provider model discovery returned HTTP " + str(response.status_code))
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024: raise ValueError("Provider model catalog is too large")
        import json
        rows = json.loads(raw).get("data", [])
        return {"models": sorted({row["id"] for row in rows if isinstance(row, dict) and
                    isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 256})[:512], "inference_called": False}
    except (httpx.HTTPError, KeyError, TypeError) as error:
        raise ValueError("Provider model discovery failed (" + type(error).__name__ + "); check the saved endpoint and authentication") from None
