"""Bound proxy outages while retaining a direct portal transport fallback."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

_unavailable_until: dict[str, float] = {}
PROXY_COOLDOWN_SECONDS = 300


def available_endpoints(proxies, direct_url):
    active = [(label, url) for label, url in proxies
              if proxy_available(url)]
    return [*active, ("direct", direct_url)]


def proxy_available(url):
    return _unavailable_until.get(urlsplit(url).netloc, 0) <= time.monotonic()


def proxy_unavailable(url):
    # Store only the host, never query parameters containing credentials.
    _unavailable_until[urlsplit(url).netloc] = time.monotonic() + PROXY_COOLDOWN_SECONDS


def request_timeout(label, timeout):
    return (min(5.0, timeout), timeout) if label.startswith("cz_proxy") else timeout
