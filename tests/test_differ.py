"""Differ tests.

The important one is ``test_random_keyed_reconciliation``: rather than assert a
particular op sequence, it applies the patches to the old tree and checks the
result equals the new tree. That is the property that actually matters, and it
catches index/ordering bugs that hand-written op assertions miss.
"""

import random

import pytest

from pyweft import Element, Text, apply_patches, diff, to_dicts
from pyweft.differ import DiffError


def el(tag, key=None, children=(), attrs=None, events=None):
    return Element(
        tag=tag,
        attrs=dict(attrs or {}),
        events=dict(events or {}),
        children=list(children),
        key=key,
    )


def roundtrip(old, new):
    """Apply diff(old, new) to old and return the resulting dict tree."""
    ops = diff(old, new)
    return apply_patches(to_dicts(old), ops), ops


def assert_converges(old, new):
    result, ops = roundtrip(old, new)
    assert result == to_dicts(new)
    return ops


# ------------------------------------------------------------- in-place ops


def test_identical_trees_produce_no_ops():
    tree = [el("div", children=[Text("hi")])]
    assert diff(tree, tree) == []


def test_text_change():
    ops = assert_converges([Text("a")], [Text("b")])
    assert ops == [{"op": "set_text", "path": [0], "text": "b"}]


def test_attribute_set_and_remove():
    old = [el("div", attrs={"class": "a", "id": "keep"})]
    new = [el("div", attrs={"class": "b", "title": "t"})]
    ops = assert_converges(old, new)
    assert ops[0]["op"] == "set_attrs"
    assert ops[0]["set"] == {"class": "b", "title": "t"}
    assert ops[0]["remove"] == ["id"]


def test_event_rebinding():
    old = [el("button", events={"click": "h1"})]
    new = [el("button", events={"click": "h2"})]
    ops = assert_converges(old, new)
    assert ops[0] == {
        "op": "set_events",
        "path": [0],
        "set": {"click": "h2"},
    }


def test_tag_change_replaces():
    ops = assert_converges([el("div")], [el("span")])
    assert ops[0]["op"] == "replace"


def test_type_change_replaces():
    ops = assert_converges([Text("a")], [el("div")])
    assert ops[0]["op"] == "replace"


def test_nested_change_addresses_correct_path():
    old = [el("div", children=[el("p", children=[Text("a")])])]
    new = [el("div", children=[el("p", children=[Text("b")])])]
    ops = assert_converges(old, new)
    assert ops == [{"op": "set_text", "path": [0, 0, 0], "text": "b"}]


# ----------------------------------------------------------- unkeyed lists


def test_unkeyed_append_and_truncate():
    assert_converges(
        [el("div", children=[Text("a")])],
        [el("div", children=[Text("a"), Text("b"), Text("c")])],
    )
    assert_converges(
        [el("div", children=[Text("a"), Text("b"), Text("c")])],
        [el("div", children=[Text("a")])],
    )


# ------------------------------------------------------------- keyed lists


def test_keyed_reverse():
    old = [el("li", key=k) for k in "abc"]
    new = [el("li", key=k) for k in "cba"]
    assert_converges(old, new)


def test_keyed_insert_in_middle():
    old = [el("li", key=k) for k in "ac"]
    new = [el("li", key=k) for k in "abc"]
    ops = assert_converges(old, new)
    assert any(o["op"] == "insert" for o in ops)


def test_keyed_removal_from_middle():
    old = [el("li", key=k) for k in "abc"]
    new = [el("li", key=k) for k in "ac"]
    ops = assert_converges(old, new)
    assert any(o["op"] == "remove" for o in ops)


def test_keyed_move_preserves_child_content():
    old = [
        el("li", key="a", children=[Text("A")]),
        el("li", key="b", children=[Text("B")]),
    ]
    new = [
        el("li", key="b", children=[Text("B")]),
        el("li", key="a", children=[Text("A2")]),
    ]
    ops = assert_converges(old, new)
    # The moved node keeps its identity: we patch its text, not replace it.
    assert any(o["op"] == "move" for o in ops)
    assert not any(o["op"] == "replace" for o in ops)


def test_keyed_full_swap_of_key_set():
    old = [el("li", key=k) for k in "abc"]
    new = [el("li", key=k) for k in "xyz"]
    assert_converges(old, new)


def test_duplicate_keys_raise():
    old = [el("li", key="a")]
    new = [el("li", key="a"), el("li", key="a")]
    with pytest.raises(DiffError):
        diff(old, new)


def test_structural_ops_precede_descendant_ops():
    old = [el("ul", children=[el("li", key="a", children=[Text("A")])])]
    new = [
        el(
            "ul",
            children=[
                el("li", key="b", children=[Text("B")]),
                el("li", key="a", children=[Text("A!")]),
            ],
        )
    ]
    ops = assert_converges(old, new)
    structural = [i for i, o in enumerate(ops) if o["op"] in ("insert", "remove", "move")]
    descendant = [i for i, o in enumerate(ops) if o["op"] == "set_text"]
    assert max(structural) < min(descendant)


# --------------------------------------------------------- property testing


def _random_children(rng, pool):
    count = rng.randint(0, 6)
    keys = rng.sample(pool, min(count, len(pool)))
    return [
        el("li", key=k, children=[Text(f"{k}{rng.randint(0, 2)}")]) for k in keys
    ]


@pytest.mark.parametrize("seed", range(300))
def test_random_keyed_reconciliation(seed):
    rng = random.Random(seed)
    pool = list("abcdefgh")
    old = [el("ul", children=_random_children(rng, pool))]
    new = [el("ul", children=_random_children(rng, pool))]
    result, _ = roundtrip(old, new)
    assert result == to_dicts(new)


@pytest.mark.parametrize("seed", range(100))
def test_random_unkeyed_reconciliation(seed):
    rng = random.Random(seed + 10_000)

    def kids():
        return [
            Text(str(rng.randint(0, 3))) if rng.random() < 0.5 else el("p")
            for _ in range(rng.randint(0, 5))
        ]

    old = [el("div", children=kids())]
    new = [el("div", children=kids())]
    result, _ = roundtrip(old, new)
    assert result == to_dicts(new)
