# SPDX-License-Identifier: GPL-3.0-only
"""Small stdin/stdout media materializer used by the DSH host boundary."""
from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path

if __package__:
    from .native_tools import read_media
else:
    from native_tools import read_media


def transcribe(path: str, config=None) -> dict:
    try:
        speech = (config or {}).get('speech', {})
        if speech.get('enabled'):
            from urllib.parse import urlsplit
            import httpx
            endpoint = urlsplit(speech.get('transcription_url', ''))
            if endpoint.scheme not in {'http', 'https'} or not endpoint.hostname or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
                raise ValueError('Explicit clean transcription endpoint required')
            audio = Path(path)
            if not audio.is_file() or audio.is_symlink() or audio.stat().st_size > 20 * 1024 * 1024:
                raise ValueError('Transcription media budget exceeded')
            if not speech.get('model') or not speech.get('api_key'):
                raise ValueError('Transcription route not configured')
            with audio.open('rb') as file, httpx.Client(trust_env=False, timeout=45) as client:
                response = client.post(speech['transcription_url'], headers={'Authorization': 'Bearer ' + speech['api_key']},
                    files={'file': (audio.name, file)}, data={'model': speech['model']})
                response.raise_for_status()
                if len(response.content) > 256 * 1024: raise ValueError('Transcription response budget exceeded')
                return {'text': str(response.json().get('text') or '')[:16000]}
        return {"text": "", "state": "disabled", "reason": "transcription_not_configured"}
    except Exception as error:
        return {"text": "", "error": type(error).__name__}


def video_audio(path: str, root: Path) -> str:
    if not shutil_which("ffmpeg"):
        return ""
    target = root / (Path(path).stem + "-audio.ogg")
    result = subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", str(target)],
                            capture_output=True, timeout=45)
    if result.returncode != 0 or not target.is_file() or target.stat().st_size > 20 * 1024 * 1024:
        return ""
    return str(target)


def video_frames(path: str, root: Path) -> list[str]:
    if not shutil_which("ffmpeg"):
        return []
    prefix = root / (Path(path).stem + "-frame")
    result = subprocess.run(["ffmpeg", "-nostdin", "-y", "-i", path, "-vf", "fps=1/4,scale=1280:-2",
                             "-frames:v", "4", str(prefix) + "%02d.jpg"], capture_output=True, timeout=45)
    if result.returncode != 0:
        return []
    values = []
    for candidate in sorted(root.glob(prefix.name + "*.jpg"))[:4]:
        if candidate.is_file() and not candidate.is_symlink() and candidate.stat().st_size <= 4 * 1024 * 1024:
            candidate.chmod(0o600); values.append(str(candidate))
    return values


def shutil_which(command: str) -> bool:
    import shutil
    return shutil.which(command) is not None


def main() -> None:
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    request = json.loads(sys.stdin.buffer.read(128 * 1024))
    media = request.get("media") or []
    results = []
    for item in media[:8]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").lower()
        if kind not in {"image", "mface", "record", "audio", "video"}:
            continue
        try:
            normalized_kind = "image" if kind in {"image", "mface"} else ("record" if kind in {"record", "audio"} else "video")
            result = read_media(config, {"kind": normalized_kind,
                                         "ref": item.get("ref"), "op": "media"})
        except Exception as error:
            result = {"ok": False, "error": type(error).__name__}
        if result.get("ok"):
            if normalized_kind in {"record", "video"}:
                audio_path = result["path"] if normalized_kind == "record" else video_audio(result["path"], Path(config["media_root"]))
                result["transcript"] = transcribe(audio_path, config).get("text", "") if audio_path else ""
            results.append(result)
            if normalized_kind == "video":
                for frame in video_frames(result["path"], Path(config["media_root"])):
                    results.append({"ok": True, "kind": "image", "path": frame, "media_type": "image/jpeg",
                                    "bytes": Path(frame).stat().st_size, "name": Path(frame).name,
                                    "sha256": __import__('hashlib').sha256(Path(frame).read_bytes()).hexdigest()})
    print(json.dumps({"items": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
