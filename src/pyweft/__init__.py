"""PyWeft -- a Blazor-shaped UI framework for Python.

Markup in XML, logic in Python, one render core that emits transport-agnostic
patches so desktop (webview), web (Pyodide) and mobile can share a codebase.

The name is a placeholder; renaming is a find-and-replace on ``pyweft``.
"""

from .component import Component, component_from_source, load_component
from .differ import DiffError, diff
from .dommodel import apply_patches
from .expressions import ExpressionError
from .parser import TemplateError, parse_template, split_source
from .renderer import Renderer
from .vdom import Element, Node, Text, to_dicts

__version__ = "0.0.1"

__all__ = [
    "Component",
    "component_from_source",
    "load_component",
    "Renderer",
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
