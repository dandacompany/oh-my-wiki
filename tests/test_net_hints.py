"""net_hints: cert-error detection + hint suffix (corporate-proxy TLS case)."""
import ssl
import urllib.error

from scripts import net_hints


def _cert_err():
    return ssl.SSLCertVerificationError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "unable to get local issuer certificate")


def test_detects_direct_ssl_cert_error():
    assert net_hints.is_cert_error(_cert_err()) is True


def test_detects_urlerror_wrapping_ssl_reason():
    # urllib wraps the SSLError as URLError.reason
    assert net_hints.is_cert_error(urllib.error.URLError(_cert_err())) is True


def test_detects_via_cause_chain():
    outer = RuntimeError("fetch failed")
    outer.__cause__ = urllib.error.URLError(_cert_err())
    assert net_hints.is_cert_error(outer) is True


def test_detects_by_message_only():
    # type not recognized, but the telltale substring is present
    assert net_hints.is_cert_error(OSError("unable to get local issuer certificate")) is True


def test_non_cert_errors_are_false():
    assert net_hints.is_cert_error(urllib.error.URLError("timed out")) is False
    assert net_hints.is_cert_error(TimeoutError("timed out")) is False
    assert net_hints.is_cert_error(None) is False


def test_cycle_safe():
    a = RuntimeError("a")
    b = RuntimeError("b")
    a.__cause__ = b
    b.__cause__ = a  # cycle
    assert net_hints.is_cert_error(a) is False  # must terminate, not hang


def test_hint_for_cert_error_mentions_ssl_cert_file():
    hint = net_hints.hint_for(_cert_err())
    assert "SSL_CERT_FILE" in hint
    assert hint.startswith("\n  hint:")


def test_hint_for_non_cert_is_empty():
    assert net_hints.hint_for(urllib.error.URLError("timed out")) == ""


def test_tls_env_status_reports_not_set(monkeypatch):
    for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR",
              "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
              "https_proxy", "http_proxy", "no_proxy"):
        monkeypatch.delenv(k, raising=False)
    st = net_hints.tls_env_status()
    assert st["SSL_CERT_FILE"] == "not set"
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/corp/ca.pem")
    assert net_hints.tls_env_status()["SSL_CERT_FILE"] == "/etc/corp/ca.pem"
