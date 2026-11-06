"""Templates compiled to Python functions.

The renderer can walk a parsed template (``Renderer._emit``), but most of
that time goes to the walking itself: dispatching on node types, copying
scopes for every loop row, rebuilding attribute dicts and handler ids from
the same template node on every render. This module turns a component's
template into the source of one Python function that does the same work
straight-line, compiles it once per class, and the renderer calls it
instead.

What it inlines is the common part of every template: text, plain HTML
elements (attributes, ``:attr``, ``class:``/``style:``, events, keys,
refs), ``<If>`` chains and ``<For>`` loops, with loop variables as Python
locals and other names looked up on the component. Anything else (child
components, ``<Dynamic>``, slots, ``<Await>``, ``<Html>``, elements with
``@bind``) is handed to the renderer's own methods with the same scope,
path and key it would have had, so it behaves exactly as before. The
output is required to be identical to the interpreter's; tests render
templates both ways and compare.

``PYWEFT_INTERPRET=1`` in the environment turns compilation off.
"""

from __future__ import annotations

import ast
import builtins
import functools
import os
from typing import Any, Callable

from .component import is_component_tag
from .expressions import ExpressionError, Scope, _FRAME_NAMES, eval_expr
from .parser import TElement, TFor, TIf, TStatic
from .styles import marker
from .vdom import Element, Text

ENABLED = os.environ.get("PYWEFT_INTERPRET", "") in ("", "0")

_BUILTINS = builtins.__dict__
_MISSING = object()


def _attr(component: Any, name: str) -> Any:
    """A name that isn't a loop variable: the component's, else a builtin
    (Scope's order, for the variables a compiled template can have)."""
    try:
        return getattr(component, name)
    except AttributeError:
        pass
    try:
        return _BUILTINS[name]
    except KeyError:
        raise NameError(f"name {name!r} is not defined") from None


def _fail(src: str, exc: Exception) -> None:
    if isinstance(exc, ExpressionError):
        raise exc
    raise ExpressionError(f"error evaluating {src!r}: {type(exc).__name__}: {exc}") from exc


def _child_scope(scope: Scope, pairs: tuple) -> Scope:
    child = Scope(scope.component, scope.vars)
    for name, value in pairs:
        child.vars[name] = value
    return child


def _marker_of(cls: type) -> str | None:
    scope_id = getattr(cls, "__scope__", None)
    return marker(scope_id) if scope_id else None


class _Fallback(Exception):
    """This expression needs eval's own frame: evaluate it the old way."""


class _Rewriter(ast.NodeTransformer):
    """Template names -> Python: loop variables to their locals, ``self``
    to the component, anything else to ``_pw_attr(_pw_c, "name")``."""

    def __init__(self, local_names: dict[str, str]):
        self.local_names = local_names
        self.scopes: list[set[str]] = []

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if not isinstance(node.ctx, ast.Load):
            return node
        if node.id in _FRAME_NAMES:
            raise _Fallback
        if any(node.id in scope for scope in self.scopes):
            return node
        if node.id in self.local_names:
            return ast.copy_location(ast.Name(self.local_names[node.id], ast.Load()), node)
        if node.id == "self":
            return ast.copy_location(ast.Name("_pw_c", ast.Load()), node)
        call = ast.Call(ast.Name("_pw_attr", ast.Load()), [ast.Name("_pw_c", ast.Load()), ast.Constant(node.id)], [])
        return ast.copy_location(call, node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:
        raise _Fallback

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
        generators[0].iter = self.visit(generators[0].iter)
        names: set[str] = set()
        self.scopes.append(names)
        for index, generator in enumerate(generators):
            if index:
                generator.iter = self.visit(generator.iter)
            names |= {n.id for n in ast.walk(generator.target) if isinstance(n, ast.Name)}
            generator.ifs = [self.visit(test) for test in generator.ifs]
        for name in fields:
            setattr(node, name, self.visit(getattr(node, name)))
        self.scopes.pop()
        return node

    def visit_ListComp(self, node: ast.ListComp) -> ast.AST:
        return self._comprehension(node, ("elt",))

    visit_SetComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node: ast.DictComp) -> ast.AST:
        return self._comprehension(node, ("key", "value"))


@functools.lru_cache(maxsize=16384)
def _rewrite(src: str, names: tuple[tuple[str, str], ...]) -> str | None:
    """An expression as Python code with these loop variables in reach, or
    None when it must be evaluated the old way. Cached: deciding whether a
    loop body needs a Scope asks again for every expression inside it, and
    templates repeat the same expressions (``label``, ``disabled``)."""
    try:
        tree = ast.parse(src, mode="eval")
        return ast.unparse(_Rewriter(dict(names)).visit(tree.body))
    except (_Fallback, SyntaxError):
        return None


class _Context:
    """Where generated code is emitting to: variable names for the scope,
    path, output list and inherited key, and the loop variables in reach."""

    def __init__(self, scope: str, path: str, out: str, key: str, names: dict[str, str]):
        self.scope, self.path, self.out, self.key, self.names = scope, path, out, key, names

    def but(self, **changes: Any) -> _Context:
        ctx = _Context(self.scope, self.path, self.out, self.key, self.names)
        for name, value in changes.items():
            setattr(ctx, name, value)
        return ctx


class _Generator:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.constants: dict[str, Any] = {}
        self.counter = 0

    # ------------------------------------------------------------ plumbing

    def const(self, value: Any) -> str:
        name = f"_pw_k{len(self.constants)}"
        self.constants[name] = value
        return name

    def tmp(self, base: str) -> str:
        self.counter += 1
        return f"_pw_{base}{self.counter}"

    def emit(self, depth: int, text: str) -> None:
        self.lines.append("    " * depth + text)

    def expression(self, src: str, ctx: _Context) -> str | None:
        return _rewrite(src.strip(), tuple(sorted(ctx.names.items())))

    def evaluate(self, depth: int, target: str, src: str, ctx: _Context) -> None:
        """``target = <src>`` with the interpreter's error wrapping."""
        code = self.expression(src, ctx)
        self.emit(depth, "try:")
        if code is None:
            self.emit(depth + 1, f"{target} = _pw_eval({self.const(src)}, {ctx.scope})")
        else:
            self.emit(depth + 1, f"{target} = {code}")
        self.emit(depth, "except Exception as _pw_e:")
        self.emit(depth + 1, f"_pw_fail({self.const(src)}, _pw_e)")

    # --------------------------------------------------------- what's what

    @staticmethod
    def inlined(node: Any) -> bool:
        if isinstance(node, (TStatic, TIf, TFor)):
            return True
        # A plain element exactly when Renderer._emit would treat it as one.
        return (
            isinstance(node, TElement)
            and node.tag != "Dynamic"
            and not is_component_tag(node.tag)
            and node.bind is None
        )

    def needs_scope(self, nodes: list[Any], ctx: _Context) -> bool:
        """Whether code for these nodes uses a Scope object (handlers,
        nodes handed to the renderer, expressions eval must run)."""
        for node in nodes:
            if not self.inlined(node):
                return True
            if isinstance(node, TStatic):
                sources = [text for kind, text in node.parts if kind == "expr"]
                children: list[list[Any]] = []
            elif isinstance(node, TIf):
                sources = [cond for cond, _ in node.branches if cond is not None]
                children = [kids for _, kids in node.branches]
            elif isinstance(node, TFor):
                sources = [node.iter_src] + ([node.key_expr] if node.key_expr else [])
                children = [node.children]
            else:
                if node.events:
                    return True
                sources = [text for parts in node.attrs.values() for kind, text in parts if kind == "expr"]
                sources += [*node.expr_attrs.values(), *node.class_toggles.values(), *node.style_props.values()]
                sources += [node.key_expr] if node.key_expr else []
                children = [node.children]
            if any(self.expression(src, ctx) is None for src in sources):
                return True
            if any(self.needs_scope(kids, ctx) for kids in children):
                return True
        return False

    # ------------------------------------------------------------- nodes

    def nodes(self, nodes: list[Any], depth: int, ctx: _Context) -> None:
        for node in nodes:
            if not self.inlined(node):
                self.emit(depth, f"_pw_r._emit({self.const([node])}, {ctx.scope}, {ctx.path}, {ctx.out}, {ctx.key})")
            elif isinstance(node, TStatic):
                self.text(node, depth, ctx)
            elif isinstance(node, TIf):
                self.branches(node, depth, ctx)
            elif isinstance(node, TFor):
                self.loop(node, depth, ctx)
            else:
                self.element(node, depth, ctx)

    def parts(self, parts: list[tuple[str, str]], depth: int, ctx: _Context) -> str:
        """Code for an interpolated string's value (statements emitted first)."""
        if len(parts) == 1 and parts[0][0] == "static":
            return repr(parts[0][1])
        pieces = []
        for kind, text in parts:
            if kind == "static":
                pieces.append(repr(text))
            else:
                value = self.tmp("v")
                self.evaluate(depth, value, text, ctx)
                pieces.append(f'("" if {value} is None else str({value}))')
        return '"".join((' + ", ".join(pieces) + ",))"

    def text(self, node: TStatic, depth: int, ctx: _Context) -> None:
        value = self.parts(node.parts, depth, ctx)
        self.emit(depth, f"{ctx.out}.append(_pw_Text({value}))")

    def branches(self, node: TIf, depth: int, ctx: _Context) -> None:
        for cond, children in node.branches:
            if cond is None:
                self.nodes(children, depth, ctx)
                self.emit(depth, "pass")
                return
            test = self.tmp("t")
            self.evaluate(depth, test, cond, ctx)
            self.emit(depth, f"if {test}:")
            self.nodes(children, depth + 1, ctx)
            self.emit(depth + 1, "pass")
            self.emit(depth, "else:")
            depth += 1
        self.emit(depth, "pass")

    def loop(self, node: TFor, depth: int, ctx: _Context) -> None:
        items, index, item = self.tmp("items"), self.tmp("i"), self.tmp("item")
        self.evaluate(depth, items, node.iter_src, ctx)
        self.emit(depth, f"if {items} is not None:")
        depth += 1
        self.emit(depth, f"for {index}, {item} in enumerate({items}):")
        depth += 1
        names = dict(ctx.names)
        names[node.var] = item
        pairs = [(node.var, item)]
        if node.index_var:
            names[node.index_var] = index
            pairs.append((node.index_var, index))
        inner = ctx.but(names=names)
        if self.needs_scope(node.children, inner) or (node.key_expr and self.expression(node.key_expr, inner) is None):
            scope = self.tmp("scope")
            pair_code = ", ".join(f"({name!r}, {value})" for name, value in pairs)
            self.emit(depth, f"{scope} = _pw_child_scope({ctx.scope}, ({pair_code},))")
            inner.scope = scope
        key = self.tmp("key")
        if node.key_expr:
            self.evaluate(depth, key, node.key_expr, inner)
        else:
            self.emit(depth, f"{key} = None")
        before = self.tmp("before")
        self.emit(depth, f"{before} = len({ctx.out})")
        self.nodes(node.children, depth, inner.but(key=key))
        if node.key_expr:
            self.emit(depth, f"if {key} is not None:")
            self.emit(depth + 1, f"_pw_keyed({ctx.out}, {before})")

    def element(self, node: TElement, depth: int, ctx: _Context) -> None:
        key = self.tmp("nk")
        self.emit(depth, f"{key} = {ctx.key}")
        if node.key_expr:
            if ctx.key == "None":
                self.evaluate(depth, key, node.key_expr, ctx)
            else:
                self.emit(depth, f"if {key} is None:")
                self.evaluate(depth + 1, key, node.key_expr, ctx)
        path = self.tmp("p")
        if ctx.key == "None" and not node.key_expr:
            self.emit(depth, f'{path} = {ctx.path} + ["i:%d" % len({ctx.out})]')
        else:
            self.emit(depth, f'{path} = {ctx.path} + [f"k:{{{key}}}" if {key} is not None else "i:%d" % len({ctx.out})]')

        attrs = self.tmp("a")
        static = {name: parts[0][1] for name, parts in node.attrs.items()
                  if len(parts) == 1 and parts[0][0] == "static"}
        if len(static) == len(node.attrs):
            self.emit(depth, f"{attrs} = {static!r}")
        else:
            self.emit(depth, f"{attrs} = {{}}")
            for name, parts in node.attrs.items():
                value = self.parts(parts, depth, ctx)
                self.emit(depth, f"{attrs}[{name!r}] = {value}")
        for name, src in node.expr_attrs.items():
            value = self.tmp("x")
            self.evaluate(depth, value, src, ctx)
            self.emit(depth, f"if {value} is not None and {value} is not False:")
            self.emit(depth + 1, f'{attrs}[{name!r}] = "" if {value} is True else str({value})')
        if node.class_toggles:
            names = self.tmp("cls")
            self.emit(depth, f"{names} = []")
            for name, src in node.class_toggles.items():
                value = self.tmp("x")
                self.evaluate(depth, value, src, ctx)
                self.emit(depth, f"if {value}:")
                self.emit(depth + 1, f"{names}.append({name!r})")
            self.emit(depth, f"if {names}:")
            self.emit(depth + 1, f'{attrs}["class"] = " ".join([*{attrs}.get("class", "").split(), *{names}])')
        if node.style_props:
            decls = self.tmp("st")
            self.emit(depth, f"{decls} = []")
            for prop, src in node.style_props.items():
                value = self.tmp("x")
                self.evaluate(depth, value, src, ctx)
                self.emit(depth, f"if {value} is not None and {value} is not False:")
                self.emit(depth + 1, f'{decls}.append(f"{prop}: {{{value}}}")')
            own = self.tmp("own")
            self.emit(depth, f"if {decls}:")
            self.emit(depth + 1, f'{own} = {attrs}.get("style", "").strip().rstrip(";")')
            self.emit(depth + 1, f'{attrs}["style"] = "; ".join([{own}, *{decls}] if {own} else {decls})')
        self.emit(depth, "if _pw_m:")
        self.emit(depth + 1, f'{attrs}[_pw_m] = ""')

        events = self.tmp("ev")
        if node.events:
            prefix = self.tmp("pre")
            self.emit(depth, f'{prefix} = "/".join({path})')
            self.emit(depth, f"{events} = {{}}")
            for spec, src in node.events.items():
                if not src.strip():
                    self.emit(depth, f'{events}[{spec!r}] = ""')
                    continue
                handler = self.tmp("h")
                self.emit(depth, f'{handler} = {prefix} + {"#" + spec!r}')
                self.emit(depth, f"_pw_r.handlers[{handler}] = _pw_r._make_handler({src!r}, {ctx.scope})")
                self.emit(depth, f"{events}[{spec!r}] = {handler}")
        else:
            self.emit(depth, f"{events} = {{}}")

        ref = None
        if "ref" in node.attrs or "ref" in node.expr_attrs:
            ref = self.tmp("ref")
            self.emit(depth, f'{ref} = {attrs}.pop("ref", None)')

        children = self.tmp("ch")
        self.emit(depth, f"{children} = []")
        self.nodes(node.children, depth, ctx.but(path=path, out=children, key="None"))
        element = self.tmp("el")
        self.emit(depth, f"{element} = _pw_Element({node.tag!r}, {attrs}, {events}, {children}, {key})")
        if ref:
            self.emit(depth, f"if {ref}:")
            self.emit(depth + 1, f"_pw_r._refs[(id(_pw_c), {ref})] = {element}")
        self.emit(depth, f"{ctx.out}.append({element})")


def _keyed(out: list, before: int) -> None:
    from .parser import TemplateError

    elements = [n for n in out[before:] if isinstance(n, Element)]
    if len(elements) != 1:
        raise TemplateError(
            "a keyed <For> body must produce exactly one element "
            f"per item, got {len(elements)}"
        )


def generate(template: list[Any]) -> tuple[str, dict[str, Any]]:
    """The source of ``_pw_render(_pw_r, _pw_scope, _pw_path, _pw_out,
    _pw_key)`` for a template, and the constants it refers to."""
    gen = _Generator()
    gen.emit(0, "def _pw_render(_pw_r, _pw_scope, _pw_path, _pw_out, _pw_key):")
    gen.emit(1, "_pw_c = _pw_scope.component")
    gen.emit(1, "_pw_m = _pw_marker_of(type(_pw_c))")
    gen.nodes(template, 1, _Context("_pw_scope", "_pw_path", "_pw_out", "_pw_key", {}))
    gen.emit(1, "return None")
    return "\n".join(gen.lines) + "\n", gen.constants


_RUNTIME = {
    "_pw_attr": _attr,
    "_pw_fail": _fail,
    "_pw_eval": eval_expr,
    "_pw_child_scope": _child_scope,
    "_pw_marker_of": _marker_of,
    "_pw_keyed": _keyed,
    "_pw_Text": Text,
    "_pw_Element": Element,
    "__builtins__": builtins,
}

_COMPILED: dict[int, tuple[Any, Callable | None]] = {}



def compiled(cls: type, create: bool = True) -> Callable | None:
    """The compiled render function for a component class's template, or
    None when compilation is off or the template couldn't be compiled (the
    renderer then walks it). Cached per template object. ``create=False``
    only looks: None if it isn't compiled yet."""
    if not ENABLED:
        return None
    template = cls.__template__
    hit = _COMPILED.get(id(template))
    if hit is not None and hit[0] is template:
        return hit[1]
    if not create:
        return None
    try:
        source, constants = generate(template)
        namespace = {**_RUNTIME, **constants}
        exec(compile(source, "<pyweft-template>", "exec"), namespace)
        function = namespace["_pw_render"]
    except (SyntaxError, RecursionError, MemoryError):
        function = None  # a template too deep for Python's compiler: walk it
    _COMPILED[id(template)] = (template, function)
    return function


__all__ = ["compiled", "generate", "ENABLED"]
