"""Keep preparation working through proxy outages without bypassing rate limits."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import source_transport as transport
import resolve_stream as resolver
import prehrajto_search as search

DETAIL = "https://prehraj.to/example/abcdef123456"
PROXY = "https://proxy.test/?key=private-key"


@pytest.fixture(autouse=True)
def isolated_transport(monkeypatch):
    monkeypatch.setattr(transport, "_unavailable_until", {})
    monkeypatch.setattr(resolver, "_rate_limit_until", 0)
    monkeypatch.setattr(resolver, "RESOLVE_MIN_GAP", 0)
    monkeypatch.setattr(search, "_last_search_at", 0)
    monkeypatch.setattr(search.time, "sleep", lambda _: None)
    monkeypatch.setattr(resolver, "_cz_proxy_fetch_urls", lambda _: [("cz_proxy_1", PROXY)])
    monkeypatch.setattr(search, "_proxy_fetch_urls", lambda _: [("cz_proxy_1", PROXY)])


def response(status=200, text="", url=DETAIL):
    value = requests.Response()
    value.status_code = status
    value._content = text.encode()
    value.url = url
    return value


@pytest.mark.parametrize("failure", ["timeout", "unavailable"])
def test_resolver_recovers_then_skips_failed_proxy_across_modules(monkeypatch, failure):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if url == PROXY:
            assert kwargs["timeout"][0] <= 5
            if failure == "timeout":
                raise requests.ConnectTimeout("private-key")
            return response(503)
        return response(text="valid player")
    session = SimpleNamespace(headers={}, get=get)
    monkeypatch.setattr(resolver, "parse_html", lambda *a, **kw: kw["fetch_via"])
    assert resolver.resolve(DETAIL, session=session, max_retries=0) == "direct"
    assert resolver.resolve(DETAIL, session=session, max_retries=0) == "direct"
    assert search.search_pages("Example", session=session, retries=1) == [[]]
    assert calls.count(PROXY) == 1
    assert all("private" not in host for host in transport._unavailable_until)


def test_second_proxy_is_tried_before_direct(monkeypatch):
    monkeypatch.setattr(resolver, "_cz_proxy_fetch_urls", lambda _: [
        ("cz_proxy_1", PROXY), ("cz_proxy_2", "https://backup.test/")])
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if url == PROXY:
            raise requests.ConnectTimeout("private-key")
        return response(text="valid")
    monkeypatch.setattr(resolver, "parse_html", lambda *a, **kw: kw["fetch_via"])
    assert resolver.resolve(DETAIL, session=SimpleNamespace(headers={}, get=get), max_retries=0) == "cz_proxy_2"
    assert calls == [PROXY, "https://backup.test/"]


@pytest.mark.parametrize("target", [resolver, search])
def test_rate_limit_never_uses_another_transport(monkeypatch, target):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        value = response(429)
        value.headers["Retry-After"] = "120"
        return value
    session = SimpleNamespace(headers={}, get=get)
    with pytest.raises((resolver.ProxyUnavailableError, requests.HTTPError)):
        if target is resolver:
            resolver.resolve(DETAIL, session=session, max_retries=0)
        else:
            search.search_pages("Example", session=session, retries=3)
    assert calls == [PROXY]


def test_cooldown_expires_and_does_not_store_credentials(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(transport.time, "monotonic", lambda: clock[0])
    transport.proxy_unavailable(PROXY)
    assert transport.available_endpoints([("cz_proxy_1", PROXY)], DETAIL) == [("direct", DETAIL)]
    clock[0] += 301
    assert len(transport.available_endpoints([("cz_proxy_1", PROXY)], DETAIL)) == 2
    assert list(transport._unavailable_until) == ["proxy.test"]


@pytest.mark.parametrize("status,body", [(404, "missing"), (502, "Upstream NotFound")])
def test_explicit_missing_source_does_not_try_direct(status, body):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return response(status, body)
    with pytest.raises(resolver.ResolveError) as error:
        resolver.resolve(DETAIL, session=SimpleNamespace(headers={}, get=get), max_retries=0)
    assert error.value.permanent
    assert calls == [PROXY]


def test_challenge_page_after_proxy_outage_does_not_burn_source():
    def get(url, **kwargs):
        if url == PROXY:
            raise requests.ConnectTimeout("private-key")
        return response(text="Please verify your browser")
    with pytest.raises(resolver.ProxyUnavailableError) as error:
        resolver.resolve(DETAIL, session=SimpleNamespace(headers={}, get=get), max_retries=0)
    assert not error.value.permanent
    assert "private-key" not in str(error.value)


def test_search_transport_exception_reaches_next_endpoint():
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if url == PROXY:
            raise requests.ConnectTimeout("private-key")
        return response(text='''<div class="video-wrapper"><a class="video--link"
            href="/example/abcdef123456" title="Example S01E01">episode</a></div>''')
    pages = search.search_pages("Example S01E01", session=SimpleNamespace(get=get), retries=1)
    assert pages[0][0].external_id == "abcdef123456"
    assert len(calls) == 2
