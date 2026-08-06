"""Fixtures HTTP locales contrôlées, confinées au sous-bloc OSIRIS."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


class TargetHandler(BaseHTTPRequestHandler):
    """Cibles déterministes pour les scénarios réseau du moteur."""

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_HEAD(self) -> None:  # noqa: N802
        self._respond(head_only=True)

    def do_GET(self) -> None:  # noqa: N802
        self._respond(head_only=False)

    def _respond(self, *, head_only: bool) -> None:
        if self.path == "/redirect":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/simple")
            self.end_headers()
            return
        if self.path == "/redirect-private":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        if self.path == "/redirect-loop":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/redirect-loop")
            self.end_headers()
            return
        if self.path == "/deep":
            tracker_url = f"http://www.google-analytics.com:{self.server.server_port}/a.js".encode()
            body = (
                b"<html><body><h1>Fixture OSIRIS Deep</h1>"
                b"<p>Gerer les cookies</p>"
                b"<button>Tout refuser</button>"
                b'<a href="/privacy">Politique de confidentialite</a>'
                b'<a href="mailto:privacy@example.test">Contact vie privee</a>'
                b"<script>setTimeout(() => { const s = document.createElement('script'); "
                b"s.src = '" + tracker_url + b"'; "
                b"document.head.appendChild(s); }, 10)</script>"
                b"</body></html>"
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        if self.path == "/slow":
            time.sleep(0.2)
        if self.path == "/large":
            body = b"x" * 8_192
        elif self.path == "/weak":
            body = (
                b"<html><body>Gerer les cookies "
                b'<script src="https://www.google-analytics.com/a.js"></script>'
                b'<a href="/privacy">Privacy</a></body></html>'
            )
        elif self.path == "/javascript":
            body = b"<html><body><script>document.body.dataset.ready='yes'</script></body></html>"
        elif self.path == "/unavailable":
            body = b"service unavailable"
            self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)
            return
        else:
            body = (
                b"<html><body><h1>Fixture OSIRIS</h1>"
                b'<a href="/privacy">Politique de confidentialite</a></body></html>'
            )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(body)


def first_free_port(start: int = 25000, end: int = 25099) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"Aucun port libre dans {start}-{end}")


@pytest.fixture
def target_server() -> Iterator[str]:
    port = first_free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), TargetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
