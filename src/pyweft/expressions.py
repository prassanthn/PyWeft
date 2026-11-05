"""Expression compilation and evaluation.

Every ``{{ expr }}`` and every directive value is compiled once, cached by
source text, into a Python function of (template variables, component):
each free name in it becomes a lookup in the template's variables (loop
variables, slot props, ``event``), then on the component, then in the
builtins, which is the order a ``Scope`` resolves names in. Being a real
function rather than ``eval`` against a mapping, it is faster, and
generator expressions, lambdas and comprehensions in it see those names
like any closure would.

The few expressions that need ``eval``'s own frame (``:=``, ``locals()``
and the like) are evaluated against the ``Scope`` as before.
"""

from __future__ import annotations

import ast
import builtins
import re
from collections.abc import Mapping, MutableMapping
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


_BUILTINS = builtins.__dict__
# Using one of these needs the eval frame (or would see the wrong one).
_FRAME_NAMES = frozenset({"locals", "vars", "dir", "globals", "eval", "exec", "super", "breakpoint"})


def _lookup(variables: dict, component: Any, name: str) -> Any:
    """A free name in a compiled expression: what ``Scope`` would give."""
    if name in variables:
        return variables[name]
    if name == "self":
        return component
    try:
        return getattr(component, name)
    except AttributeError:
        pass
    try:
        return _BUILTINS[name]
    except KeyError:
        raise NameError(f"name {name!r} is not defined") from None


class _Uncompilable(Exception):
    pass


def _bound(target: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


class _Rewriter(ast.NodeTransformer):
    """Free names -> ``_pw_lookup(_pw_vars, _pw_self, "name")``. Names a
    lambda or comprehension binds stay as they are."""

    def __init__(self) -> None:
        self.scopes: list[set[str]] = []

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if not isinstance(node.ctx, ast.Load):
            return node
        if node.id in _FRAME_NAMES:
            raise _Uncompilable(node.id)
        if any(node.id in scope for scope in self.scopes):
            return node
        call = ast.Call(
            func=ast.Name("_pw_lookup", ast.Load()),
            args=[ast.Name("_pw_vars", ast.Load()), ast.Name("_pw_self", ast.Load()), ast.Constant(node.id)],
            keywords=[],
        )
        return ast.copy_location(call, node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
        raise _Uncompilable(":=")  # it stores into the Scope: component state

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        args = node.args
        args.defaults = [self.visit(d) for d in args.defaults]
        args.kw_defaults = [self.visit(d) if d is not None else None for d in args.kw_defaults]
        names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
        names |= {a.arg for a in (args.vararg, args.kwarg) if a is not None}
        self.scopes.append(names)
        node.body = self.visit(node.body)
        self.scopes.pop()
        return node

    def _comprehension(self, node: Any, fields: tuple[str, ...]) -> ast.AST:
        generators = node.generators
        # The first iterable is evaluated outside the comprehension.
        generators[0].iter = self.visit(generators[0].iter)
        names: set[str] = set()
        self.scopes.append(names)
        for index, generator in enumerate(generators):
            if index:
                generator.iter = self.visit(generator.iter)
            names |= _bound(generator.target)
            generator.ifs = [self.visit(test) for test in generator.ifs]
        for name in fields:
            setattr(node, name, self.visit(getattr(node, name)))
        self.scopes.pop()
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return self._comprehension(node, ("elt",))

    visit_SetComp = visit_ListComp

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> ast.AST:
        return self._comprehension(node, ("elt",))

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return self._comprehension(node, ("key", "value"))


_FUNCTIONS: dict[str, Any] = {}
_FUNCTION_GLOBALS = {"_pw_lookup": _lookup, "__builtins__": builtins}


def compile_function(src: str) -> Any:
    """``src`` as a function of (variables, component), or None when it
    must be evaluated against a Scope (see the module docstring). Cached."""
    src = src.strip()
    try:
        return _FUNCTIONS[src]
    except KeyError:
        pass
    function = None
    try:
        tree = ast.parse(src, mode="eval")
        body = _Rewriter().visit(tree.body)
        lam = ast.Expression(ast.Lambda(
            args=ast.arguments(
                posonlyargs=[], args=[ast.arg("_pw_vars"), ast.arg("_pw_self")], vararg=None,
                kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[],
            ),
            body=body,
        ))
        ast.fix_missing_locations(lam)
        function = eval(compile(lam, "<pyweft>", "eval"), _FUNCTION_GLOBALS)
    except (_Uncompilable, SyntaxError):
        function = None  # eval reports a syntax error with the usual message
    _FUNCTIONS[src] = function
    return function


class Scope(MutableMapping):
    """Name resolution for template expressions.

    Looks in loop variables first, then falls back to attributes on the
    component instance. Passed to ``eval`` as the locals mapping, so a bare
    name in a template resolves the way you'd expect without the component
    needing to copy its state into a dict every render. ``self`` names the
    component itself.

    It is also the locals mapping for inline handler *statements*
    (``@click="count += 1"``): a store to a loop variable stays in the scope,
    a store to anything else becomes component state.

    Expressions are normally compiled to functions that resolve names the
    same way without going through this mapping (``compile_function``).
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
        if name == "self":
            return self.component
        try:
            return getattr(self.component, name)
        except AttributeError:
            raise KeyError(name) from None

    def __setitem__(self, name: str, value: Any) -> None:
        if name in self.vars:
            self.vars[name] = value
        else:
            setattr(self.component, name, value)

    def __delitem__(self, name: str) -> None:
        if name in self.vars:
            del self.vars[name]
        else:
            delattr(self.component, name)

    def __iter__(self):
        seen = set(self.vars)
        yield from self.vars
        for name in dir(self.component):
            if not name.startswith("_") and name not in seen:
                yield name

    def __len__(self) -> int:
        return sum(1 for _ in self)


def eval_expr(src: str, scope: Mapping) -> Any:
    function = compile_function(src) if type(scope) is Scope else None
    try:
        if function is not None:
            return function(scope.vars, scope.component)  # type: ignore[attr-defined]
        return eval(compile_expr(src), _GLOBALS, scope)
    except ExpressionError:
        raise
    except Exception as exc:
        raise ExpressionError(
            f"error evaluating {src!r}: {type(exc).__name__}: {exc}"
        ) from exc


_HANDLER_CACHE: dict[str, tuple[Any, bool]] = {}


def compile_handler(src: str) -> tuple[Any, bool]:
    """Compile a handler value; returns ``(code, is_expression)``.

    A handler is normally an expression (``remove(item)``), but the simple
    inline cases people reach for are statements (``count += 1``,
    ``show = not show``, ``a = 1; b = 2``), so fall back to ``exec`` mode when
    ``eval`` mode does not parse.
    """
    src = src.strip()
    hit = _HANDLER_CACHE.get(src)
    if hit is None:
        try:
            hit = (compile(src, "<pyweft>", "eval"), True)
        except SyntaxError:
            try:
                hit = (compile(src, "<pyweft>", "exec"), False)
            except SyntaxError as exc:
                raise ExpressionError(f"bad handler {src!r}: {exc}") from exc
        _HANDLER_CACHE[src] = hit
    return hit


def run_handler(src: str, scope: MutableMapping) -> Any:
    """Evaluate an expression handler, or execute a statement handler
    (returning ``None``), against ``scope``."""
    code, is_expr = compile_handler(src)
    function = compile_function(src) if is_expr and type(scope) is Scope else None
    try:
        if function is not None:
            return function(scope.vars, scope.component)  # type: ignore[attr-defined]
        if is_expr:
            return eval(code, _GLOBALS, scope)
        exec(code, _GLOBALS, scope)
        return None
    except ExpressionError:
        raise
    except Exception as exc:
        raise ExpressionError(
            f"error running handler {src!r}: {type(exc).__name__}: {exc}"
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
