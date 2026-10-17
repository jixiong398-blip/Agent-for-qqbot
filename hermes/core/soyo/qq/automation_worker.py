# SPDX-License-Identifier: GPL-3.0-only
"""Bounded, no-model automation; no Hermes scheduler/agent/tool imports."""
from __future__ import annotations

import hashlib
import json
import os
from soyo.platform import private_fchmod
import sys
import time
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx


def save(path: Path, value) -> None:
    temporary = path.with_name(path.name + "." + str(os.getpid()) + ".tmp")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with temporary.open("x", encoding='utf-8') as file:
        private_fchmod(file.fileno(), 0o600)
        json.dump(value, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    if os.name != 'nt':
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(directory)
        finally: os.close(directory)


def article_text(value):
    # Site watermarks/format controls are not article content or evidence weight.
    return '\n'.join(line.strip() for line in re.sub('[\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]', '', value).splitlines() if line.strip())


def bandori_sync(config, args):
    root = Path(str(config.get("bandori_knowledge_root") or ""))
    if not root.is_absolute() or root.is_symlink():
        return {"state": "blocked", "reason": "bandori_knowledge_root_not_configured"}
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = root / "native-sync-state.json"
    if state_path.is_symlink():
        raise ValueError('bandori_state_symlink')
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.is_file() else {"lastmod": {}}
    if not isinstance(state, dict) or not isinstance(state.get('lastmod'), dict):
        raise ValueError('bandori_state_shape')
    state.setdefault('fetched_at', {})
    if not isinstance(state['fetched_at'], dict):
        raise ValueError('bandori_state_shape')
    limit = args.get('limit', 10)
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('bandori_bounded_page_limit')
    started = time.monotonic(); requests = 0
    source_url = str(config.get('bandori_source_url') or '')
    source = urlsplit(source_url)
    if source.scheme != 'https' or not source.hostname or source.username or source.password or source.query or source.fragment or source.path not in ('', '/'):
        raise ValueError('explicit_https_knowledge_source_required')
    language = str(config.get('bandori_language') or 'zh-Hans')
    sections = config.get('bandori_article_sections') or ['bands', 'songs', 'events', 'news', 'releases', 'voice-actors', 'characters', 'venues']
    sitemap_path = str(config.get('bandori_sitemap_path') or '/sitemap.xml')
    if not sitemap_path.startswith('/') or sitemap_path.startswith('//'): raise ValueError('source_relative_sitemap_required')
    def permitted(url):
        parsed = urlsplit(url)
        return parsed.scheme == source.scheme and parsed.hostname == source.hostname and parsed.port == source.port and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
    fixture = None
    if config.get('bandori_fixture_allow_loopback') is True:
        fixture = urlsplit(str(config.get('bandori_fixture_api_base') or ''))
        if fixture.scheme != 'http' or fixture.hostname != '127.0.0.1' or not fixture.port or fixture.username or fixture.password or fixture.path not in ('', '/') or fixture.query or fixture.fragment:
            raise ValueError('bandori_fixture_loopback_required')
    def freshness(modified):
        try:
            value = datetime.fromisoformat(modified.replace('Z', '+00:00'))
            return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
        except (ValueError, TypeError):
            return 0
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=12) as client:
        def fetch(url):
            nonlocal requests
            if not permitted(url):
                raise ValueError("bandori_url_not_authorized")
            if time.monotonic() - started > 90 or requests >= 24:
                raise TimeoutError("bandori_budget")
            requests += 1
            endpoint = f'http://127.0.0.1:{fixture.port}' + urlsplit(url).path if fixture else url
            with client.stream("GET", endpoint) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes(64 * 1024):
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ValueError("bandori_response_too_large")
                    chunks.append(chunk)
                return b"".join(chunks)
        sitemap = ElementTree.fromstring(fetch(source_url.rstrip('/') + sitemap_path))
        documents = [sitemap]
        if sitemap.tag.endswith("sitemapindex"):
            documents = []
            for child in sitemap:
                url = child.findtext("{*}loc")
                if url and permitted(url) and urlsplit(url).path.startswith('/sitemap/' + language) and len(documents) < 4:
                    documents.append(ElementTree.fromstring(fetch(url)))
            if not documents:
                raise ValueError('bandori_chinese_sitemap_missing')
        changed = {}
        for document in documents:
            for entry in document:
                url, modified = entry.findtext('{*}loc'), entry.findtext('{*}lastmod') or ''
                if not url or not permitted(url):
                    continue
                parts = urlsplit(url).path.strip('/').split('/')
                if len(parts) < 3 or parts[0] != language or parts[1] not in sections:
                    continue  # Index/navigation/build pages do not displace article backlog.
                if modified and state['lastmod'].get(url) == modified:
                    continue
                if not modified and time.time() - float(state['fetched_at'].get(url, 0)) < 86400:
                    continue
                changed[url] = modified
        candidates = sorted(changed.items(), key=lambda item: (-freshness(item[1]), item[0]))
        imported = 0; rejected = 0; receipts = []
        from bs4 import BeautifulSoup
        for url, modified in candidates:
            if time.monotonic() - started > 80 or imported >= limit or requests >= 24:
                break
            soup = BeautifulSoup(fetch(url), 'html.parser')
            title = (soup.find('h1') or soup.find('title'))
            title = article_text(title.get_text(' ', strip=True))[:400] if title else ''
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'form']):
                tag.decompose()
            text = article_text((soup.find('main') or soup).get_text('\n', strip=True))[:60000]
            if len(text.strip()) < 80 or not title:
                rejected += 1; continue  # No state advance for shell/empty pages.
            key = hashlib.sha256(url.encode()).hexdigest(); current = root/'native-pages'/(key+'.json')
            if current.is_symlink():
                raise ValueError('bandori_page_symlink')
            if current.is_file():
                old = current.read_bytes(); previous = root/'native-versions'/key/(hashlib.sha256(old).hexdigest()+'.json')
                if not previous.exists():
                    save(previous, json.loads(old))
            page = {'url':url, 'lastmod':modified, 'title':title, 'text':text, 'fetched_at':time.time(),
                    'content_sha256':hashlib.sha256(text.encode()).hexdigest(), 'source_quality':'article-route-text'}
            save(current, page)
            state['lastmod'][url] = modified; state['fetched_at'][url] = page['fetched_at']
            save(state_path, state)  # Each real artifact/state pair is durable before proceeding.
            receipts.append({'url':url, 'relative_path':'native-pages/'+key+'.json',
                             'artifact_sha256':hashlib.sha256(current.read_bytes()).hexdigest(), 'characters':len(text)})
            imported += 1
        return {"state": "completed", "imported_pages": imported, "bounded_incremental": True,
                'scope':'bounded-incremental-batch', 'changed_article_candidates':len(candidates),
                'pending_changed_pages':len(candidates)-imported, 'quality_rejected':rejected, 'http_requests':requests,
                'artifact_receipts':receipts, 'old_native_versions_retained':True,
                "old_knowledge_unchanged": True, "elapsed_seconds": round(time.monotonic() - started, 2)}


if __name__ == "__main__":
    from soyo.platform import load_private_json
    config = load_private_json(Path(sys.argv[1]))
    args = json.loads(sys.stdin.buffer.read(64 * 1024))
    try:
        result = bandori_sync(config, args)
    except Exception as error:
        result = {"state": "failed", "reason": type(error).__name__}
    print(json.dumps(result, ensure_ascii=False))
