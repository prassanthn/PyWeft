# PyWeft — Getting Started

PyWeft is a UI framework for Python shaped like Blazor and flavored like Vue:
you write components as `.weft` files — an XML template plus a Python code
block — and PyWeft renders them to HTML, updating the page with minimal diffs
whenever state changes.

Your component code runs in **real CPython**. In the browser it runs on
Pyodide (CPython compiled to WebAssembly), so there is no transpilation and no
JavaScript to write. The same render core will later drive desktop apps
(pywebview) and mobile — only the transport differs.

```
.weft file ──parse──▶ template ──render──▶ virtual DOM ──diff──▶ patch ops ──▶ real DOM
                          ▲                                                      │
                          └────────────── state change ◀───── events ◀───────────┘
```

- **Requirements:** Python ≥ 3.10. The core has zero runtime dependencies.
- **Status:** working proof of concept. APIs may still move.

---

## 1. Install

PyWeft is not on PyPI yet, so install it straight from GitHub. With uv:

```bash
uv init myproject && cd myproject
uv add git+https://github.com/prassanthn/PyWeft.git
uv run pyweft new myapp
uv run pyweft run myapp
```

With pip, the equivalent is
`pip install git+https://github.com/prassanthn/PyWeft.git`, then `pyweft new`
and `pyweft run` directly.

To hack on the framework itself, clone it and install in editable mode:

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync --extra dev      # or: pip install -e ".[dev]"
uv run pytest            # 464 tests should pass
```

To see it working immediately, run the bundled todo app from the clone:

```bash
uv run pyweft run examples/todo
```

Then open <http://127.0.0.1:8642/> — a todo app written entirely in Python,
running in your browser.

---

## 2. Your first component

A `.weft` file has two parts: a `<template>` (well-formed XML — close your
tags, quote your attributes) and a `<code>` block (plain Python, no
indentation gymnastics).

```xml
<template>
  <div class="hello">
    <h1>Hello, {{ name or "stranger" }}!</h1>
    <input @bind="name" placeholder="your name" />
    <button @click="cheer">cheer</button>
    <p>{{ cheers }} cheers so far</p>
  </div>
</template>

<code>
name: str = ""
cheers: int = 0

def cheer(self):
    self.cheers += 1
</code>
```

How the code block works:

- **State** is declared as annotated class attributes (`cheers: int = 0`).
  Mutable defaults like `history: list = []` are safe — each component
  instance gets its own copy.
- **Handlers** are methods taking `self`. After a handler runs, the component
  re-renders automatically and the DOM is patched.
- **Computed values** are ordinary Python properties:

  ```python
  @property
  def remaining(self):
      return sum(1 for t in self.items if not t["done"])
  ```

### How state actually works

There is no change tracking. A variable in the code block is a plain
attribute on the component; the template reads it by name, and a handler
writes it with ordinary assignment (`self.cheers += 1`). What makes the UI
update is the render cycle, borrowed from Blazor:

1. An event arrives and your handler runs.
2. The component is marked dirty and re-rendered in full.
3. The new tree is diffed against the previous one.
4. Only the differences are applied to the page.

The framework never asks *whether* `cheers` changed — it re-renders after
every event and lets the differ find out what moved. That is why there are
no observables, no `useState`, no signals, and why a `@property` is
recomputed for free: every render re-evaluates the template.

The one case you must handle yourself is state that changes **outside a
handler** — a timer, a websocket message, an async callback. Nothing
triggers the re-render, so call `state_has_changed()` after the mutation:

```python
def on_message(self, msg):        # invoked by something other than the UI
    self.items.append(msg)
    self.state_has_changed()      # schedule a re-render
```

State belongs to the instance that declared it. To share data between
components, pass it down as props and send changes up with `emit` (section
4). A cross-component store and per-field watchers are on the roadmap; both
will sit on top of this model, not replace it.

---

## 3. Template syntax reference

| Syntax | Vue equivalent | Meaning |
|---|---|---|
| `{{ expr }}` | `{{ expr }}` | Interpolate a Python expression in text or attribute values |
| `:attr="expr"` | `v-bind` | Bind an attribute to an expression. `None`/`False` drop the attribute, `True` keeps it valueless (`:disabled="busy"`), anything else is stringified. On a component, passes the **typed** value as a prop |
| `@click="handler"` | `v-on` | A bare name calls that method; any other expression is evaluated, so `@click="remove(item)"` works |
| `@bind="field"` | `v-model` | Two-way binding on inputs. Coerces back to the field's existing type, so a bound `int` stays an `int` |
| `<If cond="...">` / `<ElseIf cond="...">` / `<Else>` | `v-if` / `v-else-if` / `v-else` | Conditional rendering. Branch elements must be adjacent siblings |
| `<For each="item in items" key="item['id']" index="i">` | `v-for` + `:key` | Loop. `key` gives rows stable identity across reorders (always use it for dynamic lists); `index` is optional |
| `<PascalCaseTag ... />` | component | Renders a child component (see below) |

Expressions are real Python, evaluated against the component's state plus any
loop variables. One caveat: comprehensions and lambdas inside `{{ }}` can't
see scope variables (CPython `eval` semantics) — compute those in the code
block instead.

---

## 4. Composing components

Any capitalized tag is a child component. PyWeft resolves `<TodoItem>` to
`TodoItem.weft` or `todo_item.weft` **in the same directory** as the file that
uses it — like Vue single-file components, but with zero import boilerplate.
Resolution is recursive (children can have children) and a circular reference
is reported as an error rather than looping.

A complete two-file example, taken from `examples/todo/`:

```xml
<!-- todo_item.weft — the child -->
<template>
  <li class="todo-item">
    <span :class="'done' if item['done'] else None" @click="emit('toggle', item)">
      {{ item['text'] }}
    </span>
    <button class="remove" @click="emit('remove', item)">✕</button>
  </li>
</template>

<code>
item: dict = {}
</code>
```

```xml
<!-- app.weft — the parent -->
<template>
  <ul>
    <For each="item in items" key="item['id']">
      <TodoItem :item="item" @toggle="toggle(event)" @remove="remove(event)" />
    </For>
  </ul>
</template>

<code>
items: list = []

def toggle(self, item):
    item["done"] = not item["done"]

def remove(self, item):
    self.items = [i for i in self.items if i["id"] != item["id"]]
</code>
```

Both files live in the app directory; `pyweft run` picks them up with no
registration step. The rest of this section explains each piece.

**Props go down.** Use plain attributes for strings, `:attr` for typed values:

```xml
<TodoItem :item="item" title="row" />
```

In the child, props are just state fields that the parent overwrites on every
render — declare them with defaults:

```python
item: dict = {}
title: str = ""
```

### Events: emitting and listening

There are two kinds of `@` events, and they are handled differently:

- `@click` on a **plain element** (`<button @click="cheer">`) is a DOM event.
  The browser fires it and the component whose template contains the element
  handles it.
- `@remove` on a **component tag** (`<TodoItem @remove="...">`) is a custom
  event. Nothing in the browser fires it — the child raises it by calling
  `emit`, and the parent listens.

**Emitting, in the child.** Call `emit(name, payload)` from a template
expression or from a method. The payload is optional and can be any Python
value; falsy values like `0`, `""` and `False` pass through unchanged.

```xml
<!-- todo_item.weft -->
<button @click="emit('remove', item)">✕</button>
<button @click="save">save</button>
```

```python
def save(self):
    ...
    self.emit("saved")                 # no payload
    self.emit("changed", {"id": self.item["id"], "text": self.draft})
```

**Listening, in the parent.** Put `@<name>` on the child's tag. The value is
evaluated in the parent's scope, with the payload available as `event`:

```xml
<For each="item in items" key="item['id']">
  <TodoItem :item="item"
            @remove="remove(event)"
            @changed="update(item, event)"
            @saved="mark_saved" />
</For>
```

- `@remove="remove(event)"` — any expression works, so you can mix loop
  variables with the payload, as `@changed` does.
- `@saved="mark_saved"` — a bare method name is called directly. It receives
  the payload if it declares a parameter, and nothing otherwise.

After the parent's handler runs the parent re-renders, so any state it changed
flows back down to the child as fresh props in the same cycle.

**How it connects.** `@remove="..."` on the tag becomes an `on_remove`
callback set on the child as a prop, and `self.emit("remove", x)` simply looks
up `on_remove` and calls it. Consequences worth knowing:

- Emitting an event the parent did not subscribe to is a no-op, as in Vue.
- `emit` returns whatever the parent's handler returned (`None` if nobody
  listened), so a child can ask the parent for a decision.
- Use lowercase identifier-style event names (`item_removed`, not
  `itemRemoved` or `item-removed`) so the `on_` prop name stays a valid
  Python attribute.

**State stays put.** A child keeps its internal state across parent
re-renders. Inside a `<For>`, the loop's `key` also keys the child instances,
so their state follows the data when rows reorder.

**Lifecycle:** `on_init(self)` runs once before the first render;
`on_dispose(self)` runs when the component disappears (e.g. its `<If>` went
false).

**Overriding the file lookup.** A `components` dict in the code block wins
over the sibling-file convention, which is how you pull a component from
another directory or give it a different tag name:

```python
from pyweft import load_component

components = {"Row": load_component("widgets/row.weft")}
```

From plain Python, `component_from_source(src, components={...})` accepts the
same dict.

Not yet supported: children inside a component tag (slots) — you'll get a
clear error, so pass content as a prop for now; and `@bind` directly on a
component (bind inside the child's own template instead).

---

## 5. Starting a new project

```bash
uv run pyweft new myapp
uv run pyweft run myapp
```

(Drop the `uv run` prefix if you installed with pip.) That's it — `new` scaffolds the project, `run` serves it. Open
`http://127.0.0.1:8642/`, edit a file, refresh: no build step; components are
compiled in the browser at load time.

A scaffolded app looks like this:

```
myapp/
  pyproject.toml    # name + dependencies — a completely ordinary pyproject
  app.weft          # root component (must be named app.weft)
  styles.css        # any .css files here are included automatically
```

Add more components as sibling `.weft` files — `<TodoItem>` in a template
finds `todo_item.weft` automatically.

### Using PyPI packages

Declare dependencies the normal Python way, with uv or pip:

```bash
cd myapp
uv add humanize        # or: edit dependencies = [...] in pyproject.toml
```

`pyweft run` reads `[project].dependencies` from your `pyproject.toml` and
installs those packages **inside the browser** (via Pyodide's micropip, from
PyPI) before your components load. So this just works in a component:

```python
import humanize

@property
def remaining_label(self):
    return humanize.apnumber(self.remaining)   # 3 -> "three"
```

Because the same `pyproject.toml` drives both, `uv sync`/`pip install -e .`
gives you identical packages locally for tests and tooling.

One constraint, inherited from the browser: a package must be **pure Python**
(most are) or one of the ~250 packages Pyodide ships prebuilt (numpy, pandas,
pillow, matplotlib, …). Packages needing raw sockets or subprocesses won't
work in a browser regardless.

### Building for deployment

```bash
uv run pyweft build myapp              # writes myapp/dist/
uv run pyweft build myapp --out site   # or pick the output folder
```

`dist/` is a fully static site. There is no compile step: your `.weft` files
ship verbatim and are parsed in the browser at load, and the dependencies
from your `pyproject.toml` are written into `index.html` for micropip to
install on first visit.

```
dist/
  index.html        shell: loads Pyodide, installs deps, boots app.weft
  runtime.js        applies DOM patches, sends events back to Python
  pyweft-src/*.py   the framework, served to the browser
  app/              your .weft components and .css files, copied as-is
```

**Check it locally** the way a host will serve it before deploying:

```bash
cd myapp/dist
python -m http.server 8000             # open http://localhost:8000/
```

Open it over http, not as a `file://` URL — the shell fetches its own files
and browsers block that from the local filesystem. The first visit downloads
Pyodide (about 10 MB), so allow a few seconds before the status line reads
"Running".

**Deploy the folder.** There is no server-side Python, so any static host
works:

- **GitHub Pages** — push `dist` to a `gh-pages` branch and enable Pages on
  it: `git subtree push --prefix dist origin gh-pages`. For deploy-on-push,
  add a GitHub Actions workflow that runs `pyweft build` and uploads `dist`
  with `actions/deploy-pages`.
- **Netlify / Vercel** — drag `dist` onto the dashboard, or
  `netlify deploy --dir dist --prod`.
- **S3 and similar** — `aws s3 sync dist s3://my-bucket --delete` with static
  website hosting enabled on the bucket.
- **Your own server** — copy `dist` into the nginx or Apache document root.

**Before going live:**

- The visitor's browser needs internet access: Pyodide comes from the
  jsdelivr CDN and dependencies from PyPI at runtime. Air-gapped hosting
  would need those vendored, which the CLI does not do yet.
- `.weft` files are served as plain text, so your component source is visible
  in devtools — the same as any client-side framework.
- `dist/` is a snapshot. `pyweft run` re-reads files on refresh, but you must
  rebuild after every change you want deployed.
- Subpath hosting works without configuration: every reference in
  `index.html` is relative, so the app runs at `/` or `/myapp/` alike.
- A desktop executable is not available yet; the pywebview host and
  Briefcase packaging are on the roadmap. The static site is the only
  shippable form today.

---

## 6. Using the engine from plain Python

The whole pipeline also runs headlessly — that's how you unit-test components
without a browser:

```python
from pyweft import load_component, Renderer, diff

App = load_component("myapp/app.weft")
app = App()
renderer = Renderer(app)

tree = renderer.render()              # virtual DOM (Element/Text nodes)

# find a handler id on a rendered element and fire it, as the browser would
button = tree[0].children[1]
renderer.dispatch(button.events["click"], {})

new_tree = renderer.render()
patches = diff(tree, new_tree)        # JSON-serialisable patch ops
assert app.cheers == 1
```

`examples/demo.py` walks the full render → event → diff → apply cycle in the
terminal, and `tests/test_compose.py` shows the patterns for testing composed
components.

---

## 7. What's here and what's coming

Working today: templates, expression/attribute binding, two-way `@bind`,
conditionals, keyed lists, components with props + events + lifecycle,
computed properties, browser rendering via Pyodide, PyPI dependencies via
pyproject.toml, and the `pyweft new` / `run` / `build` CLI.

Coming next, roughly in order: slots, a pywebview **desktop** host (same
components, native window), async handlers, hot-reload for `pyweft run`,
watchers, scoped CSS.

