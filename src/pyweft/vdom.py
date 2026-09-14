"""Virtual DOM node types.

The render core never touches a real DOM. It produces trees of these nodes,
which the differ turns into transport-agnostic patch ops. A webview bridge, a
Pyodide in-process call, or a websocket can all carry the same ops -- that is
what makes desktop/web/mobile one codebase instead of three.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass
class Text:
    """A text node."""

    text: str

    def to_dict(self) -> dict:
        return {"type": "text", "text": self.text}


@dataclass
class Element:
    """An element node.

    attrs:  plain HTML attributes, already stringified
    events: event name -> handler id, looked up in the renderer's handler
            table when an event arrives back over the bridge
    key:    stable identity for list reconciliation; None means "unkeyed",
            which falls back to positional matching
    """

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    events: dict[str, str] = field(default_factory=dict)
    children: list[Node] = field(default_factory=list)
    key: Any = None

    def to_dict(self) -> dict:
        return {
            "type": "element",
            "tag": self.tag,
            "attrs": dict(self.attrs),
            "events": dict(self.events),
            "key": self.key,
            "children": [c.to_dict() for c in self.children],
        }


Node = Union[Text, Element]


def to_dicts(nodes: list[Node]) -> list[dict]:
    return [n.to_dict() for n in nodes]
