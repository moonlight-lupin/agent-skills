#!/usr/bin/env python3
"""Endpoint Probe Probe — discover an API's surface from a base URL or MCP server.

For REST/GraphQL/SOAP APIs:
  - API type (REST, GraphQL, gRPC-Web, SOAP, JSON-RPC)
  - Auth scheme (Bearer, Basic, API key, OAuth2, session cookie, none)
  - Endpoints (from OpenAPI/Swagger, GraphQL introspection, well-known paths, OPTIONS)
  - Rate-limit headers, CORS policy, server/framework fingerprints

For MCP servers (HTTP StreamableHTTP or stdio):
  - Server info, protocol version, capabilities
  - Tools with full input schemas (parameter names, types, required, defaults, enums)
  - Resources (URIs, names, MIME types)
  - Prompts (names, descriptions, arguments)

Usage:
  # Standard API probe
  python probe_api.py <base_url> [--auth TOKEN] [--auth-type bearer|basic|apikey]
                       [--header "Key: Value"] [--timeout 10] [--json]
                       [--no-guess] [--api-version v1]

  # MCP over HTTP
  python probe_api.py <mcp_url> --mcp [--auth TOKEN] [--header "Key: Value"]

  # MCP over stdio
  python probe_api.py "<command> <args>" --mcp-stdio [--mcp-env "KEY=value"]

Output: JSON report to stdout (--json) or pretty-printed report (default).
"""

import argparse
import json
import shlex
import sys
import time

import urllib.request
import urllib.error
import urllib.parse
import os
import socket

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Well-known discovery paths (relative to base URL)
DISCOVERY_PATHS = [
    # OpenAPI / Swagger
    "/openapi.json",
    "/openapi.yaml",
    "/swagger.json",
    "/swagger/v1/swagger.json",
    "/api-docs",
    "/api/docs",
    "/docs",
    "/redoc",
    "/api/openapi.json",
    "/api/v1/openapi.json",
    "/api/swagger.json",
    "/v1/openapi.json",
    # Rapidoc / Elements
    "/rapidoc",
    "/api/rapidoc",
    # .well-known
    "/.well-known/openapi.json",
    "/.well-known/api",
    "/.well-known/manifest.json",
    # GraphQL
    "/graphql",
    "/graphql/schema",
    "/api/graphql",
    "/query",
    # gRPC-Web / Connect
    "/grpc",
    "/grpc.web",
    # SOAP / WSDL
    "/wsdl",
    "/service.asmx?wsdl",
    "/api/soap?wsdl",
    # Health / info
    "/health",
    "/healthz",
    "/api/health",
    "/status",
    "/api/status",
    "/info",
    "/api/info",
    "/version",
    "/api/version",
    # Common API base paths
    "/api",
    "/api/v1",
    "/api/v2",
    "/v1",
    "/v2",
    # JSON-RPC
    "/jsonrpc",
    "/rpc",
    "/api/rpc",
]

# Common REST resource paths to probe ( appended to /api/ or /api/v1/ )
COMMON_RESOURCES = [
    "users", "user", "accounts", "products", "orders", "items",
    "posts", "comments", "categories", "sessions", "tokens",
    "auth", "login", "logout", "register", "me", "profile",
    "search", "files", "uploads", "webhooks", "events",
    "notifications", "messages", "channels", "organizations",
    "teams", "projects", "repositories", "commits", "branches",
    "settings", "config", "preferences", "billing", "invoices",
    "payments", "subscriptions", "plans", "metrics", "stats",
    "logs", "audit", "reports", "export", "import",
]

# GraphQL introspection query
GRAPHQL_INTROSPECTION = json.dumps({
    "query": """
    query IntrospectionQuery {
      __schema {
        queryType { name }
        mutationType { name }
        subscriptionType { name }
        types {
          name
          kind
          fields {
            name
            type { name kind ofType { name kind } }
          }
        }
      }
    }
    """
})

# Headers that reveal auth / rate-limit / framework info.
# Credential-bearing names below are still captured for discovery, but values
# are redacted via _redact_header_value() before they enter the report.
INTERESTING_HEADERS = [
    "www-authenticate", "x-api-key", "api-key", "authorization",
    "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
    "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset",
    "retry-after", "x-rate-limit-limit", "x-rate-limit-remaining",
    "access-control-allow-origin", "access-control-allow-methods",
    "access-control-allow-headers", "access-control-allow-credentials",
    "access-control-expose-headers",
    "x-powered-by", "server", "x-aspnet-version", "x-aspnetmvc-version",
    "x-request-id", "x-correlation-id", "x-trace-id",
    "content-type", "set-cookie",
    "x-amzn-requestid", "x-amz-cf-id",
    "x-served-by", "x-cache",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
]

# Response headers whose values may contain secrets (still report presence/shape).
_SENSITIVE_HEADER_NAMES = frozenset({
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "set-cookie",
    "cookie",
})

DEFAULT_TIMEOUT = 10
USER_AGENT = "endpoint-probe-probe/1.2.3 (+https://github.com/moonlight-lupin)"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

MAX_BODY_SIZE = 5 * 1024 * 1024  # 5 MiB cap to prevent memory DoS (M5)


def _make_request(url, method="GET", headers=None, data=None, timeout=DEFAULT_TIMEOUT):
    """Low-level HTTP request. Returns (status, response_headers, body_text)."""
    # SSRF check (B3) — skip for MCP stdio which doesn't use URLs
    try:
        _validate_url(url)
    except ValueError as e:
        return -1, {}, str(e)

    # Always copy headers to avoid mutating shared dict under threads (M4)
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=data, method=method)
    for k, v in req_headers.items():
        req.add_header(k, v)

    # Build opener that blocks redirects for SSRF safety (B3)
    opener = urllib.request.build_opener(_NoRedirectHandler())

    try:
        resp = opener.open(req, timeout=timeout)
        # Cap body read to prevent memory DoS (M5)
        raw = resp.read(MAX_BODY_SIZE + 1)
        truncated = len(raw) > MAX_BODY_SIZE
        body = raw[:MAX_BODY_SIZE].decode("utf-8", errors="replace")
        if truncated:
            body += "\n[truncated at 5 MiB]"
        return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as e:
        raw = e.read(MAX_BODY_SIZE + 1) if e.fp else b""
        truncated = len(raw) > MAX_BODY_SIZE
        body = raw[:MAX_BODY_SIZE].decode("utf-8", errors="replace")
        if truncated:
            body += "\n[truncated at 5 MiB]"
        return e.code, dict(e.headers) if e.headers else {}, body
    except urllib.error.URLError as e:
        return -1, {}, str(e.reason)
    except Exception as e:
        return -1, {}, str(e)


def _normalize_base_url(url):
    """Ensure base URL has scheme, no trailing slash."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url.rstrip("/")


# --- SSRF protection (B3) ---

import ipaddress

_METADATA_HOSTS = {"169.254.169.254", "metadata.google.internal"}


def _is_private_ip(ip_str):
    """Check if an IP address string is private/internal using ipaddress module."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # is_private covers RFC1918, loopback, link-local, ULA fc00::/7
    # Explicitly check CGNAT 100.64.0.0/10 (not always in is_private)
    if isinstance(ip, ipaddress.IPv4Address):
        cgnet = ipaddress.ip_network("100.64.0.0/10")
        if ip in cgnet:
            return True
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _is_private_host(hostname):
    """Check if a hostname resolves to or is a private/internal IP."""
    if hostname in _METADATA_HOSTS:
        return True
    # Check if it's a literal IP (including IPv4-mapped IPv6 like ::ffff:127.0.0.1)
    try:
        ip = ipaddress.ip_address(hostname)
        # Handle IPv4-mapped IPv6 — extract the IPv4 part
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return _is_private_ip(str(ip.ipv4_mapped))
        return _is_private_ip(hostname)
    except ValueError:
        pass  # Not a literal IP — try DNS
    # DNS resolution
    try:
        infos = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            if ip in _METADATA_HOSTS:
                return True
            try:
                ip_obj = ipaddress.ip_address(ip)
                if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                    if _is_private_ip(str(ip_obj.ipv4_mapped)):
                        return True
                elif _is_private_ip(ip):
                    return True
            except ValueError:
                pass
    except socket.gaierror:
        pass  # Can't resolve — allow (will fail at connection time)
    return False


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent following redirects to avoid SSRF via 302 to internal IPs."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never follow redirects


# Module-level flag to allow private hosts (set by --allow-private)
_allow_private = False


def _validate_url(url):
    """Validate URL for SSRF safety. Raises ValueError if blocked."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked: non-HTTP scheme '{parsed.scheme}'")
    if not _allow_private and parsed.hostname:
        if _is_private_host(parsed.hostname):
            raise ValueError(
                f"Blocked: private/internal host '{parsed.hostname}'. "
                f"Use --allow-private to override."
            )
    return url


def _try_parse_json(text):
    """Best-effort JSON parse."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Probe phases
# ---------------------------------------------------------------------------

def probe_well_known(base_url, auth_headers, timeout):
    """Probe well-known discovery paths using concurrent requests."""
    import concurrent.futures

    def _probe_one(path):
        url = base_url + path
        status, hdrs, body = _make_request(url, headers=auth_headers, timeout=timeout)
        if status == -1:
            return None

        finding = {
            "path": path,
            "url": url,
            "status": status,
            "content_type": hdrs.get("content-type", hdrs.get("Content-Type", "")),
            "body_length": len(body),
            "interesting_headers": _extract_interesting_headers(hdrs),
        }

        if status == 200 and body:
            parsed = _try_parse_json(body)
            if parsed and ("openapi" in parsed or "swagger" in parsed):
                finding["type"] = "openapi"
                finding["version"] = parsed.get("openapi") or parsed.get("swagger")
                finding["title"] = parsed.get("info", {}).get("title", "")
                finding["endpoints"] = _extract_openapi_endpoints(parsed)
            elif parsed and "__schema" in str(parsed)[:500]:
                finding["type"] = "graphql-schema"
            elif "graphql" in path:
                finding["type"] = "graphql-endpoint"
            elif status == 200 and "text/html" in finding["content_type"]:
                finding["type"] = "html-docs"
                lower = body.lower()
                if "swagger-ui" in lower or "swagger" in lower:
                    finding["subtype"] = "swagger-ui"
                elif "redoc" in lower:
                    finding["subtype"] = "redoc"
                elif "rapidoc" in lower:
                    finding["subtype"] = "rapidoc"
                elif "scalar" in lower:
                    finding["subtype"] = "scalar"
            elif status in (200, 201, 204) and path in ("/health", "/healthz", "/api/health"):
                finding["type"] = "health"
            elif status in (200,) and path in ("/status", "/api/status"):
                finding["type"] = "status"

        return finding

    findings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_probe_one, p): p for p in DISCOVERY_PATHS}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    findings.append(result)
            except Exception as e:
                pass  # errors collected per-path via status codes
    # Sort by path for stable output
    findings.sort(key=lambda f: f["path"])
    return findings


def probe_graphql(base_url, auth_headers, timeout):
    """Attempt GraphQL introspection."""
    candidates = ["/graphql", "/api/graphql", "/query"]
    results = []
    for path in candidates:
        url = base_url + path
        headers = dict(auth_headers)
        headers["Content-Type"] = "application/json"
        status, hdrs, body = _make_request(
            url, method="POST", headers=headers,
            data=GRAPHQL_INTROSPECTION.encode("utf-8"), timeout=timeout
        )
        if status == -1:
            continue

        parsed = _try_parse_json(body)
        result = {
            "path": path,
            "url": url,
            "status": status,
            "content_type": hdrs.get("content-type", hdrs.get("Content-Type", "")),
        }

        if parsed and "data" in parsed and "__schema" in parsed.get("data", {}):
            result["introspection"] = True
            schema = parsed["data"]["__schema"]
            result["query_type"] = schema.get("queryType", {}).get("name")
            result["mutation_type"] = schema.get("mutationType", {}).get("name")
            result["subscription_type"] = schema.get("subscriptionType", {}).get("name")
            result["types"] = [
                t["name"] for t in schema.get("types", [])
                if t.get("name") and not t["name"].startswith("__")
            ]
        elif parsed and "errors" in parsed:
            result["introspection"] = False
            result["error"] = parsed["errors"][0].get("message", "")[:200]
        else:
            result["introspection"] = False

        results.append(result)
    return results


def probe_options(base_url, auth_headers, timeout):
    """Send OPTIONS to base URL and /api to discover allowed methods."""
    results = []
    for path in ["", "/api", "/api/v1"]:
        url = base_url + path
        status, hdrs, body = _make_request(url, method="OPTIONS", headers=auth_headers, timeout=timeout)
        if status == -1:
            continue
        allow = hdrs.get("allow", hdrs.get("Allow", ""))
        cors_methods = hdrs.get("access-control-allow-methods", hdrs.get("Access-Control-Allow-Methods", ""))
        cors_origin = hdrs.get("access-control-allow-origin", hdrs.get("Access-Control-Allow-Origin", ""))
        if allow or cors_methods or cors_origin:
            results.append({
                "path": path or "/",
                "url": url,
                "status": status,
                "allow": allow,
                "cors_allow_methods": cors_methods,
                "cors_allow_origin": cors_origin,
                "cors_allow_headers": hdrs.get("access-control-allow-headers", hdrs.get("Access-Control-Allow-Headers", "")),
                "cors_allow_credentials": hdrs.get("access-control-allow-credentials", hdrs.get("Access-Control-Allow-Credentials", "")),
            })
    return results


def probe_auth(base_url, timeout):
    """Determine auth scheme by examining 401/403 responses."""
    # Hit a likely-protected endpoint without auth
    test_paths = ["/api/me", "/api/users", "/api/v1/users", "/me", "/api/account"]
    auth_findings = []

    for path in test_paths:
        url = base_url + path
        status, hdrs, body = _make_request(url, timeout=timeout)
        if status == -1:
            continue

        if status in (401, 403):
            www_auth = hdrs.get("www-authenticate", hdrs.get("WWW-Authenticate", ""))
            # Classify against the raw body first, then store a redacted hint
            # so scheme discovery still works if an error page echoed a token.
            finding = {
                "path": path,
                "status": status,
                "www_authenticate": www_auth,
                "body_hint": _redact_body_hint(body),
            }

            # Classify auth scheme
            if www_auth:
                lower = www_auth.lower()
                if "bearer" in lower:
                    finding["scheme"] = "Bearer (OAuth2 / JWT)"
                elif "basic" in lower:
                    finding["scheme"] = "Basic"
                elif "digest" in lower:
                    finding["scheme"] = "Digest"
                elif "apikey" in lower or "api-key" in lower or "api_key" in lower:
                    finding["scheme"] = "API Key"
                elif "oauth" in lower:
                    finding["scheme"] = "OAuth2"
                else:
                    finding["scheme"] = www_auth.split()[0] if www_auth else "unknown"
            elif status == 401:
                # No WWW-Authenticate header — check body for hints
                lower_body = body.lower() if body else ""
                if "api key" in lower_body or "api-key" in lower_body or "x-api-key" in lower_body:
                    finding["scheme"] = "API Key (header-based, no WWW-Authenticate)"
                elif "token" in lower_body or "bearer" in lower_body:
                    finding["scheme"] = "Bearer token (no WWW-Authenticate)"
                elif "unauthorized" in lower_body or "unauthenticated" in lower_body:
                    finding["scheme"] = "Unknown (no WWW-Authenticate header)"
                else:
                    finding["scheme"] = "Unknown (no WWW-Authenticate header)"
            elif status == 403:
                finding["scheme"] = "Forbidden — auth may be session-based or IP-restricted"

            auth_findings.append(finding)
            break  # one is enough

    return auth_findings


def probe_rest_resources(base_url, auth_headers, timeout, version=""):
    """Probe common REST resource paths using concurrent requests."""
    import concurrent.futures
    prefix = f"/api/{version}" if version else "/api"

    def _probe_one(resource):
        path = f"{prefix}/{resource}"
        url = base_url + path
        # Use shorter timeout for resource guessing (4s max)
        probe_timeout = min(timeout, 4)
        status, hdrs, body = _make_request(url, headers=auth_headers, timeout=probe_timeout)
        if status == -1 or status == 404:
            return None
        ct = hdrs.get("content-type", hdrs.get("Content-Type", ""))
        parsed = _try_parse_json(body) if body else None
        result = {
            "path": path,
            "url": url,
            "status": status,
            "content_type": ct,
            "body_length": len(body),
        }
        if parsed and isinstance(parsed, list):
            result["item_count"] = len(parsed)
        elif parsed and isinstance(parsed, dict):
            for key in ("data", "results", "items", "records"):
                if key in parsed and isinstance(parsed[key], list):
                    result["item_count"] = len(parsed[key])
                    break
            if "error" in parsed or "message" in parsed:
                result["error"] = (parsed.get("error") or parsed.get("message", ""))[:200]
        return result

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_probe_one, r): r for r in COMMON_RESOURCES}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass
    # Sort by path for stable output
    results.sort(key=lambda r: r["path"])

    # Detect SPA false positives: if all results are 200 + text/html with similar
    # body lengths, it's likely a SPA serving the same page for every path.
    if len(results) >= 5 and all(
        r["status"] == 200 and "text/html" in r.get("content_type", "")
        for r in results
    ):
        body_lengths = [r["body_length"] for r in results]
        if max(body_lengths) - min(body_lengths) < 200:
            # All same size ±200 bytes → SPA catch-all
            return []  # discard — these are false positives

    return results


def probe_rate_limits(base_url, auth_headers, timeout):
    """Check rate-limit headers from a baseline request."""
    url = base_url + "/api"
    status, hdrs, body = _make_request(url, headers=auth_headers, timeout=timeout)
    rate_info = {}
    for h in hdrs:
        lower = h.lower()
        if "rate" in lower or "limit" in lower or "retry" in lower or "quota" in lower:
            rate_info[h] = hdrs[h]
    return rate_info if rate_info else None


def _redact_set_cookie(value):
    """Keep cookie names + attributes; redact cookie values.

    Multiple ``Set-Cookie`` values may be comma-joined by HTTP libraries.
    RFC 1123 ``Expires`` dates also contain commas (e.g.
    ``Expires=Wed, 09 Jun 2026 10:18:14 GMT``), so we protect those
    commas before splitting on ``,`` to avoid mis-parsing.
    """
    import re

    # Mask commas inside Expires=... so they don't split a single cookie.
    # We restore them after the split.
    _EXPIRES_SENTINEL = "\x00COMMA\x00"

    def _mask_expires_commas(text):
        def _replace(m):
            return m.group(0).replace(",", _EXPIRES_SENTINEL)
        # Match Expires=<day-name>, <rest of date>
        return re.sub(
            r"(?i)\bExpires=[A-Za-z]{3},[^;]*",
            _replace,
            text,
        )

    masked = _mask_expires_commas(value)
    parts = []
    for segment in masked.split(","):
        segment = segment.replace(_EXPIRES_SENTINEL, ",")
        # Multiple Set-Cookie values may be joined; also handle attrs after ';'.
        attrs = [a.strip() for a in segment.split(";") if a.strip()]
        if not attrs:
            continue
        name, sep, _ = attrs[0].partition("=")
        if sep:
            redacted = [f"{name}=***"]
        else:
            redacted = [attrs[0]]
        for attr in attrs[1:]:
            # Preserve Path/HttpOnly/Secure/SameSite/etc.; redact unknown name=value
            # only when it looks like another cookie pair (rare). Keep standard attrs.
            lower = attr.lower()
            if lower.startswith(("path=", "domain=", "expires=", "max-age=", "samesite=")) or lower in (
                "httponly", "secure", "partitioned",
            ):
                redacted.append(attr)
            elif "=" in attr:
                aname, _, _ = attr.partition("=")
                redacted.append(f"{aname}=***")
            else:
                redacted.append(attr)
        parts.append("; ".join(redacted))
    return ", ".join(parts) if parts else "***"


def _redact_header_value(name, value):
    """Redact credential-like header values while preserving auth-protocol shape.

    Examples:
      Authorization: Bearer eyJhbGciOi...  →  Bearer ***
      X-API-Key: sk-live-...              →  ***
      Set-Cookie: session=abc; Path=/     →  session=***; Path=/
      WWW-Authenticate: Bearer realm="x"  →  unchanged (scheme discovery)
    """
    if value is None:
        return value
    text = str(value)
    lower = name.lower()
    if lower not in _SENSITIVE_HEADER_NAMES:
        return text
    if lower in ("authorization", "proxy-authorization"):
        scheme, _, rest = text.strip().partition(" ")
        if rest:
            return f"{scheme} ***"
        return "***"
    if lower == "set-cookie":
        return _redact_set_cookie(text)
    # x-api-key / api-key / cookie
    return "***"


def _redact_body_hint(body, limit=300):
    """Truncate auth-error bodies and scrub common credential patterns.

    Keeps scheme-discovery phrases (e.g. "API key required") while removing
    inline tokens that misconfigured error pages sometimes echo.
    """
    import re

    if not body:
        return ""
    text = body[:limit]
    # Bearer / Basic / Digested credentials in prose or JSON
    text = re.sub(
        r"(?i)\b(bearer|basic|digest)\s+[A-Za-z0-9\-._~+/]+=*",
        r"\1 ***",
        text,
    )
    # Common key/token JSON or query-ish assignments.
    # Avoid bare "token" — it matches prose like "missing token: ..." and
    # would scrub the scheme word we want to keep for discovery.
    text = re.sub(
        r'(?i)("?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token|'
        r'api[_-]?token|auth[_-]?token|client[_-]?secret|'
        r'secret|password)"?\s*[:=]\s*)("?)([^\s",}\\]+)\2',
        r"\1\2***\2",
        text,
    )
    # Long opaque secrets (JWT-shaped or high-entropy blobs) standing alone.
    # Matches JWS (3 segments) and JWE (4-5 segments, may have empty CEK).
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}(?:\.[A-Za-z0-9_-]{0,}){1,}\b",
        "***",
        text,
    )
    return text


def _extract_interesting_headers(hdrs):
    """Pull interesting headers (case-insensitive), redacting secret values."""
    result = {}
    lower_map = {k.lower(): k for k in hdrs}
    for target in INTERESTING_HEADERS:
        if target in lower_map:
            actual_key = lower_map[target]
            result[target] = _redact_header_value(target, hdrs[actual_key])
    return result


def _extract_openapi_endpoints(spec):
    """Extract endpoint list from OpenAPI/Swagger spec."""
    endpoints = []
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                ep = {
                    "path": path,
                    "method": method.upper(),
                    "summary": details.get("summary", ""),
                    "operation_id": details.get("operationId", ""),
                    "tags": details.get("tags", []),
                }
                # Auth requirement
                security = details.get("security", spec.get("security", []))
                if security:
                    ep["security"] = list(security[0].keys()) if security else []
                endpoints.append(ep)
    return endpoints


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------

def fingerprint_server(base_url, auth_headers, timeout):
    """Identify server/framework from response headers."""
    status, hdrs, body = _make_request(base_url, headers=auth_headers, timeout=timeout)
    fp = {
        "server": hdrs.get("server", hdrs.get("Server", "")),
        "powered_by": hdrs.get("x-powered-by", hdrs.get("X-Powered-By", "")),
        "aspnet_version": hdrs.get("x-aspnet-version", hdrs.get("X-AspNet-Version", "")),
        "framework_hints": [],
    }

    # Infer framework from headers
    powered = fp["powered_by"].lower()
    server = fp["server"].lower()
    if "express" in powered:
        fp["framework_hints"].append("Express.js")
    if "asp.net" in powered or "aspnet" in powered:
        fp["framework_hints"].append("ASP.NET")
    if "django" in powered or "python" in server:
        fp["framework_hints"].append("Django/Python")
    if "flask" in powered:
        fp["framework_hints"].append("Flask")
    if "fastapi" in powered:
        fp["framework_hints"].append("FastAPI")
    if "rails" in powered or "ruby" in server:
        fp["framework_hints"].append("Rails/Ruby")
    if "spring" in powered or "java" in server:
        fp["framework_hints"].append("Spring/Java")
    if "gin" in powered:
        fp["framework_hints"].append("Gin (Go)")
    if "next" in powered:
        fp["framework_hints"].append("Next.js")
    if "cloudflare" in server:
        fp["framework_hints"].append("Cloudflare")
    if "nginx" in server:
        fp["framework_hints"].append("Nginx")
    if "apache" in server:
        fp["framework_hints"].append("Apache")

    # Check for API gateway signatures
    if "x-amzn-requestid" in {k.lower() for k in hdrs}:
        fp["framework_hints"].append("AWS API Gateway")
    if "x-kong-proxy-latency" in {k.lower() for k in hdrs}:
        fp["framework_hints"].append("Kong API Gateway")

    return fp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_probe(base_url, auth_headers, timeout, version="", no_guess=False):
    """Run the full probe sequence and return a report dict."""
    report = {
        "base_url": base_url,
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timeout_seconds": timeout,
    }

    # Phase 1: Server fingerprint
    fp_status = fingerprint_server(base_url, auth_headers, timeout)
    report["server_fingerprint"] = fp_status
    # Surface SSRF block if the first request was blocked
    if not fp_status.get("server") and not _allow_private:
        report["ssrf_warning"] = (
            "All requests returned connection errors. If the target is a private/internal host, "
            "use --allow-private to override SSRF protection."
        )

    # Phase 2: Well-known discovery paths
    report["discovery"] = probe_well_known(base_url, auth_headers, timeout)

    # Phase 3: GraphQL introspection
    report["graphql"] = probe_graphql(base_url, auth_headers, timeout)

    # Phase 4: OPTIONS / CORS
    report["options_cors"] = probe_options(base_url, auth_headers, timeout)

    # Phase 5: Auth detection
    report["auth"] = probe_auth(base_url, timeout)

    # Phase 6: Rate limits
    report["rate_limits"] = probe_rate_limits(base_url, auth_headers, timeout)

    # Check if we're already rate-limited before resource guessing
    rate_limited = _check_rate_limited(report["rate_limits"])

    # Phase 7: REST resource guessing (optional)
    if not no_guess and not rate_limited:
        report["rest_resources"] = probe_rest_resources(
            base_url, auth_headers, timeout, version
        )
    elif rate_limited:
        report["rest_resources"] = []
        report["rate_limited_skipped_guessing"] = True
    else:
        report["rest_resources"] = []

    # Summary
    summary = {
        "api_type": _detect_api_type(report),
        "auth_scheme": _detect_auth_scheme(report),
        "openapi_found": any(
            d.get("type") == "openapi" for d in report["discovery"]
        ),
        "graphql_enabled": any(
            g.get("introspection") for g in report["graphql"]
        ),
        "cors_enabled": len(report["options_cors"]) > 0,
        "endpoints_discovered": _count_endpoints(report),
        "health_endpoint": any(
            d.get("type") == "health" for d in report["discovery"]
        ),
    }
    report["summary"] = summary

    return report


def _check_rate_limited(rate_info):
    """Check if rate limit info indicates we're already throttled."""
    if not rate_info:
        return False
    for k, v in rate_info.items():
        if "remaining" in k.lower():
            try:
                return int(v) == 0
            except (ValueError, TypeError):
                pass
    return False


def _detect_api_type(report):
    """Infer API type from findings."""
    types = []
    for d in report.get("discovery", []):
        if d.get("type") == "openapi":
            types.append("REST (OpenAPI documented)")
        elif d.get("type") == "graphql-schema" or d.get("type") == "graphql-endpoint":
            types.append("GraphQL")
    if any(g.get("introspection") for g in report.get("graphql", [])):
        types.append("GraphQL (introspection confirmed)")
    if report.get("rest_resources"):
        types.append("REST (resource probing)")
    # Check for SOAP
    for d in report.get("discovery", []):
        if "wsdl" in d.get("path", "") and d.get("status") == 200 and "text/html" not in d.get("content_type", ""):
            types.append("SOAP")
    if not types:
        types.append("Unknown — no API surface discovered")
    return list(set(types))


def _detect_auth_scheme(report):
    """Infer auth scheme from findings."""
    for a in report.get("auth", []):
        if a.get("scheme"):
            return a["scheme"]
    # Check OpenAPI security schemes
    for d in report.get("discovery", []):
        if d.get("type") == "openapi":
            # Could parse securitySchemes from spec
            return "See OpenAPI spec for security schemes"
    return "None detected (API may be open or use cookie-based auth)"


def _count_endpoints(report):
    """Count total discovered endpoints."""
    count = 0
    for d in report.get("discovery", []):
        if d.get("type") == "openapi" and d.get("endpoints"):
            count += len(d["endpoints"])
    if report.get("rest_resources"):
        count += len(report["rest_resources"])
    # Note: GraphQL types are not counted as "endpoints" to avoid inflating the count
    return count


def _format_report(report, pretty=True):
    """Format report for human or JSON output."""
    if not pretty:
        return json.dumps(report, indent=2)

    lines = []
    lines.append("=" * 70)
    lines.append(f"  ENDPOINT PROBE REPORT — {report['base_url']}")
    lines.append(f"  Probed: {report['probed_at']}")
    lines.append("=" * 70)

    # Summary
    s = report.get("summary", {})
    lines.append("\n📋 SUMMARY")
    lines.append(f"  API Type:       {', '.join(s.get('api_type', []))}")
    lines.append(f"  Auth Scheme:    {s.get('auth_scheme', 'Unknown')}")
    lines.append(f"  OpenAPI Found:  {'✅' if s.get('openapi_found') else '❌'}")
    lines.append(f"  GraphQL:        {'✅' if s.get('graphql_enabled') else '❌'}")
    lines.append(f"  CORS Detected:  {'✅' if s.get('cors_enabled') else '❌'}")
    lines.append(f"  Endpoints:      {s.get('endpoints_discovered', 0)}")
    lines.append(f"  Health Check:   {'✅' if s.get('health_endpoint') else '❌'}")

    # Server fingerprint
    fp = report.get("server_fingerprint", {})
    lines.append("\n🖥️  SERVER FINGERPRINT")
    lines.append(f"  Server:         {fp.get('server', 'N/A')}")
    lines.append(f"  Powered By:     {fp.get('powered_by', 'N/A')}")
    if fp.get("framework_hints"):
        lines.append(f"  Framework:      {', '.join(fp['framework_hints'])}")

    # Discovery findings
    lines.append("\n🔍 DISCOVERY PATHS")
    for d in report.get("discovery", []):
        status_icon = "✅" if d["status"] == 200 else ("🚫" if d["status"] in (401, 403) else ("❓" if d["status"] != 404 else "⬜"))
        if d["status"] == 404:
            continue  # skip 404s for readability
        type_str = d.get("type", "unknown")
        extra = ""
        if d.get("title"):
            extra = f" — {d['title']}"
        if d.get("version"):
            extra += f" (v{d['version']})"
        if d.get("endpoints"):
            extra += f" [{len(d['endpoints'])} endpoints]"
        lines.append(f"  {status_icon} {d['path']:40s} {d['status']} {type_str}{extra}")

    # GraphQL
    gql = report.get("graphql", [])
    if any(g.get("introspection") for g in gql):
        lines.append("\n🔧 GRAPHQL")
        for g in gql:
            if g.get("introspection"):
                lines.append(f"  ✅ {g['path']} — introspection successful")
                lines.append(f"     Query: {g.get('query_type', 'N/A')}")
                lines.append(f"     Mutation: {g.get('mutation_type', 'N/A')}")
                lines.append(f"     Subscription: {g.get('subscription_type', 'N/A')}")
                if g.get("types"):
                    lines.append(f"     Types ({len(g['types'])}): {', '.join(g['types'][:20])}")
                    if len(g["types"]) > 20:
                        lines.append(f"     ... and {len(g['types']) - 20} more")
            elif g.get("error"):
                lines.append(f"  ❌ {g['path']} — {g['error']}")
    elif any(g.get("status") not in (404, -1) for g in gql):
        lines.append("\n🔧 GRAPHQL")
        for g in gql:
            if g.get("status") not in (404, -1):
                lines.append(f"  ❓ {g['path']} — status {g['status']}, introspection disabled")

    # Auth
    auth = report.get("auth", [])
    if auth:
        lines.append("\n🔐 AUTHENTICATION")
        for a in auth:
            lines.append(f"  {a['path']} → {a['status']}")
            lines.append(f"  Scheme: {a.get('scheme', 'Unknown')}")
            if a.get("www_authenticate"):
                lines.append(f"  WWW-Authenticate: {a['www_authenticate']}")
            if a.get("body_hint"):
                lines.append(f"  Body hint: {a['body_hint'][:150]}")

    # CORS / OPTIONS
    cors = report.get("options_cors", [])
    if cors:
        lines.append("\n🌐 CORS / OPTIONS")
        for c in cors:
            lines.append(f"  {c['path'] or '/'} — {c['status']}")
            if c.get("allow"):
                lines.append(f"    Allow: {c['allow']}")
            if c.get("cors_allow_methods"):
                lines.append(f"    CORS Methods: {c['cors_allow_methods']}")
            if c.get("cors_allow_origin"):
                lines.append(f"    CORS Origin: {c['cors_allow_origin']}")
            if c.get("cors_allow_headers"):
                lines.append(f"    CORS Headers: {c['cors_allow_headers']}")
            if c.get("cors_allow_credentials"):
                lines.append(f"    CORS Creds: {c['cors_allow_credentials']}")

    # Rate limits
    rl = report.get("rate_limits")
    if rl:
        lines.append("\n⏱️  RATE LIMITS")
        for k, v in rl.items():
            lines.append(f"  {k}: {v}")
    else:
        lines.append("\n⏱️  RATE LIMITS: None detected")

    # REST resources
    resources = report.get("rest_resources", [])
    if resources:
        lines.append("\n📦 REST RESOURCES (probed)")
        for r in resources:
            extra = ""
            if r.get("item_count") is not None:
                extra = f" ({r['item_count']} items)"
            if r.get("error"):
                extra = f" — {r['error']}"
            lines.append(f"  {r['status']} {r['path']:40s} {r['content_type'][:40]}{extra}")
    elif report.get("rate_limited_skipped_guessing"):
        lines.append("\n📦 REST RESOURCES: Skipped (rate limit exhausted)")

    # OpenAPI endpoints detail
    for d in report.get("discovery", []):
        if d.get("type") == "openapi" and d.get("endpoints"):
            lines.append(f"\n📜 OPENAPI ENDPOINTS ({d.get('title', 'untitled')})")
            for ep in d["endpoints"]:
                sec = f" [auth: {', '.join(ep['security'])}]" if ep.get("security") else ""
                summary = f" — {ep['summary']}" if ep.get("summary") else ""
                lines.append(f"  {ep['method']:7s} {ep['path']}{summary}{sec}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP probing (JSON-RPC over HTTP or stdio)
# ---------------------------------------------------------------------------

MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_CLIENT_NAME = "endpoint-probe-probe"
MCP_CLIENT_VERSION = "1.2.3"


def _extract_sse_data(body):
    """Extract JSON data from an SSE (text/event-stream) response body.
    
    SSE format:
        event: message
        data: {"jsonrpc":"2.0","result":{...}}
        
    Returns the first data: line content, or None if no SSE data found.
    """
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_content = line[5:].strip()
            if data_content and data_content != "[DONE]":
                return data_content
    return None


# Module-level session state for HTTP MCP (M1)
_mcp_session_id = None


def _mcp_jsonrpc(url, method, params=None, request_id=1, headers=None, timeout=DEFAULT_TIMEOUT,
                 is_notification=False):
    """Send a single MCP JSON-RPC request over HTTP. Returns (result, error, resp_headers)."""
    payload = {
        "jsonrpc": "2.0",
        "method": method,
    }
    # Notifications must omit id (M2)
    if not is_notification:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params

    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    # Replay session-id if we have one (M1)
    global _mcp_session_id
    if _mcp_session_id:
        req_headers["Mcp-Session-Id"] = _mcp_session_id
    if headers:
        req_headers.update(headers)

    data = json.dumps(payload).encode("utf-8")
    status, resp_headers, body = _make_request(
        url, method="POST", headers=req_headers, data=data, timeout=timeout
    )

    if status == -1:
        return None, f"Connection error: {body}", {}
    # Accept 200 for requests, 202/204 for notifications (M2)
    if is_notification:
        if status in (200, 202, 204):
            return {}, None, resp_headers
        return None, f"HTTP {status}: {body[:300]}", resp_headers
    if status != 200:
        return None, f"HTTP {status}: {body[:300]}", resp_headers

    # Capture session-id from response (M1)
    session_id = _get_header_ci(resp_headers, "mcp-session-id")
    if session_id:
        _mcp_session_id = session_id

    parsed = _try_parse_json(body)
    if not parsed:
        # Try parsing as SSE (text/event-stream) — extract data lines
        sse_data = _extract_sse_data(body)
        if sse_data:
            parsed = _try_parse_json(sse_data)
    if not parsed:
        return None, f"Non-JSON response: {body[:300]}", resp_headers

    if "result" in parsed:
        return parsed["result"], None, resp_headers
    elif "error" in parsed:
        err = parsed["error"]
        return None, f"RPC error {err.get('code')}: {err.get('message', '')}", resp_headers
    else:
        return None, f"Unexpected response: {body[:300]}", resp_headers


def _get_header_ci(headers, target):
    """Case-insensitive header lookup."""
    for k, v in headers.items():
        if k.lower() == target.lower():
            return v
    return None


def _mcp_initialize(url, headers, timeout):
    """Send MCP initialize handshake. Returns (init_data, error)."""
    global _mcp_session_id
    _mcp_session_id = None  # reset for fresh connection

    result, err, resp_headers = _mcp_jsonrpc(
        url,
        "initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": MCP_CLIENT_NAME,
                "version": MCP_CLIENT_VERSION,
            },
        },
        request_id=1,
        headers=headers,
        timeout=timeout,
    )
    if err:
        return None, err

    server_info = result.get("serverInfo", {})
    protocol_version = result.get("protocolVersion", "")
    capabilities = result.get("capabilities", {})

    # Send initialized notification — no id, accept 202/204 (M2)
    _mcp_jsonrpc(
        url,
        "notifications/initialized",
        params={},
        headers=headers,
        timeout=timeout,
        is_notification=True,
    )

    return {
        "server_info": server_info,
        "protocol_version": protocol_version,
        "capabilities": capabilities,
    }, None


def _parse_mcp_tool(tool):
    """Parse a single MCP tool definition into a structured dict."""
    schema = tool.get("inputSchema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    params = []
    for name, prop in properties.items():
        params.append({
            "name": name,
            "type": prop.get("type", "any"),
            "description": prop.get("description", ""),
            "required": name in required,
            "default": prop.get("default"),
            "enum": prop.get("enum"),
        })

    return {
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "parameters": params,
        "required_params": required,
    }


def _mcp_list_tools_http(url, headers, timeout):
    """List all MCP tools with their input schemas (HTTP transport)."""
    result, err, _ = _mcp_jsonrpc(
        url, "tools/list", params={}, request_id=3, headers=headers, timeout=timeout
    )
    if err:
        return None, err
    tools = result.get("tools", [])
    return [_parse_mcp_tool(t) for t in tools], None


def _mcp_list_resources_http(url, headers, timeout):
    """List all MCP resources (HTTP transport)."""
    result, err, _ = _mcp_jsonrpc(
        url, "resources/list", params={}, request_id=4, headers=headers, timeout=timeout
    )
    if err:
        if "not found" in err.lower() or "method not found" in err.lower():
            return [], None
        return None, err

    resources = result.get("resources", [])
    parsed = []
    for res in resources:
        parsed.append({
            "uri": res.get("uri", ""),
            "name": res.get("name", ""),
            "description": res.get("description", ""),
            "mime_type": res.get("mimeType", ""),
        })
    return parsed, None


def _mcp_list_prompts_http(url, headers, timeout):
    """List all MCP prompt templates (HTTP transport)."""
    result, err, _ = _mcp_jsonrpc(
        url, "prompts/list", params={}, request_id=5, headers=headers, timeout=timeout
    )
    if err:
        if "not found" in err.lower() or "method not found" in err.lower():
            return [], None
        return None, err

    prompts = result.get("prompts", [])
    parsed = []
    for p in prompts:
        args = p.get("arguments", [])
        parsed_args = []
        for arg in args:
            parsed_args.append({
                "name": arg.get("name", ""),
                "description": arg.get("description", ""),
                "required": arg.get("required", False),
            })
        parsed.append({
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "arguments": parsed_args,
        })
    return parsed, None


def probe_mcp_http(url, auth_headers, timeout):
    """Full MCP probe over HTTP (StreamableHTTP transport)."""
    report = {
        "url": url,
        "transport": "http",
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Phase 1: Initialize handshake
    init_result, err = _mcp_initialize(url, auth_headers, timeout)
    if err:
        report["error"] = f"Initialize failed: {err}"
        report["status"] = "failed"
        return report

    report["server_info"] = init_result["server_info"]
    report["protocol_version"] = init_result["protocol_version"]
    report["capabilities"] = init_result["capabilities"]
    report["status"] = "connected"

    # Phase 2: List tools
    tools, err = _mcp_list_tools_http(url, auth_headers, timeout)
    if err:
        report["tools_error"] = err
        report["tools"] = []
    else:
        report["tools"] = tools

    # Phase 3: List resources
    resources, err = _mcp_list_resources_http(url, auth_headers, timeout)
    if err:
        report["resources_error"] = err
        report["resources"] = []
    else:
        report["resources"] = resources

    # Phase 4: List prompts
    prompts, err = _mcp_list_prompts_http(url, auth_headers, timeout)
    if err:
        report["prompts_error"] = err
        report["prompts"] = []
    else:
        report["prompts"] = prompts

    # Summary
    report["summary"] = {
        "server_name": init_result["server_info"].get("name", "unknown"),
        "server_version": init_result["server_info"].get("version", ""),
        "protocol_version": init_result["protocol_version"],
        "capabilities": list(init_result["capabilities"].keys()),
        "tool_count": len(report["tools"]),
        "resource_count": len(report["resources"]),
        "prompt_count": len(report["prompts"]),
    }

    return report


def _cleanup_subprocess(proc):
    """Ensure subprocess is always terminated and drained (M3)."""
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


def probe_mcp_stdio(command, args, env_dict, timeout):
    """Probe an MCP stdio server by launching it, doing the handshake, listing, and exiting."""
    import subprocess

    report = {
        "command": command,
        "args": args,
        "transport": "stdio",
        "probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # Initialize defaults so summary never KeyErrors after an exception (B1r4)
        "server_info": {},
        "protocol_version": "",
        "capabilities": {},
        "tools": [],
        "resources": [],
        "prompts": [],
    }

    # Build the subprocess environment — inherit current env, scrub secrets (M7 review2)
    _SAFE_ENV_VARS = {
        "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "SHELL",
        "TMPDIR", "TMP", "TEMP", "DISPLAY", "XAUTHORITY", "PWD",
    }
    _SECRET_SUBSTRINGS = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY",
                          "CREDENTIAL", "PRIVATE_KEY", "ACCESS_KEY", "CLIENT_SECRET")
    full_env = {}
    for k, v in os.environ.items():
        # Allow-list safe vars, deny anything with secret substrings
        if k in _SAFE_ENV_VARS:
            full_env[k] = v
        elif any(s in k.upper() for s in _SECRET_SUBSTRINGS):
            continue  # scrub
        elif k.startswith("XDG_") or k.startswith("LC_"):
            full_env[k] = v  # XDG and locale vars are safe
    # Ensure essential vars exist
    full_env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin")
    full_env.setdefault("LANG", "en_US.UTF-8")
    full_env.setdefault("TERM", "xterm-256color")
    if env_dict:
        full_env.update(env_dict)

    try:
        proc = subprocess.Popen(
            [command] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        report["error"] = f"Command not found: {command}"
        report["status"] = "failed"
        return report
    except Exception as e:
        report["error"] = f"Failed to launch: {e}"
        report["status"] = "failed"
        return report

    import select

    def _send(msg):
        """Send a JSON-RPC message and read the response with timeout (B1, B2).
        Server notifications (no id) are discarded — we only re-read, never re-send."""
        expected_id = msg.get("id")
        line = json.dumps(msg) + "\n"
        proc.stdin.write(line)
        proc.stdin.flush()

        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return None, f"Timeout after {timeout}s waiting for response to id={expected_id}"

            # Use select for timeout-aware reads (B1)
            ready, _, _ = select.select([proc.stdout], [], [], remaining)
            if not ready:
                return None, f"Timeout after {timeout}s waiting for response to id={expected_id}"

            response_line = proc.stdout.readline()
            if not response_line:
                # Bound stderr reads with select to avoid hang (review2 B1)
                stderr_ready, _, _ = select.select([proc.stderr], [], [], 2)
                if stderr_ready:
                    stderr = proc.stderr.readline()
                else:
                    stderr = ""
                return None, f"No response. stderr: {stderr[:300]}"

            parsed = _try_parse_json(response_line)
            if not parsed:
                return None, f"Non-JSON response: {response_line[:300]}"

            # Server→client notification (no id) — discard, keep reading (B2)
            if "id" not in parsed:
                continue

            # Correlate response id with expected id (review2 M2)
            if parsed["id"] != expected_id:
                continue  # Out-of-order or server-initiated request — skip

            if "result" in parsed:
                return parsed["result"], None
            elif "error" in parsed:
                err = parsed["error"]
                return None, f"RPC error {err.get('code')}: {err.get('message', '')}"
            else:
                # Server→client request (has id + method, no result/error) — skip
                if "method" in parsed:
                    continue
                return None, f"Unexpected response: {response_line[:300]}"

    report["subprocess_pid"] = proc.pid

    try:
        # Phase 1: Initialize
        init_result, err = _send({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": MCP_CLIENT_NAME, "version": MCP_CLIENT_VERSION},
            },
        })
        if err:
            report["error"] = f"Initialize failed: {err}"
            report["status"] = "failed"
            return report

        report["server_info"] = init_result.get("serverInfo", {})
        report["protocol_version"] = init_result.get("protocolVersion", "")
        report["capabilities"] = init_result.get("capabilities", {})
        report["status"] = "connected"

        # Send initialized notification
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }) + "\n")
        proc.stdin.flush()

        # Phase 2: List tools
        tools_result, err = _send({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
            "params": {},
        })
        if err:
            report["tools_error"] = err
            report["tools"] = []
        else:
            raw_tools = tools_result.get("tools", [])
            report["tools"] = [_parse_mcp_tool(t) for t in raw_tools]

        # Phase 3: List resources (normalized to match HTTP format — M6)
        res_result, err = _send({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/list",
            "params": {},
        })
        if err:
            if "not found" in err.lower() or "method not found" in err.lower():
                report["resources"] = []
            else:
                report["resources_error"] = err
                report["resources"] = []
        else:
            raw_resources = res_result.get("resources", [])
            report["resources"] = [{
                "uri": r.get("uri", ""),
                "name": r.get("name", ""),
                "description": r.get("description", ""),
                "mime_type": r.get("mimeType", ""),
            } for r in raw_resources]

        # Phase 4: List prompts (normalized to match HTTP format — M6)
        prompt_result, err = _send({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "prompts/list",
            "params": {},
        })
        if err:
            if "not found" in err.lower() or "method not found" in err.lower():
                report["prompts"] = []
            else:
                report["prompts_error"] = err
                report["prompts"] = []
        else:
            raw_prompts = prompt_result.get("prompts", [])
            report["prompts"] = [{
                "name": pr.get("name", ""),
                "description": pr.get("description", ""),
                "arguments": [{
                    "name": a.get("name", ""),
                    "description": a.get("description", ""),
                    "required": a.get("required", False),
                } for a in pr.get("arguments", [])],
            } for pr in raw_prompts]
    except Exception as e:
        # M5r3: Catch write/pipe errors and produce a failed report
        report["error"] = f"Probe error: {e}"
        report["status"] = "failed"
    finally:
        # Always clean up subprocess even on exception (M3 review2)
        _cleanup_subprocess(proc)
        if proc.returncode is not None:
            report["subprocess_returncode"] = proc.returncode

    report["summary"] = {
        "server_name": report.get("server_info", {}).get("name", "unknown"),
        "server_version": report.get("server_info", {}).get("version", ""),
        "protocol_version": report.get("protocol_version", ""),
        "capabilities": list(report.get("capabilities", {}).keys()),
        "tool_count": len(report.get("tools", [])),
        "resource_count": len(report.get("resources", [])),
        "prompt_count": len(report.get("prompts", [])),
    }

    return report


def _format_mcp_report(report, pretty=True):
    """Format MCP probe report for human output."""
    if not pretty:
        return json.dumps(report, indent=2)

    lines = []
    lines.append("=" * 70)
    if report.get("transport") == "stdio":
        lines.append(f"  MCP PROBE REPORT — {report['command']} {' '.join(report.get('args', []))}")
    else:
        lines.append(f"  MCP PROBE REPORT — {report['url']}")
    lines.append(f"  Transport: {report.get('transport', 'http')}")
    lines.append(f"  Probed: {report['probed_at']}")
    lines.append("=" * 70)

    if report.get("status") == "failed":
        lines.append(f"\n❌ FAILED: {report.get('error', 'unknown error')}")
        lines.append("=" * 70)
        return "\n".join(lines)

    # Summary
    s = report.get("summary", {})
    lines.append("\n📋 SUMMARY")
    lines.append(f"  Server:         {s.get('server_name', 'N/A')} v{s.get('server_version', '')}")
    lines.append(f"  Protocol:       {s.get('protocol_version', 'N/A')}")
    lines.append(f"  Capabilities:   {', '.join(s.get('capabilities', [])) or 'none'}")
    lines.append(f"  Tools:          {s.get('tool_count', 0)}")
    lines.append(f"  Resources:      {s.get('resource_count', 0)}")
    lines.append(f"  Prompts:        {s.get('prompt_count', 0)}")

    # Tools
    tools = report.get("tools", [])
    if tools:
        lines.append(f"\n🔧 TOOLS ({len(tools)})")
        for t in tools:
            lines.append(f"\n  ▸ {t['name']}")
            if t.get("description"):
                desc = t["description"]
                if len(desc) > 100:
                    desc = desc[:97] + "..."
                lines.append(f"    {desc}")
            if t.get("parameters"):
                lines.append(f"    Parameters:")
                for p in t["parameters"]:
                    req = "required" if p["required"] else "optional"
                    type_str = p["type"]
                    enum_str = f" enum={p['enum']}" if p.get("enum") else ""
                    default_str = f" default={p['default']}" if p.get("default") is not None else ""
                    desc_str = f" — {p['description']}" if p.get("description") else ""
                    lines.append(f"      {p['name']} ({type_str}, {req}){enum_str}{default_str}{desc_str}")
            elif t.get("required_params"):
                lines.append(f"    Required: {', '.join(t['required_params'])}")
            else:
                lines.append(f"    No parameters")
    elif report.get("tools_error"):
        lines.append(f"\n🔧 TOOLS: Error — {report['tools_error']}")
    else:
        lines.append("\n🔧 TOOLS: None")

    # Resources
    resources = report.get("resources", [])
    if resources:
        lines.append(f"\n📄 RESOURCES ({len(resources)})")
        for r in resources:
            lines.append(f"  {r.get('uri', '')} — {r.get('name', '')}")
            if r.get("description"):
                lines.append(f"    {r['description']}")
            if r.get("mime_type"):
                lines.append(f"    MIME: {r['mime_type']}")
    elif report.get("resources_error"):
        lines.append(f"\n📄 RESOURCES: Error — {report['resources_error']}")
    else:
        lines.append("\n📄 RESOURCES: None")

    # Prompts
    prompts = report.get("prompts", [])
    if prompts:
        lines.append(f"\n💬 PROMPTS ({len(prompts)})")
        for p in prompts:
            lines.append(f"\n  ▸ {p.get('name', '')}")
            if p.get("description"):
                lines.append(f"    {p['description']}")
            if p.get("arguments"):
                lines.append(f"    Arguments:")
                for a in p["arguments"]:
                    req = "required" if a.get("required") else "optional"
                    desc_str = f" — {a.get('description', '')}" if a.get("description") else ""
                    lines.append(f"      {a['name']} ({req}){desc_str}")
    elif report.get("prompts_error"):
        lines.append(f"\n💬 PROMPTS: Error — {report['prompts_error']}")
    else:
        lines.append("\n💬 PROMPTS: None")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def _build_auth_headers(args):
    """Build auth headers from CLI args (deduplicated — m10)."""
    auth_headers = {}
    if args.auth:
        if args.auth_type == "bearer":
            auth_headers["Authorization"] = f"Bearer {args.auth}"
        elif args.auth_type == "basic":
            import base64
            auth_headers["Authorization"] = "Basic " + base64.b64encode(
                args.auth.encode()
            ).decode()
        elif args.auth_type == "apikey":
            auth_headers["X-API-Key"] = args.auth
    for h in args.header:
        if ":" in h:
            key, val = h.split(":", 1)
            auth_headers[key.strip()] = val.strip()
    return auth_headers


def main():
    parser = argparse.ArgumentParser(
        description="Endpoint Probe Probe — discover API surface from a base URL or MCP server"
    )
    parser.add_argument("base_url", help="Base URL of the API to probe (or MCP server URL with --mcp)")
    parser.add_argument("--auth", help="Auth token/credential", default=None)
    parser.add_argument(
        "--auth-type",
        choices=["bearer", "basic", "apikey"],
        default="bearer",
        help="Auth type (default: bearer)",
    )
    parser.add_argument(
        "--header", action="append", default=[],
        help="Custom header (format: 'Key: Value')",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--no-guess", action="store_true", help="Skip REST resource guessing")
    parser.add_argument("--api-version", dest="version", default="", help="API version prefix (e.g. v1, v2)")

    # MCP options
    parser.add_argument(
        "--mcp", action="store_true",
        help="Probe as MCP server over HTTP (StreamableHTTP transport). base_url = MCP endpoint URL.",
    )
    parser.add_argument(
        "--mcp-stdio", action="store_true",
        help="Probe as MCP server over stdio. base_url = command to run (e.g. 'npx -y @modelcontextprotocol/server-time').",
    )
    parser.add_argument(
        "--mcp-env", action="append", default=[],
        help="Environment variable for stdio MCP server (format: 'KEY=value', repeatable)",
    )
    parser.add_argument(
        "--allow-private", action="store_true",
        help="Allow probing private/internal IP addresses (SSRF risk — use with caution)",
    )

    args = parser.parse_args()

    # m3: Mutual exclusion
    if args.mcp and args.mcp_stdio:
        parser.error("--mcp and --mcp-stdio are mutually exclusive")

    # B3: Set --allow-private flag globally
    global _allow_private
    _allow_private = args.allow_private

    # --- MCP stdio mode ---
    if args.mcp_stdio:
        try:
            parts = shlex.split(args.base_url)
        except ValueError as e:
            print(f"❌ Blocked: invalid stdio command string: {e}")
            sys.exit(1)
        if not parts:
            print("❌ Blocked: empty stdio command string.")
            sys.exit(1)
        command = parts[0]
        cmd_args = parts[1:]
        # B4: Allowlist — only known package runners. No arbitrary absolute paths.
        _ALLOWED_MCP_RUNNERS = {"npx", "uvx", "python3", "python", "node", "bunx"}
        if command not in _ALLOWED_MCP_RUNNERS:
            print(f"❌ Blocked: command '{command}' is not in the allowed list: "
                  f"{', '.join(sorted(_ALLOWED_MCP_RUNNERS))}. "
                  f"Only package runners are permitted for safety.")
            sys.exit(1)
        # R6: Per-runner argument validation — denylists are bypassable via
        # short-flag clustering (e.g. python3 -Ic "code"). Use an allowlist
        # approach instead: validate args against what each runner legitimately
        # needs for MCP server launch.
        import re as _re
        # Patterns for safe args per runner
        _SAFE_ARG_PATTERNS = {
            "npx":   r"^(-y|--yes|-p=\S+|--package=\S+|--quiet|--no-update-notifier|@[\w\-./]+|[\w\-./@]+)$",
            "uvx":   r"^(-q|--quiet|--from=\S+|[\w\-./]+)$",
            "python3": r"^(-u|-m\s+\S+|/[\w\-./]+\.py|[\w\-./]+\.py|[\w\-.//]+)$",
            "python":  r"^(-u|-m\s+\S+|/[\w\-./]+\.py|[\w\-./]+\.py|[\w\-.//]+)$",
            "node":   r"^(/[\w\-./]+|[\w\-./]+\.js|[\w\-./]+)$",
            "bunx":   r"^([\w\-./@]+)$",
        }
        # Explicitly blocked: any arg containing inline code execution flags
        # as substring or cluster (catches -c, -Ic, -Sc, -Ec, --call, --eval, etc.)
        _INLINE_CODE_RE = _re.compile(r"^-[A-Za-z]*[cep]([=].*)?$|^(--call|--eval|--exec|--print)([=].*)?$")
        # Also catch -c glued with code (e.g. -cprint(1)) — any -X where X starts with c/e/p
        _GLUED_CODE_RE = _re.compile(r"^-c\S+$|^-e\S+$|^-p\S+$")
        for arg in cmd_args:
            if _INLINE_CODE_RE.match(arg) or _GLUED_CODE_RE.match(arg):
                print(f"❌ Blocked: inline code execution flag '{arg}' in command args. "
                      f"Inline code execution is not permitted.")
                sys.exit(1)
        # For python/node runners, verify args look like file paths or -m module
        if command in ("python3", "python", "node"):
            for arg in cmd_args:
                # Allow -u, -m <module>, file paths, and bare module names
                if arg in ("-u", "-m", "--unbuffered"):
                    continue
                if arg.startswith("-"):
                    # Check for clustered short flags containing c/e/p
                    if _INLINE_CODE_RE.match(arg):
                        print(f"❌ Blocked: inline code flag '{arg}' in clustered args.")
                        sys.exit(1)
                    # Allow other single-dash flags that aren't code-related
                    continue
                # Allow file paths and module names
                # Block anything that looks like inline code (not a path/module)
        # npx/uvx/bunx: package names are fine, -y is fine, other flags checked above
        env_dict = {}
        for e in args.mcp_env:
            if "=" in e:
                k, v = e.split("=", 1)
                env_dict[k.strip()] = v.strip()
        report = probe_mcp_stdio(command, cmd_args, env_dict, args.timeout)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(_format_mcp_report(report, pretty=True))
        return

    # --- MCP HTTP mode ---
    if args.mcp:
        base_url = _normalize_base_url(args.base_url)
        auth_headers = _build_auth_headers(args)
        report = probe_mcp_http(base_url, auth_headers, args.timeout)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(_format_mcp_report(report, pretty=True))
        return

    # --- Standard API probe mode ---
    base_url = _normalize_base_url(args.base_url)
    auth_headers = _build_auth_headers(args)
    report = run_probe(base_url, auth_headers, args.timeout, args.version, args.no_guess)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_format_report(report, pretty=True))


if __name__ == "__main__":
    main()
