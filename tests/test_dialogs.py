"""pyweft.dialogs: the calls apps make, and the desktop host behind them."""

import asyncio

import pytest

from pyweft import dialogs
from pyweft.dialogs import PickedFile


class FakeHost:
    def __init__(self, chosen=(), saved=True, answer=True):
        self.chosen, self.saved, self.answer = list(chosen), saved, answer
        self.calls = []

    async def open(self, types, multiple):
        self.calls.append(("open", types, multiple))
        return self.chosen

    async def save(self, name, data, types):
        self.calls.append(("save", name, data, types))
        return self.saved

    async def confirm(self, message, title):
        self.calls.append(("confirm", message, title))
        return self.answer


@pytest.fixture
def host():
    def install(**kw):
        fake = FakeHost(**kw)
        dialogs.set_host(fake)
        return fake

    yield install
    dialogs.set_host(dialogs._NoHost())


def test_open_file_returns_the_file_or_none(host):
    fake = host(chosen=[("a.csv", b"x,y\n1,2", "C:/a.csv")])
    file = asyncio.run(dialogs.open_file(types=["CSV", ".txt", "*.tsv"]))
    assert file == PickedFile("a.csv", b"x,y\n1,2", "C:/a.csv") and file.text == "x,y\n1,2"
    assert fake.calls == [("open", ["csv", "txt", "tsv"], False)]
    host(chosen=[])
    assert asyncio.run(dialogs.open_file()) is None


def test_open_files_returns_a_list(host):
    fake = host(chosen=[("a", b"1", None), ("b", b"2", None)])
    files = asyncio.run(dialogs.open_files())
    assert [f.name for f in files] == ["a", "b"] and fake.calls[0][2] is True


def test_save_file_encodes_text_and_infers_the_type(host):
    fake = host(saved=False)
    assert asyncio.run(dialogs.save_file("héllo", name="notes.txt")) is False
    assert fake.calls == [("save", "notes.txt", "héllo".encode(), ["txt"])]
    asyncio.run(dialogs.save_file(b"\x00", name="blob"))
    assert fake.calls[-1] == ("save", "blob", b"\x00", [])


def test_confirm(host):
    fake = host(answer=False)
    assert asyncio.run(dialogs.confirm("Delete?", title="Orders")) is False
    assert fake.calls == [("confirm", "Delete?", "Orders")]


def test_bad_file_types_are_errors(host):
    host()
    with pytest.raises(ValueError, match="extensions like 'csv'"):
        asyncio.run(dialogs.open_file(types=["text/csv"]))


def test_without_a_host_the_error_says_where_dialogs_work():
    with pytest.raises(RuntimeError, match="in the browser and in a desktop window"):
        asyncio.run(dialogs.confirm("x"))


def test_mime_type():
    assert dialogs.mime_type("a.csv") in ("text/csv", "application/vnd.ms-excel")
    assert dialogs.mime_type("a.unknownext") == "application/octet-stream"


# ------------------------------------------------------------- desktop host


def test_the_desktop_host_uses_the_native_dialogs(tmp_path):
    webview = pytest.importorskip("webview")
    from pyweft.desktop import _Dialogs

    source = tmp_path / "in.csv"
    source.write_bytes(b"1,2")
    target = tmp_path / "out.csv"

    class Window:
        def __init__(self):
            self.calls = []

        def create_file_dialog(self, kind, **kw):
            self.calls.append((kind, kw))
            return (str(source),) if kind == webview.FileDialog.OPEN else str(target)

        def create_confirmation_dialog(self, title, message):
            self.calls.append(("confirm", title, message))
            return True

    window = Window()
    host = _Dialogs(type("App", (), {"window": window})())

    async def main():
        opened = await host.open(["csv"], False)
        saved = await host.save("out.csv", b"x", ["csv"])
        answer = await host.confirm("Sure?", "")
        return opened, saved, answer

    opened, saved, answer = asyncio.run(main())
    assert opened == [("in.csv", b"1,2", str(source))]
    assert saved is True and target.read_bytes() == b"x" and answer is True
    open_call, save_call, confirm_call = window.calls
    assert open_call[1]["file_types"] == ("CSV files (*.csv)", "All files (*.*)")
    assert save_call[1]["save_filename"] == "out.csv"
    assert confirm_call == ("confirm", "Confirm", "Sure?")


def test_a_cancelled_desktop_dialog(tmp_path):
    pytest.importorskip("webview")
    from pyweft.desktop import _Dialogs

    class Window:
        def create_file_dialog(self, kind, **kw):
            return None

    host = _Dialogs(type("App", (), {"window": Window()})())
    assert asyncio.run(host.open([], True)) == []
    assert asyncio.run(host.save("x.txt", b"", [])) is False
