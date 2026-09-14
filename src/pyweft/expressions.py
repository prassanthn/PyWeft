"""Expression compilation and evaluation.

Every ``{{ expr }}`` and every directive value is compiled once with
``compile(..., "eval")`` and cached by source text, then evaluated against a
``Scope`` at render time. Compiling at parse time rather than calling ``eval``
on a string every render is the single biggest perf lever in the render loop.
"""

from __future__ import annotations

import builtins
import re
from collections.abc import Mapping
from typing import Any


class ExpressionError(RuntimeError):
    pass


_CACHE: dict[str, Any] = {}
_GLOBALS: dict[str, Any] = {"__builtins__": builtins}


def compile_expr(src: str):
    src = src.strip()
    code = _CACHE.get(src)
    if code is None:
        try:
            code = compile(src, "<pyweft>", "eval")
        except SyntaxError as exc:
            raise ExpressionError(f"bad expression {src!r}: {exc}") from exc
        _CACHE[src] = code
    return code


class Scope(Mapping):
    """Name resolution for template expressions.

    Looks in loop variables first, then falls back to attributes on the
    component instance. Passed to ``eval`` as the locals mapping, so a bare
    name in a template resolves the way you'd expect without the component
    needing to copy its state into a dict every render.

    Known limitation: comprehensions and lambdas inside an expression build
    their own frame and only see globals, so ``{{ [x for x in items] }}``
    cannot see ``items``. Assign such values in the code block instead.
    """

    __slots__ = ("component", "vars")

    def __init__(self, component: Any, vars: dict | None = None):
        self.component = component
        self.vars = dict(vars) if vars else {}

    def child(self, **extra) -> Scope:
        scope = Scope(self.component, self.vars)
        scope.vars.update(extra)
        return scope

    def __getitem__(self, name: str) -> Any:
        if name in self.vars:
            return self.vars[name]
        try:
            return getattr(self.component, name)
        except AttributeError:
            raise KeyError(name) from None

    def __iter__(self):
        seen = set(self.vars)
        yield from self.vars
        for name in dir(self.component):
            if not name.startswith("_") and name not in seen:
                yield name

    def __len__(self) -> int:
        return sum(1 for _ in self)


def eval_expr(src: str, scope: Mapping) -> Any:
    code = compile_expr(src)
    try:
        return eval(code, _GLOBALS, scope)
    except ExpressionError:
        raise
    except Exception as exc:
        raise ExpressionError(
            f"error evaluating {src!r}: {type(exc).__name__}: {exc}"
        ) from exc


_INTERP = re.compile(r"\{\{(.*?)\}\}", re.S)


def parse_interpolation(text: str) -> list[tuple[str, str]]:
    """'a {{x}} b' -> [('static','a '), ('expr','x'), ('static',' b')]"""
    parts: list[tuple[str, str]] = []
    pos = 0
    for match in _INTERP.finditer(text):
        if match.start() > pos:
            parts.append(("static", text[pos : match.start()]))
        parts.append(("expr", match.group(1).strip()))
        pos = match.end()
    if pos < len(text):
        parts.append(("static", text[pos:]))
    return parts or [("static", "")]


def render_parts(parts: list[tuple[str, str]], scope: Mapping) -> str:
    if len(parts) == 1 and parts[0][0] == "static":
        return parts[0][1]
    out = []
    for kind, val in parts:
        if kind == "static":
            out.append(val)
        else:
            value = eval_expr(val, scope)
            out.append("" if value is None else str(value))
    return "".join(out)


def is_static(parts: list[tuple[str, str]]) -> bool:
    return all(kind == "static" for kind, _ in parts)
