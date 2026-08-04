"""Interface web légère et sans collecte pour OSIRIS Scanner."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from report import (
    LEGAL_DISCLAIMER_EN,
    LEGAL_DISCLAIMER_FR,
    _build_report_data,
    generate_json_report,
    generate_markdown_report,
    generate_pdf_report,
)
from scanner import ScanOutcome, execute_scan
from url_security import URLSecurityError, validate_url_syntax

logger = logging.getLogger("osiris.web")
DEFAULT_PORT_START = 25000
DEFAULT_PORT_END = 25099
MAX_ACTIVE_JOBS = 4
MAX_REQUEST_BYTES = 4096
MAX_CONNECTIONS = 32
SOCKET_TIMEOUT_SECONDS = 10.0


@dataclass
class ScanJob:
    id: str
    url: str
    mode: str
    profile: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Analyse en attente"
    progress: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    outcome: ScanOutcome | None = None
    report_data: dict[str, Any] | None = None
    report_paths: dict[str, Path] = field(default_factory=dict)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()

    def create(self, url: str, mode: str, profile: str) -> ScanJob:
        with self._lock:
            active = sum(job.status in {"queued", "running"} for job in self._jobs.values())
            if active >= MAX_ACTIVE_JOBS:
                raise RuntimeError("Capacité temporairement atteinte; réessayez plus tard")
            job = ScanJob(id=uuid.uuid4().hex, url=url, mode=mode, profile=profile)
            self._jobs[job.id] = job
            self._prune_locked()
            return job

    def get(self, job_id: str) -> ScanJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return copy.deepcopy(job) if job is not None else None

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.time()

    def _prune_locked(self) -> None:
        expiry = time.time() - 3600
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.updated_at < expiry and job.status not in {"queued", "running"}
        ]
        for job_id in expired:
            job = self._jobs.pop(job_id, None)
            report_path = next(iter(job.report_paths.values()), None) if job else None
            if report_path is not None:
                shutil.rmtree(report_path.parent, ignore_errors=True)


STORE = JobStore()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="osiris-scan")
ARTIFACT_DIRECTORY = tempfile.TemporaryDirectory(prefix="osiris-scanner-web-")
ARTIFACT_ROOT = Path(ARTIFACT_DIRECTORY.name)


def _job_payload(job: ScanJob) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": job.id,
        "url": job.url,
        "mode": job.mode,
        "profile": job.profile,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "progress": job.progress,
    }
    if job.report_data is not None:
        payload["result"] = job.report_data
        payload["downloads"] = {
            kind: f"/api/scans/{job.id}/reports/{kind}" for kind in sorted(job.report_paths)
        }
    elif job.outcome and job.outcome.status == "failed":
        payload["errors"] = job.outcome.errors
    return payload


def _run_job(job_id: str) -> None:
    job = STORE.get(job_id)
    if job is None:
        return
    STORE.update(job_id, status="running", stage="validation", message="Validation de la cible")

    def progress(stage: str, message: str, percent: int) -> None:
        STORE.update(job_id, stage=stage, message=message, progress=percent)

    try:
        outcome = asyncio.run(
            execute_scan(
                job.url,
                mode=job.mode,
                progress_callback=progress,
            )
        )
        if outcome.status == "failed" or outcome.score is None:
            STORE.update(
                job_id,
                status="failed",
                stage="failed",
                message="Le scan n'a produit aucune donnée exploitable",
                progress=100,
                outcome=outcome,
            )
            return

        output_dir = ARTIFACT_ROOT / job.id
        output_dir.mkdir(parents=True, exist_ok=True)
        meta = outcome.scan_meta()
        meta["profile"] = job.profile
        report_data = _build_report_data(
            outcome.url,
            outcome.results,
            outcome.score,
            outcome.grade,
            meta,
        )
        report_paths = {
            "json": generate_json_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                str(output_dir),
                meta,
                report_data=report_data,
            ),
            "markdown": generate_markdown_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                str(output_dir),
                meta,
                report_data=report_data,
            ),
            "pdf": generate_pdf_report(
                outcome.url,
                outcome.results,
                outcome.score,
                outcome.grade,
                str(output_dir),
                meta,
                report_data=report_data,
            ),
        }
        STORE.update(
            job_id,
            status="complete",
            stage="complete",
            message="Diagnostic terminé",
            progress=100,
            outcome=outcome,
            report_data=report_data,
            report_paths=report_paths,
        )
    except Exception as exc:
        logger.exception("Échec inattendu du job %s", job_id)
        STORE.update(
            job_id,
            status="failed",
            stage="failed",
            message=f"Erreur technique : {exc}",
            progress=100,
        )


class OsirisHandler(BaseHTTPRequestHandler):
    server_version = "OSIRIS/0.3"
    protocol_version = "HTTP/1.1"

    def log_message(self, format_string: str, *args: Any) -> None:
        logger.info("%s — %s", self.client_address[0], format_string % args)

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header("Cache-Control", "no-store")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _static(self, name: str, content_type: str) -> None:
        resource = files("osiris_web").joinpath("static", name)
        if not resource.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Ressource introuvable"})
            return
        body = resource.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/":
            self._static("index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._static("styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._static("app.js", "text/javascript; charset=utf-8")
            return
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok", "version": "0.3.0"})
            return
        if path == "/api/methodology":
            self._json(
                HTTPStatus.OK,
                {
                    "axes": ["O", "S", "I", "R", "V", "L"],
                    "disclaimer": {"fr": LEGAL_DISCLAIMER_FR, "en": LEGAL_DISCLAIMER_EN},
                },
            )
            return

        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "scans"]:
            job = STORE.get(parts[2])
            if job is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "Analyse introuvable"})
                return
            self._json(HTTPStatus.OK, _job_payload(job))
            return
        if len(parts) == 5 and parts[:2] == ["api", "scans"] and parts[3] == "reports":
            job = STORE.get(parts[2])
            kind = parts[4]
            report_path = job.report_paths.get(kind) if job else None
            if report_path is None or not report_path.is_file():
                self._json(HTTPStatus.NOT_FOUND, {"error": "Rapport introuvable"})
                return
            content_types = {
                "json": "application/json; charset=utf-8",
                "markdown": "text/markdown; charset=utf-8",
                "pdf": "application/pdf",
            }
            body = report_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._security_headers(content_types[kind])
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="osiris-{parts[2]}.{report_path.suffix.lstrip(".")}"',
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        self._json(HTTPStatus.NOT_FOUND, {"error": "Route introuvable"})

    def do_HEAD(self) -> None:  # noqa: N802
        """Expose les mêmes métadonnées que GET sans transférer le corps."""

        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/scans":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Route introuvable"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Requête invalide"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "JSON invalide"})
            return

        if not isinstance(payload, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Le corps JSON doit être un objet"})
            return

        url = payload.get("url")
        mode = payload.get("mode", "fast")
        profile = payload.get("profile", "general")
        if not isinstance(url, str) or not isinstance(mode, str) or mode not in {"fast", "deep"}:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "URL ou mode invalide"})
            return
        if not isinstance(profile, str) or profile not in {"general", "loi25"}:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Profil invalide"})
            return
        try:
            normalized = validate_url_syntax(url)
            job = STORE.create(normalized, mode, profile)
        except URLSecurityError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._json(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
            return

        EXECUTOR.submit(_run_job, job.id)
        self._json(HTTPStatus.ACCEPTED, _job_payload(job))


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Serveur de démonstration borné contre les connexions lentes ou excessives."""

    daemon_threads = True
    block_on_close = False
    request_queue_size = MAX_CONNECTIONS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._connection_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)

    def get_request(self) -> tuple[Any, Any]:
        request, client_address = super().get_request()
        request.settimeout(SOCKET_TIMEOUT_SECONDS)
        return request, client_address

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


def _find_available_port(host: str, start: int, end: int) -> int:
    import socket

    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"Aucun port libre dans le sous-bloc {start}-{end}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interface web OSIRIS Scanner")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    if args.port is not None and not 25000 <= args.port <= 25999:
        parser.error("Le port doit rester dans la plage OSIRIS 25000-25999")
    port = args.port or _find_available_port(args.host, DEFAULT_PORT_START, DEFAULT_PORT_END)
    server = BoundedThreadingHTTPServer((args.host, port), OsirisHandler)
    print(f"OSIRIS Scanner — http://{args.host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        EXECUTOR.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
