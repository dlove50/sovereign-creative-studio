import httpx
import pytest

from app.services import brand_spec


def test_redirect_is_checked_before_request(monkeypatch):
    requested = []
    def resolve(host, port):
        address = "127.0.0.1" if host == "localhost" else "93.184.216.34"
        return [(2, 1, 6, "", (address, port))]
    monkeypatch.setattr(brand_spec.socket, "getaddrinfo", resolve)
    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://localhost/private"})
    real_client = httpx.Client
    monkeypatch.setattr(brand_spec.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ValueError, match="Only public"):
        brand_spec._fetch("https://example.com/start", 100)
    assert requested == ["https://example.com/start"]


def test_relative_redirect_and_size_limit(monkeypatch):
    monkeypatch.setattr(brand_spec, "assert_public_url", lambda url: url)
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, content=b"hello")
    real_client = httpx.Client
    monkeypatch.setattr(brand_spec.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    response = brand_spec._fetch("https://example.com/start", 5)
    assert response.content == b"hello"
    assert str(response.request.url) == "https://example.com/final"
    with pytest.raises(ValueError, match="too large"):
        brand_spec._fetch("https://example.com/start", 4)
