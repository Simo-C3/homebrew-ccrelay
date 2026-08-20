from __future__ import annotations

import hmac
import json
import socket
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import urlsplit

import httpx

LOCAL_KEY_HEADER = "X-CCRelay-Key"
DEFAULT_CHATGPT_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

_IMAGE_PATHS = frozenset({"/v1/images/generations", "/v1/images/edits"})
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
_OPENAI_IDENTITY_HEADERS = frozenset(
    {
        "chatgpt-account-id",
        "x-openai-actor-authorization",
        "x-openai-fedramp",
    }
)


class GatewayRequestError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class UpstreamRequest:
    url: str
    headers: dict[str, str]
    is_image_request: bool


@dataclass(frozen=True)
class GatewayRouter:
    backend_base_url: str
    proxy_key: str
    chatgpt_base_url: str = DEFAULT_CHATGPT_CODEX_BASE_URL

    def route(self, path: str, headers: Mapping[str, str]) -> UpstreamRequest:
        parsed = urlsplit(path)
        is_image_request = parsed.path in _IMAGE_PATHS
        normalized_headers = {name.lower(): value for name, value in headers.items()}
        local_header_authorized = self._matches_proxy_key(
            normalized_headers.get(LOCAL_KEY_HEADER.lower())
        )
        authorization = normalized_headers.get("authorization")
        bearer_authorized = self._matches_proxy_key(_bearer_token(authorization))
        if not (local_header_authorized or bearer_authorized):
            raise GatewayRequestError(401, "Invalid ccrelay credentials")

        forwarded = _forwardable_headers(normalized_headers)
        forwarded.pop(LOCAL_KEY_HEADER.lower(), None)
        if is_image_request:
            if (
                not local_header_authorized
                or _bearer_token(authorization) is None
                or bearer_authorized
            ):
                raise GatewayRequestError(401, "ChatGPT authentication is required for imagegen")
            # Codex does not advertise response-compression support for image requests.  Without
            # an explicit value, httpx adds its own ``Accept-Encoding`` header and can make the
            # ChatGPT backend return compressed JSON that Codex then tries to decode as JSON.
            forwarded["accept-encoding"] = "identity"
            suffix = parsed.path.removeprefix("/v1")
            target = f"{self.chatgpt_base_url.rstrip('/')}{suffix}"
        else:
            for name in _OPENAI_IDENTITY_HEADERS:
                forwarded.pop(name, None)
            forwarded["authorization"] = f"Bearer {self.proxy_key}"
            target = f"{self.backend_base_url.rstrip('/')}{parsed.path}"

        if parsed.query:
            target = f"{target}?{parsed.query}"
        return UpstreamRequest(
            url=target,
            headers=forwarded,
            is_image_request=is_image_request,
        )

    def _matches_proxy_key(self, value: str | None) -> bool:
        return value is not None and hmac.compare_digest(value, self.proxy_key)


def _bearer_token(value: str | None) -> str | None:
    if value is None:
        return None
    scheme, separator, token = value.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        return None
    return token


def _forwardable_headers(headers: Mapping[str, str]) -> dict[str, str]:
    connection_headers = {
        name.strip().lower() for name in headers.get("connection", "").split(",") if name.strip()
    }
    excluded = _HOP_BY_HOP_HEADERS | connection_headers | {"content-length", "host", "expect"}
    return {name.lower(): value for name, value in headers.items() if name.lower() not in excluded}


def available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class RelayGateway:
    def __init__(
        self,
        *,
        port: int,
        backend_base_url: str,
        proxy_key: str,
        chatgpt_base_url: str = DEFAULT_CHATGPT_CODEX_BASE_URL,
    ) -> None:
        router = GatewayRouter(
            backend_base_url=backend_base_url,
            proxy_key=proxy_key,
            chatgpt_base_url=chatgpt_base_url,
        )
        self._server = _RelayHttpServer(("127.0.0.1", port), router)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("ccrelay gateway is already running")
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="ccrelay-gateway",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._server.shutdown()
            self._thread.join(timeout=5)
            self._thread = None
        self._server.server_close()
        self._server.client.close()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


class _RelayHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], router: GatewayRouter) -> None:
        super().__init__(address, _RelayRequestHandler)
        self.router = router
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(connect=10, read=None, write=60, pool=10),
        )


class _RelayRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ccrelay"
    sys_version = ""

    def do_DELETE(self) -> None:
        self._proxy()

    def do_GET(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _proxy(self) -> None:
        server = cast(_RelayHttpServer, self.server)
        try:
            upstream = server.router.route(self.path, dict(self.headers.items()))
            body = self._read_request_body()
            with server.client.stream(
                self.command,
                upstream.url,
                headers=upstream.headers,
                content=body,
            ) as response:
                self._relay_response(response, decode_content=upstream.is_image_request)
        except GatewayRequestError as exc:
            self._send_json(exc.status_code, str(exc))
        except (httpx.HTTPError, OSError):
            self._send_json(502, "ccrelay upstream request failed")

    def _read_request_body(self) -> bytes | None:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return None
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise GatewayRequestError(400, "Invalid Content-Length") from exc
        if length < 0:
            raise GatewayRequestError(400, "Invalid Content-Length")
        return self.rfile.read(length)

    def _relay_response(self, response: httpx.Response, *, decode_content: bool = False) -> None:
        has_body = self.command != "HEAD" and response.status_code not in {204, 304}
        content_encoding = response.headers.get("Content-Encoding")
        normalize_encoding = decode_content and content_encoding is not None
        content_length = None if normalize_encoding else response.headers.get("Content-Length")
        use_chunked = has_body and content_length is None

        self.send_response(response.status_code)
        connection_headers = {
            name.strip().lower()
            for name in response.headers.get("Connection", "").split(",")
            if name.strip()
        }
        excluded = _HOP_BY_HOP_HEADERS | connection_headers | {"date", "server"}
        if normalize_encoding:
            excluded = excluded | {"content-encoding", "content-length"}
        for name, value in response.headers.multi_items():
            lowered = name.lower()
            if lowered in excluded or (lowered == "content-length" and use_chunked):
                continue
            self.send_header(name, value)
        if use_chunked:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        if not has_body:
            return
        try:
            chunks = response.iter_bytes() if normalize_encoding else response.iter_raw()
            for chunk in chunks:
                if not chunk:
                    continue
                if use_chunked:
                    self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                else:
                    self.wfile.write(chunk)
                self.wfile.flush()
            if use_chunked:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, httpx.HTTPError):
            self.close_connection = True

    def _send_json(self, status_code: int, message: str) -> None:
        if self.wfile.closed:
            return
        self.close_connection = True
        payload = json.dumps({"error": {"message": message}}).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
