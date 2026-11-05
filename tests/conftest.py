import httpx
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    if request.node.path.name == "test_providers.py":
        return
    original = httpx.Client.send

    def _blocked(self, request, *args, **kwargs):
        host = request.url.host
        if host in {"127.0.0.1", "localhost"} or isinstance(getattr(self, "_transport", None), httpx.MockTransport):
            return original(self, request, *args, **kwargs)
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr(httpx.Client, "send", _blocked)
