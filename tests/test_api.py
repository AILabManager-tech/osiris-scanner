"""Contrats de sécurité de l'adaptateur serverless."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from api.scan import handler
from tests.conftest import first_free_port


@pytest.fixture
def api_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", first_free_port()), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_api_rejects_non_object_json_with_security_headers(api_server: str) -> None:
    request = Request(
        api_server,
        data=json.dumps([]).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(HTTPError) as error:
        urlopen(request, timeout=3)  # noqa: S310 - serveur fixture local
    response = error.value
    try:
        assert response.code == 400
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    finally:
        response.close()
