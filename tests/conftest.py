import pytest


@pytest.fixture(autouse=True)
def no_pypi(monkeypatch):
    """Tests never ask the real PyPI: a test that wants answers passes its
    own fetch, and anything else gets a network error (a warning)."""
    from pyweft import browser_deps

    def offline(url):
        raise OSError("the network is off in tests")

    monkeypatch.setattr(browser_deps, "fetch_json", offline)
