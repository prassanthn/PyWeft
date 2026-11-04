"""Slider: one value, or a (low, high) range."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def ranges(tree):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if n.tag == "input" and n.attrs.get("type") == "range":
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def move(r, tree, which, value, kind="input"):
    r.dispatch(ranges(tree)[which].events[kind], {"type": kind, "value": str(value)})
    return cycle(r, tree)


CODE = "volume: int = 30\nlevel: float = 0.5\nprice: tuple = (100, 400)\nchanges: list = []\nblurs: list = []\n"


def test_single_value_binds_an_int(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider label="Volume" @bind="volume" @change="changes.append(event)" /></div>', CODE)
    (thumb,) = ranges(tree)
    assert (thumb.attrs["min"], thumb.attrs["max"], thumb.attrs["step"], thumb.attrs["value"]) == ("0", "100", "1", "30")
    assert thumb.attrs["aria-label"] == "Volume" and thumb.attrs["aria-valuetext"] == "30"
    tree = move(r, tree, 0, "42")
    assert a.volume == 42 and type(a.volume) is int and a.changes == []
    tree = move(r, tree, 0, "43", "change")
    assert a.volume == 43 and a.changes == [43]
    assert ranges(tree)[0].attrs["value"] == "43"
    assert "--hi: 43" in find(tree, cls("slider")).attrs["style"]


def test_fractional_step_gives_floats_on_the_step(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider :min="0" :max="1" :step="0.1" @bind="level" /></div>', CODE)
    tree = move(r, tree, 0, "0.30000000000000004")
    assert a.level == 0.3 and type(a.level) is float
    tree = move(r, tree, 0, "7")
    assert a.level == 1.0


def test_value_outside_is_shown_clamped_and_snapped(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider :min="0" :max="50" :step="5" :value="73" /><ui.Slider :step="5" :value="12" /></div>')
    assert [t.attrs["value"] for t in ranges(tree)] == ["50", "10"]


def test_range_binds_an_ordered_pair_and_thumbs_pass(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider label="Price" :min="0" :max="500" :step="10" range="true" '
                                  'name="price" @bind="price" /></div>', CODE)
    lo, hi = ranges(tree)
    assert (lo.attrs["value"], hi.attrs["value"]) == ("100", "400")
    assert (lo.attrs["name"], hi.attrs["name"]) == ("price_min", "price_max")
    assert (lo.attrs["aria-label"], hi.attrs["aria-label"]) == ("Price, minimum", "Price, maximum")
    style = find(tree, cls("slider")).attrs["style"]
    assert "--lo: 20" in style and "--hi: 80" in style
    tree = move(r, tree, 1, "250")
    assert a.price == (100, 250)
    # The low thumb dragged past the high one: each input keeps its own
    # place (the browser has it there anyway) and the value stays ordered.
    tree = move(r, tree, 0, "300")
    assert a.price == (250, 300)
    lo, hi = ranges(tree)
    assert (lo.attrs["value"], hi.attrs["value"]) == ("300", "250")
    assert (lo.attrs["aria-label"], hi.attrs["aria-label"]) == ("Price, maximum", "Price, minimum")
    tree = move(r, tree, 1, "400")
    assert a.price == (300, 400)


def test_range_without_a_value_spans_everything(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider range="true" :value="None" /></div>')
    assert [t.attrs["value"] for t in ranges(tree)] == ["0", "100"]


def test_lazy_updates_on_release_only(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider lazy="true" value_label="side" label="V" @bind="volume" /></div>', CODE)
    tree = move(r, tree, 0, "70")
    assert a.volume == 30
    assert text([find(tree, cls("side"))]) == "70"
    tree = move(r, tree, 0, "71", "change")
    assert a.volume == 71


def test_format_bubbles_and_valuetext(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider range="true" format="${}" value_label="always" @bind="price" :max="500" /></div>', CODE)
    assert "bubbles" in find(tree, cls("slider")).attrs["class"]
    assert text([find(tree, cls("b-lo"))]) == "$100" and text([find(tree, cls("b-hi"))]) == "$400"
    assert [t.attrs["aria-valuetext"] for t in ranges(tree)] == ["$100", "$400"]
    _, a, r, tree = app(tmp_path, '<div><ui.Slider value_label="none" @bind="volume" /></div>', CODE)
    assert find(tree, cls("bubble")) is None


def test_ticks_and_marks(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider :max="10" :step="2.5" ticks="true" :value="5" '
                                  'marks="0, 5, 10" /><ui.Slider :marks="[(0, \'Low\'), (100, \'High\')]" /></div>')
    sliders = [n for n in tree[0].children]
    ticks = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if "tick" in n.attrs.get("class", "").split():
                    ticks.append(n)
                walk(n.children)

    walk([sliders[0]])
    assert [t.attrs["style"] for t in ticks] == [f"left: {p}%" for p in (0.0, 25.0, 50.0, 75.0, 100.0)]
    assert ["on" in t.attrs["class"] for t in ticks] == [True, True, True, False, False]
    marks = [text([m]) for m in sliders[0].children[-1].children]
    assert marks == ["0", "5", "10"]
    assert [text([m]) for m in sliders[1].children[-1].children] == ["Low", "High"]


def test_disabled_error_hint_and_blur(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Slider label="V" disabled="true" hint="h" error="Too loud" '
                                  '@bind="volume" @blur="blurs.append(event)" /></div>', CODE)
    (thumb,) = ranges(tree)
    assert "disabled" in thumb.attrs and thumb.attrs["aria-invalid"] == "true"
    assert text([find(tree, cls("error"))]) == "Too loud" and find(tree, cls("hint")) is None
    r.dispatch(thumb.events["blur"], {"type": "blur"})
    assert a.blurs == [30]


def test_works_with_form(tmp_path):
    code = ("from pyweft_ui import Form\nfrom pyweft_ui import rules\n"
            "volume: int = 0\nform = Form(volume=lambda v: None if v >= 10 else 'At least 10')\n")
    _, a, r, tree = app(tmp_path, '<div><ui.Slider ref="volume" label="V" @bind="volume" :error="form.error(\'volume\')" '
                                  '@blur="form.touch(\'volume\')" /></div>', code)
    assert find(tree, cls("error")) is None
    r.dispatch(ranges(tree)[0].events["blur"], {"type": "blur"})
    tree = cycle(r, tree)
    assert text([find(tree, cls("error"))]) == "At least 10"
    tree = move(r, tree, 0, "20")
    assert find(tree, cls("error")) is None
