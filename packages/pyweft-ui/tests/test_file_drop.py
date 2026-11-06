"""ui.FileDrop: dropped and chosen files, accepted or turned away."""

import base64

from pyweft import Renderer, component_from_source
from pyweft.vdom import Element


def encoded(name, data, kind=""):
    return {"name": name, "type": kind, "size": len(data), "data": base64.b64encode(data).decode()}


def drop_zone(**props):

    app = component_from_source(
        "<template><div><ui.FileDrop :accept='accept' :max_mb='max_mb' :multiple='multiple' "
        "@files='got.extend(event)' @reject='rejected.extend(event)' /></div></template>"
        "<code>\nfrom pyweft_ui import ui\naccept = ''\nmax_mb: float = 0\nmultiple: bool = True\n"
        "got: list = []\nrejected: list = []\n</code>",
        "App",
    )(**props)
    r = Renderer(app)
    r.init_root()
    r.render()
    (drop,) = [c for c in r.instances.values() if type(c).__name__ == "FileDrop"]
    return app, r, drop


def zone_events(r):
    found = {}

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if "zone" in n.attrs.get("class", ""):
                    found.update(n.events)
                    found["_class"] = n.attrs["class"]
                walk(n.children)
    walk(r._tree)
    return found


def test_file_drop_accepts_and_rejects():
    app, r, _ = drop_zone(accept="csv, txt", max_mb=0.001)
    events = zone_events(r)
    payload = {"type": "drop", "files": [
        encoded("ok.csv", b"a,b"), encoded("big.txt", b"x" * 2000), encoded("tool.exe", b"MZ"),
    ]}
    r.dispatch(events["drop.prevent"], payload)
    assert [f.name for f in app.got] == ["ok.csv"]
    assert app.rejected == [("big.txt", "over 0.001 MB"), ("tool.exe", "not one of csv, txt")]
    r.render()
    text = repr(r._tree)
    assert "big.txt: over 0.001 MB; tool.exe: not one of csv, txt" in text


def test_file_drop_one_file_and_highlight():
    app, r, drop = drop_zone(multiple=False)
    events = zone_events(r)
    r.dispatch(events["dragenter.prevent"], {"type": "dragenter", "kinds": ["Files"]})
    r.render()
    assert "over" in zone_events(r)["_class"]
    r.dispatch(events["dragenter.prevent"], {"type": "dragenter", "kinds": ["Files"]})  # a child
    r.dispatch(events["dragleave"], {"type": "dragleave"})
    r.render()
    assert "over" in zone_events(r)["_class"]  # still inside
    r.dispatch(events["dragleave"], {"type": "dragleave"})
    r.render()
    assert "over" not in zone_events(r)["_class"]
    r.dispatch(events["dragenter.prevent"], {"type": "dragenter", "kinds": ["text/plain"]})
    r.render()
    assert "over" not in zone_events(r)["_class"]  # text being dragged: not for us
    r.dispatch(events["drop.prevent"], {"type": "drop", "files": [encoded("a.txt", b"1"), encoded("b.txt", b"2")]})
    assert [f.name for f in app.got] == ["a.txt"]
    assert app.rejected == [("b.txt", "only one file at a time")]
    assert drop.default_hint == "one file"


def test_file_drop_choose_uses_dialogs():
    import asyncio

    from pyweft import dialogs

    class Picker:
        asked = None

        async def open(self, types, multiple):
            Picker.asked = (types, multiple)
            return [("data.csv", b"1,2", None), ("photo.jpg", b"\xff", None)]

    dialogs.set_host(Picker())
    try:
        async def main():
            app, r, _ = drop_zone(accept="csv")
            button = [n for n in _walk(r._tree) if n.tag == "button"][0]
            r.dispatch(button.events["click"], {"type": "click"})
            await r.idle()
            return app
        app = asyncio.run(main())
        assert Picker.asked == (["csv"], True)
        assert [f.name for f in app.got] == ["data.csv"]
        assert app.rejected == [("photo.jpg", "not one of csv")]
    finally:
        dialogs.set_host(dialogs._NoHost())


def _walk(nodes):
    for n in nodes:
        if isinstance(n, Element):
            yield n
            yield from _walk(n.children)
