"""Adaptateur HTTP synchrone pour l'accès public OSIRIS sur Vercel."""

from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from report import _build_report_data
from scanner import execute_scan
from url_security import URLSecurityError, validate_url_syntax

MAX_REQUEST_BYTES = 4096


class handler(BaseHTTPRequestHandler):  # noqa: N801
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Requête invalide"})
            return

        try:
            payload = json.loads(self.rfile.read(length))
            url = validate_url_syntax(payload.get("url", ""))
            profile = payload.get("profile", "general")
            if profile not in {"general", "loi25"}:
                raise ValueError("Profil invalide")
        except (json.JSONDecodeError, URLSecurityError, ValueError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        try:
            outcome = asyncio.run(execute_scan(url, mode="fast"))
            if outcome.status == "failed" or outcome.score is None:
                self._json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    {
                        "error": "Le scan n'a produit aucune donnée exploitable",
                        "errors": outcome.errors,
                    },
                )
                return
            meta = outcome.scan_meta()
            meta["profile"] = profile
            result = _build_report_data(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                meta,
            )
            self._json(
                HTTPStatus.OK,
                {
                    "url": outcome.url,
                    "mode": "fast",
                    "profile": profile,
                    "status": "complete",
                    "result": result,
                    "downloads": {},
                },
            )
        except Exception:
            self._json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Erreur technique pendant le scan"},
            )

    def do_GET(self) -> None:  # noqa: N802
        self._json(HTTPStatus.OK, {"status": "ok", "version": "0.3.0"})
