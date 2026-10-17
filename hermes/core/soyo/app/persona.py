# SPDX-License-Identifier: MIT
"""Bounded private persona editor and named presets, with non-destructive backups."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import secrets

from soyo.platform import assert_private, file_lock, protect


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[\w-]{1,64}", value, flags=re.UNICODE):
        raise ValueError("Persona preset name must be 1–64 letters, digits, underscores or hyphens")
    return value


def _read(path):
    try:
        assert_private(path, max_bytes=256 * 1024)
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""


def view(home):
    directory = Path(home) / "persona"
    text = _read(directory / "SOUL.md")
    presets = directory / "presets"
    if presets.exists(): assert_private(presets, directory=True)
    return {"text": text, "digest": hashlib.sha256(text.encode()).hexdigest(),
            "presets": sorted(p.stem for p in presets.glob("*.md") if re.fullmatch(r"[\w-]{1,64}", p.stem))[:64]}


def save(home, *, text=None, operation="save", name=None, digest=None):
    home = Path(home)
    with file_lock(home / "run/persona.lock"):
        current = view(home)
        if digest is not None and current["digest"] != digest:
            raise ValueError("PERSONA_CONFLICT: reload before saving")
        file = home / "persona/SOUL.md"
        if operation in {"save_preset", "use_preset"}:
            directory = home / "persona/presets"
            directory.mkdir(mode=0o700, exist_ok=True); protect(directory, directory=True)
            preset = directory / (_name(name) + ".md")
            if operation == "use_preset": text = _read(preset)
            else:
                if not preset.exists() and len(current["presets"]) >= 64:
                    raise ValueError("At most 64 persona presets are supported")
                file = preset
        elif operation != "save":
            raise ValueError("Unsupported persona operation")
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 256 * 1024:
            raise ValueError("A nonempty bounded persona is required")
        if file.exists():
            assert_private(file, max_bytes=256 * 1024)
            backup = home / "backups" / ("persona-" + secrets.token_hex(8) + ".md")
            backup.write_bytes(file.read_bytes()); protect(backup)
        temporary = file.with_name("." + file.name + "." + secrets.token_hex(8) + ".pending")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as stream:
                from soyo.platform import private_fchmod
                private_fchmod(stream.fileno(), 0o600)
                stream.write(text); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, file)
        finally:
            temporary.unlink(missing_ok=True)
        return {"saved": True, **view(home)}
