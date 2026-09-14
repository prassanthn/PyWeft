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

PyWeft is not on PyPI yet; install from the repo in editable mode:

```bash
git clone <this-repo> pyweft && cd pyweft
pip install -e ".[dev]"
pytest        # 456 tests should pass
```

To see it working immediately, run the bundled todo app:

```bash
pyweft run examples/todo
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
  re-renders automatically and the DOM is patched. (Only if you mutate state
  *outside* a handler — a timer, a background task — must you call
  `self.state_has_changed()` yourself.)
- **Computed values** are ordinary Python properties:

  ```python
  @property
  def remaining(self):
      return sum(1 for t in self.items if not t["done"])
  ```

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

**Events come up.** The child calls `self.emit("remove", payload)`; the parent
listens with `@remove` and receives the payload as `event`:

```xml
<!-- parent -->
<TodoItem :item="item" @remove="remove(event)" />
```

```xml
<!-- child template -->
<button @click="emit('remove', item)">✕</button>
```

**State stays put.** A child keeps its internal state across parent
re-renders. Inside a `<For>`, the loop's `key` also keys the child instances,
so their state follows the data when rows reorder.

**Lifecycle:** `on_init(self)` runs once before the first render;
`on_dispose(self)` runs when the component disappears (e.g. its `<If>` went
false).

Not yet supported: children inside a component tag (slots) — you'll get a
clear error; and `@bind` directly on a component.

---

## 5. Starting a new project

```bash
pyweft new myapp
pyweft run myapp
```

That's it — `new` scaffolds the project, `run` serves it. Open
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

### Shipping it

```bash
pyweft build myapp          # writes myapp/dist/
```

`dist/` is a fully static site — your components, the pyweft runtime, and an
index.html that installs your dependencies at load. Host it anywhere static
files go (GitHub Pages, S3, nginx); there is no server-side Python.

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

