from __future__ import annotations

import gzip
import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import pytest

from ccrelay.gateway import RelayGateway, available_loopback_port


class _CompressedImageUpstream(ThreadingHTTPServer):
    accept_encoding: str | None = None


class _CompressedImageHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        server = cast(_CompressedImageUpstream, self.server)
        server.accept_encoding = self.headers.get("Accept-Encoding")
        length = int(self.headers["Content-Length"])
        self.rfile.read(length)

        payload = gzip.compress(
            json.dumps({"created": 1, "data": [{"b64_json": "aW1hZ2U="}]}).encode()
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Deliberately ignore Accept-Encoding to verify the gateway's defensive normalization.
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


@pytest.mark.integration
def test_image_response_is_uncompressed_for_codex() -> None:
    upstream = _CompressedImageUpstream(
        ("127.0.0.1", available_loopback_port()), _CompressedImageHandler
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    gateway = RelayGateway(
        port=available_loopback_port(),
        backend_base_url="http://127.0.0.1:1",
        proxy_key="sk-ccrelay-integration-secret",
        chatgpt_base_url=f"http://127.0.0.1:{upstream.server_port}/backend-api/codex",
    )
    gateway.start()

    connection = HTTPConnection("127.0.0.1", gateway._server.server_port, timeout=5)
    try:
        connection.request(
            "POST",
            "/v1/images/edits",
            body=b"{}",
            headers={
                "X-CCRelay-Key": "sk-ccrelay-integration-secret",
                "Authorization": "Bearer chatgpt-access-token",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        body = response.read()

        assert response.status == 200
        assert response.getheader("Content-Encoding") is None
        assert json.loads(body) == {"created": 1, "data": [{"b64_json": "aW1hZ2U="}]}
        assert upstream.accept_encoding == "identity"
    finally:
        connection.close()
        gateway.stop()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)
