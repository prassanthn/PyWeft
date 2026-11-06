"""``pyweft check``: find mistakes in an app's ``.weft`` files without
running it in a browser.

Each component is loaded as ``pyweft run`` would (so template and Python
syntax errors, and missing components, show up), then its template is
walked with what the component defines in hand: unknown names in
expressions, handlers and ``@bind`` fields that don't exist, props a
component doesn't declare, events it never emits, slots it doesn't have,
and the traps listed in the guide for coding assistants. Problems carry
the file and line, and a "did you mean" where one is close.

Host-only, like the CLI: never shipped to the browser.
"""

from __future__ import annotations

import ast
import builtins
import difflib
import re
import sys
import textwrap
import traceback
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .component import (
    Component,
    ComponentLibrary,
    block_spans,
    component_named,
    declared_props,
    is_component_tag,
    load_component,
    split_source,
)
from .a11y import audit, ignored
from .parser import TAwait, TDefer, TElement, TemplateError, TFill, TFor, THead, THtml, TIf, TSlot, TStatic, subtrees

BUILTINS = frozenset(dir(builtins))
# Attributes any element may carry: not taken for a mistyped prop when
# written on a component tag (they go to its root element).
_GLOBAL_ATTRS = frozenset({
    "id", "class", "style", "title", "role", "tabindex", "hidden", "lang", "dir",
    "draggable", "translate", "inert", "accesskey", "spellcheck", "autofocus",
    "contenteditable", "slot", "part", "popover", "key", "ref",
})
_BROWSER_ONLY = ("js", "pyodide")


@dataclass
class Problem:
    file: str            # relative to the app folder, with forward slashes
    line: int            # 1-based; 0 when not known
    severity: str        # "error" or "warning"
    code: str            # a short id, e.g. "unknown-name"
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{where}: {self.severity}: {self.message} [{self.code}]"


def check_app(app_dir: Path, deps: bool = True, fetch: Any = None,
              a11y: bool = True) -> tuple[list[Problem], int]:
    """Every problem found in the app's components (and, with ``deps``, in
    whether its dependencies install in the browser; with ``a11y``, in
    accessibility), and how many component files were checked. ``fetch``
    stands in for PyPI in tests."""
    from .cli import app_pyweft_files

    app_dir = app_dir.resolve()
    files = app_pyweft_files(app_dir)
    problems: list[Problem] = []
    with _app_on_path(app_dir):
        for rel in files:
            problems += _Checker(app_dir, rel, a11y).run()
    if deps:
        problems += _browser_dependencies(app_dir, fetch)
    # One file's failure shows again in every component that uses it.
    seen: set[tuple[str, int, str]] = set()
    unique = []
    for p in problems:
        if (p.file, p.line, p.message) not in seen:
            seen.add((p.file, p.line, p.message))
            unique.append(p)
    unique.sort(key=lambda p: (p.file, p.line, p.severity != "error"))
    return unique, len(files)


def _browser_dependencies(app_dir: Path, fetch: Any) -> list[Problem]:
    """Dependencies that won't install in the browser, against the line of
    pyproject.toml that brings each in."""
    from . import browser_deps
    from .cli import browser_packages

    requirements = browser_packages(app_dir)
    if not requirements:
        return []
    findings = browser_deps.check(requirements, **({"fetch": fetch} if fetch else {}))
    pyproject = app_dir / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.exists() else ""
    lines = text.splitlines()

    def line_of(name: str) -> int:
        for number, line in enumerate(lines, 1):
            quoted = re.findall(r"[\"']([^\"']+)[\"']", line)
            if any(browser_deps.normalise(re.split(r"[\s\[<>=!~;@(]", q, maxsplit=1)[0]) == name for q in quoted):
                return number
        return next((n for n, line in enumerate(lines, 1) if line.strip().startswith("dependencies")), 0)

    return [
        Problem("pyproject.toml", line_of(f.root), f.severity, f.code,
                f"in the browser: {f.message} (the desktop app isn't affected)")
        for f in findings
    ]


class _app_on_path:
    """The app folder importable (its .py modules), and stand-ins for the
    browser-only modules a code block may import (``js``, ``pyodide``)."""

    def __init__(self, app_dir: Path):
        self.app_dir = str(app_dir)
        self.added: list[str] = []

    def __enter__(self) -> None:
        sys.path.insert(0, self.app_dir)
        for name in _BROWSER_ONLY:
            if name not in sys.modules:
                sys.modules[name] = _Stub(name)
                self.added.append(name)

    def __exit__(self, *exc: Any) -> None:
        if self.app_dir in sys.path:
            sys.path.remove(self.app_dir)
        for name in self.added:
            sys.modules.pop(name, None)


class _Stub(types.ModuleType):
    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        return _Stub(f"{self.__name__}.{name}")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return _Stub(self.__name__ + "()")


# ------------------------------------------------------------------ checking


class _Checker:
    def __init__(self, app_dir: Path, rel: str, a11y: bool = True):
        self.a11y = a11y
        self.app_dir = app_dir
        self.rel = rel
        self.path = app_dir / rel
        self.src = self.path.read_text(encoding="utf-8")
        self.lines = self.src.splitlines()
        self.problems: list[Problem] = []

    def add(self, line: int, severity: str, code: str, message: str, file: str | None = None) -> None:
        if (file is None or file == self.rel) and line and ignored(self.lines, line, code):
            return  # <!-- pyweft-ignore: code --> just above the element
        self.problems.append(Problem(file or self.rel, line, severity, code, message))

    def run(self) -> list[Problem]:
        cls = self._load()
        if cls is not None:
            self.cls = cls
            self.known = self._known_names(cls)
            self._walk(cls.__template__, frozenset(), 0)
            if self.a11y:
                audit(cls.__template__, self.add, is_component_tag)
            self._shadowed_builtins()
        return self.problems

    # -------------------------------------------------------------- loading

    def _load(self) -> type | None:
        try:
            return load_component(self.path, root=self.app_dir)
        except TemplateError as exc:
            self._template_error(str(exc))
        except SyntaxError as exc:
            self.add(exc.lineno or 0, "error", "syntax", f"Python syntax error: {exc.msg}",
                     file=self._rel_of(exc.filename))
        except ModuleNotFoundError as exc:
            line, file = self._traceback_line(exc)
            self.add(line, "error", "import",
                     f"no module named {exc.name!r}: if it's a dependency, add it "
                     "(uv add ...) and install it here to check this file", file=file)
        except Exception as exc:  # the code block raised as it ran
            line, file = self._traceback_line(exc)
            self.add(line, "error", "code-block",
                     f"the code block failed as it ran: {type(exc).__name__}: {exc}", file=file)
        return None

    def _rel_of(self, filename: str | None) -> str:
        if not filename:
            return self.rel
        try:
            return Path(filename).resolve().relative_to(self.app_dir).as_posix()
        except ValueError:
            return self.rel

    def _traceback_line(self, exc: BaseException) -> tuple[int, str]:
        for frame in reversed(traceback.extract_tb(exc.__traceback__)):
            if frame.filename.endswith(".weft") or Path(frame.filename).is_relative_to(self.app_dir):
                return frame.lineno or 0, self._rel_of(frame.filename)
        return 0, self.rel

    def _template_error(self, message: str) -> None:
        file = self.rel
        m = re.match(r"^([\w./-]+\.weft): (.*)$", message, re.S)
        if m:
            file, message = m.group(1), m.group(2)
        line = int(found.group(1)) if (found := re.search(r"\bline (\d+)", message)) else 0
        missing = re.match(r"component <([\w.]+)> used in (\S+) but no", message)
        if missing:
            tag = missing.group(1)
            line = line or _line_of(self.path.read_text(encoding="utf-8") if file == self.rel
                                    else (self.app_dir / file).read_text(encoding="utf-8"), f"<{tag}")
            hint = _did_you_mean(tag, self._component_candidates(file, tag))
            message += hint
            self.add(line, "error", "unknown-component", message, file=file)
        else:
            self.add(line, "error", "template", message, file=file)

    def _component_candidates(self, file: str, tag: str) -> list[str]:
        """Tags that would resolve, for a "did you mean" on a missing one."""
        here = (self.app_dir / file).parent
        *prefix, _ = tag.split(".")
        if prefix:
            # A library imported in the code block (from pyweft_ui import ui)?
            target = _imported(self.app_dir / file, prefix[0])
            for part in prefix[1:]:
                target = getattr(target, part, None)
            if isinstance(target, ComponentLibrary):
                return [".".join(prefix) + "." + _camel(p.stem) for p in target._folder.glob("*.weft")]
            folder = self.app_dir.joinpath(*prefix)
            return [".".join(prefix) + "." + _camel(p.stem) for p in folder.glob("*.weft")]
        return [_camel(p.stem) for p in here.glob("*.weft")]

    # -------------------------------------------------------------- names

    def _known_names(self, cls: type) -> frozenset[str]:
        names = set(dir(cls)) | BUILTINS | {"self"}
        # Attributes set on self in the code (self._id = ... in on_init).
        try:
            tree = ast.parse(textwrap.dedent(split_source(self.src)[1]))
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "self" and isinstance(node.ctx, ast.Store):
                names.add(node.attr)
        return frozenset(names)

    def _expr(self, src: str, line: int, scope: frozenset[str], what: str, handler: bool = False) -> None:
        src = src.strip()
        if not src:
            return
        try:
            tree: ast.AST = ast.parse(src, mode="eval")
        except SyntaxError:
            if not handler:
                self.add(line, "error", "syntax", f"{what}: not a Python expression: {src!r}")
                return
            try:
                tree = ast.parse(src, mode="exec")
            except SyntaxError as exc:
                self.add(line, "error", "syntax", f"{what}: not Python: {src!r} ({exc.msg})")
                return
        visible = self.known | scope | ({"event"} if handler else set())
        finder = _Names()
        finder.visit(tree)
        # Expressions are compiled to functions in which a comprehension,
        # generator or lambda sees template names like any closure; only
        # statement handlers (count += 1) still run through exec.
        statement = isinstance(tree, ast.Module)
        for name, nested in finder.loads:
            if nested and statement and name not in BUILTINS:
                if nested in ("generator expression", "lambda"):
                    self.add(line, "error", "template-closure",
                             f"{what}: a {nested} in a statement handler can't see {name!r} "
                             "(statements run in a scope of their own): move the statement into a method")
                else:
                    self.add(line, "warning", "template-closure",
                             f"{what}: a {nested} in a statement handler can't see {name!r} on "
                             "Python 3.10/3.11: move the statement into a method to run everywhere")
                continue
            if name not in visible:
                self.add(line, "error", "unknown-name",
                         f"{what}: unknown name {name!r}" + _did_you_mean(name, self._suggestable(scope)))
        for name in finder.stores:
            if handler and name not in visible:
                self.add(line, "warning", "new-state",
                         f"{what}: sets {name!r}, which this component doesn't declare"
                         + _did_you_mean(name, self._suggestable(scope)))

    def _suggestable(self, scope: Iterable[str]) -> list[str]:
        own = [n for n in self.known if not n.startswith("_") and n not in BUILTINS
               and not hasattr(Component, n)]
        return own + list(scope)

    # -------------------------------------------------------------- walking

    def _walk(self, nodes: list[Any], scope: frozenset[str], line: int) -> None:
        for node in nodes:
            if isinstance(node, TStatic):
                for kind, text in node.parts:
                    if kind == "expr":
                        self._expr(text, line, scope, "{{ }}")
            elif isinstance(node, TIf):
                for cond, children in node.branches:
                    if cond is not None:
                        self._expr(cond, node.line or line, scope, "<If cond>")
                    self._walk(children, scope, node.line or line)
            elif isinstance(node, TFor):
                at = node.line or line
                self._expr(node.iter_src, at, scope, "<For each>")
                inner = scope | {node.var} | ({node.index_var} if node.index_var else set())
                if node.key_expr:
                    self._expr(node.key_expr, at, inner, "<For key>")
                    roots = [c for c in node.children if not _blank(c)]
                    if len(roots) > 1:
                        self.add(at, "error", "keyed-for",
                                 f"a keyed <For> must render one element per item, but its body has "
                                 f"{len(roots)}: wrap them in one element")
                self._walk(node.children, inner, at)
            elif isinstance(node, TSlot):
                at = node.line or line
                self._attrs(node.attrs, node.expr_attrs, at, scope, "<Slot>")
                self._walk(node.children, scope, at)
            elif isinstance(node, TFill):
                self._walk(node.children, scope, node.line or line)
            elif isinstance(node, TAwait):
                at = node.line or line
                self._expr(node.task, at, scope, "<Await task>")
                if node.key_expr:
                    self._expr(node.key_expr, at, scope, "<Await key>")
                self._walk(node.pending, scope, at)
                if node.then is not None:
                    self._walk(node.then, scope | {node.then_var}, at)
                if node.catch is not None:
                    self._walk(node.catch, scope | {node.catch_var}, at)
            elif isinstance(node, TDefer):
                if node.ready:
                    self._expr(node.ready, node.line or line, scope, "<Defer :ready>")
                self._walk(node.placeholder, scope, node.line or line)
                self._walk(node.children, scope, node.line or line)
            elif isinstance(node, THead):
                self._walk(node.children, scope, node.line or line)
            elif isinstance(node, THtml):
                self._expr(node.content, node.line or line, scope, "<Html :content>")
            elif isinstance(node, TElement):
                self._element(node, scope, node.line or line)

    def _attrs(self, attrs: dict, expr_attrs: dict, line: int, scope: frozenset[str], where: str) -> None:
        for name, parts in attrs.items():
            for kind, text in parts:
                if kind == "expr":
                    self._expr(text, line, scope, f"{where} {name}=")
        for name, src in expr_attrs.items():
            self._expr(src, line, scope, f"{where} :{name}=")

    def _element(self, node: TElement, scope: frozenset[str], line: int) -> None:
        where = f"<{node.tag}>"
        self._attrs(node.attrs, node.expr_attrs, line, scope, where)
        for name, src in node.class_toggles.items():
            self._expr(src, line, scope, f"{where} class:{name}=")
        for name, src in node.style_props.items():
            self._expr(src, line, scope, f"{where} style:{name}=")
        if node.key_expr:
            self._expr(node.key_expr, line, scope, f"{where} key=")
        for spec, handler in node.events.items():
            what = f"{where} @{spec}"
            if handler.strip().isidentifier():
                name = handler.strip()
                if name not in self.known | scope:
                    self.add(line, "error", "unknown-handler",
                             f"{what}: no method {name!r}" + _did_you_mean(name, self._suggestable(scope)))
            else:
                self._expr(handler, line, scope, what, handler=True)
        if node.bind and node.bind not in self.known:
            self.add(line, "error", "unknown-bind",
                     f"{where} @bind: no field {node.bind!r}" + _did_you_mean(node.bind, self._suggestable(())))
        if node.tag == "Dynamic":
            self._walk(node.children, scope, line)
            return
        if is_component_tag(node.tag):
            child = self._child(node.tag)
            if child is not None:
                self._component(node, child, scope, line)
                return
        elif "class" in node.attrs and "class" in node.expr_attrs:
            self.add(line, "warning", "class-replaced",
                     f"{where}: :class replaces class on the same element, so the static "
                     "classes are lost: keep class= and add the conditional ones with "
                     "class:name=\"condition\"")
        self._walk(node.children, scope, line)

    def _child(self, tag: str) -> type | None:
        registry = getattr(self.cls, "components", {}) or {}
        return registry.get(tag) or component_named(self.cls, tag)

    def _component(self, node: TElement, child: type, scope: frozenset[str], line: int) -> None:
        where = f"<{node.tag}>"
        props = declared_props(child)
        for name in [*node.attrs, *node.expr_attrs]:
            if name in props or name in _GLOBAL_ATTRS or name.startswith(("aria-", "data-")):
                continue
            hint = _did_you_mean(name, props)
            self.add(line, "warning", "unknown-prop",
                     f"{where}: {name!r} is not one of its props, so it goes to its root "
                     f"element as an attribute{hint}")
        emits = _emitted_events(child)
        for spec in node.events:
            event = spec.split(".")[0]
            if "." in spec:
                self.add(line, "error", "component-event-modifier",
                         f"{where} @{spec}: a component's events take no modifiers")
            if emits is not None and event not in emits and f"on_{event}" not in props:
                self.add(line, "warning", "unknown-event",
                         f"{where} @{event}: it never emits {event!r}"
                         + _did_you_mean(event, sorted(emits)))
        if node.bind and "value" not in props:
            self.add(line, "error", "component-bind",
                     f"{where} @bind: it has no value prop (a bindable component declares "
                     "value and emits update)")
        # Content between the tags: named fills, and the default slot.
        slots = _slots(child)
        loose = [c for c in node.children if not isinstance(c, TFill) and not _blank(c)]
        if loose and slots is not None and "default" not in slots:
            self.add(line, "error", "unknown-slot",
                     f"{where}: it has no default slot, so the content between its tags "
                     "would never show")
        for child_node in node.children:
            if isinstance(child_node, TFill):
                fill_line = child_node.line or line
                if slots is not None and child_node.name not in slots:
                    self.add(fill_line, "error", "unknown-slot",
                             f"{where} <Fill name={child_node.name!r}>: it has no such slot"
                             + _did_you_mean(child_node.name, sorted(set(slots) - {"default"})))
                inner = scope | (slots or {}).get(child_node.name, frozenset())
                self._walk(child_node.children, inner, fill_line)
        if loose:
            self._walk(loose, scope | (slots or {}).get("default", frozenset()), line)

    # -------------------------------------------------------------- code

    def _shadowed_builtins(self) -> None:
        """A field or def named like a builtin hides it in the code block:
        `max: int = 5` then `max(a, b)` calls the field."""
        code = split_source(self.src)[1]
        span = block_spans(self.src).get("code")
        pad = "\n" * self.src.count("\n", 0, span[0]) if span else ""
        try:
            tree = ast.parse(pad + textwrap.dedent(code))
        except SyntaxError:
            return
        defined: set[str] = set()
        for stmt in tree.body:
            targets: list[ast.AST] = []
            if isinstance(stmt, ast.Assign):
                targets = stmt.targets
            elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
                targets = [stmt.target]
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(stmt.name)
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                defined.update((a.asname or a.name).split(".")[0] for a in stmt.names)
            for t in targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
        hidden = defined & BUILTINS
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in hidden:
                name = node.func.id
                self.add(node.lineno, "warning", "shadowed-builtin",
                         f"{name}(...) calls this component's {name!r}, not Python's builtin: "
                         f"the field or def named {name!r} hides it in this code block "
                         f"(rename it, or keep the builtin first: _{name} = {name})")


# ------------------------------------------------------------------ helpers


class _Names(ast.NodeVisitor):
    """Names an expression reads from outside itself, and, for each, whether
    it is read inside a comprehension, generator or lambda (which run in a
    scope of their own)."""

    def __init__(self) -> None:
        self.loads: list[tuple[str, str | None]] = []
        self.stores: list[str] = []
        self._bound: list[set[str]] = []
        self._nested: list[str] = []

    def _bound_here(self, name: str) -> bool:
        return any(name in b for b in self._bound)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if not self._bound_here(node.id):
                self.loads.append((node.id, self._nested[-1] if self._nested else None))
        elif not self._nested:
            self.stores.append(node.id)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name) and not self._bound_here(node.target.id):
            self.loads.append((node.target.id, self._nested[-1] if self._nested else None))
        self.visit(node.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                self.visit(default)
        args = node.args
        names = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
        names |= {a.arg for a in (args.vararg, args.kwarg) if a}
        self._enter("lambda", names, [node.body])

    def _comprehension(self, node: Any, kind: str, parts: list[ast.AST]) -> None:
        # The first iterable is evaluated outside; the rest inside.
        self.visit(node.generators[0].iter)
        bound: set[str] = set()
        for gen in node.generators:
            for target in ast.walk(gen.target):
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        inner: list[ast.AST] = []
        for i, gen in enumerate(node.generators):
            if i:
                inner.append(gen.iter)
            inner.extend(gen.ifs)
        self._enter(kind, bound, inner + parts)

    def _enter(self, kind: str, bound: set[str], nodes: list[ast.AST]) -> None:
        self._bound.append(bound)
        self._nested.append(kind)
        for n in nodes:
            self.visit(n)
        self._nested.pop()
        self._bound.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comprehension(node, "list comprehension", [node.elt])

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._comprehension(node, "set comprehension", [node.elt])

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._comprehension(node, "dict comprehension", [node.key, node.value])

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._comprehension(node, "generator expression", [node.elt])


def _blank(node: Any) -> bool:
    return isinstance(node, TStatic) and all(k == "static" and not t.strip() for k, t in node.parts)


def _did_you_mean(name: str, candidates: Iterable[str]) -> str:
    close = difflib.get_close_matches(name, list(set(candidates)), n=1, cutoff=0.75)
    if not close:
        lowered = {c.lower(): c for c in candidates}
        if name.lower() in lowered:
            close = [lowered[name.lower()]]
    return f" (did you mean {close[0]!r}?)" if close else ""


def _camel(stem: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in stem.split("_"))


def _line_of(text: str, needle: str) -> int:
    at = text.find(needle)
    return text.count("\n", 0, at) + 1 if at >= 0 else 0


def _imported(path: Path, name: str) -> Any:
    """What ``name`` is bound to by the import statements of a file's code
    block (only those: the rest of the block isn't run)."""
    try:
        tree = ast.parse(textwrap.dedent(split_source(path.read_text(encoding="utf-8"))[1]))
    except (SyntaxError, TemplateError, OSError):
        return None
    namespace: dict[str, Any] = {}
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            try:
                exec(compile(ast.Module(body=[stmt], type_ignores=[]), str(path), "exec"), namespace)
            except Exception:
                pass
    return namespace.get(name)


_EMITS: dict[type, frozenset[str] | None] = {}


def _emitted_events(cls: type) -> frozenset[str] | None:
    """Event names a component emits, found in its code and template; None
    when that can't be told (an emit with a computed name, or no source)."""
    if cls in _EMITS:
        return _EMITS[cls]
    src = getattr(cls, "__weft_src__", None)
    if not src:
        _EMITS[cls] = None
        return None
    sources = [textwrap.dedent(split_source(src)[1])]

    def gather(nodes: list[Any]) -> None:
        for node in nodes:
            if isinstance(node, TElement):
                sources.extend(node.events.values())
            for children in subtrees(node):
                gather(children)

    gather(cls.__template__)
    names: set[str] = set()
    for text in sources:
        try:
            tree = ast.parse(text.strip())
        except SyntaxError:
            continue
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and call.args):
                continue
            func = call.func
            if not ((isinstance(func, ast.Attribute) and func.attr == "emit")
                    or (isinstance(func, ast.Name) and func.id == "emit")):
                continue
            arg = call.args[0]
            constants = [n.value for n in ast.walk(arg) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            if not constants or not _only_constants(arg):
                _EMITS[cls] = None
                return None
            names.update(constants)
    result = frozenset(names)
    _EMITS[cls] = result
    return result


def _only_constants(node: ast.AST) -> bool:
    """"open" or `"open" if x else "close"`: every possible value is literal."""
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.IfExp):
        return _only_constants(node.body) and _only_constants(node.orelse)
    return False


def _slots(cls: type) -> dict[str, frozenset[str]] | None:
    """Each slot a component renders, with the names of its slot props."""
    template = getattr(cls, "__template__", None)
    if template is None:
        return None
    found: dict[str, set[str]] = {}

    def walk(nodes: list[Any]) -> None:
        for node in nodes:
            if isinstance(node, TSlot):
                found.setdefault(node.name, set()).update(node.attrs, node.expr_attrs)
            for children in subtrees(node):
                walk(children)

    walk(template)
    return {name: frozenset(props) for name, props in found.items()}


def format_report(problems: list[Problem], files: int) -> str:
    errors = sum(p.severity == "error" for p in problems)
    warnings = len(problems) - errors
    lines = [str(p) for p in problems]
    if not problems:
        lines.append(f"No problems found in {files} component file{'s' if files != 1 else ''}.")
    else:
        lines.append(f"{errors} error{'s' if errors != 1 else ''}, {warnings} warning"
                     f"{'s' if warnings != 1 else ''} in {files} component file{'s' if files != 1 else ''}.")
    return "\n".join(lines)


def as_json(problems: list[Problem], files: int) -> dict[str, Any]:
    return {"files": files, "problems": [asdict(p) for p in problems]}


__all__ = ["Problem", "check_app", "format_report", "as_json"]
