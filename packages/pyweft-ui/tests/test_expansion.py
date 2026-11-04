"""Expansion (one panel) and Accordion (a stack of them)."""

from pyweft.vdom import Element

from test_controls import app, cls, cycle, find, text


def all_nodes(tree, test):
    out = []

    def walk(nodes):
        for n in nodes:
            if isinstance(n, Element):
                if test(n):
                    out.append(n)
                walk(n.children)

    walk(tree)
    return out


def headers(tree):
    return all_nodes(tree, cls("header"))


def panels(tree):
    return all_nodes(tree, cls("expansion"))


def is_open(panel):
    return "open" in panel.attrs["class"].split()


def click(r, tree, index):
    r.dispatch(headers(tree)[index].events["click"], {"type": "click"})
    return cycle(r, tree)


def focused_path(r):
    r.after_render()
    commands = [c for c in r.take_commands() if c["op"] == "focus"]
    assert commands, "no focus request"
    return commands[-1]["path"]


def node_at(tree, path):
    node, nodes = None, tree
    for index in path:
        node = nodes[index]
        nodes = node.children
    return node


# ------------------------------------------------------------------ Expansion

CODE = "shown: bool = False\nlog: list = []\nnote: str = ''\n"


def test_expansion_binds_and_reports(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Expansion title="Shipping" description="Where to" @bind="shown" '
                                  '@open="log.append(\'open\')" @close="log.append(\'close\')">'
                                  '<p class="body-text">Inside</p></ui.Expansion></div>', CODE)
    (panel,) = panels(tree)
    header = headers(tree)[0]
    assert not is_open(panel) and header.attrs["aria-expanded"] == "false"
    assert text([find(tree, cls("title"))]) == "Shipping" and text([find(tree, cls("desc"))]) == "Where to"
    body = find(tree, cls("body"))
    assert "inert" in body.attrs and body.attrs["role"] == "region"
    assert body.attrs["aria-labelledby"] == header.attrs["id"] and header.attrs["aria-controls"] == body.attrs["id"]
    # Closed content is still there (state survives), just unreachable.
    assert text([find(tree, cls("body-text"))]) == "Inside"
    tree = click(r, tree, 0)
    assert a.shown is True and a.log == ["open"]
    assert is_open(panels(tree)[0]) and "inert" not in find(tree, cls("body")).attrs
    assert headers(tree)[0].attrs["aria-expanded"] == "true"
    tree = click(r, tree, 0)
    assert a.shown is False and a.log == ["open", "close"]


def test_expansion_unbound_starts_closed_or_open(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Expansion title="A">a</ui.Expansion>'
                                  '<ui.Expansion title="B" open="true">b</ui.Expansion></div>')
    assert [is_open(p) for p in panels(tree)] == [False, True]
    tree = click(r, tree, 0)
    tree = click(r, tree, 1)
    assert [is_open(p) for p in panels(tree)] == [True, False]


def test_expansion_lazy_renders_once_opened(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Expansion title="A" lazy="true">'
                                  '<p class="body-text">heavy</p></ui.Expansion></div>')
    assert find(tree, cls("body-text")) is None and find(tree, cls("content")) is None
    tree = click(r, tree, 0)
    assert find(tree, cls("body-text")) is not None
    tree = click(r, tree, 0)
    assert find(tree, cls("body-text")) is not None


def test_expansion_header_fill_actions_toggle_disabled(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Expansion toggle="before" icon="user" level="2" disabled="true" open="true">'
                                  '<Fill name="header"><b class="custom">Custom {{ note }}</b></Fill>'
                                  'Body<Fill name="actions"><button class="act">Save</button></Fill>'
                                  '</ui.Expansion><ui.Expansion title="X" toggle="none">x</ui.Expansion></div>', CODE)
    first, second = panels(tree)
    assert find([first], cls("custom")) is not None and find([first], cls("title")) is None
    assert find([first], cls("icon")) is not None
    header = find([first], cls("header"))
    assert "disabled" in header.attrs and "disabled" in first.attrs["class"]
    assert [c.attrs["class"] for c in header.children if isinstance(c, Element)][0] == "chev"
    assert find([first], cls("head")).attrs["aria-level"] == "2"
    assert text([find([first], cls("act"))]) == "Save"
    assert find([second], cls("chev")) is None and find([second], cls("actions")) is None


def test_standalone_expansion_leaves_arrow_keys_alone(tmp_path):
    _, a, r, tree = app(tmp_path, '<div><ui.Expansion title="A">a</ui.Expansion></div>')
    assert list(headers(tree)[0].events) == ["click"]


# ------------------------------------------------------------------ Accordion

ACC = ("section = None\nopen_ones: list = []\n"
       "opts: list = [{'value': 'account', 'label': 'Account', 'description': 'Name and email', 'icon': 'user'},"
       " ('billing', 'Billing'), {'value': 'old', 'label': 'Legacy', 'disabled': True}, 'Privacy']\n")


def accordion(tmp_path, attrs):
    return app(tmp_path, f'<div><ui.Accordion :options="opts" {attrs}>'
                         '<p class="body-text">Panel {{ panel }}</p></ui.Accordion></div>', ACC)


def test_accordion_opens_one_at_a_time(tmp_path):
    _, a, r, tree = accordion(tmp_path, '@bind="section"')
    assert [text([find([p], cls("title"))]) for p in panels(tree)] == ["Account", "Billing", "Legacy", "Privacy"]
    assert text([find(tree, cls("desc"))]) == "Name and email"
    assert [text([find([p], cls("body-text"))]) for p in panels(tree)] == [
        "Panel account", "Panel billing", "Panel old", "Panel Privacy"]
    assert not any(is_open(p) for p in panels(tree))
    assert "disabled" in headers(tree)[2].attrs
    tree = click(r, tree, 1)
    assert a.section == "billing" and [is_open(p) for p in panels(tree)] == [False, True, False, False]
    tree = click(r, tree, 0)
    assert a.section == "account" and [is_open(p) for p in panels(tree)] == [True, False, False, False]
    tree = click(r, tree, 0)
    assert a.section is None and not any(is_open(p) for p in panels(tree))


def test_accordion_multiple_binds_a_list_in_order(tmp_path):
    _, a, r, tree = accordion(tmp_path, 'multiple="true" @bind="open_ones"')
    tree = click(r, tree, 3)
    tree = click(r, tree, 0)
    assert a.open_ones == ["account", "Privacy"]
    assert [is_open(p) for p in panels(tree)] == [True, False, False, True]
    tree = click(r, tree, 3)
    assert a.open_ones == ["account"]


def test_accordion_unbound_keeps_its_own_state(tmp_path):
    _, a, r, tree = accordion(tmp_path, '')
    tree = click(r, tree, 1)
    tree = click(r, tree, 3)
    assert [is_open(p) for p in panels(tree)] == [False, False, False, True]


def test_accordion_arrow_keys_skip_disabled_and_wrap(tmp_path):
    _, a, r, tree = accordion(tmp_path, '@bind="section"')

    def press(index, key):
        r.dispatch(headers(tree)[index].events[f"keydown.{key}.prevent"], {"type": "keydown", "key": key})
        path = focused_path(r)
        # A ref on a component names its root; the runtime focuses the
        # first focusable thing inside, i.e. the header.
        return panels(tree).index(node_at(tree, path))

    assert press(1, "down") == 3       # Legacy is disabled
    assert press(3, "down") == 0       # wraps
    assert press(0, "up") == 3
    assert press(3, "up") == 1
    assert press(1, "home") == 0
    assert press(0, "end") == 3
