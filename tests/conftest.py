import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch, request):
    if request.node.path.name == "test_providers.py":
        return

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("network disabled in tests")

    monkeypatch.setattr("httpx.Client.send", _blocked)
