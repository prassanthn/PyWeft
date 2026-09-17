# PyWeft — Getting Started

PyWeft is a UI framework for Python: you write components as `.weft` files — an XML template plus a Python code
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
uv run pytest            # 507 tests should pass
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
update is the render cycle:

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

| Syntax | Meaning |
|---|---|
| `{{ expr }}` | Interpolate a Python expression in text or attribute values |
| `:attr="expr"` | Bind an attribute to an expression. `None`/`False` drop the attribute, `True` keeps it valueless (`:disabled="busy"`), anything else is stringified. On a component, passes the **typed** value as a prop |
| `@click="handler"` | A bare name calls that method; an expression is evaluated, so `@click="remove(item)"` works; simple statements run inline, so `@click="count += 1"` and `@click="show = not show"` work without a method |
| `@bind="field"` | Two-way binding on inputs. Coerces back to the field's existing type, so a bound `int` stays an `int` |
| `<If cond="...">` / `<ElseIf cond="...">` / `<Else>` | Conditional rendering. Branch elements must be adjacent siblings |
| `<For each="item in items" key="item['id']" index="i">` | Loop. `key` gives rows stable identity across reorders (always use it for dynamic lists); `index` is optional |
| `<PascalCaseTag ... />` | Renders a child component (see below) |

Expressions are real Python, evaluated against the component's state plus any
loop variables. `self` is the component, so `{{ self.count }}` is the explicit
spelling of `{{ count }}`. One caveat: comprehensions and lambdas inside
`{{ }}` can't see scope variables (CPython `eval` semantics) — compute those
in the code block instead.

### Inline handlers

An event attribute accepts three forms. Pick the smallest one that fits:

```xml
<button @click="increment">+1</button>              <!-- 1. call a method -->
<button @click="remove(item)">remove</button>        <!-- 2. an expression -->
<button @click="count += 1">+1</button>              <!-- 3. inline statements -->
```

1. **A bare name** calls that method. If the method declares a parameter it
   receives the event payload, otherwise it is called with no arguments.
2. **An expression** is evaluated in the template's scope, so loop variables
   and the `event` payload are available: `@click="remove(item)"`,
   `@input="search(event['value'])"`. Whatever it returns is returned from
   the dispatch, which matters for `emit` (section 4).
3. **Statements** run when the value does not parse as an expression.
   Assignment, augmented assignment and `;`-separated statements all work:

   ```xml
   <button @click="show = not show">toggle</button>
   <button @click="count += 1; history.append(count)">record</button>
   <For each="item in items" key="item['id']">
     <li @click="selected = item">{{ item['text'] }}</li>
   </For>
   ```

   A bare name on the left of `=` writes component state, so `count += 1`
   updates `self.count` on the component that owns the template. Assigning
   to a loop variable only changes it inside that handler; it never becomes
   state. `self.count += 1` is the explicit spelling if you prefer it.

After any of the three runs, the component re-renders. Keep inline handlers
to a statement or two; once logic needs a name, a comment, or a test, move it
to a method.

### Component styles

A `<style>` block in a `.weft` file is **scoped to that component**: its
rules match only elements this component's template renders.

```xml
<template>
  <li class="row"><span>{{ item['text'] }}</span></li>
</template>

<style>
.row { display: flex; gap: .5rem; }
span:hover { text-decoration: underline; }
</style>
```

Write selectors as if the component were the whole page. `span:hover` above
cannot reach a `<span>` rendered by a child or a parent, so two components can
both use `.row` without a naming scheme. Under the hood every element gets a
`data-w-<component>` marker and each selector has `[data-w-<component>]`
appended, which you will see in the browser's element inspector.

Two rules of thumb:

- A parent *can* style the outermost element of a child it places, so
  `.list > .row` in the parent works for spacing children. It cannot reach
  inside them.
- Page-wide rules (`body`, fonts, CSS variables) go in a `.css` file in the
  app directory, which is included unscoped. `var(--name)` defined there is
  usable from any component's `<style>`.

`@media`, `@supports` and `@container` blocks are scoped too; `@keyframes`,
`@font-face` and `@import` are passed through as written.

---

## 4. Composing components

Any capitalized tag is a child component. PyWeft resolves `<TodoItem>` to
`TodoItem.weft` or `todo_item.weft` **in the same directory** as the file that
uses it, with no import boilerplate.
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

- Emitting an event the parent did not subscribe to is a no-op.
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
  styles.css        # global CSS; component styles go in <style> blocks
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

### Calling JavaScript

In the browser your component code runs inside Pyodide, which exposes the
page's JavaScript globals as a Python module named `js`. Anything the page
can do, a handler can do:

```python
import js

def save(self):
    js.localStorage.setItem("draft", self.draft)

def restore(self):
    self.draft = js.localStorage.getItem("draft") or ""

def shout(self):
    js.alert(f"{self.count} clicks")

def retitle(self):
    js.document.title = f"{self.count} clicks"
```

- **Globals** are attributes of `js`: `js.window`, `js.document`,
  `js.console.log(...)`, `js.navigator.clipboard.writeText(text)`.
- **Libraries** you load with a `<script>` tag in a custom shell appear the
  same way, for example `js.Chart`.
- **Raw JavaScript** runs with `js.eval("...")` when you need a one-off.
- **Async APIs** such as `fetch` return promises; `await` them from an
  `async` method (`await js.fetch(url)`), or use `pyodide.http.pyfetch`.
- **Callbacks.** Passing a Python function to `js.setTimeout(fn, ms)` works
  for a one-shot call. For a listener that lives on, wrap it with
  `pyodide.ffi.create_proxy(fn)` and call `.destroy()` when you remove it,
  otherwise it leaks.

Two rules keep this safe:

1. **Never modify elements PyWeft rendered.** The runtime owns everything
   under `#app` and patches it by position. Reading is fine; adding or
   removing nodes there from JavaScript puts the next patch on the wrong
   node. If you need a DOM library to draw somewhere, give it an element
   outside `#app` or a container your template renders and leaves empty.
2. **Keep `import js` inside handlers, not templates.** The `js` module only
   exists in the browser. A component that imports it at the top of its
   code block fails in headless tests and on the desktop target, where
   Python runs natively; importing inside the method that needs it keeps
   the rest of the component portable.

State changed from a JavaScript callback happens outside a handler, so call
`self.state_has_changed()` afterwards, exactly as with a timer.

A transport-independent way to call JavaScript, a `call` patch op that works
identically in the browser, on desktop and in tests, is on the roadmap.

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

