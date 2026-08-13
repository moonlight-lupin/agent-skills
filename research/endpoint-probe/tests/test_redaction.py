"""Tests for credential redaction in endpoint-probe reports."""

import probe_api as ep


def test_redact_authorization_keeps_scheme():
    assert ep._redact_header_value("authorization", "Bearer eyJhbGciOiJIUzI1NiJ9.abc") == "Bearer ***"
    assert ep._redact_header_value("Authorization", "Basic dXNlcjpwYXNz") == "Basic ***"
    assert ep._redact_header_value("proxy-authorization", "Bearer tok_abc") == "Bearer ***"


def test_redact_api_key_headers():
    assert ep._redact_header_value("x-api-key", "sk-live-secret") == "***"
    assert ep._redact_header_value("api-key", "abc123") == "***"


def test_redact_set_cookie_keeps_name_and_attrs():
    raw = "sessionid=abc123def; Path=/; HttpOnly; Secure"
    out = ep._redact_header_value("set-cookie", raw)
    assert "sessionid=***" in out
    assert "abc123def" not in out
    assert "Path=/" in out
    assert "HttpOnly" in out
    assert "Secure" in out


def test_redact_set_cookie_with_expires_date():
    """RFC 1123 Expires dates contain a comma — must not split the cookie."""
    raw = "session=abc123; Expires=Wed, 09 Jun 2026 10:18:14 GMT; Path=/; HttpOnly"
    out = ep._redact_header_value("set-cookie", raw)
    assert "session=***" in out
    assert "abc123" not in out
    assert "Expires=Wed, 09 Jun 2026 10:18:14 GMT" in out
    assert "Path=/" in out
    assert "HttpOnly" in out


def test_redact_set_cookie_multi_cookie_with_expires():
    """Two comma-joined cookies, first with an Expires date."""
    raw = "session=abc; Expires=Wed, 09 Jun 2026 10:18:14 GMT; Path=/, csrf=xyz; Path=/"
    out = ep._redact_header_value("set-cookie", raw)
    assert "session=***" in out
    assert "csrf=***" in out
    assert "abc" not in out.replace("abc123", "")  # no bare value leak
    assert "xyz" not in out
    assert "Expires=Wed, 09 Jun 2026 10:18:14 GMT" in out


def test_www_authenticate_not_redacted():
    # Scheme discovery depends on the full challenge string.
    challenge = 'Bearer realm="api", error="invalid_token"'
    assert ep._redact_header_value("www-authenticate", challenge) == challenge


def test_extract_interesting_headers_redacts_secrets():
    hdrs = {
        "WWW-Authenticate": 'Bearer realm="api"',
        "Authorization": "Bearer leaked-token",
        "X-API-Key": "sk-echoed",
        "Set-Cookie": "sid=secretvalue; Path=/",
        "X-RateLimit-Remaining": "42",
        "Server": "nginx",
    }
    interesting = ep._extract_interesting_headers(hdrs)
    assert interesting["www-authenticate"] == 'Bearer realm="api"'
    assert interesting["authorization"] == "Bearer ***"
    assert interesting["x-api-key"] == "***"
    assert interesting["set-cookie"].startswith("sid=***")
    assert "secretvalue" not in interesting["set-cookie"]
    assert interesting["x-ratelimit-remaining"] == "42"
    assert interesting["server"] == "nginx"


def test_redact_body_hint_keeps_scheme_phrases():
    body = '{"error":"unauthorized","message":"API key required in X-API-Key header"}'
    hint = ep._redact_body_hint(body)
    assert "API key required" in hint
    assert "X-API-Key" in hint


def test_redact_body_hint_strips_tokens():
    body = (
        'Unauthorized. Use Authorization: Bearer '
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaaaa.bbbbbbbbbb '
        'or {"api_key":"sk-live-supersecret"}'
    )
    hint = ep._redact_body_hint(body)
    assert "Bearer ***" in hint
    assert "eyJhbGciOi" not in hint
    assert "«redacted:sk-…»" not in hint
    assert "***" in hint


def test_redact_body_hint_strips_jwe_tokens():
    """JWE (encrypted JWT) has 4-5 segments, not 3 — regex must still catch it."""
    jwe = (
        "eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4R0NNIn0."
        "kkkkkkkkkkkk.vvvvvvvvvv.cccccccccc.tttttttttt"
    )
    hint = ep._redact_body_hint(f"token={jwe} leaked")
    assert jwe not in hint
    assert "***" in hint

    # JWE with empty CEK (two dots in a row)
    jwe_empty = (
        "eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4R0NNIn0."
        ".vvvvvvvvvv.cccccccccc.tttttttttt"
    )
    hint2 = ep._redact_body_hint(f"token={jwe_empty} leaked")
    assert "eyJhbGciOi" not in hint2
    assert "***" in hint2


def test_probe_auth_stores_redacted_body_hint(monkeypatch):
    def fake_request(url, method="GET", headers=None, data=None, timeout=10):
        return (
            401,
            {"WWW-Authenticate": "Bearer realm=\"api\""},
            'missing token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaaaaaaaa.bbbbbbbbbb',
        )

    monkeypatch.setattr(ep, "_make_request", fake_request)
    findings = ep.probe_auth("https://api.example.com", timeout=5)
    assert len(findings) == 1
    assert findings[0]["scheme"] == "Bearer (OAuth2 / JWT)"
    assert findings[0]["www_authenticate"] == 'Bearer realm="api"'
    assert "eyJhbGciOi" not in findings[0]["body_hint"]
    assert "Bearer ***" in findings[0]["body_hint"]
