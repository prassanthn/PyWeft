"""End-to-end walkthrough with no webview: render, dispatch, diff, apply.

Run:  python examples/demo.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pyweft import Renderer, apply_patches, diff, load_component, to_dicts


def show(label, ops):
    print(f"\n--- {label}: {len(ops)} op(s)")
    for op in ops:
        print("   ", json.dumps(op, default=str))


def main():
    Counter = load_component(Path(__file__).with_name("counter.weft"))
    counter = Counter()
    renderer = Renderer(counter)

    tree = renderer.render()
    dom = to_dicts(tree)
    print("initial render:", len(dom), "root node(s)")

    def step(label, handler_id, event=None):
        nonlocal tree, dom
        renderer.dispatch(handler_id, event)
        new_tree = renderer.render()
        ops = diff(tree, new_tree)
        show(label, ops)
        dom = apply_patches(dom, ops)
        tree = new_tree
        assert dom == to_dicts(tree), "patched DOM diverged from the vdom"

    def find(node, pred):
        if pred(node):
            return node
        for child in node.get("children", []):
            hit = find(child, pred)
            if hit:
                return hit
        return None

    plus = find(dom[0], lambda n: n.get("children") and n["children"][0].get("text") == "+1")
    name_box = find(dom[0], lambda n: n.get("attrs", {}).get("placeholder") == "your name")

    step("type a name", name_box["events"]["input"], {"value": "Prassanth"})
    for i in range(4):
        step(f"click +1 ({i + 1})", plus["events"]["click"])

    # Remove the middle history row -- the keyed diff should move/remove, not
    # rebuild the whole list.
    row = tree[0].children[-1].children[1]
    step("forget row 2", row.events["click"])

    print("\nfinal count:", counter.count, "| history:", [h["label"] for h in counter.history])
    print("DOM stayed in sync with the vdom at every step.")


if __name__ == "__main__":
    main()
