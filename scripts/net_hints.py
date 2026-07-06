"""Recognize TLS/proxy-interception failures and emit an actionable hint.

Corporate proxies that inspect HTTPS (TLS interception / MITM) re-sign traffic
with a private root CA that Python does not trust by default, so urllib raises
``ssl.SSLCertVerificationError`` ("unable to get local issuer certificate").
That raw message tells the user nothing about the fix. These helpers detect the
condition anywhere in an exception chain and produce a one-line hint pointing at
``SSL_CERT_FILE``.

No project imports (stdlib only) → any module may use it, like fetch_errors.
"""
from __future__ import annotations

import os
import ssl

# Substrings OpenSSL/Python emit when a corporate CA re-signs intercepted HTTPS.
# Matched in addition to the typed check because the exact type/text varies across
# Python and OpenSSL versions.
_CERT_MARKERS = (
    "CERTIFICATE_VERIFY_FAILED",
    "unable to get local issuer certificate",
    "self signed certificate",
    "self-signed certificate",
)

_HINT = (
    "TLS certificate verification failed — this usually means a corporate proxy "
    "is intercepting HTTPS. Point Python at your company's root CA: "
    "export SSL_CERT_FILE=/path/to/corporate-ca.pem "
    "(also set HTTPS_PROXY if your network requires a proxy). See: omw doctor"
)


def _matches(exc: BaseException) -> bool:
    text = str(exc)
    return any(m in text for m in _CERT_MARKERS)


def is_cert_error(exc: BaseException | None) -> bool:
    """True if a cert-verification failure appears anywhere in the exception chain.

    Walks ``__cause__``/``__context__`` and ``URLError.reason`` (which holds the
    inner ``SSLError``). Cycle-safe via a seen-set.
    """
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError):
            return True
        reason = getattr(exc, "reason", None)  # urllib.error.URLError.reason
        if isinstance(reason, ssl.SSLError) and _matches(reason):
            return True
        if _matches(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def hint_for(exc: BaseException | None) -> str:
    """A ``\\n  hint: …`` suffix for a cert error, else an empty string.

    Empty-string fallback means callers can append it unconditionally without
    changing any non-TLS error message.
    """
    return f"\n  hint: {_HINT}" if is_cert_error(exc) else ""


def tls_env_status() -> dict[str, str]:
    """TLS-trust / proxy environment as {var: value|'not set'} — for omw doctor.

    Purely reads env vars (no network), so it stays hermetic and fast.
    """
    keys = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR",
            "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")
    out: dict[str, str] = {}
    for k in keys:
        out[k] = os.environ.get(k) or os.environ.get(k.lower()) or "not set"
    return out
