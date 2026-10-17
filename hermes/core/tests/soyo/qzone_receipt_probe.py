"""Actual Qzone native subprocess/HTTP/SQLite; only the platforms are loopback stand-ins."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import json
import os
import sqlite3
import subprocess
import sys
import threading

from soyo.qq import qzone_publisher


def main():
    root = Path(sys.argv[1]); assert root.is_absolute() and not root.exists(); root.mkdir(mode=0o700)
    requests, effects = [], []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            requests.append(self.path)
            if self.path == '/get_cookies':
                assert self.headers['Authorization'] == 'Bearer fixture-only-napcat'
                assert json.loads(raw)['domain'] == 'qzone.qq.com'
                response = {'retcode': 0, 'data': {'cookies': 'uin=o900001; skey=fixture-skey; p_skey=fixture-p-skey'}}
            else:
                assert self.headers.get('Authorization') is None
                assert 'fixture-p-skey' in self.headers['Cookie']
                assert parse_qs(urlparse(self.path).query)['g_tk'][0] == str(qzone_publisher._gtk('fixture-p-skey'))
                form = parse_qs(raw.decode()); assert form['hostuin'] == ['900001'] and form['ugc_right'] == ['1']
                effects.append(form['con'][0]); response = {'code': 0, 'tid': 'fixture-real-http-post-id'} if len(effects) == 1 else {'code': 0}
            body = json.dumps(response).encode(); self.send_response(200); self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    proof = {'status': 'unverified', 'actual_qzone_sends': 0, 'external_model_calls': 0, 'platform': 'loopback-only'}
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        config = {'native_root': str(root), 'corpus_db': str(root/'corpus.db'), 'account_id': '900001', 'http_url': url,
                  'onebot_token': 'fixture-only-napcat', 'qzone_fixture_allow_loopback': True, 'qzone_fixture_api_base': url}
        path = root/'config.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
        def call(occurrence, content):
            result = subprocess.run([sys.executable, '-B', qzone_publisher.__file__, str(path)],
                input=json.dumps({'op': 'publish', 'occurrence_id': occurrence, 'content': content}), text=True, capture_output=True, timeout=30,
                env={'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1'})
            assert result.returncode == 0, result.stderr; return json.loads(result.stdout)
        accepted = call('probe-first', '早上阳光很好')
        assert accepted['state'] == 'platform_accepted' and accepted['qzone_message_id'] == 'fixture-real-http-post-id'
        unknown = call('probe-unknown', '夜里的琴声')
        assert unknown['state'] == 'unknown' and unknown['reason'] == 'qzone_publish_id_missing'
        assert call('probe-unknown', '夜里的琴声')['state'] == 'unknown'
        assert call('probe-first', '早上阳光很好')['qzone_message_id'] == 'fixture-real-http-post-id'
        assert len(effects) == 2 and len(requests) == 4
        with sqlite3.connect(root/'qzone/ledger.db') as db:
            assert db.execute("SELECT state,qzone_message_id FROM posts WHERE occurrence_id='probe-first'").fetchone() == ('platform_accepted', 'fixture-real-http-post-id')
        proof.update(status='verified_qzone_native_receipt_path', actual_post_id_saved=True, empty_id_not_success=True,
                     unknown_not_republished=True, repeated_occurrence_not_republished=True, token_not_sent_to_qzone=True,
                     p_skey_gtk_used=True, loopback_posts=len(effects))
    except BaseException as error: proof['error'] = type(error).__name__ + ': ' + str(error); raise
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=10)
        (root/'probe.json').write_text(json.dumps(proof, indent=2)); print(json.dumps(proof))


if __name__ == '__main__': main()
