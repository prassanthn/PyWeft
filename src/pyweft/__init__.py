"""PyWeft -- a UI framework for Python.

Markup in XML, logic in Python, one render core that emits transport-agnostic
patches so desktop (webview), web (Pyodide) and mobile can share a codebase.
"""

from .background import BackgroundError, run_in_background
from .component import (
    Component,
    ComponentLibrary,
    component_from_source,
    load_component,
)
from .differ import DiffError, diff
from .dommodel import apply_patches
from .effects import effect
from .events import Event
from .expressions import ExpressionError
from .parser import TemplateError, parse_template, split_source
from .renderer import EffectLoopError, Renderer
from .styles import collect_styles, scope_css
from .vdom import Element, Node, Text, to_dicts

__version__ = "0.0.1"

__all__ = [
    "Component",
    "ComponentLibrary",
    "component_from_source",
    "load_component",
    "Renderer",
    "effect",
    "Event",
    "EffectLoopError",
    "run_in_background",
    "BackgroundError",
    "collect_styles",
    "scope_css",
    "diff",
    "apply_patches",
    "Element",
    "Text",
    "Node",
    "to_dicts",
    "DiffError",
    "TemplateError",
    "ExpressionError",
    "parse_template",
    "split_source",
    "__version__",
]
