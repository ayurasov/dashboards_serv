"""Поддельный HTTP-сервер для тестов подключений: настоящий сервер на 127.0.0.1:0 в отдельном потоке
(как FakeJira и FakeConfluence в burndown_tool), без сторонних пакетов.

    server = FakeServer()
    server.route("GET", "/api/meta", lambda req: (200, {"name": "Пульс"}))
    server.route("GET", "/moved", lambda req: (302, b"", {"Location": "https://elsewhere/"}))
    with server:
        client = HttpClient(server.url, ...)
    server.requests  # [Request(method, path, query, headers, body)]

Ответ обработчика: (статус, тело) или (статус, тело, заголовки); тело — dict/list (JSON), str или bytes.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes

    def json(self):
        return json.loads(self.body or b"null")


@dataclass
class FakeServer:
    routes: dict[tuple[str, str], Callable] = field(default_factory=dict)
    requests: list[Request] = field(default_factory=list)

    def route(self, method: str, path: str, handler: Callable) -> None:
        self.routes[(method.upper(), path)] = handler

    def start(self) -> FakeServer:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):  # тишина в выводе тестов
                return

            def _handle(self):
                parts = urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                request = Request(self.command, parts.path, parse_qs(parts.query),
                                  {k.lower(): v for k, v in self.headers.items()}, self.rfile.read(length))
                fake.requests.append(request)
                handler = fake.routes.get((self.command, parts.path))
                if handler is None:
                    result = (404, {"message": "not found"})
                else:
                    result = handler(request)
                status, body, headers = (*result, {})[:3] if len(result) == 2 else result
                if isinstance(body, (dict, list)):
                    payload, ctype = json.dumps(body, ensure_ascii=False).encode(), "application/json"
                elif isinstance(body, str):
                    payload, ctype = body.encode(), "text/html; charset=utf-8"
                else:
                    payload, ctype = body, "application/octet-stream"
                self.send_response(status)
                headers = {"Content-Type": ctype, **headers}
                if "Content-Length" not in headers:
                    headers["Content-Length"] = str(len(payload))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self) -> FakeServer:
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()
