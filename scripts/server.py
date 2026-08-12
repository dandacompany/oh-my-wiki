"""omw serve — token-authenticated retrieve-only query API over a local vault.

Retrieve-only by design: the server runs NO LLM. It returns `search_index.query`
hits unchanged; answer synthesis stays in-session (host LLM) or a future flag.
See docs/superpowers/specs/2026-05-30-omw-messenger-query-api-design.md.
"""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from scripts import config
from scripts import embed
from scripts import recall
from scripts import registry
from scripts import search_index


class ServeError(Exception):
    """A client-facing error carrying an HTTP status and a safe message."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def verify_bearer(auth_header: str | None, expected: str) -> bool:
    """Constant-time check of an `Authorization: Bearer <token>` header."""
    if not expected or not auth_header:
        return False
    prefix = "Bearer "
    if not auth_header.startswith(prefix):
        return False
    presented = auth_header[len(prefix):]
    return hmac.compare_digest(presented, expected)


def _resolve_vault(db_path: Path, name: str | None):
    """Resolve a vault row by name, else the active vault. Raises ServeError."""
    if name:
        for row in registry.list_vaults(db_path):
            if row["name"] == name:
                return row
        raise ServeError(404, f"vault not found: {name}")
    row = registry.get_active(db_path)
    if row is None:
        raise ServeError(409, "no active vault; run omw vault use <name>")
    return row


def handle_query(
    payload: dict,
    *,
    db_path: Path,
    default_vault: str | None = None,
    max_limit: int = 10,
) -> dict:
    """Validate, resolve vault, run the ranker. Pure (no HTTP/auth). Raises ServeError."""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ServeError(400, "missing or empty 'text'")

    raw_limit = payload.get("limit", 5)
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        raise ServeError(400, "'limit' must be an integer")
    limit = max(1, min(limit, max_limit))

    row = _resolve_vault(db_path, payload.get("vault") or default_vault)
    rc = (config.load_config().get("recall") or {})
    strat = recall.effective_strategy(rc.get("strategy", "fts"), quiet=True)
    embedder = embed.active_embedder(
        db_path, rc.get("embedding") or {}
    ) if strat != "fts" else None
    hits = search_index.search_strategy(
        db_path,
        vault_id=row["id"],
        q=text,
        fts_query=text,
        limit=limit,
        strategy=strat,
        embedder=embedder,
        visibility="public",
    )
    return {"query": text, "vault": row["name"], "count": len(hits), "hits": hits}


class QueryHandler(BaseHTTPRequestHandler):
    """Thin HTTP shell over handle_query: auth + JSON + status mapping.

    Relies on the stdlib default ``protocol_version = "HTTP/1.0"`` (no keep-alive),
    so early-return paths (401/400) need not drain the request body. If this is
    ever bumped to HTTP/1.1, those paths must read+discard the body first.
    """

    def log_message(self, *args):  # silence default stderr access logging
        pass

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/query":
            self._send_json(405, {"error": "method not allowed"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/health":
            self._send_json(405, {"error": "method not allowed"})
            return
        if self.path != "/query":
            self._send_json(404, {"error": "not found"})
            return
        if not verify_bearer(self.headers.get("Authorization"), self.server.omw_token):
            self._send_json(401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0:
                raise ValueError
        except ValueError:
            self._send_json(400, {"error": "invalid Content-Length"})
            return
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        try:
            result = handle_query(
                payload,
                db_path=self.server.omw_db,
                default_vault=self.server.omw_default_vault,
                max_limit=self.server.omw_max_limit,
            )
        except ServeError as exc:
            self._send_json(exc.status, {"error": exc.message})
            return
        except Exception:
            self._send_json(500, {"error": "internal"})
            return
        self._send_json(200, result)


def make_server(
    *,
    host: str,
    port: int,
    token: str,
    db_path: Path,
    default_vault: str | None = None,
    max_limit: int = 10,
) -> ThreadingHTTPServer:
    """Build (but do not start) the HTTP server with request context attached."""
    httpd = ThreadingHTTPServer((host, port), QueryHandler)
    httpd.omw_token = token
    httpd.omw_db = db_path
    httpd.omw_default_vault = default_vault
    httpd.omw_max_limit = max_limit
    return httpd


def startup_line(host: str, port: int, vault: str | None) -> str:
    vault_label = vault if vault else "active"
    return f"omw serve on http://{host}:{port} (vault: {vault_label}, token: set)"


def serve(
    *,
    host: str,
    port: int,
    token: str,
    db_path: Path,
    default_vault: str | None = None,
    max_limit: int = 10,
) -> None:
    """Construct the server, print a startup line, and serve until interrupted."""
    if not token:
        raise ValueError("a token is required to serve (set OMW_SERVE_TOKEN)")
    httpd = make_server(
        host=host, port=port, token=token,
        db_path=db_path, default_vault=default_vault, max_limit=max_limit,
    )
    print(startup_line(host, httpd.server_address[1], default_vault), flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
