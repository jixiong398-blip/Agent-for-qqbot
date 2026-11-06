# SPDX-License-Identifier: MIT
"""Real loopback OneBot image resolution without a CDN download or filesystem trust."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from soyo.qq.inbound import parse_message
from soyo.qq.native_tools import read_media


def test_image_keeps_stable_napcat_handle_instead_of_ephemeral_cdn_url():
    value = parse_message([{"type": "image", "data": {
        "url": "https://gchat.qpic.cn/expired?rkey=old", "file": "stable-image.jpg", "summary": "image"}}])
    assert value.media[0].ref == "stable-image.jpg"


def test_authenticated_napcat_bytes_are_saved_without_reading_paths_or_fetching_cdn(tmp_path):
    # Admission to the native image service does the full raster validation later.
    image = b"\xff\xd8\xff\xe0fixture-image-bytes"
    observed = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            observed.append((self.path, self.headers.get("Authorization"), body))
            payload = json.dumps({"retcode": 0, "data": {
                "file": "/must/not/read/private/config", "url": "https://gchat.qpic.cn/expired",
                "base64": base64.b64encode(image).decode()}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        result = read_media({"account_id": "900001", "http_url": f"http://127.0.0.1:{server.server_port}",
                             "onebot_token": "fixture-only", "media_root": str(tmp_path / "media")},
                            {"ref": "stable-image.jpg", "kind": "image"})
        assert result["ok"] and result["media_type"] == "image/jpeg"
        assert Path(result["path"]).read_bytes() == image
        assert observed == [("/get_image", "Bearer fixture-only", {"file": "stable-image.jpg"})]
    finally:
        server.shutdown(); server.server_close(); thread.join()
