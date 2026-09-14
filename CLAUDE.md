# CLAUDE.md

Project context for Claude Code. Read this before changing anything.

## What this is

**PyWeft** — a Blazor-shaped UI framework for Python. XML markup, Python
code-behind, one render core targeting desktop (webview) now, web (Pyodide) and
mobile (Briefcase/Kivy) later.

The name is **PyWeft** (import `pyweft`, CLI `pyweft`): the weft is the thread
woven through the warp to make fabric. Component files keep the short `.weft`
extension deliberately.

Python >= 3.10. Zero runtime dependencies — keep it that way in the core.
`pytest` is the only dev dependency.

## The architecture bet (do not violate this)

Blazor doesn't render native widgets, it renders HTML. `BlazorWebView` is a
webview hosting the same DOM, and Blazor Server proves component code can live
in a different process from the renderer and ship only diffs.

Copying that makes three targets nearly free:

| Target | Where Python runs | Renderer | Transport |
|---|---|---|---|
| Desktop | CPython process | webview (WebView2 / WKWebView / WebKitGTK) | JSON over webview IPC |
| Web | Pyodide in browser | same DOM | in-process call |
| Mobile | CPython via Briefcase / Kivy | webview | same bridge as desktop |

**The one rule this codebase enforces: the render core never touches a DOM.**
It emits JSON-serialisable patch op dicts. Porting to a new target means
writing a transport, not a renderer.

If a change would make the core import a webview library, reach for `document`,
or assume a specific host, it is the wrong change. Push it into the host layer.

The rejected alternative was a native-widget abstraction over Qt/GTK. That is
rebuilding Flutter and it makes the web target genuinely painful. Don't
relitigate this without a strong reason.

## Current state

**Stage 1 complete and tested: the render core.** **Stage 2 working: the web
target** — the same core running in the browser under Pyodide (CPython on
WASM), chosen as the first visible target because it needs no bridge: Python
and the DOM share a process. Desktop (pywebview) reuses `web/runtime.js`
unchanged.

```
src/pyweft/
  vdom.py         Text / Element dataclasses, to_dict()
  expressions.py  compile-once expression cache, Scope, {{ }} interpolation
  parser.py       .weft -> template tree (TStatic/TElement/TIf/TFor) + code block
  component.py    Component base class, lifecycle, .weft loader + SFC resolution
  renderer.py     template tree -> vdom, handler table, event dispatch, composition
  differ.py       keyed reconciliation -> patch ops
  dommodel.py     reference patch applier (executable spec for runtime.js)
  cli.py          pyweft new / run / build (host-only, never shipped to browser)
  static/
    runtime.js    JS twin of dommodel.py — applies ops to real DOM, sends events
    shell.html    app shell template; CLI fills placeholders (files, packages, css)
tests/            464 tests, 400 of them randomised
examples/         counter.weft + demo.py (headless); todo/ (composed browser app)
```

```bash
pip install -e ".[dev]"
pytest                     # must stay green
python examples/demo.py    # render -> event -> diff -> apply, headless
pyweft run examples/todo     # live in the browser at http://127.0.0.1:8642/
pyweft new myapp             # scaffold; pyweft build myapp -> static dist/
```

A pyweft app is a directory: `app.weft` root component, sibling `.weft`
components, optional `.css` files, and an ordinary `pyproject.toml` whose
`[project].dependencies` the shell installs **in the browser** via micropip at
load (pure-Python wheels or Pyodide-prebuilt only). Users manage those deps
with `uv add` / pip — do not invent a separate manifest format.

`static/runtime.js` must stay in lockstep with `dommodel.py`; the Python file
is the spec. It has no automated tests yet — verify by exercising the todo
demo in a browser (bind, conditional swap, keyed insert/remove, emit) until a
JS test rig exists.

## Component format

```xml
<template>
  <div class="counter">
    <h1>Count: {{ count }}</h1>
    <input @bind="name" placeholder="your name" />
    <button @click="increment">+1</button>

    <If cond="count == 0"><p>click the button</p></If>
    <ElseIf cond="count > 3"><p>a lot{{ greeting }}</p></ElseIf>
    <Else><p>keep going</p></Else>

    <ul>
      <For each="entry in history" key="entry['id']" index="i">
        <li @click="forget(entry)">{{ i }}. {{ entry['label'] }}</li>
      </For>
    </ul>
  </div>
</template>

<code>
count: int = 0
name: str = ""
history: list = []

def increment(self):
    self.count += 1
    self.history.append({"id": self.count, "label": f"click {self.count}"})

def forget(self, entry):
    self.history = [h for h in self.history if h["id"] != entry["id"]]
</code>
```

Control flow is **elements** (`<If>`/`<ElseIf>`/`<Else>`/`<For>`), not
Razor-style `@if` blocks. Lexing indentation-sensitive Python inside markup is a
tarpit; elements sidestep it and read closer to XAML. Don't add a Razor-style
block syntax.

Directive semantics:
- `{{ expr }}` — interpolates in text and attribute values
- `:attr="expr"` — Vue-style expression binding. On a plain element the result
  is stringified (`None`/`False` drop the attribute, `True` keeps it
  valueless); on a component it passes the *typed* value as a prop
- `@click="handler"` — bare name calls that method; anything else is evaluated,
  so `@click="forget(entry)"` works inside a loop
- `@bind="field"` — two-way, coerces back to the field's existing type so a
  bound `int` doesn't become a string on first keystroke
- `key="..."` on `<For>` — stable row identity across reorders

## Component composition

A capitalised tag that names an entry in the owner's `components` registry is a
child component: `<TodoItem :item="item" @remove="remove(event)" />`.

- **Resolution**: `load_component()` resolves `<TodoItem>` to `TodoItem.weft`
  or `todo_item.weft` next to the referencing file, Vue-SFC-style, recursively,
  with cycle detection. An explicit `components = {...}` dict in the code block
  (or passed to `component_from_source`) overrides.
- **Props** flow down every render: interpolated attrs as strings, `:attrs` as
  evaluated Python values.
- **Events up**: `@remove="..."` on a component tag becomes an `on_remove`
  callback prop bound to the parent's scope, with the emitted payload available
  as `event`. The child calls `self.emit("remove", payload)`. Falsy payloads
  pass through untouched — don't reintroduce `event or {}`.
- **Identity**: instances are cached by template path (keyed segments where
  available) so child state survives parent re-renders. Key components inside
  a `<For>` or their state follows position, not data.
- **Lifecycle**: `on_init` on first appearance, `on_dispose` when a render no
  longer produces the instance's path.
- Handlers and `@bind` resolve against the *owning* component
  (`scope.component`), never the root — that is what makes bare names in child
  templates work.

## Decisions with reasons (don't silently reverse these)

**`.weft`, not `.pyx`.** `.pyx` is Cython's extension and breaks editors and
build tooling in the same tree.

**`@click` works via preprocessing.** XML attribute names cannot start with
`@`, so `rewrite_at_directives()` in `parser.py` is a small state machine that
rewrites `@click=` to `py-at-click=` before the XML parser sees it, skipping
`@` inside text and attribute values. `py-at-click` also works directly. If you
hit an edge case, fix the state machine rather than falling back to a bare regex.

**The `<code>` block is cut out by string scanning before any XML parsing.**
Python source is full of `<`, `>`, `&` and would blow up an XML parser.

**Templates must be well-formed XML.** This buys the stdlib `xml.etree` parser
instead of a bespoke HTML5 tokenizer — a large amount of complexity to skip.
Don't swap in an HTML5 parser without a real forcing reason.

**Reactivity is Blazor's, not React's.** No observables, no proxies. A handler
runs, the component re-renders, the tree is diffed. Mutating state outside a
handler means calling `state_has_changed()` yourself. That's ~30 lines instead
of ~800 for a signals system and covers almost everything. Fine-grained
reactivity can be added later without changing the component API.

**Mutable class-level defaults are deep-copied per instance** in
`Component.__init__`. `history: list = []` in a code block would otherwise be
shared across instances — a Python footgun that would look like a framework bug.

## Patch op contract

Structural ops carry the **parent** path plus an index. In-place ops carry the
**node's own** path.

| Op | Payload |
|---|---|
| `insert` / `remove` / `replace` | parent `path`, `index`, (`node`) |
| `move` | parent `path`, `from`, `to` (pop then insert) |
| `set_text` | node `path`, `text` |
| `set_attrs` / `set_events` | node `path`, `set` dict, `remove` list |
| `set_key` | node `path`, `key` |

**Ordering invariant:** at every level, all structural ops for a parent are
emitted before any op that descends into that parent's children. Indices in
descendant ops therefore already reflect the reconciled order, and a consumer
applies the list front to back with zero bookkeeping. Any change to `differ.py`
must preserve this.

`dommodel.py` is the executable spec — whatever it does to dicts, the eventual
`runtime.js` must do to real DOM nodes. Keep them in lockstep.

`_diff_keyed` evicts keys absent from the new list **before** reconciling
survivors. Without that pass, deleting one middle row makes every row below it
look out of place and produces O(n) moves for what should be one removal.

## Handler identity

Handler ids are path strings from **keys where available**, index otherwise:
`i:0/i:5/k:3#click`. Purely positional ids would change for every row whenever a
list reordered, churning event bindings on every move. Keyed segments mean a row
keeps its id wherever it lands.

The handler table is rebuilt every render, so ids for vanished nodes disappear
and a late event against a stale id is a no-op, not a crash. Preserve that
property — it matters more once events cross an async bridge.

## Testing rules

**Test the differ by convergence, not op sequences.** Apply the patches to the
old tree and assert the result equals the new tree. Asserting exact op lists
locks in the current algorithm and still misses the index bugs that actually
bite. 400 of the 442 tests are randomised trees checked this way; that is what
caught the middle-row deletion cascade.

When adding differ behaviour, add randomised cases, not just hand-written ones.
`pytest` must stay green before any commit.

## Known limitations (accepted for now)

- No slots yet — a component tag with children is a `TemplateError`. **This is
  the next composition gap.**
- Comprehensions and lambdas inside `{{ }}` build their own frame and can't see
  scope variables (CPython `eval` semantics). Compute them in the code block.
- A keyed `<For>` body must produce exactly one element per item.
- Whitespace-only text containing a newline is dropped as formatting.
- `key` is reserved as an element attribute name.
- Renderer is a tree-walking interpreter. Codegen-to-Python-source is a later
  optimisation, only if profiling demands it.

## Roadmap

**Done:** JS runtime mirroring `dommodel.py`; Pyodide (web) target — moved up
from "later" because it was the cheapest path to pixels and proves the
transport-agnostic bet; component composition (props, `:expr` bindings,
`emit`, lifecycle, SFC-style file resolution) — `examples/todo/` is the
reference usage.

The framework is tracking Vue feature-by-feature. Parity so far: `v-if/v-for`
(`<If>/<For>`), `v-model` (`@bind`), `v-on` (`@click`), `v-bind` (`:attr`),
computed (`@property`), components/props/emit, SFC files (`.weft`).

**Done (continued):** `pyweft` CLI (`new` / `run` / `build`) with PyPI deps read
from the app's `pyproject.toml` and micropip-installed in the browser.

**Finishes the PoC:**
1. Slots (content projection into component children)
2. pywebview host with the bridge wired both ways (reuses `static/runtime.js`)
3. asyncio render queue (async handlers, re-entrant events serialised)
4. Hot-reload for `pyweft run` (currently refresh-on-save)

**Later (Vue parity):** watchers, provide/inject, scoped CSS, transitions,
router, store. **Later (targets):** Briefcase packaging, render codegen,
devtools.

## Working style

- Small, reviewable changes. One concern per commit.
- Comments explain *why*, not *what*. Don't narrate the code.
- No new runtime dependencies in `src/pyweft/` without discussion.
- If a design decision above blocks you, say so and argue the case — don't
  quietly work around it.
