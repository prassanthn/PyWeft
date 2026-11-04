"""Progress: bar and circle, determinate and not."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def bar(tree):
    return find(tree, lambda n: n.attrs.get("role") == "progressbar")


CODE = "sent: int = 40\nsize: int = 200\nfiles: int = 4\n"


def test_bar_with_label_value_and_aria(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Progress label="Uploading" :value="sent" :max="size" show_value="true" /></div>', CODE)
    pb = bar(tree)
    assert (pb.attrs["aria-valuemin"], pb.attrs["aria-valuemax"], pb.attrs["aria-valuenow"]) == ("0", "200", "40")
    assert pb.attrs["aria-valuetext"] == "20%" and "aria-busy" not in pb.attrs
    assert pb.attrs["aria-labelledby"] == find(tree, cls("label")).attrs["id"]
    assert text([find(tree, cls("value"))]) == "20%"
    assert find(tree, cls("fill")).attrs["style"] == "width: 20.0%"
    a.sent = 250                                              # clamped to the end
    tree = cycle(r, tree)
    assert find(tree, cls("fill")).attrs["style"] == "width: 100.0%" and bar(tree).attrs["aria-valuetext"] == "100%"


def test_format_fractions_and_hidden_value(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Progress :value="files" max="12" format="{} of 12 files" show_value="true" />'
                                  '<ui.Progress :value="0.25" max="1" aria_label="Sync" /></div>', CODE)
    first, second = [n for n in tree[0].children]
    assert text([find([first], cls("value"))]) == "4 of 12 files"
    assert bar([first]).attrs["aria-valuetext"] == "4 of 12 files" and bar([first]).attrs["aria-valuemax"] == "12"
    assert find([second], cls("value")) is None and find([second], cls("top")) is None
    assert bar([second]).attrs["aria-label"] == "Sync" and bar([second]).attrs["aria-valuenow"] == "0.25"
    assert find([second], cls("fill")).attrs["style"] == "width: 25.0%"


def test_indeterminate_and_buffer(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Progress label="Loading" show_value="true" />'
                                  '<ui.Progress :value="40" :buffer="70" kind="success" size="lg" striped="true" /></div>')
    busy, buffered = tree[0].children
    pb = bar([busy])
    assert pb.attrs["aria-busy"] == "true" and "aria-valuenow" not in pb.attrs and "aria-valuetext" not in pb.attrs
    assert "busy" in busy.attrs["class"] and "style" not in find([busy], cls("fill")).attrs
    assert find([busy], cls("value")) is None
    assert find([buffered], cls("buffer")).attrs["style"] == "width: 70.0%"
    assert all(c in buffered.attrs["class"] for c in ("kind-success", "size-lg", "striped"))


def test_circle(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Progress shape="circle" :value="72" label="Storage" />'
                                  '<ui.Progress shape="circle" :value="72" size="sm" />'
                                  '<ui.Progress shape="circle" /></div>')
    big, small, busy = tree[0].children
    ring = bar([big])
    assert "ring" in ring.attrs["class"] and ring.attrs["aria-valuetext"] == "72%"
    assert text([find([big], cls("ring-value"))]) == "72%" and text([find([big], cls("label"))]) == "Storage"
    arc = find([big], cls("ring-fill"))
    circumference = float(arc.attrs["stroke-dasharray"])
    assert abs(float(arc.attrs["stroke-dashoffset"]) - circumference * 0.28) < 0.02
    assert find([small], cls("ring-value")) is None                # too small for text
    assert bar([busy]).attrs["aria-busy"] == "true" and "stroke-dashoffset" not in find([busy], cls("ring-fill")).attrs
    assert " " in find([busy], cls("ring-fill")).attrs["stroke-dasharray"]   # a short arc that turns
