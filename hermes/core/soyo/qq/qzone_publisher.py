# SPDX-License-Identifier: GPL-3.0-only
"""Native Qzone publisher with its own ledger and side-effect fence.

It uses NapCat only to obtain Qzone cookies.  It never opens Hermes's
memory_store.db and never sends an Authorization header to Qzone domains.
"""
from __future__ import annotations

import base64
from soyo.platform import fcntl, open_private
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

QZONE_HOSTS = {"qzone.qq.com", "user.qzone.qq.com", "up.qzone.qq.com", "upbak.photo.qzone.qq.com"}
MEDIA_HOSTS = {"multimedia.nt.qq.com.cn", "qpic.cn", "qq.com", "gtimg.cn", "gtimg.com"}


def _id(value):
    text = str(value or "").strip()
    return text if re.fullmatch(r"[1-9][0-9]{0,19}", text) else ""


def _root(config):
    root = Path(str(config.get("qzone_root") or Path(config["native_root"]) / "qzone"))
    if not root.is_absolute() or root.is_symlink():
        raise ValueError("qzone root must be an explicit non-symlink path")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def _db(config):
    root = _root(config)
    path = root / "ledger.db"
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
            occurrence_id TEXT PRIMARY KEY, content TEXT NOT NULL, normalized TEXT NOT NULL,
            image_path TEXT NOT NULL DEFAULT '', state TEXT NOT NULL,
            qzone_code TEXT NOT NULL DEFAULT '', response TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL, updated_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_qzone_posts_norm ON posts(normalized, created_at);
    """)
    if 'qzone_message_id' not in {row[1] for row in db.execute('PRAGMA table_info(posts)')}:
        db.execute("ALTER TABLE posts ADD COLUMN qzone_message_id TEXT NOT NULL DEFAULT ''")
        db.commit()
    return db


def _normalize(value):
    value = re.sub(r"\s+", "", str(value or ""))
    value = re.sub(r"[，。！？、…~～\[\]【】()（）{}「」『』\"'#*—]", "", value)
    value = re.sub(r"[\U0001f000-\U0001ffff]", "", value)
    return value[:160]


def _lock(config):
    path = _root(config) / "publisher.lock"
    fd = open_private(path, os.O_CREAT | os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def _cookies(config):
    parsed = urlparse(config["http_url"])
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
        raise ValueError("OneBot cookie endpoint must be loopback")
    with httpx.Client(base_url=config["http_url"].rstrip("/"), trust_env=False, timeout=15,
                      headers={"Authorization": "Bearer " + config["onebot_token"]}) as client:
        response = client.post("/get_cookies", json={"domain": "qzone.qq.com"})
        response.raise_for_status(); result = response.json()
    if result.get("retcode") != 0 or not (result.get("data") or {}).get("cookies"):
        raise RuntimeError("NapCat did not return Qzone cookies")
    values = {}
    for item in result["data"]["cookies"].split(";"):
        if "=" in item:
            key, value = item.strip().split("=", 1); values[key.strip()] = value.strip()
    if not values.get("skey") or not values.get("uin"):
        raise RuntimeError("Qzone cookie set is incomplete")
    return values


def _gtk(skey):
    result = 5381
    for char in skey:
        result += (result << 5) + ord(char)
    return result & 0x7FFFFFFF


def _json_response(response):
    if len(response.content) > 1024 * 1024:
        raise ValueError('Qzone response exceeds receipt budget')
    try:
        return response.json()
    except ValueError:
        match = re.search(r"\{.*\}", response.text, re.DOTALL)
        if not match:
            raise RuntimeError("Qzone response was not JSON")
        return json.loads(match.group(0))


def _endpoint(config, url):
    """Test substitution is deployment-owned, never supplied by a draft/tool argument."""
    if config.get('qzone_fixture_allow_loopback') is not True:
        return url
    base = urlparse(str(config.get('qzone_fixture_api_base') or ''))
    if base.scheme != 'http' or base.hostname != '127.0.0.1' or not base.port or base.username or base.password or base.path not in ('', '/') or base.query or base.fragment:
        raise ValueError('Qzone fixture endpoint must be explicit loopback')
    value = urlparse(url)
    return f'http://127.0.0.1:{base.port}' + value.path


def _publication_receipt(payload):
    if not isinstance(payload, dict):
        return {'state': 'unknown', 'reason': 'qzone_response_shape', 'qzone_code': '', 'qzone_message_id': ''}
    code = str(payload.get('code', payload.get('ret', '')))
    data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    identity = payload.get('tid', data.get('tid'))
    valid_id = isinstance(identity, str) and re.fullmatch(r'[!-~]{1,160}', identity) is not None
    return {'state': 'platform_accepted' if code == '0' and valid_id else 'failed' if code and code != '0' else 'unknown',
            'qzone_code': code, 'qzone_message_id': identity if valid_id else '',
            **({'reason': 'qzone_publish_id_missing'} if code == '0' and not valid_id else {})}


def _approved_image(config, path):
    if not path:
        return None
    raw, configured = Path(path), Path(str(config.get('media_root') or ''))
    if not raw.is_absolute() or raw.is_symlink() or not configured.is_absolute() or configured.is_symlink():
        raise ValueError('Explicit native image path required')
    candidate = raw.resolve(); root = configured.resolve()
    try: candidate.relative_to(root)
    except ValueError: raise ValueError("Qzone image outside native media root")
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 12 * 1024 * 1024:
        raise ValueError("Qzone image artifact rejected")
    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise ValueError("Qzone image extension rejected")
    return candidate


def _upload_image(config, image, cookies, uin, gtk):
    data = image.read_bytes(); filename = image.name
    with httpx.Client(trust_env=False, timeout=60, cookies=cookies) as client:
        response = client.post(_endpoint(config, "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"), params={"g_tk": gtk},
            data={"filename": filename, "uin": uin, "skey": cookies["skey"], "p_skey": cookies.get("p_skey", ""),
                  "zzpaneluin": uin, "p_uin": uin, "uploadtype": "1", "albumtype": "7", "exttype": "0",
                  "refer": "shuoshuo", "output_type": "json", "charset": "utf-8", "output_charset": "utf-8",
                  "upload_hd": "1", "hd_width": "2048", "hd_height": "10000", "hd_quality": "96",
                  "base64": "1", "picfile": base64.b64encode(data).decode("ascii"),
                  "qzreferrer": f"https://user.qzone.qq.com/{uin}"},
            headers={"Origin": "https://user.qzone.qq.com", "Referer": f"https://user.qzone.qq.com/{uin}",
                     "X-Requested-With": "XMLHttpRequest"})
        response.raise_for_status(); payload = _json_response(response)
    if str(payload.get("ret", payload.get("code", ""))) != "0":
        raise RuntimeError("Qzone image upload rejected")
    values = payload.get("data") or {}; url = str(values.get("url") or "")
    pic_bo = str(values.get("pic_bo") or values.get("picbo") or "")
    if not pic_bo:
        match = re.search(r"(?:^|[?&])bo=([^&\s]+)", url); pic_bo = match.group(1) if match else ""
    fields = [values.get("albumid", values.get("album_id", "")), values.get("lloc", ""), values.get("sloc", ""),
              values.get("type", values.get("phototype", "1")), values.get("height", values.get("h", "0")), values.get("width", values.get("w", "0"))]
    if not pic_bo or not all(str(item) for item in fields[:3]): raise RuntimeError("Qzone image metadata missing")
    return {"pic_bo": pic_bo, "richval": "," + ",".join(map(str, fields)) + ",," + str(fields[4]) + "," + str(fields[5])}


def context(config, hours=6):
    db = _db(config); cutoff = time.time() - min(24, max(1, float(hours))) * 3600
    posts = [dict(row) for row in db.execute("SELECT occurrence_id,content,state,created_at FROM posts WHERE created_at>? ORDER BY created_at DESC LIMIT 20", (cutoff,))]
    db.close()
    # Corpus is the native public scene source, not the legacy memory store.
    corpus = Path(config["corpus_db"])
    messages = []
    if corpus.is_file():
        with sqlite3.connect(corpus) as source:
            for row in source.execute("SELECT route,body FROM messages m WHERE route LIKE 'qq-group-%' AND CAST(json_extract(body,'$.occurred_at') AS REAL)>=? "
                "AND NOT EXISTS (SELECT 1 FROM message_flags f WHERE f.route=m.route AND f.event_id=json_extract(m.body,'$.event_id') AND f.flag='recalled') ORDER BY seq DESC LIMIT 100", (time.time() - min(24, max(1, float(hours))) * 3600,)):
                value = json.loads(row[1]); messages.append({"route_id": row[0], "sender_id": value.get("sender_id"), "text": str(value.get("text") or "")[:800], "occurred_at": value.get("occurred_at")})
    return {"state": "observed", "recent_posts": posts, "public_group_messages": list(reversed(messages))}


def publish(config, args):
    occurrence = str(args.get("occurrence_id") or "").strip(); content = str(args.get("content") or "").strip(); image = _approved_image(config, args.get("image_path"))
    if not occurrence or not content or len(content) > 1000 or re.search(r"\b(?:sk-|access_token|api[_ -]?key)\b", content, re.I): raise ValueError("Qzone publication rejected")
    fd = _lock(config); db = _db(config)
    try:
        row = db.execute("SELECT * FROM posts WHERE occurrence_id=?", (occurrence,)).fetchone()
        if row:
            return {"state": row["state"], "occurrence_id": occurrence, "qzone_code": row["qzone_code"],
                    "qzone_message_id": row['qzone_message_id'], "replayed": False}
        normalized = _normalize(content)
        if not normalized: raise ValueError('A punctuation-only Qzone draft is not publishable')
        recent = db.execute("SELECT 1 FROM posts WHERE created_at>? AND (normalized=? OR instr(normalized,?)>0 OR instr(?,normalized)>0) LIMIT 1", (time.time() - 86400, normalized, normalized, normalized)).fetchone()
        if recent:
            db.execute("INSERT INTO posts(occurrence_id,content,normalized,image_path,state,qzone_code,response,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (occurrence, content, normalized, str(image or ""), "skipped_duplicate", "", "{}", time.time(), time.time())); db.commit()
            return {"state": "skipped_duplicate", "occurrence_id": occurrence}
        db.execute("INSERT INTO posts(occurrence_id,content,normalized,image_path,state,qzone_code,response,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (occurrence, content, normalized, str(image or ""), "effect_started", "", "{}", time.time(), time.time())); db.commit()
        cookies = _cookies(config); uin = cookies['uin'].removeprefix('o')
        if not _id(uin) or uin != _id(config.get('account_id')): raise ValueError('Qzone cookie account mismatch')
        gtk = _gtk(cookies.get('p_skey') or cookies['skey']); rich = _upload_image(config, image, cookies, uin, gtk) if image else None
        data = {"con": content, "feedversion": 1, "ver": 1, "hostuin": uin, "format": "json", "code_version": 1,
                'syn_tweet_verson': '1', 'paramstr': '1', 'who': '1', 'ugc_right': '1', 'to_sign': '0',
                'qzreferrer': f'https://user.qzone.qq.com/{uin}'}
        if rich: data.update({"pic_bo": rich["pic_bo"], "richtype": "1", "richval": rich["richval"]})
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        with httpx.Client(trust_env=False, timeout=20) as client:
            response = client.post(_endpoint(config, "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"),
                params={"g_tk": gtk, "qzreferrer": f"https://user.qzone.qq.com/{uin}"}, data=data,
                headers={"Cookie": cookie_header, "User-Agent": "Mozilla/5.0", 'Referer': f'https://user.qzone.qq.com/{uin}', 'Origin': 'https://user.qzone.qq.com'})
            response.raise_for_status(); payload = _json_response(response)
        receipt = _publication_receipt(payload)
        db.execute("UPDATE posts SET state=?,qzone_code=?,qzone_message_id=?,response=?,updated_at=? WHERE occurrence_id=?",
                   (receipt['state'], receipt['qzone_code'], receipt['qzone_message_id'], json.dumps(receipt), time.time(), occurrence)); db.commit()
        return {**receipt, "occurrence_id": occurrence}
    except Exception as error:
        db.execute("UPDATE posts SET state=?,response=?,updated_at=? WHERE occurrence_id=?", ("unknown", json.dumps({"error": type(error).__name__}), time.time(), occurrence)); db.commit()
        return {"state": "unknown", "occurrence_id": occurrence, "reason": type(error).__name__}
    finally:
        db.close(); fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)


def validate(config, args):
    content = str(args.get("content") or "").strip()
    if not content or len(content) > 1000:
        raise ValueError("bounded qzone content required")
    image = _approved_image(config, args.get("image_path"))
    db = _db(config)
    try:
        duplicate = db.execute("SELECT occurrence_id,state FROM posts WHERE created_at>? AND normalized=? LIMIT 1",
                               (time.time() - 86400, _normalize(content))).fetchone()
        return {"state": "validated", "duplicate": dict(duplicate) if duplicate else None,
                "image": str(image) if image else "", "ledger": str(_root(config) / "ledger.db"),
                "side_effect": False, "qzone_http_post": False}
    finally:
        db.close()


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1])); args = json.loads(sys.stdin.buffer.read(128 * 1024));
    try:
        result = context(config, args.get("hours", 6)) if args.get("op") == "context" else validate(config, args) if args.get("op") == "validate" else publish(config, args)
    except Exception as error: result = {"state": "failed", "reason": type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
