# SPDX-License-Identifier: MIT
"""QQ's built-in small-face catalogue.

NapCat sometimes supplies a name in ``raw.faceText`` and sometimes supplies
only an id.  Keep both directions in one deployment-owned table so inbound
normalisation and outbound encoding cannot drift apart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


_TABLE = json.loads((Path(__file__).with_name("faces.json")).read_text(encoding="utf-8"))
_ROWS = tuple(row for row in _TABLE.get("faces", []) if isinstance(row, dict))
BY_ID = {str(row["id"]): str(row["name"]) for row in _ROWS if row.get("id") is not None and row.get("name")}
BY_NAME = {name: face_id for face_id, name in BY_ID.items()}
ALIASES = {
    str(alias): str(row["id"])
    for row in _ROWS
    if row.get("id") is not None
    for alias in (row.get("aliases") or ())
    if str(alias) not in BY_NAME
}
BY_NAME.update(ALIASES)

TOKEN = re.compile(r"\[表情:([^\[\]\s:]{1,12})\]")


def clean_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip("/[]【】 ")[:12]


def name_of(data: Mapping[str, Any]) -> str:
    raw = data.get("raw") if isinstance(data.get("raw"), Mapping) else {}
    supplied = clean_name(raw.get("faceText")) or clean_name(data.get("text") or data.get("Text"))
    if supplied in ALIASES:
        return BY_ID.get(ALIASES[supplied], supplied)
    if supplied:
        return supplied
    face_id = str(data.get("id") or data.get("face_id") or "").strip()
    return BY_ID.get(face_id) or ("id-" + face_id if face_id.isdigit() else "")


def id_of(name: str) -> str | None:
    value = clean_name(name)
    face_id = BY_NAME.get(value)
    return face_id or None
