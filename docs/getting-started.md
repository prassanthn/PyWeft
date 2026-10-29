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

**Contents**

1. [Install](#1-install)
2. [Your first component](#2-your-first-component): how state works,
   [effects](#effects-reacting-to-state-changes),
   [async handlers, background work](#async-handlers-and-background-work),
   [heavy work in a Web Worker](#heavy-work-run_in_background),
   [threads](#threads)
3. [Template syntax reference](#3-template-syntax-reference): bindings,
   inline handlers, [the event object](#the-event-object),
   [event modifiers](#event-modifiers),
   [binding form controls](#binding-form-controls), component styles
4. [Composing components](#4-composing-components): props, events,
   components in folders, [slots](#passing-content-slots),
   [@bind on components](#bind-on-your-own-components),
   [attributes on a component tag](#attributes-on-a-component-tag),
   [components from packages](#components-from-packages)
5. [Starting a new project](#5-starting-a-new-project):
   [hot reload](#hot-reload), [the loading screen](#the-loading-screen),
   [head.html and assets](#the-page-head-and-the-assets-folder),
   [CSS frameworks (Tailwind, Bootstrap)](#using-css-frameworks),
   [ready-made controls (pyweft-ui)](#ready-made-controls-pyweft-ui),
   [PyPI packages](#using-pypi-packages),
   [calling JavaScript](#calling-javascript),
   [building for deployment](#building-for-deployment)
6. [Using the engine from plain Python](#6-using-the-engine-from-plain-python):
   headless tests, including async ones
7. [What's here and what's coming](#7-whats-here-and-whats-coming)

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
uv run pytest            # 786 tests should pass
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
handler** — a timer, a websocket message, a JavaScript callback. Nothing
triggers the re-render, so call `state_has_changed()` after the mutation
(`async` handlers are covered for you; see "Async handlers" below):

```python
def on_message(self, msg):        # invoked by something other than the UI
    self.items.append(msg)
    self.state_has_changed()      # schedule a re-render
```

The re-render happens right after your code returns, not inside the call, so
calling `state_has_changed()` many times in a row (in a loop, say) still
costs one render. It works the same in a child component as in the root.

State belongs to the instance that declared it. To share data between
components, pass it down as props and send changes up with `emit` (section
4). A cross-component store is on the roadmap; it will sit on top of this
model, not replace it.

### Effects: reacting to state changes

Some code should run *because* state changed, not because an event fired:
keeping the tab title in sync, saving a draft, starting a subscription.
Mark a method with `@effect`:

```python
from pyweft import effect

@effect
def sync_title(self):
    import js
    js.document.title = f"{self.remaining} left"
```

- **When it runs.** Once after the component's first render, then after any
  later render in which a value it read has changed. Effects run after the
  page has been patched, so the DOM already shows the new state.
- **What it depends on** is discovered automatically: every state attribute
  the method reads, including reads inside `@property` values and helper
  methods it calls. Above, `remaining` reads `self.items`, so the effect
  re-runs when the list changes and never when, say, a text input does.
- **In-place changes count.** Values are compared against a copy taken after
  the last run, so `self.items.append(x)` and `item["done"] = True` re-run
  the effect, not only reassignment.
- **Cleanup.** Return a function and it runs before the next run and when the
  component is removed, which is how you cancel timers and listeners. This
  saves the draft half a second after the user stops typing; each keystroke
  cancels the previous pending save:

  ```python
  @effect
  def autosave(self):
      import js
      from pyodide.ffi import create_proxy
      draft = self.draft
      save = create_proxy(lambda: js.localStorage.setItem("draft", draft))
      timer = js.setTimeout(save, 500)
      def cancel():
          js.clearTimeout(timer)
          save.destroy()
      return cancel
  ```

- **Writing state from an effect works**, for example deriving one field
  from another. The component re-renders once the effects have run. An
  effect writing one of its own inputs does not re-trigger itself; two
  effects that keep changing each other's inputs raise `EffectLoopError`
  after 100 rounds instead of hanging the page. For a value that is purely
  derived from other state, a `@property` is still simpler.

Effects run synchronously and only in components that are rendered. The
older `on_after_render(self, first)` hook still exists for code that must
run after every render; it now fires for child components too, not only the
root.

### Async handlers and background work

Any handler can be `async def`. Use it for anything that waits: a network
request, a delay, a JavaScript promise.

```xml
<button :disabled="loading" @click="load_users">Load users</button>
<p>{{ status }}</p>
```

```python
import asyncio

loading: bool = False
status: str = ""
users: list = []

async def load_users(self):
    import js
    self.loading = True               # shown as soon as you click
    self.status = "Loading…"
    response = await js.fetch("assets/users.json")
    self.users = (await response.json()).to_py()["users"]
    self.status = f"{len(self.users)} users"
    self.loading = False              # shown when the handler finishes
```

- **When the page updates.** Everything up to the first `await` appears in
  the same update as the click, so a spinner or a disabled button shows
  immediately. The component updates again when the handler finishes. To
  show progress in between (a counter in a long loop, say), call
  `self.state_has_changed()` after the change.
- **`on_init` can be async**, which is the usual way to load a component's
  data. The component renders right away with whatever it has (say,
  "Loading…") and again when `on_init` finishes. `on_after_render` can be
  async too; `on_dispose` cannot.
- **Clicking again while it waits** runs the handler a second time, alongside
  the first. Both run on one thread and only take turns at `await`, so they
  never corrupt each other's state, but you usually want one at a time:
  disable the button while `loading` is true, as above.
- **Removed components stop.** If a component is removed while one of its
  handlers is still waiting (a row deleted mid-save, a dialog closed
  mid-request), the handler is cancelled at its current `await`, as an
  `asyncio.CancelledError`. Catch it with `try`/`finally` to tidy up.
- **Errors** raised after an `await` have nobody to return to, so in
  development they appear in the error overlay with the file and line, and
  always in the browser console with the full traceback. Everything the
  handler changed before failing is still shown.

**Starting work yourself.** `self.start_task(coroutine)` runs a coroutine
alongside the component, with the same rules: the component updates when it
finishes, and it is cancelled if the component is removed. It returns the
`asyncio.Task`. For example, a clock:

```python
async def tick(self):
    while True:
        self.now = time.strftime("%H:%M:%S")
        self.state_has_changed()
        await asyncio.sleep(1)

def on_init(self):
    self.start_task(self.tick())     # stops by itself when the clock is removed
```

**Effects cannot be async** (only the reads before the first `await` could
be tracked), but an effect can start a task. Return the task's `cancel` as
the cleanup and only the latest run survives, which is exactly what a
search box needs; each keystroke cancels the request still in flight:

```python
@effect
def search_as_you_type(self):
    task = self.start_task(self.search(self.query))
    return task.cancel

async def search(self, query):
    await asyncio.sleep(0.3)          # wait for typing to pause
    response = await js.fetch(f"/api/search?q={query}")
    self.results = (await response.json()).to_py()
```

#### Heavy work: `run_in_background`

Python in the browser runs on the page's main thread, so a long calculation
freezes the page: no clicks, no repaints, until it is done. For work like
that (parsing a big file, statistics, image processing), run it in the
background:

```python
from pyweft import run_in_background

busy: bool = False
report: str = ""

async def analyse(self):
    self.busy = True                                   # shows immediately
    self.report = await run_in_background(build_report, self.rows, title="Q3")
    self.busy = False

def build_report(rows, title=""):     # a plain function: no self
    ...                               # takes seconds; the page stays responsive
    return text
```

In the browser the call runs in a **Web Worker**: a second Python on its own
browser thread. The page keeps responding while it works, and you `await` the
result like any other async call. Headless (tests), and on the desktop target
when it arrives, the same call runs on a thread instead.

The worker is a separate copy of Python, which sets the rules:

- **Pass a plain function** defined at the top level of the `<code>` block,
  without `self` (or one from an importable module, such as
  `run_in_background(statistics.median, values)`). It is found in the
  worker by name, so methods, lambdas and nested functions are refused with
  a clear error. Other functions and imports from the same `<code>` block are
  available to it.
- **It cannot see the component or the page.** Pass in the data it needs and
  return the result; change state after the `await`, as above. `js` in the
  worker is the worker's own scope, with no `document`.
- **Arguments and the result must be picklable**: numbers, strings, lists,
  dicts, tuples, sets, dates, and objects from installed packages (NumPy
  arrays, for example). Instances of classes defined in a `.weft` file are
  not. Everything is copied in and out, so a list the function changes in
  the worker is not changed on the page.
- **Exceptions come back**: `ValueError` in the worker raises `ValueError`
  at the `await`, and the error overlay shows both lines, the `await` and the
  line in the background function that failed.
- **The top level of the `<code>` block runs again in the worker** (that is
  how it finds the function), so keep page-only code such as
  `js.document...` inside methods, where it belongs anyway.
- **It must be a regular `def`, not `async def`.** Do any waiting (a
  download, say) in your handler, then pass the data in:

  ```python
  async def load_report(self):
      from pyodide.http import pyfetch
      rows = await (await pyfetch("assets/sales.json")).json()   # waiting: on the page
      self.report = await run_in_background(build_report, rows)  # computing: in the worker
  ```

- **Blocking is fine inside it.** `time.sleep()` or a long loop blocks only
  the worker, never the page.
- **`print()` and `js.console.log()` work inside it** and show up in the
  browser's console as usual, which is handy for checking what it received.

How it behaves:

- **The first call starts the worker**, which loads Python and your
  dependencies from `pyproject.toml`: a few seconds, mostly cached after the
  first visit. Later calls start immediately. To start it early, call
  `pyweft.background.warm_up()` in `on_init`.
- **One worker, one call at a time**, in the order they were made. Calls
  made while one runs wait their turn.
- **Cancelling** (the component is removed, or an effect's cleanup cancels the
  task) drops a call that has not started yet. A call already running
  finishes in the worker and its result is discarded; Python in a worker
  cannot be interrupted. For search-as-you-type, that means at most one
  stale search runs before the latest one.
- **Hot reload** reaches the worker too: edit the function, save, and the
  next call runs the new code.

Use it for work measured in hundreds of milliseconds or more. Each call
copies its data both ways, so many tiny calls are slower than doing the work
directly.

**Seeing that it works.** Add a counter next to the button that starts the
work. While the background call runs, the counter should keep counting:

```xml
<button :disabled="busy" @click="analyse">Analyse</button>
<p>{{ report }}</p>
<button @click="clicks += 1">clicks while it runs: {{ clicks }}</button>
```

**Common mistakes**, with the error each one gives:

| You wrote | You see | Fix |
|---|---|---|
| `def work(self): ... self.number ...` | `AttributeError: 'int' object has no attribute 'number'`: `self` received the first argument you passed | Take the data as parameters: `def work(number)`, called as `run_in_background(work, self.number)` |
| `run_in_background(self.work, ...)` | `TypeError: run_in_background needs a plain function, not the method ...` | Pass `work`, not `self.work`, and remove `self` from it |
| `run_in_background(lambda: ...)` | `TypeError: ... lambdas and nested functions cannot be` | Give it a name at the top level of the `<code>` block |
| `async def work(...)` | `BackgroundError: the result of work could not be pickled: cannot pickle 'coroutine' object` | Make it a plain `def`; await things in the handler first |
| An argument such as an open file or a lock | `TypeError: the arguments to run_in_background(...) must be picklable` | Pass the data itself (the file's text, a list) |
| Changing a list inside the function, expecting the page to see it | Nothing changes on the page | Return the new value and assign it after the `await` |
| (with `pyweft run`) | `the background worker could not start: worker.js was not found (HTTP 404)` | `pyweft run` is older than PyWeft's files: restart it |
| (on a deployed site) | the same message | Upload `worker.js` with the rest of `pyweft build`'s output |

#### Threads

In the browser, Python has no threads. It runs on the page's main thread,
the same one that draws the page and handles clicks:

| In the browser | What happens |
|---|---|
| `threading.Thread(...).start()`, `ThreadPoolExecutor` | `RuntimeError: can't start new thread` |
| `threading.Lock()` and friends | work (harmless with one thread) |
| `time.sleep()`, a long calculation | work, but the page is frozen until they finish |
| `await asyncio.to_thread(work)` | works, but runs `work` right there on the main thread |

So, in practice:

- **For waiting** (network, delays, timers), use `async` handlers and
  `await`, as above. No thread is needed.
- **For heavy computation**, use `run_in_background` (above). It is the
  portable choice: a Web Worker in the browser, a thread elsewhere.
- **For long work that needs the component as it goes**, split it up and
  give the page a turn every so often:

  ```python
  async def crunch(self):
      for i, row in enumerate(self.rows):
          process(row)
          if i % 500 == 0:
              self.progress = i
              self.state_has_changed()
              await asyncio.sleep(0)      # the page repaints and handles clicks here
  ```

- **Never change component state from another thread.** Rendering happens on
  the main thread, and a thread writing `self.items` halfway through a render
  can corrupt it. Return the result and assign it after the `await`, as
  `run_in_background` makes you do. (On the desktop target, real threads
  will exist and this matters most there.)

---

## 3. Template syntax reference

| Syntax | Meaning |
|---|---|
| `{{ expr }}` | Interpolate a Python expression in text or attribute values |
| `:attr="expr"` | Bind an attribute to an expression. `None`/`False` drop the attribute, `True` keeps it valueless (`:disabled="busy"`), anything else is stringified. On a component, passes the **typed** value as a prop |
| `@click="handler"` | A bare name calls that method; an expression is evaluated, so `@click="remove(item)"` works; simple statements run inline, so `@click="count += 1"` and `@click="show = not show"` work without a method. Any DOM event works the same way (`@input`, `@keydown`, `@submit` ...) |
| `@event.modifier` | `@submit.prevent`, `@keydown.enter`, `@click.stop`, `@keydown.ctrl.s.prevent`: see [event modifiers](#event-modifiers) |
| `@bind="field"` | Two-way binding on inputs, textareas, selects, checkboxes and radio buttons, converting to the field's declared type. `@bind.lazy`, `.trim`, `.number`: see [binding form controls](#binding-form-controls) |
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
   `@input="search(event.value)"`. Whatever it returns is returned from
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

### The event object

A handler that declares a parameter, or an expression that uses `event`,
gets the event's details. It is a dict that also allows attribute access, so
`event.key` and `event["key"]` both work:

```python
def on_key(self, event):
    if event.key == "Enter" and event.ctrlKey:
        self.send()
```

| Key | On |
|---|---|
| `type` | every event: `"click"`, `"keydown"` ... |
| `value` | inputs, textareas and selects: the current text |
| `checked` | checkboxes and radio buttons |
| `key`, `code`, `repeat` | keyboard events: `key` is the character or name (`"a"`, `"Enter"`, `"ArrowUp"`); `code` the physical key (`"KeyA"`) |
| `ctrlKey`, `shiftKey`, `altKey`, `metaKey` | keyboard and mouse events |
| `clientX`, `clientY`, `offsetX`, `offsetY`, `button`, `buttons` | mouse and pointer events (`deltaX`, `deltaY` on `wheel`) |
| `form` | `submit`: the form's fields as `{name: value}`, a list when several fields share a name (file inputs are left out) |

Asking for a key the event doesn't have raises an `AttributeError` that
lists the keys it does have.

### Event modifiers

Add modifiers after the event name to handle the browser's behaviour in the
template instead of in your method:

```xml
<form @submit.prevent="save">...</form>             <!-- no page reload -->
<a href="/help" @click.prevent="open_help">help</a> <!-- no navigation -->
<input @keydown.enter="search" @keydown.esc="clear" />
<textarea @keydown.ctrl.enter="send"></textarea>
<div @click="close" class="backdrop">
  <div @click.stop="" class="dialog">...</div>     <!-- clicks inside don't close it -->
</div>
```

| Modifier | Effect |
|---|---|
| `.prevent` | `preventDefault()`: no form submission, link navigation, browser shortcut |
| `.stop` | `stopPropagation()`: parents don't see the event |
| `.self` | only when the event happened on this element itself, not a child |
| `.once` | at most once |
| `.capture`, `.passive` | listener options, for capture-phase and scroll-performance cases |
| `.enter`, `.tab`, `.esc`, `.space`, `.delete` (Delete or Backspace), `.up`, `.down`, `.left`, `.right` | key events: only for that key |
| any key name in kebab-case | `.a`, `.f1`, `.page-down`: `KeyboardEvent.key` lower-cased, `PageDown` becomes `page-down` |
| `.ctrl`, `.alt`, `.shift`, `.meta` | only while that key is held (on keyboard and mouse events) |
| `.exact` | and no other of those keys: `@click.ctrl.exact` ignores Ctrl+Shift+click |
| `.left`, `.middle`, `.right` | mouse events: that button. `@click.right` handles right-clicks (the context menu), so add `.prevent` to suppress the menu |

- **Modifiers only:** `@submit.prevent=""` with an empty value prevents the
  default and calls nothing.
- **Several handlers for one event** are fine when their modifiers differ:
  `@keydown.enter="search"` and `@keydown.esc="clear"` on one input.
- **Filters come first.** `.prevent` and `.stop` apply only when the key,
  button, `.self` and `.ctrl`-style conditions match, whatever order you
  write them in. `@keydown.ctrl.s.prevent="save"` blocks the browser's Save
  dialog for Ctrl+S and leaves every other key alone.
- **Typos are caught**: `@submit.prevnt` or `@click.enter` is a template
  error naming the modifier, not a handler that silently never runs.
- Modifiers belong to page events. A component's own events (`@remove` on
  `<TodoItem>`) take none.

### Binding form controls

`@bind="field"` keeps a control and a field in sync both ways:

```xml
<input @bind="name" />                                  <!-- str -->
<input type="number" @bind="age" />                     <!-- int -->
<textarea @bind="notes"></textarea>
<input type="checkbox" @bind="subscribed" />            <!-- bool: checked -->
<input type="radio" value="s" @bind="size" />
<input type="radio" value="m" @bind="size" />           <!-- the checked one's value -->
<select @bind="country">
  <option value="in">India</option>
  <option value="nl">Netherlands</option>
</select>
```

- **Types follow the field's declaration.** `age: int = 0` stores an `int`;
  `price: float | None = None` a `float`, or `None` when the box is empty.
  Text that doesn't fit (letters in a number box, an empty box for a field
  that can't be `None`) leaves the field at its last good value while the
  user is still typing, instead of turning it into a string.
- **Checkboxes** bind a `bool` to the checked state; **radio buttons** store
  the `value` of the one that is checked (converted, so `value="2"` with
  `size: int` stores `2`).
- **Modifiers:** `@bind.lazy` updates when the user leaves the field (the
  `change` event) rather than on every keystroke; `@bind.trim` strips
  surrounding spaces; `@bind.number` parses a number even when the field has
  no declared type.
- **Your own handler alongside:** `@bind` and `@input` on one element both
  run, the binding first, so your handler already sees the new value:

  ```xml
  <input @bind="query" @input="search()" />
  ```

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

**Components in folders.** Put a folder name in front of the tag, with a
dot, the way you would write a Python module path:

| Tag | File |
|---|---|
| `<TodoItem />` | `todo_item.weft` next to the file using the tag |
| `<widgets.Row />` | `widgets/row.weft` |
| `<forms.inputs.TextField />` | `forms/inputs/text_field.weft` |

A dotted tag is always looked up from the **app root** (the folder holding
`app.weft`), no matter which file uses it, so `<shared.Icon />` means the same
file in `app.weft` and in `forms/inputs/text_field.weft`. A plain tag inside a
folder finds its neighbours in that folder: `forms/field.weft` can use
`<Label />` for `forms/label.weft`.

```
myapp/
  app.weft
  widgets/
    row.weft            <widgets.Row />
  forms/
    field.weft          <forms.Field />, which can use <Label />
    label.weft
  shared/
    icon.weft           <shared.Icon />, usable from anywhere
```

Folder names must be valid Python identifiers (letters, digits, underscores);
only the last part of the tag is capitalized. Two components may share a file
name in different folders; their `<style>` blocks stay separate.

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
over the file conventions, which is how you give a component a different tag
name or use one from outside the app folder:

```python
from pyweft import load_component

components = {"Row": load_component("widgets/row.weft")}
```

A relative path here is relative to the `.weft` file that contains it, not to
the folder you started the app from, so it works the same in the browser and
in tests.

From plain Python, `component_from_source(src, components={...})` accepts the
same dict.

### Passing content: slots

A component can take markup between its tags. It marks where that content
goes with `<Slot />`:

```xml
<!-- card.weft -->
<template>
  <section class="card">
    <h3><Slot name="title">Untitled</Slot></h3>
    <div class="body"><Slot /></div>
    <If cond="has_slot('footer')"><footer><Slot name="footer" /></footer></If>
  </section>
</template>
```

```xml
<!-- using it -->
<Card>
  <Fill name="title">Sign up</Fill>
  <p>Hello {{ name }}</p>
  <Fill name="footer"><button @click="save">Save</button></Fill>
</Card>
```

- **Content outside any `<Fill>`** goes to the unnamed `<Slot />`.
  `<Fill name="...">` targets a named one.
- **The slot's own children are the fallback** when nothing is passed
  ("Untitled" above). `has_slot("footer")` tells the component whether
  content was passed, so it can leave out the wrapper when there is none.
- **Slot content belongs to the component that wrote it.** `{{ name }}` and
  `@click="save"` above are the *using* component's state and method,
  including loop variables when the `<Card>` sits inside a `<For>`, and its
  scoped styles apply to that content.
- **Slots can hand data to the content** (handy for lists and tables). Props
  on `<Slot>` become variables inside the content:

  ```xml
  <!-- data_list.weft -->
  <ul><For each="item in items" key="item" index="i">
    <li><Slot :item="item" :index="i">{{ item }}</Slot></li>
  </For></ul>
  ```

  ```xml
  <DataList :items="fruits"><b>{{ index + 1 }}. {{ item.upper() }}</b></DataList>
  ```

- **Mistakes are errors, not silence:** content for a slot the component
  doesn't have, two `<Fill>`s with one name, or a `<Fill>` outside a
  component tag all fail with a message saying what's wrong.

### @bind on your own components

`@bind` works on a component tag too, so a form control you write is used
exactly like an `<input>`:

```xml
<TextField label="Email" @bind="email" />
```

The component receives the field as its `value` prop and reports a new value
with `emit("update", new_value)`:

```xml
<!-- text_field.weft -->
<template>
  <label>{{ label }}
    <input :value="value" @input="emit('update', event.value)" />
  </label>
</template>

<code>
label: str = ""
value: str = ""
</code>
```

The using component's field is updated, then its own `@update` handler runs
if it has one. `@bind` modifiers (`.lazy` and so on) apply to plain inputs
only; inside your component, pick the event you emit on.

### Attributes on a component tag

Attributes a component **declares as fields** are props: `variant` and
`disabled` below set those fields. **Any other attribute** goes onto the
component's root element, so styling and accessibility attributes just work:

```xml
<Button variant="primary" class="wide" id="save" aria-label="Save order">Save</Button>
```

- **Plain values are converted to the field's type**, so attributes read
  naturally: with `cols: int = 0`, `cols="3"` sets the number 3; with
  `disabled: bool = False`, `disabled="true"` (or `disabled=""`) sets `True`
  and `disabled="false"` sets `False`. A value that doesn't fit, such as
  `cols="three"`, is a template error naming the field.
- `class` and `style` are **added to** the root element's own; other
  attributes replace them.
- `:attr="expr"` works the same way: a prop if declared (passed as is,
  no conversion), otherwise an attribute (`None`/`False` leave it out,
  `True` writes it without a value).
- The component must render a **single root element** to receive them; if
  it renders several, you get an error naming the attribute.
- Events (`@click`) are never passed through: the component decides what
  it emits, typically with `@click="emit('click', event)"` on its button.

### Components from packages

A component class can come from an import, and the tag follows the name you
imported it under:

```python
# in the <code> block
from pyweft_ui import ui          # then <ui.Button>, <ui.Card> ...
from reports import ChartPanel    # then <ChartPanel>
```

Imported names win over files of the same name next to your component.

**Writing a component library** takes one line in its `__init__.py`:

```python
# my_widgets/__init__.py
from pathlib import Path
from pyweft import ComponentLibrary

ui = ComponentLibrary(Path(__file__).parent, prefix="ui")
```

`ui.Button` then loads `button.weft` (or `Button.weft`) from the package
folder on first use. Inside the library, components use each other as usual.
The `prefix` keeps the library's scoped styles apart from the app's, so a
library `.card` and an app `.card` never collide.

**Using a library in an app**: add it to the app's `pyproject.toml` like any
dependency (`uv add my-widgets`, or edit `dependencies`). How it reaches the
browser:

- **If it is installed where you run `pyweft run`** (published, a local
  path, or an editable install while you develop it), PyWeft ships it from
  there: `run` serves it and `build` copies it into `dist/lib/`. The browser
  gets exactly the version you have, and an unpublished library works.
  Editing its files reloads the page. Its own dependencies are installed in
  the browser from PyPI as usual.
- **Otherwise** it is installed from PyPI in the browser like any package,
  which works once it is published as a wheel that includes its `.weft`
  files (hatchling and uv's build backend include them by default).

A dependency counts as a component library when its package folder contains
`.weft` files; everything else is an ordinary package.

---

## 5. Starting a new project

```bash
uv run pyweft new myapp
uv run pyweft run myapp
```

(Drop the `uv run` prefix if you installed with pip.) That's it — `new` scaffolds the project, `run` serves it. Open
`http://127.0.0.1:8642/`, then edit a file and save: the open page updates in
place, without losing what you'd clicked or typed (see "Hot reload" below).
There is no build step; components are compiled in the browser.

A scaffolded app looks like this:

```
myapp/
  pyproject.toml    # name + dependencies — a completely ordinary pyproject
  app.weft          # root component (must be named app.weft)
  styles.css        # global CSS; component styles go in <style> blocks
  head.html         # extra <head> tags: CDN stylesheets, scripts, fonts
  loading.html      # what visitors see while Python starts (see below)
```

Add more components as sibling `.weft` files — `<TodoItem>` in a template
finds `todo_item.weft` automatically — or group them in folders and use
dotted tags such as `<widgets.Row>` (section 4). `pyweft run` and `pyweft
build` pick up `.weft` and `.css` files in subfolders too. They skip folders
a tag cannot name (`.venv`, anything starting with `_`), `node_modules`,
`assets/` (served as-is, see below), and build output such as `dist/`.

### Hot reload

While `pyweft run` is serving, every save shows up in the open page within
about half a second, and the app keeps its state: todos you added, text
you'd typed, toggles you'd set. What happens depends on what you saved:

| You save | The page | State |
|---|---|---|
| a `.weft` file: template, `<code>` or `<style>` | recompiles it and patches only what changed | kept |
| a global `.css` file | swaps the stylesheet, in the same place | kept |
| `pyproject.toml`, `head.html` or `loading.html` | reloads (they only apply at startup) | reset |
| anything in `assets/` | reloads (an image may be used anywhere) | reset |

How state carries over:

- Values of existing fields are kept. Change `count: int = 0` to
  `count: int = 5` and a counter that is already at 3 stays at 3; the new
  default applies to fresh components and after a reload.
- New fields start at their default, so you can add a field and use it in the
  template in the same save.
- `on_init` does not run again for components that are already on the page.
  Effects in the file you edited do re-run: their cleanup first, then the new
  code.
- A child component is identified by its position in the template, as on any
  re-render. Insert something *before* it and it starts fresh; give it a
  `key` to keep its state when it moves.

**Mistakes don't break the page.** Save a syntax error or unbalanced markup
and an overlay at the bottom shows what's wrong and where, for example:

```
app.weft, line 38: cleared: int = = 0
SyntaxError: invalid syntax
```

The page underneath keeps running the last version that worked, so you can
keep clicking around. Fix the file and save; the overlay goes away and the
fix applies. An exception raised by an event handler, including an `async`
one after its `await`, shows in the same overlay with the line in your
`.weft` file, headed "unhandled error; the page is still running".

A few more details:

- **Saves made while the page is still starting** (Python is loading) are not
  lost: the page catches up on them as soon as it is ready.
- **One server per port.** If `pyweft run` says it cannot listen on the port,
  another `pyweft run` is still running somewhere. Stop it, or start this one
  with `--port 8700`.
- **After updating PyWeft itself, restart `pyweft run`.** Your app's files
  reload on their own, but the server's own code only loads when it starts.
  If PyWeft changes while the server runs, open pages show an amber
  "restart `pyweft run`" banner at the top instead of reloading into a
  half-updated state, and the terminal says the same.

Hot reload is a development feature only: `pyweft build` output contains none
of it.

### The loading screen

Starting Python in the browser takes a few seconds on the first visit (the
runtime is downloaded, then cached), so the page shows a loading screen until
your app has rendered, then fades it out. `pyweft new` gives you the default
one as `loading.html`: three threads weaving back and forth, with a line of
progress text underneath. It follows the system's light or dark colors and
calms down for visitors who prefer reduced motion.

The file is plain HTML and CSS, inserted into the page before anything else
loads, so change it however you like. Replace the animation, add your logo,
set your brand colors:

```html
<style>
  .splash { position: fixed; inset: 0; display: grid; place-content: center;
            background: #1e3a5f; color: #fff; font: 600 1.4rem system-ui; }
  .splash small { display: block; margin-top: .5rem; font-size: .9rem; }
</style>
<div class="splash">
  My Todo App
  <small data-pyweft-status></small>
</div>
```

- **Progress messages** ("Loading Python…", "Installing humanize…") go into
  every element with a `data-pyweft-status` attribute. Leave it out if you
  don't want them.
- **If startup fails**, the error appears in that same element, and the
  wrapper (`#pyweft-loading`) gets the class `pyweft-failed`, so you can style
  the failure state: `.pyweft-failed .splash { background: #7a1f1f; }`. The
  full Python traceback is in the browser console.
- **Cover the page.** Use `position: fixed; inset: 0` and a background, as
  above, because the app is rendered underneath while the screen is up.
- **Delete `loading.html`** to go back to the built-in default; **leave it
  empty** for no loading screen at all. Projects created before this file
  existed get the default automatically.

With `pyweft run`, saving `loading.html` reloads the page so you see it
again; `pyweft build` writes the screen
into `index.html`, so it appears before any other file has downloaded.

### The page head and the assets folder

**`head.html`** is added to the page's `<head>`, so anything that belongs
there goes in it: stylesheets and scripts from a CDN, web fonts, a favicon,
meta tags.

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" />
<link rel="icon" href="assets/favicon.svg" />
<meta name="theme-color" content="#4f46e5" />
```

`pyweft new` creates one with every line commented out, as a menu of common
uses. Saving it reloads the page.

**Stylesheet order.** The page loads `head.html` first, then your own `.css`
files in alphabetical order, then the components' `<style>` blocks. When the
order matters, for example your overrides must come after a framework,
link your file in `head.html` at the point where it should load:

```html
<link rel="stylesheet" href="https://cdn.example/framework.css" />
<link rel="stylesheet" href="app/overrides.css" />
```

A `.css` file linked this way is not added a second time, and hot reload
still swaps it in place when you save it.

**The `assets/` folder** holds files the page uses as-is: images, fonts,
icons, a vendored stylesheet or script. They are served at `assets/...`, so
`myapp/assets/logo.svg` is `<img src="assets/logo.svg" />` in a template,
`url("assets/inter.woff2")` in a global `.css` file, or
`<link rel="stylesheet" href="assets/icons.css" />` in `head.html`. Files in
`assets/` are never linked or loaded on their own, and `pyweft build` copies
the folder unchanged.

**The page starts unstyled.** PyWeft styles only its own loading screen and
error overlay; layout, fonts and colors are yours. New projects get a simple
centered column in `styles.css`. A project created before this changed had
that column built in, so to keep it, add this to its `styles.css`:

```css
body { font-family: system-ui, sans-serif; max-width: 40rem;
       margin: 3rem auto; padding: 0 1rem; color: #222; }
```

### Using CSS frameworks

Class names in a template are ordinary HTML classes, so any CSS framework
works. Delete the `body` rule from `styles.css` first, so it doesn't fight
the framework's layout.

**Bootstrap.** Link its stylesheet in `head.html`, then use its classes:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" />
```

```xml
<button class="btn btn-primary" @click="save">Save</button>
<ul :class="'dropdown-menu show' if open else 'dropdown-menu'">...</ul>
```

Use Bootstrap's CSS and leave out its JavaScript bundle. Its dropdowns and
modals open by changing classes on elements PyWeft owns, and the next update
to that element undoes them. Keep "open" in your component's state instead,
as above.

**Tailwind, without a build step.** Add Tailwind's browser script to
`head.html`, optionally with your theme:

```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
  @theme { --color-brand: #4f46e5; }
</style>
```

Then use classes anywhere, with nothing else to run:

```xml
<button class="bg-brand text-white rounded-lg px-4 py-2" @click="save">Save</button>
<p :class="f'text-{level}-600'">{{ message }}</p>
```

The script watches the page and generates CSS for each class as it appears,
so classes built in Python (the f-string above) work too. It's a large
download and Tailwind doesn't recommend it for production, so switch to the
CLI before you deploy.

**Tailwind, with its CLI (for production).** The CLI scans your `.weft`
files and writes a stylesheet containing only the classes you use. Put its
input file in a folder starting with `_`, which PyWeft ignores:

```css
/* myapp/_tailwind/input.css */
@import "tailwindcss";
@source "../**/*.weft";
@theme { --color-brand: #4f46e5; }
```

Install the CLI in your project, not the app (`pytailwindcss` downloads
Tailwind's standalone binary, so Node isn't needed; with Node, use
`npx @tailwindcss/cli` instead):

```bash
uv add --dev pytailwindcss     # or: pip install pytailwindcss
```

Run it in watch mode next to `pyweft run`:

```bash
uv run tailwindcss -i myapp/_tailwind/input.css -o myapp/tailwind.css --watch
```

and link the output first in `head.html`, so your own CSS comes after it:

```html
<link rel="stylesheet" href="app/tailwind.css" />
```

Each save regenerates `tailwind.css` and hot reload swaps it in. Before
`pyweft build`, run the same command once without `--watch` (add `--minify`).

Two things the CLI can't do, because it reads your files instead of the
page:

- **Built-up class names.** `f'text-{level}-600'` produces nothing; write the
  classes out in full, for example
  `:class="'text-red-600' if late else 'text-green-600'"`.
- **Variants containing `&`.** Templates are XML, so `[&>li]:py-1` must be
  written `[&amp;>li]:py-1`, which the CLI does not recognize. Use the
  browser script while you need these, or give the children their own
  classes.

`@apply` works in `_tailwind/input.css`, but not in a component's `<style>`
block, which Tailwind never reads.

### Ready-made controls: pyweft-ui

If you'd rather not write HTML and CSS at all, `pyweft-ui` gives you styled,
accessible controls as components:

```xml
<ui.Theme mode="auto">
  <ui.AppShell title="Orders">
    <ui.Card title="New order">
      <ui.TextField label="Customer" @bind="customer" required="true" />
      <ui.Select label="Size" options="Small, Medium, Large" @bind="size" />
      <Fill name="footer">
        <ui.Button variant="primary" icon="send" @click="submit">Place order</ui.Button>
      </Fill>
    </ui.Card>
  </ui.AppShell>
</ui.Theme>
```

with `from pyweft_ui import ui` in the code block. It covers layout
(`AppShell`, `Row`, `Column`, `Grid`, `Card`), form fields (`TextField`,
`TextArea`, `NumberField`, `Select`, `RadioGroup`, `Checkbox`, `Switch`),
actions and feedback (`Button`, `Dialog`, `Alert`, `Badge`, `Spinner`,
`Icon`) and a `Theme` with light, dark and system modes and your own
colours. The [pyweft-ui guide](../packages/pyweft-ui/docs/guide.md) shows how
to build pages, forms and dialogs with them;
[packages/pyweft-ui/README.md](../packages/pyweft-ui/README.md) is the
reference; and the gallery shows every control live:

```bash
uv run pyweft run packages/pyweft-ui/gallery
```

It is not on PyPI yet. Install it from GitHub into the same environment as
PyWeft:

```bash
uv add "pyweft-ui @ git+https://github.com/prassanthn/PyWeft.git#subdirectory=packages/pyweft-ui"
```

(with pip: `pip install "git+https://github.com/prassanthn/PyWeft.git#subdirectory=packages/pyweft-ui"`),
then add `"pyweft-ui"` to the `dependencies` in your app's own
`pyproject.toml`. PyWeft ships it to the browser for you (see "Components
from packages"). Inside a clone of this repository, `uv sync` already
installs it.

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
- **Libraries** you load with a `<script>` tag in `head.html` appear the
  same way, for example `js.Chart`.
- **Raw JavaScript** runs with `js.eval("...")` when you need a one-off.
- **Async APIs** such as `fetch` return promises; `await` them in an
  `async` handler (`await js.fetch(url)`), or use `pyodide.http.pyfetch`.
  See "Async handlers and background work" in section 2.
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
  worker.js         the Web Worker for run_in_background (started on first use)
  pyweft-src/*.py   the framework, served to the browser
  app/              your .weft components and .css files, copied as-is
  assets/           your assets/ folder, copied as-is
```

`head.html` and `loading.html` are written into `index.html` rather than
copied.

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

Effects and `on_after_render` run when the host reports that a render is on
the page, so a test that exercises them calls `renderer.after_render()` after
each render. It returns `True` when an effect changed state; render again and
repeat until it returns `False`.

Components with async handlers or an async `on_init` need an event loop, so
test them inside `asyncio.run`. Call `renderer.init_root()` to run the root's
`on_init` (child components get theirs automatically), and
`await renderer.idle()` to wait for every pending handler and task:

```python
import asyncio

async def main():
    app = App()
    renderer = Renderer(app)
    renderer.init_root()
    tree = renderer.render()                       # "Loading…"
    renderer.dispatch(tree[0].events["click"], {})
    await renderer.idle()                          # the handler has finished
    assert not app.loading
    new_tree = renderer.render()                   # the finished state

asyncio.run(main())
```

`run_in_background` calls run on a thread in tests, through the same
lookup-by-name and pickling as the browser's worker, so a function or
argument the worker could not handle fails in the test too.

Errors in async handlers have no caller to raise to; set
`renderer.on_error` to a function to receive them, as the browser does to
show them in the overlay.

To see changes made outside a handler, set `renderer.on_invalidate` to a
function; it is called whenever `state_has_changed()` runs and no render is
already on its way. The browser uses it to schedule a render; a test can use
it to assert that one was requested, and `renderer.needs_render()` reports
whether any component is waiting to be redrawn.

`examples/demo.py` walks the full render → event → diff → apply cycle in the
terminal, `tests/test_compose.py` shows the patterns for testing composed
components, `tests/test_effects.py` the patterns for effects, and
`tests/test_async.py` the patterns for async handlers and tasks.

---

## 7. What's here and what's coming

Working today:

- **Components:** XML templates with `{{ }}` and `:attr` bindings, two-way
  `@bind` for every form control, event handlers (methods, expressions or
  inline statements) with modifiers (`@submit.prevent`, `@keydown.enter`)
  and a detailed event object (keys, modifier keys, mouse, form fields),
  `<If>`/`<For>` with keyed lists, `@property` computed values.
- **Composition:** child components with props, events (`emit`) and
  lifecycle hooks; slots (named, with fallbacks and slot props); `@bind` on
  components; attributes passed through to a component's root element;
  components in subfolders as `<folder.Name>`, or imported from packages
  (`ComponentLibrary`), shipped to the browser from your environment.
- **Reacting to change:** `@effect` methods with automatic dependency
  tracking and cleanup; `state_has_changed()` for changes from timers and
  callbacks.
- **Async:** `async def` handlers and `on_init`, `self.start_task()` for
  background work, cancellation when a component is removed.
- **Heavy work:** `run_in_background()` runs a function in a Web Worker, so
  the page stays responsive; on a thread outside the browser.
- **Styling:** scoped `<style>` blocks, global `.css` files, `head.html` for
  CDN stylesheets and scripts, an `assets/` folder, so CSS frameworks such as
  Tailwind and Bootstrap work.
- **Tooling:** `pyweft new` / `run` / `build`; hot reload that keeps state,
  with an error overlay; a customizable loading screen; PyPI dependencies
  from `pyproject.toml`, installed in the browser.
- **Controls:** `pyweft-ui`, 19 ready-made, themeable controls (see
  "Ready-made controls" in section 5), with a live gallery.

Coming next: more controls (tabs, menus, tables, toasts, a date picker,
form validation), and a pywebview **desktop** host (same components, native
window, real threads).

