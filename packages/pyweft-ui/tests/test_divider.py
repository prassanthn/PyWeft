"""Divider: plain, inset, labelled, vertical."""

from test_controls import app, cls, find, text


def dividers(tree):
    out = []

    def walk(nodes):
        for n in nodes:
            if hasattr(n, "attrs"):
                if "divider" in n.attrs.get("class", "").split():
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def test_plain_and_inset(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Divider /><ui.Divider inset="true" spacing="lg" />'
                                  '<ui.Divider inset="3rem" /><ui.Divider inset="false" spacing="none" /></div>')
    plain, inset, custom, off = dividers(tree)
    assert plain.attrs["role"] == "separator" and "aria-orientation" not in plain.attrs
    assert plain.attrs["class"] == "divider horizontal space-md" and "style" not in plain.attrs
    assert inset.attrs["style"] == "margin-left: 4.5rem" and "space-lg" in inset.attrs["class"]
    assert custom.attrs["style"] == "margin-left: 3rem"
    assert "style" not in off.attrs and "space-none" in off.attrs["class"]
    assert all(d.children == [] for d in dividers(tree))


def test_labelled_is_text_not_a_separator(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Divider label="or" /><ui.Divider label="Today" align="start" /></div>')
    middle, start = dividers(tree)
    assert "role" not in middle.attrs and text([find([middle], cls("text"))]) == "or"
    assert "labelled" in middle.attrs["class"] and "align-center" in middle.attrs["class"]
    assert "align-start" in start.attrs["class"]
    assert len([c for c in middle.children if "line" in c.attrs.get("class", "")]) == 2


def test_vertical_ignores_label_and_inset(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Divider vertical="true" label="x" inset="true" class="mine" /></div>')
    (d,) = dividers(tree)
    assert d.attrs["role"] == "separator" and d.attrs["aria-orientation"] == "vertical"
    assert "vertical" in d.attrs["class"] and "mine" in d.attrs["class"] and "style" not in d.attrs
    assert d.children == []
