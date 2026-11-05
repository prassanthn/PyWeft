"""<Window> and <Document>: event handlers on the window or document,
rendered as hidden placeholders whose listeners the runtime moves there."""

import pytest

from pyweft import Renderer, TemplateError
from pyweft.component import component_from_source
from pyweft.parser import parse_template


def test_window_becomes_a_hidden_placeholder_with_its_events():
    (div,) = parse_template('<div><Window @keydown.ctrl.k.prevent="search" @scroll="moved" /><p>x</p></div>')
    win = div.children[0]
    assert win.tag == "pyweft-window" and set(win.attrs) == {"hidden"}
    assert win.events == {"keydown.ctrl.k.prevent": "search", "scroll": "moved"}
    (doc,) = parse_template('<Document @visibilitychange="paused(event)" />')
    assert doc.tag == "pyweft-document"


@pytest.mark.parametrize("src, message", [
    ('<Window @keydown="a"><p>x</p></Window>', "takes no content"),
    ('<Window class="x" @keydown="a" />', "only event handlers"),
    ("<Window />", "needs an event handler"),
])
def test_window_takes_only_handlers(src, message):
    with pytest.raises(TemplateError, match=message):
        parse_template(src)


def test_handlers_dispatch_and_go_with_their_component():
    App = component_from_source("""<template><div>
  <If cond="listening"><Window @keydown.esc="presses += 1" /></If>
</div></template>
<code>
listening: bool = True
presses: int = 0
</code>""")
    app = App()
    r = Renderer(app)
    (div,) = r.render()
    win = div.children[0]
    r.dispatch(win.events["keydown.esc"], {"type": "keydown", "key": "Escape"})
    assert app.presses == 1
    app.listening = False
    (div,) = r.render()
    assert div.children == []                                 # the runtime then drops the listener
    r.dispatch(win.events["keydown.esc"], {"type": "keydown"})  # a late event: no-op
    assert app.presses == 1
