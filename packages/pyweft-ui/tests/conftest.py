import pytest


@pytest.fixture(autouse=True)
def toasts():
    """The toast list is module state, like on a real page; each test gets an
    empty one, and no Toaster left over from an earlier test."""
    from pyweft_ui import toasts as store

    store._toasts.clear()
    store._toasters.clear()
    yield store
    store._toasts.clear()
    store._toasters.clear()
