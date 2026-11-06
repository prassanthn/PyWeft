# PyWeft — Getting Started

PyWeft is a UI framework for Python: you write components as `.weft` files — an XML template plus a Python code
block — and PyWeft renders them to HTML, updating the page with minimal diffs
whenever state changes.

Your component code runs in **real CPython**. In the browser it runs on
Pyodide (CPython compiled to WebAssembly), so there is no transpilation and no
JavaScript to write. The same render core drives desktop apps in a native
window ([`pyweft run --desktop`](#a-desktop-app-pyweft-run---desktop)), and
later mobile: only the transport differs.

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
   [lifecycle](#lifecycle-when-your-code-runs),
   [effects](#effects-reacting-to-state-changes),
   [async handlers, background work](#async-handlers-and-background-work),
   [heavy work in a Web Worker](#heavy-work-run_in_background),
   [threads](#threads),
   [waiting in the template (Await)](#waiting-in-the-template-await)
3. [Template syntax reference](#3-template-syntax-reference): bindings,
   inline handlers, [the event object](#the-event-object),
   [element size (@resize)](#reacting-to-an-elements-size-resize),
   [events on the whole page (Window, Document)](#events-on-the-whole-page-window-and-document),
   [event modifiers](#event-modifiers),
   [binding form controls and checkbox groups](#binding-form-controls),
   [input masks](#input-masks),
   [focus and scrolling](#moving-focus-and-scrolling-ref), component styles,
   [transitions and animations](#transitions-and-animations),
   [drag to reorder (sortable)](#drag-to-reorder-sortable-lists),
   [resizable panes (splitter)](#resizable-panes-splitter),
   [showing HTML (Html)](#showing-html-from-elsewhere-html)
4. [Composing components](#4-composing-components): props, events,
   components in folders, [slots](#passing-content-slots),
   [@bind on components](#bind-on-your-own-components),
   [attributes on a component tag](#attributes-on-a-component-tag),
   [components from packages](#components-from-packages),
   [shared state (Store)](#sharing-state-between-components-store),
   [provide and inject](#passing-values-down-the-tree-provide-and-inject),
   [Dynamic](#choosing-a-component-while-the-app-runs-dynamic),
   [pages and navigation](#pages-and-navigation)
5. [Starting a new project](#5-starting-a-new-project):
   [hot reload](#hot-reload), [checking an app (pyweft check)](#checking-an-app-pyweft-check),
   [the loading screen](#the-loading-screen),
   [the first screen before Python starts](#the-first-screen-before-python-starts),
   [title and icon](#the-apps-title-and-icon),
   [head.html and assets](#the-page-head-and-the-assets-folder),
   [per-page tags (Head)](#per-page-tags-head),
   [CSS frameworks (Tailwind, Bootstrap)](#using-css-frameworks),
   [ready-made controls (pyweft-ui)](#ready-made-controls-pyweft-ui),
   [PyPI packages](#using-pypi-packages),
   [calling JavaScript](#calling-javascript),
   [files and dialogs, dropped files](#files-and-dialogs),
   [loading data (http)](#loading-data-pywefthttp),
   [live data: events, WebSockets, streams](#live-data-server-sent-events-websockets-and-streams),
   [saving data between visits (storage)](#saving-data-between-visits-pyweftstorage),
   [building for deployment](#building-for-deployment),
   [inside another website](#putting-an-app-inside-another-website),
   [a desktop app](#a-desktop-app-pyweft-run---desktop),
   [handing it out](#handing-out-a-desktop-app-pyweft-build---desktop)
6. [Using the engine from plain Python](#6-using-the-engine-from-plain-python):
   headless tests, including async ones
7. [What's here and what's coming](#7-whats-here-and-whats-coming)

---

## 1. Install

With uv:

```bash
uv init myproject && cd myproject
uv add pyweft
uv run pyweft new myapp
uv run pyweft run myapp
```

With pip, the equivalent is `pip install pyweft`, then `pyweft new` and
`pyweft run` directly.

To hack on the framework itself, clone it and install in editable mode:

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync --extra dev      # or: pip install -e ".[dev]"
uv run pytest            # 920 tests should pass
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
    <input @bind="name" placeholder="your name" aria-label="Your name" />
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

Functions you import into the code block stay plain functions:
`from textwrap import shorten` lets the template call `{{ shorten(title, 40) }}`
and a method call `shorten(self.title, 40)`, without `self` being slipped in
as the first argument. (An imported function whose first parameter is named
`self` is taken to be a method you want to share, and becomes one.)

State belongs to the instance that declared it. To share data between a
parent and its children, pass it down as props and send changes up with
`emit` (section 4). For state that many components use, such as a cart, the
signed-in user or settings, use a [store](#sharing-state-between-components-store).

### Lifecycle: when your code runs

Besides handlers, a component can define methods that PyWeft calls at set
moments in its life:

| Method | When it runs | `async`? |
|---|---|---|
| `on_init(self)` | once, when the component first appears, before its first render; its props are already set | yes |
| `on_after_render(self, first)` | after every render, once the changes are on the page; `first` is `True` the first time | yes |
| `on_dispose(self)` | once, when the component is removed: its `<If>` turned false, its row left a `<For>`, you left its page | no |
| an `@effect` method | after the first render, then after any render in which a field it reads changed | no |

```python
from pyweft import effect

orders = None
query: str = ""

async def on_init(self):
    self.orders = await fetch_orders()   # the part before the await is in the first render

def on_after_render(self, first):
    if first:
        self.focus("search")             # the elements are on the page now

@effect
def remember_query(self):                # runs again whenever self.query changes
    save_setting("query", self.query)

def on_dispose(self):
    close_connection()
```

**What each is for:**

- **`on_init`**: loading data and setting things up. An `async` one shows
  what it set before its first `await` straight away (`self.loading =
  True`), and the component renders again by itself when it finishes. Child
  components get theirs the first time a render produces them.
- **`on_after_render`**: anything that needs the component's elements to be
  on the page, such as measuring them or handing one to JavaScript.
- **`@effect`**: keeping something in step with state, such as saving,
  syncing or subscribing. It works out which fields it depends on by itself
  and can return a cleanup function (see [effects](#effects-reacting-to-state-changes)).
- **`on_dispose`**: letting go of what you opened: timers, connections,
  JavaScript listeners. Tasks started with `self.start_task()` and effect
  cleanups have already been run by then, so it must not be `async`.

**The order in one update.** An event arrives and its handler runs; the page
renders again, and components appearing for the first time get `on_init`
while vanished ones get `on_dispose`; the changes are applied to the page;
effects run, then `on_after_render`, children before the root; if any of
them changed state, it renders and applies again; finally `focus()` and
`scroll_to()` requests are carried out.

**Good to know:**

- With [pages](#pages-and-navigation), every address is a fresh page
  component: its `on_init` runs on each visit and `on_dispose` when you
  leave.
- [Hot reload](#hot-reload) keeps components alive, so `on_init` does not
  run again; the effects of an edited component start over.
- When the first screen is [rendered ahead of time](#the-first-screen-before-python-starts),
  `on_init` and `on_after_render` also run on your machine during
  `pyweft run` and `build`, up to the first `await`. Keep side effects, such
  as sending analytics, after an `await` or in a handler.
- A change that doesn't come from a handler, such as a timer or a JavaScript
  callback, is outside this cycle: call `self.state_has_changed()`.

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

Effects run synchronously and only in components that are rendered. For code
that must run after every render, whatever changed, use `on_after_render`
(see [lifecycle](#lifecycle-when-your-code-runs)).

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
result like any other async call. Headless (tests), and in a
[desktop app](#a-desktop-app-pyweft-run---desktop), the same call runs on a
thread instead.

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
  not; define the class in one of your app's `.py` modules instead (section
  5). Everything is copied in and out, so a list the function changes in
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
  `run_in_background` makes you do. (In a desktop app, real threads exist,
  so this matters most there.)

### Waiting in the template: Await

Loading something usually means three fields (`loading`, `error`, the data)
and an `<If>` over them. `<Await>` does that bookkeeping: it starts an async
call, shows its own content while the call runs, then the `<Then>` block
with what it returned, or the `<Catch>` block with what it raised.

```xml
<Await task="load_user(user_id)" key="user_id">
  <p>Loading…</p>
  <Then as="user">
    <h2>{{ user['name'] }}</h2>
  </Then>
  <Catch as="error">
    <p class="error">Couldn't load it: {{ error }}</p>
  </Catch>
</Await>
```

```python
from pyweft import http

user_id: int = 1

async def load_user(self, uid):
    return await http.get_json(f"/api/users/{uid}")
```

- **When it runs.** The call starts when the `<Await>` first appears and
  runs once: re-rendering doesn't start it again. Give `key` an expression
  and it starts over (showing the waiting content again) whenever that
  value changes; above, choosing another user loads that user. A run that
  is replaced, or whose `<Await>` leaves the page, is cancelled.
- **A task you keep.** `task` can also be a task you started yourself,
  kept in a field: `self.users = self.start_task(self.fetch_users())`.
  Assigning a new task (a Refresh button) shows the new one; the old one is
  left alone, since other code may be waiting for it too.
- **A plain value** shows the `<Then>` block straight away, so
  `task="cached or fetch()"` skips the wait when there's a cached copy.
- **`<Then>` and `<Catch>` are optional.** `as` names the variable
  (`value` and `error` when left out). Without a `<Catch>`, an error is
  reported like any failed handler (in the error overlay during `pyweft
  run`) and nothing is shown.
- Everything inside is in the component's scope as usual: its fields,
  methods and loop variables, plus the `as` name.

---

## 3. Template syntax reference

| Syntax | Meaning |
|---|---|
| `{{ expr }}` | Interpolate a Python expression in text or attribute values |
| `:attr="expr"` | Bind an attribute to an expression. `None`/`False` drop the attribute, `True` keeps it valueless (`:disabled="busy"`), anything else is stringified. On a component, passes the **typed** value as a prop |
| `class:name="expr"` | Add the class `name` while `expr` is true, on top of `class` (or `:class`): `<li class="row" class:active="item == chosen">` |
| `style:prop="expr"` | Set one CSS property (custom properties too: `style:--progress`) unless `expr` is `None`/`False`, on top of `style`: `style:width="f'{pct}%'"` |
| `@click="handler"` | A bare name calls that method; an expression is evaluated, so `@click="remove(item)"` works; simple statements run inline, so `@click="count += 1"` and `@click="show = not show"` work without a method. Any DOM event works the same way (`@input`, `@keydown`, `@submit` ...) |
| `@event.modifier` | `@submit.prevent`, `@keydown.enter`, `@click.stop`, `@keydown.ctrl.s.prevent`: see [event modifiers](#event-modifiers) |
| `@bind="field"` | Two-way binding on inputs, textareas, selects, checkboxes and radio buttons, converting to the field's declared type. `@bind.lazy`, `.trim`, `.number`: see [binding form controls](#binding-form-controls) |
| `<If cond="...">` / `<ElseIf cond="...">` / `<Else>` | Conditional rendering. Branch elements must be adjacent siblings |
| `<For each="item in items" key="item['id']" index="i">` | Loop. `key` gives rows stable identity across reorders (always use it for dynamic lists); `index` is optional |
| `<Await task="load(id)" key="id">` ... `<Then as="data">` ... `<Catch as="error">` | Wait for an async call: the content shown while it runs, then the `<Then>` or `<Catch>` block. See [waiting in the template](#waiting-in-the-template-await) |
| `<Head>...</Head>` | `<title>`, `<meta>`, `<link>` and `<style>` for the page's head while the component is shown. See [per-page tags](#per-page-tags-head) |
| `<Html :content="expr" />` | Show an HTML string (rendered Markdown, say) as markup, sanitized. See [showing HTML](#showing-html-from-elsewhere-html) |
| `<PascalCaseTag ... />` | Renders a child component (see below) |

Expressions are real Python, evaluated against the component's state plus any
loop variables. `self` is the component, so `{{ self.count }}` is the explicit
spelling of `{{ count }}`. Comprehensions, generator expressions and lambdas
see those names too: `{{ sum(i['price'] * qty for i in items) }}` works.
(Inline *statement* handlers such as `@click="total = sum(...)"` are the
exception: a generator or lambda there can't see them, so move such a
statement into a method.)

Each component's template is compiled into a Python function the first time
the component renders, which makes rendering about twice as fast as walking
the template. You don't have to do anything for it. Should you ever suspect
it, `PYWEFT_INTERPRET=1` in the environment turns it off.

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
| `localX`, `localY`, `width`, `height` | mouse and pointer events: the pointer's position inside the element the handler is on, and that element's size |
| `width`, `height`, `scrollX`, `scrollY` | events on `<Window>`: the window's size and how far it is scrolled |
| `hidden` | events on `<Document>`: whether the page is hidden (`visibilitychange`) |
| `form` | `submit`: the form's fields as `{name: value}`, a list when several fields share a name (file inputs are left out) |
| `files` | `drop` and a file `<input>`'s `change`: the files, as `PickedFile`s (see [files dragged onto the page](#files-and-dialogs)) |
| `kinds` | drag events: what is being dragged, `["Files"]` for files from the computer |
| `from_index`, `to_index`, `from_list`, `to_list`, `keyboard` | `@sort` on a [sortable list](#drag-to-reorder-sortable-lists) |
| `ratio`, `before`, `after` | `@split` on a [splitter](#resizable-panes-splitter) |

Asking for a key the event doesn't have raises an `AttributeError` that
lists the keys it does have.

### Reacting to an element's size: @resize

`@resize` isn't a browser event: it fires when the element is first laid
out and again whenever its size changes, with `event.width` and
`event.height` in whole pixels (the content box). Use it to lay something
out for the space it really has, such as fewer labels on a narrow screen:

```xml
<div @resize="fit"> ... </div>
```

```python
wide: bool = True

def fit(self, event):
    self.wide = event.width >= 600
```

It needs a page, so it never fires in pre-rendering or headless tests:
start with a sensible default.

### Events on the whole page: Window and Document

`<Window>` and `<Document>` listen to the window or the document instead
of one element: keyboard shortcuts that work wherever the focus is, the
window being scrolled or resized, the tab being hidden.

```xml
<Window @keydown.ctrl.k.prevent="focus('search')" @scroll="moved" />
<Document @visibilitychange="paused(event)" />
```

```python
def moved(self, event):
    self.show_back_to_top = event.scrollY > 600

def paused(self, event):
    if event.hidden:
        self.save_draft()
```

They take event handlers only (no content, no other attributes) and work
anywhere in a template, with the usual modifiers. They listen while the
component that renders them is on the page: put one inside an `<If>` to
listen only some of the time, and when the component goes, so do its
listeners (and their `.prevent`). A `<Window>` event carries `width`,
`height`, `scrollX` and `scrollY`; a `<Document>` one carries `hidden`.

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
- **Checkbox groups:** checkboxes bound to a `list` (or `set`, `tuple`)
  field share it. Each one is checked while its `value` is in the list, and
  adds or removes it when clicked:

  ```xml
  <For each="t in ['cheese', 'olives', 'basil']">
    <label><input type="checkbox" :value="t" @bind="toppings" /> {{ t }}</label>
  </For>
  ```

  ```python
  toppings: list[str] = []      # ["cheese", "basil"] when those are ticked
  ```

  With `:value`, the list gets the value itself, with its type
  (`:value="row['id']"` adds an `int`); with `value="..."` it gets the text.
  Each click stores a new list rather than changing the old one, so
  effects and other code see the change.
- **Modifiers:** `@bind.lazy` updates when the user leaves the field (the
  `change` event) rather than on every keystroke; `@bind.trim` strips
  surrounding spaces; `@bind.number` parses a number even when the field has
  no declared type.
- **Your own handler alongside:** `@bind` and `@input` on one element both
  run, the binding first, so your handler already sees the new value:

  ```xml
  <input @bind="query" @input="search()" />
  ```

### Input masks

`data-mask` shapes what's typed into an input as the user types, such as a
phone or card number:

```xml
<input @bind="phone" data-mask="(999) 999-9999" inputmode="numeric" />
<input @bind="card" data-mask="9999 9999 9999 9999" />
<input @bind="plate" data-mask="aa-9999" />
```

- **In a mask**, `9` is a digit, `a` a letter, `*` a letter or digit, and
  `\` makes the next character literal; anything else is shown as it is,
  filled in around what's typed (but never after the last character, so
  Backspace works as expected).
- **It happens in the page**, before your `@bind` or `@input` sees the
  event, so the cursor stays where the user is typing, even in the middle.
  Characters that don't fit (a letter where a digit goes) are refused, and
  extra ones are dropped. Your field gets the shaped text,
  `"(555) 123-4567"`.
- **`pyweft.masks`** has the same rules in Python:
  `masks.apply("(999) 999-9999", "5551234567")` shapes a starting value,
  `masks.complete(mask, text)` checks every slot is filled, and
  `masks.typed(mask, text)` gives just the typed characters
  (`"5551234567"`), for storing.

### Moving focus and scrolling: ref

Mark an element with `ref="name"`, then move keyboard focus to it or scroll
to it from Python:

```xml
<template>
  <form @submit.prevent="save">
    <input ref="title" @bind="title" />
    <If cond="error"><p ref="problem" class="error">{{ error }}</p></If>
    <button>Save</button>
  </form>
</template>

<code>
title: str = ""
error: str = ""

def on_init(self):
    self.focus("title")           # ready to type as soon as it shows

def save(self):
    if not self.title:
        self.error = "Give it a title"
        self.scroll_to("problem")  # the <p> appears in this same render
        self.focus("title")
</code>
```

- **Requests wait for the render**, so they can name an element that the
  same handler makes appear, like `problem` above.
- `ref` on a component tag (`<ui.TextField ref="email" />`) names the
  component; `focus()` then goes to the first thing inside it that takes
  focus, such as its input.
- In a loop, make each name unique: `ref="row-{{ i }}"`.
- A name that isn't on the page when the request is carried out is
  ignored.

| Method | Does |
|---|---|
| `focus(ref)` | focuses the element (or the first focusable thing inside it) |
| `focus_first(ref)`, `focus_last(ref)` | focuses the first or last focusable element inside |
| `scroll_to(ref)` | scrolls the page just enough to show the element; `scroll_to(ref, align="start")` brings it to the top of the window (or `"center"`, `"end"`), as a link to a section would |
| `keep_in_view(ref)` | shifts the element sideways just enough to stay inside the window: for a popup opening near the edge. `keep_in_view(ref, vertical=True)` shifts it up or down too, for a popup placed at a point, such as a context menu at the pointer; `flip=True` moves a popup opened beside its parent (a submenu) to the parent's other side when it doesn't fit |
| `save_focus()`, `restore_focus()` | remembers what has focus, and later puts it back, for popups |

`ref` is not written to the page as an attribute.

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

### Transitions and animations

Give an element `transition` and it animates when it appears and when it
goes, instead of jumping in and out:

```xml
<If cond="saved">
  <p class="notice" transition="fade">Saved</p>
</If>

<ul>
  <For each="item in items" key="item['id']">
    <li transition="slide" animate="flip">{{ item['text'] }}</li>
  </For>
</ul>
```

| Attribute | Plays |
|---|---|
| `transition="..."` | when the element appears and when it leaves |
| `in="..."` / `out="..."` | only when it appears / only when it leaves (use both for different ones) |
| `animate="flip"` | when a render moves it (a keyed list reordered, a row above removed): it slides to its new place |

The built-in transitions are `fade`, `fly` (fades and moves in from
`x`/`y` pixels away; default `y=16`), `slide` (grows from nothing to its
height, `axis=x` for width), `scale` (from `start=0.9`) and `blur`. Options
follow the name: `transition="fly y=-20 duration=300 delay=50"`, plus
`easing=ease-out` or any CSS easing. Durations are in milliseconds (200 by
default). Any other name plays the app's own CSS `@keyframes` of that
name, forwards to appear and backwards to leave.

A leaving element stays on screen until its animation ends, and can't be
clicked or focused meanwhile; the next render already treats it as gone.
Transitions play for the element that appears or leaves itself, not for
everything inside a block that does, and not on the page's first render.
Anyone who asks their system for reduced motion gets none. On a component
tag, they apply to the component's root element; `:transition="..."`
works too (`None` for no transition).

### Drag to reorder: sortable lists

Mark a list `sortable` and its items can be dragged into a new order, with
a mouse, a finger, or the keyboard. When one is dropped, the list's `@sort`
handler gets where it came from and where it went; reorder your list there
and the page follows:

```xml
<ul sortable="" @sort="move(event)">
  <For each="task in tasks" key="task['id']">
    <li tabindex="0" animate="flip">{{ task['title'] }}</li>
  </For>
</ul>
```

```python
def move(self, event):
    task = self.tasks.pop(event.from_index)
    self.tasks.insert(event.to_index, task)
```

- **While dragging**, the item follows the pointer and the others slide
  aside to show where it would land; nothing changes in your state until
  the drop. The window scrolls when the pointer nears its edge, and Esc
  cancels. An item being dragged has a `data-pw-dragging` attribute, for
  your own style (it gets a shadow by default).
- **A grip:** put `sortable-handle=""` on an element inside each item (an
  icon) and only that starts a drag, so the rest of the item can be
  clicked and selected as usual. Without one, the whole item drags, except
  from its buttons, links and fields. On a phone, an item without a grip
  starts dragging after the finger rests on it for a moment, so the list
  still scrolls.
- **Keyboard:** Alt+↑/↓ (or ←/→ in a row) moves the focused item one place,
  and a screen reader hears its new position. Give items `tabindex="0"`
  (or put a focusable element in them) so they can be reached.
- **Between lists**, for a kanban board: lists with the same name in
  `sortable="board"` share their items. `sortable-name` says which list is
  which, and arrives as `event.from_list` and `event.to_list`:

  ```xml
  <For each="col in ['todo', 'doing', 'done']" key="col">
    <ul sortable="board" :sortable-name="col" @sort="move_card(event)">
      <For each="card in cards[col]" key="card['id']"><li>{{ card['title'] }}</li></For>
    </ul>
  </For>
  ```

  ```python
  def move_card(self, event):
      card = self.cards[event.from_list].pop(event.from_index)
      self.cards[event.to_list].insert(event.to_index, card)
  ```

  `@sort` goes to the list the item was dropped on.
- The items are the list's child elements; mark one that isn't (a heading
  inside the list) with `sortable-ignore=""` so the positions match your
  list. Key the `<For>`, and `animate="flip"` makes the final move slide.
- Your handler decides: it may refuse a move (leave the list as it is) and
  the item slides back.

### Resizable panes: splitter

A `splitter` element between two others in a flex row (or column) is a
divider the user can drag to resize them. The browser moves it smoothly,
and your handler hears the result once, on release:

```xml
<div class="panes">
  <div :style="f'flex: {left} 1 0'">...</div>
  <div class="divider" splitter="" @split="resized(event)"></div>
  <div :style="f'flex: {100 - left} 1 0'">...</div>
</div>
```

```python
left: float = 30

def resized(self, event):
    self.left = round(event.ratio * 100, 1)   # ratio: the first one's share
```

`event.before` and `event.after` are the two sizes in pixels. Their
`min-width` and `max-width` (height in a column) limit the drag, and while
it lasts `@resize` handlers wait, hearing only the final size. In most apps
[`ui.Splitter`](#ready-made-controls-pyweft-ui) is the easier way: panes,
keyboard support, collapsing and remembered sizes included.

### Showing HTML from elsewhere: Html

Text in `{{ }}` is always shown as text: `<b>` in a value appears as the
characters `<b>`. To show an HTML string as markup, Markdown rendered to
HTML or rich text from a CMS, use `<Html>`:

```xml
<article class="post">
  <Html :content="body_html" />
</article>
```

```python
import markdown            # a PyPI package, in your pyproject.toml

text: str = "# Hello\n\nSome *Markdown*."

@property
def body_html(self):
    return markdown.markdown(self.text)
```

- **It is sanitized.** The string often comes from users or another
  service, so anything that could run code is removed first: `<script>`,
  `<iframe>`, `<object>`, forms, `on...` attributes, `javascript:` links,
  and styles that load files or cover the page. Headings, paragraphs,
  lists, tables, links, images, code blocks and the like stay.
- **`trusted="true"`** keeps everything except `<script>`, for HTML you
  wrote yourself (an embedded video, an inline SVG). Never use it for text
  a user typed.
- The markup goes in place of the tag, with no wrapper element, and your
  component's `<style>` block applies to it (`.post h2 { ... }` above works).
- `None` shows nothing; an object with an `__html__()` method (such as
  markupsafe's `Markup`) gives its HTML.
- The HTML is turned into the same kind of nodes a template produces, so an
  update changes only what changed, the same in the browser, the desktop
  app and the first-screen pre-render.

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

**Lifecycle:** a child's `on_init` runs the first time a render produces it,
and its `on_dispose` when a render no longer does (its `<If>` went false, its
row left the list). A parent's `on_init` runs before its children's, since
its render is what creates them. See
[lifecycle](#lifecycle-when-your-code-runs) for all of them.

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

### Sharing state between components: Store

Some state belongs to the whole app rather than to one component: a cart
that the header counts and every page adds to, the signed-in user, settings.
Put it in a store, a class in one of your app's `.py` modules:

```python
# cart.py, next to app.weft
from pyweft import Store

class Cart(Store):
    items: list = []

    @property
    def count(self):
        return len(self.items)

    def add(self, product):
        self.items.append(product)

    def clear(self):
        self.items = []

cart = Cart()
```

Any component imports it and uses it like its own state:

```xml
<!-- header.weft -->
<template>
  <header>Cart ({{ cart.count }})</header>
</template>

<code>
from cart import cart
</code>
```

```xml
<!-- pages/product.weft -->
<template>
  <button @click="cart.add(name)">Add {{ name }} to cart</button>
</template>

<code>
from cart import cart
name: str = "Teapot"
</code>
```

- **Everything showing it updates.** Clicking the button changes the cart,
  and the header's count follows, though neither component knows the other.
- **Changes from anywhere work**: a timer, an async task, a JavaScript
  callback. Setting a field (`cart.items = [...]`) or calling one of the
  store's methods (`cart.add(...)`) re-renders the page; an `async` method
  does it when it finishes. Inside a handler you don't notice the
  difference, since the page renders after every handler anyway.
- **Change it through its methods** when you change something in place.
  `cart.items.append(x)` from a timer, outside the store, isn't seen; call
  `cart.changed()` after it, or better, give the store a method.
- **Computed values are `@property`s**, like `count`. Methods are for
  changes.
- **Fields work like a component's:** declare them with a default, and a
  mutable default (`items: list = []`) is copied for each store you create.
  `Cart(items=["mug"])` starts with values of your own.
- **Effects see stores too:** an `@effect` that reads `self.cart` (or reads
  it through a property) runs again when the cart changes.
- **One store object, everywhere.** It lives in a module, so every
  component that imports it gets the same object, and it keeps its contents
  while you navigate between pages and through hot reloads of `.weft` files
  (editing the `.py` file itself reloads the page).

A store is the right place for state that outlives one component. For state
that only a component and its children use, props and `emit` stay simpler.

### Passing values down the tree: provide and inject

Some values are needed deep inside a part of the page without the
components in between caring: the current theme, the signed-in user, the
form a field belongs to. Instead of passing them as props through every
level, a component *provides* a value and any component below it *injects*
it:

```python
# app.weft (or any component)
from session import Session

def on_init(self):
    self.provide("session", Session(user="ada"))
```

```xml
<!-- a component anywhere inside it -->
<p>Signed in as {{ inject('session').user }}</p>
```

- **Keys** are strings, or classes for a typed lookup:
  `self.provide(Session, ...)` and `self.inject(Session)`.
- **Nearest wins.** `inject` asks the component above, then the one above
  that, and so on, and a component's own `provide` is only seen by those
  below it. So a component can inject a value and provide a changed one to
  its own children (a nested section that's one level deeper).
- **Content passed into a slot** sees what the component showing it
  provides, so a wrapper like `<ThemeProvider>...</ThemeProvider>` works.
- **Missing values:** `inject("x", None)` returns the default; without
  one, a missing key raises an error naming the component.
- **Changes:** read it where you use it (in the template or a property),
  not once into a field: a template reads it on every render, so it sees a
  value the provider later replaces with another `provide`. For changing
  state, provide a [Store](#sharing-state-between-components-store) or
  another object and change its fields.
- Call `provide` in `on_init` (children are created after it, so they can
  inject in their own `on_init`). Like everything else, it works from
  `on_init` onwards, not in `__init__`.

### Choosing a component while the app runs: Dynamic

When *which* component to show is decided by your state, write `<Dynamic>`
and give it the class with `:is`:

```xml
<Dynamic :is="EDITORS[shape]" :value="settings" @update="save(event)" />
```

```python
from pyweft import load_component
EDITORS = {"circle": load_component("circle_editor.weft"),
           "square": load_component("square_editor.weft")}
shape: str = "circle"
```

- **Switching the class replaces the component:** the old one's
  `on_dispose` runs, and the new one starts fresh with `on_init`.
- **`:is="None"` shows nothing.**
- **Attributes, events, `@bind` and slot content** work as on any component
  tag. `:props="mapping"` passes props by name too, for when which ones
  apply depends on the class; attributes written out win over it.
- A `key="..."` on it makes a new key mean a new instance even when the
  class stays the same.

### Pages and navigation

An app with several screens keeps them in a `pages/` folder, one `.weft` file
per page, and shows the current one with a router:

```
myapp/
  app.weft
  pages/
    index.weft        /
    orders.weft       /orders
    order.weft        /orders/7 (its route says so, below)
    settings/
      user_profile.weft   /settings/user-profile
    not_found.weft    any address without a page
```

```xml
<!-- app.weft -->
<template>
  <div>
    <nav>
      <Link to="/">Home</Link>
      <Link to="/orders">Orders</Link>
    </nav>
    <main><Pages /></main>
  </div>
</template>

<code>
from pyweft import Link, router

Pages = router("pages")
</code>
```

`<Pages />` shows the page for the current address; everything around it
(the nav here) stays put. The address is the part after `#` in the browser
(`http://localhost:8642/#/orders`), so Back, Forward, bookmarks and reloading
all work, and a built app needs no special server setup.

**URLs come from file names.** `index.weft` is its folder's address, a
folder adds a segment, and `_` in a name becomes `-`. Files and folders
starting with `_` are not pages. Keep components that pages share somewhere
else, such as next to `app.weft` or in a `components/` folder (used as
`<components.OrderRow>`), since every file in `pages/` is a page.

**Values from the address arrive as fields.** A page can set its own
address with `route`, with `{name}` for a part that varies:

```xml
<!-- pages/order.weft -->
<template>
  <section>
    <h1>Order #{{ id }}</h1>
    <If cond="order is None"><p>Loading…</p></If>
    <Else><p>{{ order['customer'] }}</p></Else>
  </section>
</template>

<code>
route = "/orders/{id}"
id: int = 0
order = None

async def on_init(self):
    self.order = await fetch_order(self.id)
</code>
```

`id` is converted to the type the page declares, so `/orders/7` gives the
`int` 7 and `/orders/abc` is not this page at all (it shows `not_found`).
Query parameters fill fields too: `/orders?status=paid` sets the orders
page's `status: str = "all"` field to `"paid"`. When two routes could match,
the fixed one wins: `pages/orders/new.weft` takes `/orders/new` before
`/orders/{id}` sees it.

**Every address is a fresh page.** Going from `/orders/7` to `/orders/8`, or
from `?status=paid` to `?status=pending`, creates a new page component, so
`on_init` loads its data again and fields not in the address start at their
defaults.

**Links:** `<Link to="/orders">` is a link (`<a href="#/orders">`) that gets
`class="active"` and `aria-current="page"` while its page, or one below it,
is showing; add `exact="true"` to match only that address. Ctrl- and
Cmd-clicks open a new tab as usual. A plain `<a href="#/orders">` works too,
just without the active marking.

**From code:**

```python
from pyweft import navigate
from pyweft.routing import back, location

navigate("/orders/7")                            # go there
navigate("/orders", query={"status": "paid"})    # /orders?status=paid
navigate("/login", replace=True)                 # Back won't return here
back()                                           # the Back button
location().path, location().query                # "/orders", {"status": "paid"}
```

Calling `navigate()` in a page's `on_init` redirects: the new page replaces
it before anything is shown. Use `replace=True` there so Back doesn't land on
the redirect again.

**Page titles:** a `<Head><title>Order #{{ id }} - Acme</title></Head>` in
the page's template names the browser tab or window after it, or call
`set_title(...)` in its `on_init` (see [per-page tags](#per-page-tags-head)).

**Breadcrumbs:** give a page a `crumb` in its code block (`crumb = "Orders"`,
or `crumb = "Order #{id}"` to fill in route parameters), and
`pyweft.routing.trail()` gives the trail to the current page: one
`Crumb(to, label)` per level, so `/orders/7` is Home, Orders, Order #7. A
page without a `crumb` is named after its URL segment (`order-items`
becomes "Order items"), and a level with no page of its own (`/settings`
when only `/settings/profile` exists) comes with `to=None`.
`pyweft-ui`'s `<ui.Breadcrumbs auto="true" />` shows it.

**The page for unknown addresses** is `pages/not_found.weft`; declare
`path: str = ""` in it to show the address that was asked for. Without the
file, a plain "There is no page at …" message is shown.

`examples/shop/` is a small app using all of this:
`uv run pyweft run examples/shop`.

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
  AGENTS.md         # how to write this app, for AI coding assistants
  CLAUDE.md         # "@AGENTS.md": Claude Code reads AGENTS.md through it
```

`AGENTS.md` is for AI coding assistants (Claude Code, Codex, Cursor,
Copilot and others read it): PyWeft is too new for them to know, so it
spells out the file format, the directives, components, async, routing,
`pyweft-ui`, and the mistakes generated code usually makes. It is written
for the PyWeft version you have; after upgrading, refresh it with
`uv run pyweft agents myapp` (which also adds the two files to an app made
before they existed, and leaves an existing `CLAUDE.md` alone). The same
text is on the website as
[agents.md](https://prassanthn.github.io/PyWeft/agents.md), and all the
documentation as one plain-text file for AI tools at
[llms-full.txt](https://prassanthn.github.io/PyWeft/llms-full.txt) (indexed
by [llms.txt](https://prassanthn.github.io/PyWeft/llms.txt)).

Add more components as sibling `.weft` files — `<TodoItem>` in a template
finds `todo_item.weft` automatically — or group them in folders and use
dotted tags such as `<widgets.Row>` (section 4). `pyweft run` and `pyweft
build` pick up `.weft` and `.css` files in subfolders too. They skip folders
a tag cannot name (`.venv`, anything starting with `_`), `node_modules`,
`assets/` (served as-is, see below), and build output such as `dist/`.

Plain Python modules work the same way. Put shared data or helper functions
in a `.py` file next to `app.weft` (or in a package folder with an
`__init__.py`) and import it from any component's `<code>` block:

```
myapp/
  app.weft
  orders_data.py    # ORDERS = [...], def total(order): ...
  pages/
    orders.weft     # <code> import orders_data </code>
```

The app folder is on the import path in the browser, and in the
`run_in_background` worker too. `.py` files follow the same folder rules as
components, so keep scripts that must not reach the browser (a deploy script
with a token in it, say) in a `_`-prefixed folder or outside the app folder:
everything else **is shipped to visitors**.

### Hot reload

While `pyweft run` is serving, every save shows up in the open page within
about half a second, and the app keeps its state: todos you added, text
you'd typed, toggles you'd set. What happens depends on what you saved:

| You save | The page | State |
|---|---|---|
| a `.weft` file: template, `<code>` or `<style>` | recompiles it and patches only what changed | kept |
| a global `.css` file | swaps the stylesheet, in the same place | kept |
| a `.py` module of your app | reloads (Python keeps imported modules cached) | reset |
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

### Checking an app: pyweft check

```bash
uv run pyweft check myapp
```

`check` finds mistakes without running the app in a browser. It loads every
component as `pyweft run` would, then reads each template against what its
component defines, and prints one line per problem with the file and line:

```
app.weft:12: error: {{ }}: unknown name 'cout' (did you mean 'count'?) [unknown-name]
app.weft:20: warning: <ui.TextField>: 'lable' is not one of its props, so it goes to its root element as an attribute (did you mean 'label'?) [unknown-prop]
1 error, 1 warning in 4 component files.
```

**Errors** (the app would fail, or something would silently not work):
template and Python syntax errors, a code block that fails as it runs,
missing modules, components that can't be found, unknown names in
expressions, handlers and `@bind` fields that don't exist, slot content for
a slot the component doesn't have, modifiers on a component's events, a
keyed `<For>` whose body has more than one element, and generator
expressions or lambdas in an inline statement handler that use the
component's names (they can't see them).

**Warnings** (probably a mistake): an attribute on a component tag that
isn't one of its props (it goes to the component's root element instead;
`class`, `id`, `style`, `title`, `aria-*`, `data-*` and the like are
expected there, so they don't count), an event the component never emits,
a handler that sets state the component doesn't declare, `:class` next to
`class` (it replaces it), a field named like a Python builtin that the same
code block calls (`max: int` then `max(a, b)`), and list comprehensions in
an inline statement handler that fail on Python 3.10 and 3.11.

**It also checks that the app's dependencies install in the browser**
(see [Using PyPI packages](#using-pypi-packages)): each one, and everything
it needs, must be pure Python or built into Pyodide, in a version that fits.
That part asks PyPI (answers are kept for a day); offline, it says it
couldn't check rather than failing, and `--no-deps` skips it.

**Accessibility.** `check` also warns (codes starting `a11y-`) about
markup that shuts out keyboard and screen-reader users:

| Code | What it means |
|---|---|
| `a11y-missing-alt` | an `<img>` without `alt` (write `alt=""` for a decorative one) |
| `a11y-click-without-keyboard` | `@click` on a `<div>`, `<span>`, `<li>` ... with no keyboard way to do it: use a `<button>` |
| `a11y-not-focusable` | it handles keys or has a widget role, but Tab never reaches it: add `tabindex="0"` |
| `a11y-anchor-no-href` | `<a @click>` without `href` is not a link: use `<button type="button">` |
| `a11y-missing-label` | an input, select or textarea with no label (a placeholder is not one) |
| `a11y-empty-button` | a button with nothing to read out: add text or `aria-label` (icon buttons) |
| `a11y-positive-tabindex` | `tabindex` above 0, which jumbles the Tab order |
| `a11y-unknown-role`, `a11y-unknown-aria` | a misspelt `role` or `aria-*` attribute, with a "did you mean" |

A click target marked `aria-hidden="true"` (a backdrop that closes a popup,
while Esc does the same from the keyboard) is fine. When something is
right as it is, say so above the element and that warning goes away (any
`check` warning or error can be silenced this way; with no codes, all of
them are):

```xml
<!-- pyweft-ignore: a11y-click-without-keyboard (the arrow keys do this) -->
<div class="cell" @click="pick(cell)"></div>
```

`--no-a11y` skips these checks altogether.

It exits with 1 when there are errors, so it can guard a commit or a CI job.
`--json` prints the problems as JSON (`file`, `line`, `severity`, `code`,
`message`) for editors and other tools. AI coding assistants are told to
run it after every change (see `AGENTS.md` above); its "did you mean"
suggestions are what lets them fix their own mistakes.

`check` runs your code blocks (and the modules they import) the way `run`
does, but never your app's handlers, `on_init` or network calls.
Browser-only modules (`js`, `pyodide`) are stood in for; a dependency that
isn't installed where you run `check` is reported, so install the app's
dependencies there first.

### The loading screen

Starting Python in the browser takes a few seconds on the first visit (the
runtime is downloaded, then cached), so the page shows a loading screen until
your app has rendered, then fades it out. `pyweft new` gives you the default
one as `loading.html`: a small piece of cloth being woven, two rows for each
startup step, with a line of progress text underneath. It follows the
system's light or dark colors (set `--pyweft-loader-color` on
`#pyweft-loading` to tint it) and stays still for visitors who prefer
reduced motion.

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
- **Progress you can style:** the wrapper `#pyweft-loading` gets
  `data-pyweft-step="python"`, then `"packages"` (only when the app has
  dependencies), `"app"` and finally `"ready"` as it fades out, and the CSS
  variable `--pyweft-progress` goes from 0 to 1 with them. A progress bar
  needs no JavaScript:

  ```css
  .bar { height: 3px; background: #1e3a5f;
         width: calc(var(--pyweft-progress, 0) * 100%); transition: width .3s; }
  #pyweft-loading[data-pyweft-step="packages"] .hint { display: block; }
  ```

  Downloading Python is most of a first visit, so the bar moves by step, not
  by bytes.
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

### The first screen, before Python starts

Most visitors never see the loading screen: `pyweft run` and `pyweft build`
render your app's first screen on your machine and put it in the page. The
real page appears at once, slightly dimmed and not yet clickable, with a thin
progress bar along the top. When Python has started in the browser it takes
over that same page, which brightens and starts responding. Nothing moves or
blinks, because the page Python renders is the same one.

What the first screen shows is what your app renders before anything
arrives: initial field values, synchronous `on_init` code, effects, and an
async `on_init` up to its first `await` (a "Loading orders…" message, say).
Your own `.py` modules and installed component libraries work as they do in
the browser.

The loading screen is used instead when:

- **the app can't be rendered on your machine**: code that only works in a
  browser (`import js`, `pyodide`), or a package that isn't installed
  locally. `pyweft run` and `build` print why, and the page still works;
- **the page is opened at another address** than the one rendered (a link
  to `#/orders/7` in an app with pages), so the wrong page never flashes up;
- **you turn it off** with `--no-prerender` on `run` or `build`, for example
  to keep a custom splash screen.

Two things to know:

- **Your app's code runs on your machine** as part of `run` and `build`, up
  to its first `await`, in a separate process. Keep code with side effects
  (sending analytics, say) behind an `await` or in a handler.
- **Clicks and typing before Python is ready don't count**: the page is
  inert until then, which is why it is dimmed.

The bar's color is your system's highlight color; set `--pyweft-bar-color`
on `:root` in your CSS to change it.

### The app's title and icon

Name your app in its `pyproject.toml` (`pyweft new` starts you off):

```toml
[tool.pyweft]
title = "Acme Orders"
icon = "assets/icon.ico"
```

- **`title`** is the browser tab's title, and the desktop window's. Without
  it, the app folder's name is used.
- **`icon`** is the browser tab's icon (favicon) and the desktop window's.
  It must be a file in your app's `assets/` folder: `.ico` (needed for a
  Windows window icon), `.png` or `.svg`.

A mistake, such as a misspelled setting or an icon that isn't there, stops
`pyweft run` and `build` with a message naming it.

**Changing the title while the app runs:** call `set_title()` from a
handler, an `on_init` or a task:

```python
from pyweft import set_title

def on_init(self):
    set_title(f"Order #{self.id} - Acme")
```

It updates the browser tab, or the window in a desktop app. A title stays
until the next `set_title()`, so with [pages](#pages-and-navigation), give
each page its own in its `on_init`. A `<title>` in a [`<Head>`
block](#per-page-tags-head) does the same from the template.

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

### Per-page tags: Head

`head.html` is the same for every page. For tags that depend on what is
shown, a description or a link preview for this order, write a `<Head>`
block in the component's template:

```xml
<Head>
  <title>Order #{{ id }} - Acme</title>
  <meta name="description" :content="f'{order_count} items for {customer}'" />
  <meta property="og:title" :content="f'Order #{id}'" />
  <link rel="canonical" :href="f'https://acme.example/#/orders/{id}'" />
</Head>
```

- It renders nothing where it is written: its tags go into the page's
  `<head>` while the component is shown, update when the values change, and
  leave when the component does. `<If>` and `<For>` work inside it.
- It holds `<title>`, `<meta>`, `<link>` and `<style>`. A `<title>` names
  the browser tab (or the desktop window), and the app's own title comes
  back once no `<Head>` has one. Scripts go in `head.html`.
- Several components can have one; their tags add up, and the last
  `<title>` wins.
- **Link previews and search engines** read the HTML before any Python
  runs. The first screen is [rendered ahead of time](#the-first-screen-before-python-starts)
  with its `<Head>` tags, so the app's start page carries them in the HTML
  that `pyweft build` writes. Other pages of a single-page app share that
  file, so their tags are only seen by visitors' browsers.

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

**Classes that depend on state.** Keep the fixed classes in `class` and
add each conditional one with `class:name="condition"`:

```xml
<button @click="show = name" class="rounded-lg px-3 py-1.5"
        class:bg-slate-900="name == show" class:text-white="name == show"
        class:text-slate-500="name != show">
  {{ name }}
</button>
```

A class name with a `:` or `/` in it (`dark:bg-white`, `w-1/2`) can't be
written that way: put those in a `:class` expression. `:class` sets the
whole attribute, so an element with both `class` and `:class` gets only
the `:class` one; write the fixed classes in the expression too.

The todo and shop examples (`examples/todo`, `examples/shop`) are styled
with Tailwind's CLI exactly as above: see each one's `_tailwind/input.css`
for the setup and the command that rebuilds its `tailwind.css`.

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
(`AppShell`, `Row`, `Column`, `Grid`, `Card`, `Divider`, `Carousel`, `Expansion`, `Accordion`), form fields (`TextField`,
`TextArea`, `NumberField`, `Select`, `Autocomplete`, `CascadeSelect`, `Chips`, `ChipInput`, `ButtonToggle`,
`Slider`, `RadioGroup`, `Checkbox`, `Switch`, `DatePicker`, `DateRangePicker`, `Calendar`), data and navigation (`Table` with sorting, `Tree`, `Tabs`, `Stepper`, `Breadcrumbs`,
`EventCalendar`), charts (`BarChart`, `LineChart`, `PieChart`, `PolarAreaChart`,
`RadarChart`, `ScatterChart`, `Sparkline`, `Gauge`, `FunnelChart`, `WaterfallChart`, `Histogram`, `BoxPlot`,
`Heatmap`, `CorrelationMatrix`, `CandlestickChart`, `Treemap`, `SankeyChart`, `CalendarHeatmap`), actions
and feedback (`Button`, `Menu`, `ContextMenu`, `Dialog`, `BottomSheet`, `Popover`, `Tooltip`, `Alert`, `Toaster` with `toast()`, `Badge`, `Spinner`, `Progress`,
`Icon`) and a `Theme` with light, dark and system modes and your own
colours.

It also checks forms. Name each field's rules, show each field's message,
and check them all on submit:

```python
from pyweft_ui import Form, rules

form = Form(
    email=[rules.required(), rules.email()],
    password=[rules.required(), rules.min_length(8)],
)

async def submit(self):
    if not self.form.check():   # shows every message, focuses the first field to fix
        return
```

```xml
<ui.TextField ref="email" label="Email" @bind="email"
              :error="form.error('email')" @blur="form.touch('email')" />
```

A message appears once the user has left the field or tried to submit,
then follows what they type.

The [pyweft-ui guide](../packages/pyweft-ui/docs/guide.md) shows how
to build pages, forms, tables and dialogs with them;
[packages/pyweft-ui/README.md](../packages/pyweft-ui/README.md) is the
reference; and the gallery shows every control live:

```bash
uv run pyweft run packages/pyweft-ui/gallery
```

Install it into the same environment as PyWeft:

```bash
uv add pyweft-ui
```

(with pip: `pip install pyweft-ui`), then add `"pyweft-ui"` to the `dependencies` in your app's own
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

One constraint, inherited from the browser: a package, and everything it
depends on, must be **pure Python** (most are) or one of the packages
[Pyodide ships prebuilt](https://pyodide.org/en/0.26.4/usage/packages-in-pyodide.html)
(numpy, pandas, pydantic, scikit-learn, …), and the prebuilt ones come in
fixed versions (pydantic is 2.7.0). A package with native code that Pyodide
doesn't build can't be installed: today that includes LangChain and the
official OpenAI and Anthropic SDKs. Packages needing raw sockets or
subprocesses won't work in a browser regardless. The desktop app runs
ordinary Python, so none of this applies there.

**`pyweft check` tells you before you ship** (see
[Checking an app](#checking-an-app-pyweft-check)): it follows each
dependency's own requirements the way micropip would and names the one
that won't install, and why:

```
pyproject.toml:8: error: in the browser: 'jiter' (needed by anthropic) has native code (wheels only for Windows, macOS and Linux), and Pyodide 0.26.4 doesn't build it, so it can't be installed in the browser (the desktop app isn't affected) [dependency-native]
```

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

### Files and dialogs

`pyweft.dialogs` opens and saves files and asks yes-or-no questions, the
same way in the browser and in a [desktop app](#a-desktop-app-pyweft-run---desktop).
The calls are `async`, so use them in `async` handlers:

```python
import csv, io
from pyweft import dialogs

async def import_orders(self):
    file = await dialogs.open_file(types=["csv"])
    if file:                                    # None when cancelled
        self.orders = list(csv.DictReader(io.StringIO(file.text)))

async def export(self):
    await dialogs.save_file(self.as_csv(), name="orders.csv")

async def clear(self):
    if await dialogs.confirm("Delete all orders?", title="Orders"):
        self.orders = []
```

| Call | Returns | In the browser | In a desktop app |
|---|---|---|---|
| `open_file(types=["csv"])` | a `PickedFile`, or `None` if cancelled | the browser's file picker | the system's Open dialog |
| `open_files(types=[...])` | a list of `PickedFile`s (empty if cancelled) | the same, choosing several | the same, choosing several |
| `save_file(data, name="x.csv")` | `True` once saved, `False` if cancelled | a download | the system's Save As dialog |
| `confirm(message, title="")` | `True` for OK | the browser's confirm box | a system dialog |

- **A `PickedFile`** has `name`, `data` (the bytes) and `text` (the bytes
  as UTF-8). In a desktop app it also has `path`; in the browser that is
  `None`, because a web page is never shown your file system.
- **`types`** are extensions: `"csv"`, `".csv"` or `"*.csv"`. `save_file`
  takes text (saved as UTF-8) or bytes, and in the browser always returns
  `True`, since a download can't be cancelled from the page.
- **In the browser, open a file from a click.** Browsers only show a file
  picker in answer to the user, so call `open_file` in a click handler
  before any other `await`, not from a timer.
- **In a desktop app, your code can also use files directly**, since it
  runs in ordinary Python: `Path.home() / "Documents" / "orders.csv"`.
  Use absolute paths (a relative one starts from where you ran
  `pyweft run`), and keep files your app writes out of its own folder,
  where `pyweft run` would take them for edits.
- **In tests**, `dialogs.set_host()` installs a stand-in that answers
  instead of the user; without one, the calls raise an error saying so.

**Files dragged onto the page.** A `drop` event's `event.files` holds the
dropped files as the same `PickedFile`s, read before your handler runs;
`<input type="file" @change="...">` gets them the same way. `PickedFile`
also has `size` (bytes) and `type` (the media type its name suggests,
`image/png`). A drop zone needs `@dragover.prevent=""` and
`@drop.prevent="..."`, or the browser opens the file instead.
[`ui.FileDrop`](#ready-made-controls-pyweft-ui) does all of that, plus a
"Choose files" button, types and sizes:

```xml
<ui.FileDrop accept="csv, xlsx" max_mb="5" @files="import_files(event)" />
```

### Loading data: pyweft.http

`pyweft.http` calls web APIs and loads files, the same way in the browser
and in a [desktop app](#a-desktop-app-pyweft-run---desktop). Requests are
`async`, so make them in `async` handlers or an `async def on_init`:

```python
from pyweft import http

orders: list = []
error: str = ""

async def on_init(self):
    self.orders = await http.get_json("https://api.example.com/orders")

async def save(self, order):
    response = await http.post("https://api.example.com/orders", json=order)
    if not response.ok:
        self.error = f"Couldn't save the order ({response.status})"
```

| Call | Returns |
|---|---|
| `get_json(url)` | the body parsed as JSON; `http.HTTPError` unless the status is 2xx |
| `get(url)`, `post(url)`, `put(url)`, `patch(url)`, `delete(url)` | a `Response`, whatever its status |
| `request(method, url)` | the same, for any method |

Each takes `params=` (added to the URL's query), `headers=`, `timeout=`
(seconds, 30 by default) and a body: `json=` (any JSON value) or `data=`
(bytes, text, or a dict sent as a form).

- **A `Response`** has `status`, `ok` (a 2xx status), `headers` (names in
  lower case), `data` (the bytes), `text` and `json()`.
  `raise_for_status()` raises `http.HTTPError` unless it's 2xx.
- **A relative URL is a file your app ships.** Put data files in
  `assets/`, and `await http.get_json("assets/prices.json")` reads them in
  the browser and in a desktop window alike.
- **Failures:** no answer at all (offline, a mistyped address) raises
  `http.NetworkError`; a slow server raises `TimeoutError`.
- **In the browser, the browser's rules apply.** A request to another site
  only works if that server allows it (it must send CORS headers; public
  APIs usually do). There is no such rule in a desktop app.
- **Everyone can see the requests a web app makes**, as with any web page,
  so an API key in your code isn't secret. Keep secrets on a server of
  your own and call that.
- **In tests**, requests go out for real through the standard library.
  `http.set_host()` installs a stand-in instead: an object with `async
  request(method, url, headers, body, timeout)` returning `(status,
  headers, data, url)`.

**Headers on every request: `http.Client`.** An API you sign in to wants
the same address and `Authorization` header on every call. A client keeps
both:

```python
from pyweft import http

api = http.Client("https://api.example.com/v1",
                  headers={"Authorization": f"Bearer {token}"})

async def on_init(self):
    self.orders = await api.get_json("/orders")        # .../v1/orders
```

- It has the same calls as the module (`get_json`, `get`, `post`, ...,
  `stream`, `events`, `websocket`). Relative URLs join its address; full
  ones go as they are. Headers given to one call are added to the
  client's, and win.
- **A token that changes** (it expires, the user signs in again): pass a
  function, called for every request, instead of a dict:
  `headers=lambda: {"Authorization": f"Bearer {session.token}"}`. It may
  be `async`, to refresh the token first.
- A header such as `Authorization` on a request to another site makes the
  browser ask that server first (a CORS "preflight"), so the server must
  allow the header.

### Live data: server-sent events, WebSockets and streams

For data that keeps coming (prices, a chat, progress, a model writing its
answer), keep a connection open in a task the component owns, and render
as each piece arrives. Data that arrives this way comes in outside a
handler, so call `self.state_has_changed()` after changing state (or keep
it in a [Store](#sharing-state-between-components-store), which updates
the page on its own).

**Server-sent events** are the simplest: the server keeps a response open
and sends events down it. Plain HTTP, so they work through proxies and
with headers:

```python
from pyweft import http

prices: dict = {}

def on_init(self):
    self.start_task(self.follow())       # stops when the component goes away

async def follow(self):
    async for event in http.events("https://api.example.com/prices/live"):
        if event.event == "price":
            update = event.json()
            self.prices[update["symbol"]] = update["price"]
            self.state_has_changed()
```

- Each event has `data` (text), `event` (its type, `"message"` unless the
  server named one), `id` and `json()`.
- **It reconnects by itself** when the connection drops, after the wait
  the server asked for (`retry:`, else 3 seconds), and tells the server
  the last `id` it got so it can carry on from there. `reconnect=False`
  ends the loop instead. An error status raises `http.HTTPError`; a 204
  answer ends it.
- `headers=`, `params=` and a `Client`'s headers work, sign-in included.
  (They don't with the browser's own `EventSource`, which PyWeft doesn't
  use.)

**WebSockets** go both ways, for chat and anything interactive:

```python
async def join(self):
    async with await http.websocket("wss://chat.example.com/room?token=" + self.token) as ws:
        self.socket = ws
        await ws.send_json({"join": "general"})
        async for message in ws:              # ends when the server closes it
            self.lines.append(message)
            self.state_has_changed()

async def say(self, text):
    await self.socket.send(text)
```

- `send()` takes text or bytes, `send_json()` any JSON value;
  `receive()` and `receive_json()` wait for the next message, or `async
  for` reads them until the connection closes. `close()` ends it (the
  `async with` does that for you); `close_code` and `close_reason` say how
  it ended.
- A relative address (`/ws`) means the server the page came from.
  `protocols=["chat"]` offers subprotocols; `ws.protocol` is the one the
  server chose.
- **Sign-in:** browsers don't let a page send headers with a WebSocket, so
  put the token in the address, as above, or send it as the first
  message. (`headers=` works on the desktop and in tests, and in the
  browser raises an error saying so, rather than being dropped.)
- It doesn't reconnect by itself: wrap the `async with` in a loop with a
  `try`/`except http.NetworkError` and a pause if it should.

**A response read as it arrives**, such as a long download or a model's
answer streamed token by token:

```python
async def ask(self):
    self.answer = ""
    async with api.stream("POST", "/chat", json={"question": self.question}) as reply:
        async for text in reply.iter_text():
            self.answer += text
            self.state_has_changed()
```

`iter_bytes()`, `iter_text()` and `iter_lines()` read it in pieces,
`read()` all at once; `status`, `ok` and `headers` are there before the
body. The timeout only covers waiting for the answer to begin.

**Stopping.** A loop in a task started with `self.start_task()` stops when
the component is removed, and that closes the connection. To stop it
earlier, keep the task (`self.feed = self.start_task(...)`) and call
`self.feed.cancel()`, or `break` out of the loop.

### Saving data between visits: pyweft.storage

`pyweft.storage` keeps small amounts of data, such as settings, a draft or
a list, until the next visit:

```python
from pyweft import effect, storage

items: list = []

def on_init(self):
    self.items = storage.get("todos", [])   # [] the first time

@effect
def keep(self):
    storage.set("todos", self.items)        # runs again whenever items changes
```

| Call | Does |
|---|---|
| `get(key, default=None)` | the stored value, or `default` |
| `set(key, value)` | stores `value`, replacing what was there |
| `delete(key)`, `clear()` | removes one key, or everything this app stored |
| `has(key)`, `keys()` | whether a key has a value; every key, sorted |

- **Values are anything JSON can hold:** numbers, text, `True`/`False`/
  `None`, and lists and dicts of those. Anything else raises `TypeError`;
  turn dates into text first, for example.
- **`get` returns a copy.** Changing a list you got back doesn't change
  what's stored until you `set` it again, which is what the effect above
  does.
- **The calls aren't `async`**, so they work anywhere: in `on_init`, an
  effect, a property, or a module of your app.
- **Where it lives:** in the browser, the browser's local storage for your
  site (about 5 MB in all, cleared if the visitor clears site data), kept
  apart per app by the `[project]` name in its `pyproject.toml`. In a
  desktop app, a JSON file in the user's data folder:
  `%APPDATA%\<name>\storage.json` on Windows,
  `~/Library/Application Support/<name>/` on macOS,
  `~/.local/share/<name>/` on Linux.
- **Not in `run_in_background`:** the worker can't reach the page's
  storage, so read what the function needs first and pass it in.
- **In tests** it lives in memory. `storage.set_host(storage.MemoryStorage())`
  starts a test empty; `storage.FileStorage(path)` keeps it in a file.

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
  app/              your .weft components, .py modules and .css files, as-is
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
- The same app can also be handed out as a desktop program, with
  [`pyweft build --desktop`](#handing-out-a-desktop-app-pyweft-build---desktop).

### Putting an app inside another website

A built app can go into any web page, a WordPress post, a company intranet,
docs, without that site using PyWeft. `pyweft build` writes an `embed.js`
next to `index.html`; the other page loads it and places a `<pyweft-app>`
element where the app should appear:

```html
<script src="https://you.github.io/orders/embed.js" defer></script>

<pyweft-app data-customer="42" route="/orders" label="Orders"></pyweft-app>
```

- **`src`** is the app's address; leave it out and it is the folder
  `embed.js` came from. **`route`** opens a given page (`/orders/7`).
- **Height:** the element grows and shrinks with the app's content. An app
  laid out to fill the window (`min-height: 100vh`) has no content height
  of its own, so give it one: `height="600px"`.
- **`label`** names the app for screen readers.
- The app runs in a frame of its own: its styles and the page's don't
  meet, two apps on one page are independent, and its page addresses
  (`#/orders`) don't change the host page's address.

The app and the page can talk through `pyweft.embed`:

```python
from pyweft import embed

customer: str = embed.params().get("customer", "")   # data-customer="42"

def save(self):
    embed.send("saved", {"id": self.order_id})

def on_init(self):
    embed.on_message(self.message)      # the page called el.send(...)

def message(self, name, detail):
    if name == "select":
        self.order_id = detail["id"]
        self.state_has_changed()        # it arrives outside any handler
```

```html
<script>
  const app = document.querySelector("pyweft-app");
  app.addEventListener("saved", (event) => console.log(event.detail.id));
  app.addEventListener("pyweft-ready", () => app.send("select", { id: 7 }));
</script>
```

- `params()` holds the element's `data-*` attributes (without `data-`),
  read when the app starts. `send(name, detail)` fires a DOM event of that
  name on the element, with `detail` (anything JSON can carry) as
  `event.detail`. `pyweft-ready` fires once the app is on screen.
- Outside a host page, `embedded()` is `False`, `params()` is empty and
  `send()` does nothing, so the same app works on its own too.
- Whatever the page sends or sets is input from outside: check it like
  form input. And whatever the app sends goes to any site that embeds it,
  so keep secrets out of it.
- Every `<pyweft-app>` starts its own Python, so a page with several of
  them downloads Pyodide once (the browser caches it) but runs each app
  separately.

### A desktop app: `pyweft run --desktop`

The same app runs in a native window, with Python running on your own
machine instead of in a browser:

```bash
uv add "pyweft[desktop]"          # once: installs pywebview
uv run pyweft run myapp --desktop
```

With pip: `pip install "pyweft[desktop]"`, then `pyweft run myapp --desktop`.

Nothing in the app changes. The window is a webview (WebView2 on Windows,
WebKit on macOS, GTK or Qt on Linux) showing the same page; your components
run in ordinary Python, and each event and update crosses between the two.

- **What you gain:** Python starts at once, with no download; your code
  can use the machine (files, sockets, databases, any installed package,
  including ones with C extensions that can't run in a browser); and
  `run_in_background` runs functions on real threads.
- **System dialogs:** [`pyweft.dialogs`](#files-and-dialogs) shows the
  system's own Open, Save As and confirmation dialogs here, and the
  browser's equivalents on the web, with the same code.
- **What works the same:** templates, handlers, `@bind`, async handlers,
  effects, focus, pages and Back/Forward, stores, `pyweft-ui`, scoped styles,
  your `.css` files, `head.html` and `assets/`.
- **Hot reload:** saving a `.weft` or `.css` file updates the open window
  and keeps its state, as in the browser. Editing a `.py` module or PyWeft
  itself needs a restart, since Python keeps imported modules loaded; the
  terminal says so.
- **Errors** in a handler are shown in the window and printed in the
  terminal, and the app keeps running.
- **Browser-only code** (`import js`, `pyodide`) doesn't exist on the
  desktop. Code that needs both should check, for example
  `import sys; in_browser = sys.platform == "emscripten"`.
- **Your code runs one thing at a time**, on a single thread, as in the
  browser. If you start threads of your own, hand results back with
  `run_in_background` or asyncio rather than changing component state from
  another thread.

**The window** takes its title and icon from
[`[tool.pyweft]`](#the-apps-title-and-icon), and the rest from
`[tool.pyweft.desktop]` in your app's `pyproject.toml`:

```toml
[tool.pyweft.desktop]
width = 1200
height = 800
min_size = [800, 600]
maximized = false
```

| Setting | Meaning | Default |
|---|---|---|
| `width`, `height` | the window's size in pixels when it opens | 1100, 800 |
| `min_size` | the smallest it can be resized to, `[width, height]` | none |
| `resizable` | whether the user can resize it | `true` |
| `maximized`, `fullscreen` | open maximized, or full screen | `false` |
| `on_top` | stay above other windows | `false` |
| `frameless` | no title bar or border (your page draws everything) | `false` |
| `background_color` | shown before the page paints, like `"#0d1117"` | the system's |

- **The icon** shows on the window and in the taskbar on Windows (it must
  be an `.ico`; other formats keep the default icon, and the terminal says
  so) and on Linux. On macOS the Dock icon comes from a packaged app, so it
  waits for packaging.
- **`set_title()`** renames the window while the app runs, and saving a new
  `title` in `pyproject.toml` renames the open window. The other window
  settings apply the next time it opens.

Close the window to stop.

### Handing out a desktop app: `pyweft build --desktop`

To give your app to people who don't have Python, build it into one
program they can run:

```bash
uv add --dev "pyweft[package]"    # once: installs PyInstaller, only where you build
uv run pyweft build myapp --desktop
```

With pip: `pip install "pyweft[package]"`, then `pyweft build myapp --desktop`.

This writes `myapp/dist-desktop/Acme Orders.exe` on Windows, an `Acme
Orders.app` on macOS, or a program on Linux, named after your
[title](#the-apps-title-and-icon) and carrying your icon. It contains
Python, PyWeft, your app and everything it uses, so the people you give it
to just run it: nothing to install.

- **Build on each system you ship for.** PyInstaller builds for the system
  it runs on: build the `.exe` on Windows, the `.app` on a Mac.
- **What goes in:** your `.weft`, `.css` and `.py` files, `assets/`,
  `head.html` and `pyproject.toml` (for the window settings); every module
  your code blocks and modules import, which PyWeft finds by reading them;
  and your component libraries, such as `pyweft-ui`, whole. Anything else in
  the app folder stays out.
- **The icon** must be an `.ico` for Windows and an `.icns` for macOS;
  with another format, the program keeps the default icon and the build
  says so.
- **It runs like `pyweft run --desktop`**, without hot reload or a terminal.
  If it can't start, it opens a window saying why.
- **Size and speed:** a small app is around 15 MB, and the program unpacks
  itself each time it starts, so it opens in a second or two.
- **Imports PyWeft can't see**, such as `importlib.import_module(name)` with
  a name worked out at run time, aren't bundled. Import such modules
  plainly somewhere in your code so they're found.
- A building tool won't sign the program: Windows and macOS may warn the
  first time it runs, as they do for any unsigned download. Signing with a
  certificate, and installers (`.msi`, `.dmg`), are on the roadmap.

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
  `<If>`/`<For>` with keyed lists, `<Await>` for async data, `<Html>` for
  sanitized HTML, `<Head>` for per-page tags, lists sorted by dragging, `class:`/`style:` toggles, transitions and list
  animations, `<Window>`/`<Document>` events, checkbox groups bound to a
  list, `@property` computed values, `ref=` with `focus()`, `scroll_to()`
  and `keep_in_view()`, and input masks (`data-mask`).
- **Composition:** child components with props, events (`emit`) and
  lifecycle hooks; slots (named, with fallbacks and slot props); `@bind` on
  components; attributes passed through to a component's root element;
  components in subfolders as `<folder.Name>`, or imported from packages
  (`ComponentLibrary`), shipped to the browser from your environment;
  `Store` for state many components share; `provide`/`inject` for values
  a whole part of the page needs;
  `<Dynamic :is>` for a component chosen at runtime.
- **Pages:** `router("pages")` turns a folder into screens, with `<Link>`,
  `navigate()`, Back/Forward, typed `{params}` and query values as fields.
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
- **Desktop:** `pyweft run --desktop` opens the same app in a native window,
  with Python running on your machine and hot reload included; the window's
  size and the like come from `[tool.pyweft.desktop]`. `pyweft build
  --desktop` makes it a single program to hand out (an `.exe`, `.app` or
  Linux program) with nothing to install.
- **Files and dialogs:** `pyweft.dialogs` opens and saves files and asks for
  confirmation with one API: the browser's picker and downloads on the web,
  the system's dialogs on the desktop.
- **Title and icon:** `[tool.pyweft]` names the app and gives it an icon for
  the browser tab and the window; `set_title()` changes the title as the
  app runs.
- **Tooling:** `pyweft new` / `run` / `build`; hot reload that keeps state,
  with an error overlay; the first screen rendered ahead of time, so pages
  appear at once; a customizable loading screen that shows real progress;
  PyPI dependencies from `pyproject.toml`, installed in the browser.
- **Data in and out:** `pyweft.http` calls web APIs (with sign-in
  headers through `http.Client`), follows live data with server-sent
  events, WebSockets and streamed responses, and loads the app's
  data files; `pyweft.storage` keeps data between visits. Same code on
  both targets.
- **Controls:** `pyweft-ui`, 65 ready-made, themeable controls: layout
  (resizable panes included),
  form fields with validation, autocomplete, chips, sliders and masks, a file drop zone, date and date-range pickers,
  calendars of events, charts, menus, tabs, tables, dialogs, toasts (see
  "Ready-made controls" in section 5), with a live gallery.
- **Embedding:** `<pyweft-app>` (from the build's `embed.js`) puts an app
  in any other website, with `pyweft.embed` for events and data both ways.
- **Releases:** `pyweft` and `pyweft-ui` on PyPI.

Coming next: a faster first start that also works offline, and installers
(`.msi`, `.dmg`) and code signing for desktop apps.

