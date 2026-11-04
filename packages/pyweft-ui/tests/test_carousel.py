"""Carousel: slides, arrows, dots, swipe, loop, several per view, autoplay."""

import asyncio

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def every(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def slides(tree):
    return every(tree, cls("slide"))


def shown(tree):
    return [text([s]).strip() for s in slides(tree) if "inert" not in s.attrs]


def press(r, tree, name, payload=None):
    r.dispatch(find(tree, cls(name)).events["click"], payload or {})
    return cycle(r, tree)


CODE = "at: int = 0\nchanges: list = []\nPHOTOS = ['A', 'B', 'C', 'D', 'E']\n"
ONE = ('<div><ui.Carousel label="Photos" :items="PHOTOS" @bind="at" @change="changes.append(event)" {extra}>'
       '<Fill name="slide"><p class="pic">{{ slide }}{{ index }}{{ "*" if active else "" }}</p></Fill>'
       '</ui.Carousel></div>')


def carousel(tmp_path, extra="", code=CODE):
    return app(tmp_path, ONE.replace("{extra}", extra), code)


def test_slides_aria_and_arrows(tmp_path):
    _, a, r, tree = carousel(tmp_path)
    root = find(tree, cls("carousel"))
    assert root.attrs["aria-roledescription"] == "carousel" and root.attrs["aria-label"] == "Photos"
    assert [s.attrs["aria-label"] for s in slides(tree)] == [f"{i} of 5" for i in range(1, 6)]
    assert all(s.attrs["aria-roledescription"] == "slide" for s in slides(tree))
    assert shown(tree) == ["A0*"]
    assert "disabled" in find(tree, cls("prev")).attrs and "disabled" not in find(tree, cls("next")).attrs
    tree = press(r, tree, "next")
    assert a.at == 1 and a.changes == [1] and shown(tree) == ["B1*"]
    assert find(tree, cls("track")).attrs["style"] == "--at: 1"
    tree = press(r, tree, "prev")
    assert a.at == 0 and a.changes == [1, 0]


def test_dots_jump_and_mark_the_current(tmp_path):
    _, a, r, tree = carousel(tmp_path)
    dots = every(tree, cls("dot"))
    assert len(dots) == 5 and dots[0].attrs["aria-current"] == "true" and dots[0].attrs["tabindex"] == "0"
    assert dots[3].attrs["aria-label"] == "Slide 4" and "aria-current" not in dots[3].attrs
    r.dispatch(dots[3].events["click"], {})
    tree = cycle(r, tree)
    assert a.at == 3 and every(tree, cls("dot"))[3].attrs["aria-current"] == "true"
    group = find(tree, cls("dots"))
    r.dispatch(group.events["keydown.right.prevent"], {})
    tree = cycle(r, tree)
    assert a.at == 4
    r.after_render()
    assert [c["op"] for c in r.take_commands()] == ["focus"]
    r.dispatch(find(tree, cls("dots")).events["keydown.right.prevent"], {})   # the end, no loop
    tree = cycle(r, tree)
    assert a.at == 4 and "disabled" in find(tree, cls("next")).attrs


def test_loop_wraps(tmp_path):
    _, a, r, tree = carousel(tmp_path, 'loop="true"')
    assert "disabled" not in find(tree, cls("prev")).attrs
    tree = press(r, tree, "prev")
    assert a.at == 4
    tree = press(r, tree, "next")
    assert a.at == 0


def test_swipe_decided_on_release(tmp_path):
    _, a, r, tree = carousel(tmp_path)
    view = find(tree, cls("viewport"))
    root = find(tree, cls("carousel"))
    assert "touch-action" not in view.attrs   # (CSS, not an attribute)
    r.dispatch(view.events["pointerdown"], {"clientX": 300})
    r.dispatch(root.events["pointerup"], {"clientX": 280})          # too short
    tree = cycle(r, tree)
    assert a.at == 0
    r.dispatch(view.events["pointerdown"], {"clientX": 300})
    r.dispatch(root.events["pointerup"], {"clientX": 200})          # left: next
    tree = cycle(r, tree)
    assert a.at == 1
    r.dispatch(find(tree, cls("viewport")).events["pointerdown"], {"clientX": 100})
    r.dispatch(find(tree, cls("carousel")).events["pointerup"], {"clientX": 250})   # right: previous
    tree = cycle(r, tree)
    assert a.at == 0
    r.dispatch(find(tree, cls("carousel")).events["pointerup"], {"clientX": 0})   # no grab: nothing
    assert a.at == 0


def test_several_per_view(tmp_path):
    _, a, r, tree = carousel(tmp_path, 'per_view="3" gap="12px"')
    root = find(tree, cls("carousel"))
    assert "multi" in root.attrs["class"] and root.attrs["style"] == "--per: 3; --gap: 12px"
    assert shown(tree) == ["A0*", "B1*", "C2*"]
    assert len(every(tree, cls("dot"))) == 3                        # starts 0, 1, 2
    for _ in range(4):
        tree = press(r, tree, "next")
    assert a.at == 2 and shown(tree) == ["C2*", "D3*", "E4*"]


def test_unbound_and_small_lists(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Carousel :items="[1, 2]"><Fill name="slide">{{ slide }}</Fill></ui.Carousel>'
                                  '<ui.Carousel :items="[1]" ><Fill name="slide">{{ slide }}</Fill></ui.Carousel></div>')
    first, single = every(tree, cls("carousel"))
    r.dispatch(find([first], cls("next")).events["click"], {})
    tree = cycle(r, tree)
    first, single = every(tree, cls("carousel"))
    assert [text([s]).strip() for s in every([first], cls("slide")) if "inert" not in s.attrs] == ["2"]
    assert find([single], cls("arrow")) is None and find([single], cls("controls")) is None


def test_autoplay_advances_pauses_and_stops(tmp_path):
    async def main():
        _, a, r, tree = carousel(tmp_path, 'autoplay="0.3"')
        state = {"tree": tree}

        async def wait(seconds, until=None):
            # Sleep as a page would, rendering whenever something changed so
            # the bound value reaches the carousel between its steps; stop
            # early once `until` holds. Returns whether it did.
            for _ in range(round(seconds / 0.02)):
                await asyncio.sleep(0.02)
                if r.needs_render():
                    state["tree"] = cycle(r, state["tree"])
                if until is not None and until():
                    return True
            return until is None

        def root():
            return find(state["tree"], cls("carousel"))

        assert find(tree, cls("play")).attrs["aria-label"] == "Stop the slides"
        assert find(tree, cls("viewport")).attrs["aria-live"] == "off"
        r.after_render()                                            # starts the timer
        assert await wait(2, until=lambda: a.at == 1)
        r.dispatch(root().events["mouseenter"], {})                 # paused while pointed at
        await wait(0.8)
        assert a.at == 1
        r.dispatch(root().events["mouseleave"], {})
        assert await wait(2, until=lambda: a.at == 2)
        state["tree"] = press(r, state["tree"], "next")             # by hand: stops for good
        assert a.at == 3
        assert find(state["tree"], cls("play")).attrs["aria-label"] == "Play the slides"
        assert find(state["tree"], cls("viewport")).attrs["aria-live"] == "polite"
        await wait(0.8)
        assert a.at == 3
        state["tree"] = press(r, state["tree"], "play")             # play again
        assert await wait(2, until=lambda: a.at == 4)
        assert await wait(2, until=lambda: a.at == 0)               # past the end: back to the start
        assert a.changes == [1, 2, 3, 4, 0]

    asyncio.run(main())
