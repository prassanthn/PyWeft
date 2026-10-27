# PyWeft

A UI framework for Python. Markup in XML, logic in Python, and a
render core that emits transport-agnostic patches so desktop, web and mobile
can share one codebase.

*PyWeft: the weft is the thread woven through the warp to make fabric.*

**New here? Read [docs/getting-started.md](docs/getting-started.md)** — how to
write components and start a project.

## Status

**Working proof of concept; the web target runs today.** Components run in the
browser on Pyodide (CPython in WebAssembly), patching the real DOM. The desktop
target (pywebview) is next. APIs may still move.

## Features

- **Components** — `.weft` files: an XML template, a Python `<code>` block and
  an optional scoped `<style>` block. `{{ }}` and `:attr` bindings, two-way
  `@bind`, `@click` handlers (a method, an expression or an inline statement),
  `<If>`/`<ElseIf>`/`<Else>` and keyed `<For>`, `@property` computed values.
- **Composition** — child components with props, events (`self.emit`) and
  lifecycle hooks (`on_init`, `on_after_render`, `on_dispose`). Group them in
  folders and use them as `<widgets.Row>`.
- **Effects** — `@effect` methods re-run after a render when state they read
  changed; dependencies are tracked automatically; return a function for
  cleanup.
- **Async** — `async def` handlers and `on_init`: the code before the first
  `await` shows with the click, the rest when it finishes. `self.start_task()`
  runs background work; a component's tasks are cancelled when it is removed.
- **Heavy work** — `await run_in_background(fn, *args)` runs a plain function
  in a Web Worker (a second Python on its own browser thread), so the page
  stays responsive; outside the browser it runs on a thread.
  ([Details and rules](docs/getting-started.md#heavy-work-run_in_background);
  [threads](docs/getting-started.md#threads).)
- **Styling** — scoped component styles, global `.css` files, `head.html` for
  CDN stylesheets, scripts and fonts, and an `assets/` folder for images and
  fonts. CSS frameworks such as Tailwind and Bootstrap work; the guide has
  [both setups](docs/getting-started.md#using-css-frameworks).
- **Dev loop** — `pyweft run` serves the app and hot-reloads every save while
  keeping state (form input, toggles, lists); mistakes show in an error
  overlay with the `.weft` file and line, while the page keeps running.
- **Ship** — `pyweft build` writes a static site for any host. PyPI
  dependencies come from the app's ordinary `pyproject.toml` and install in
  the browser. A customizable loading screen shows while Python starts.

Use it in a project (not on PyPI yet, so install from GitHub):

```bash
uv add git+https://github.com/prassanthn/PyWeft.git   # or: pip install git+https://github.com/prassanthn/PyWeft.git
uv run pyweft new myapp
uv run pyweft run myapp     # open http://127.0.0.1:8642/
```

Work on the framework itself:

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync --extra dev         # or: pip install -e ".[dev]"
uv run pytest               # 657 tests
uv run python examples/demo.py   # render -> event -> diff -> apply, no browser
uv run pyweft run examples/todo  # the todo app live in the browser at :8642 —
                                 # composed components + a PyPI dep via micropip
```

## The architecture bet

PyWeft doesn't render native widgets, it renders HTML. A desktop app is a
webview hosting the same DOM the browser target uses, and the component code
can live in a different process from the renderer and ship only diffs.

That is what makes three targets nearly free:

| Target | Where Python runs | Renderer | Transport |
|---|---|---|---|
| Desktop | CPython process | webview (WebView2 / WKWebView / WebKitGTK) | JSON over the webview IPC bridge |
| Web | Pyodide in the browser | same DOM | in-process call |
| Mobile | CPython via Briefcase / Kivy | webview | same bridge as desktop |

Hence the one rule this codebase enforces: **the render core never touches a
DOM.** It emits patch op dicts. Porting to a new target is writing a transport,
not a renderer.

## Component format

```xml
<template>
  <div class="counter">
    <h1>Count: {{ count }}</h1>

    <input @bind="name" placeholder="your name" />
    <button @click="increment">+1</button>

    <If cond="count == 0"><p>click the button</p></If>
    <ElseIf cond="count > 3"><p>that's a lot{{ greeting }}</p></ElseIf>
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

@property
def greeting(self):
    return f", {self.name}" if self.name else ""

def increment(self):
    self.count += 1
    self.history.append({"id": self.count, "label": f"click {self.count}"})

def forget(self, entry):
    self.history = [h for h in self.history if h["id"] != entry["id"]]
</code>
```

Control flow is elements (`<If>` / `<ElseIf>` / `<Else>` / `<For>`) rather than
Python blocks embedded in the markup. Lexing indentation-sensitive Python inside
markup is a tarpit; elements sidestep it entirely.

- `{{ expr }}` interpolates in text and attribute values
- `@click="handler"` binds an event — a bare name calls that method, an
  expression is evaluated (`@click="forget(entry)"` inside a loop), and simple
  statements work inline (`@click="count += 1"`, `@click="show = not show"`)
- `@bind="field"` is two-way, and coerces back to the field's existing type so a
  bound `int` doesn't become a string on first keystroke
- `key="..."` on `<For>` gives rows stable identity across reorders

A `<style>` block in the same file is scoped to the component: its selectors
only match elements that component renders, so `.row` in two components never
collide. Page-wide CSS goes in `.css` files in the app directory; CDN
stylesheets and scripts (Tailwind, Bootstrap, web fonts) go in `head.html`, and
images and fonts in `assets/`.

Split files work too: put the markup in `Counter.weft` and the code in a normal
module if you prefer code-behind to single-file.

## Reactivity

No observables, no proxies. A handler runs, the
component re-renders, the tree is diffed. Handlers may be `async def`: the
part before the first `await` renders with the click, the rest when the
handler finishes. Mutating state outside a handler (a timer, a JavaScript
callback) means calling `state_has_changed()` yourself. `@effect` methods
are the one place dependencies are tracked: they run against a stand-in for
`self` that records what they read, and re-run only when that changed.

That's ~30 lines instead of ~800 for a signals system, and it covers almost
everything. Fine-grained reactivity can be added later without changing the
component API.

## Patch ops

Structural ops carry the **parent** path plus an index; in-place ops carry the
**node's own** path.

| Op | Payload |
|---|---|
| `insert` / `remove` / `move` / `replace` | parent `path` + `index` (`from`/`to` for move) |
| `set_text` | node `path`, `text` |
| `set_attrs` / `set_events` | node `path`, `set` dict, `remove` list |
| `set_key` | node `path`, `key` |

At every level, structural ops for a parent are emitted before anything that
descends into it, so indices in descendant ops already reflect the reconciled
order. A consumer applies the list front to back with zero bookkeeping.

`dommodel.py` is the executable spec: whatever it does to dicts, the eventual
`runtime.js` must do to real DOM nodes.

## Handler identity

Handler ids are path strings built from **keys where available**, index
otherwise — `i:0/i:5/k:3#click`. Purely positional ids would change for every
row whenever a list reordered, churning event bindings on every move. Keyed
segments mean a row keeps its id wherever it lands.

The handler table is rebuilt each render, so ids for nodes that no longer exist
simply vanish and a late event against a stale id is a no-op, not a crash.

## Testing approach

The differ is tested by **convergence, not op sequences**: apply the patches to
the old tree and assert the result equals the new tree. 400 of the 657 tests are
randomised trees checked this way. Asserting exact op lists would lock in the
current algorithm and still miss the index bugs that actually bite.

## Known limitations

- Templates must be well-formed XML — close your tags, quote your attributes.
  This buys the stdlib parser instead of an HTML5 tokenizer.
- Comprehensions and lambdas inside `{{ }}` build their own frame and can't see
  scope variables. Compute them in the code block.
- A keyed `<For>` body must produce exactly one element per item.
- No slots yet — a component tag with children raises a clear error. This is
  the next composition gap to close.
- Whitespace-only text containing a newline is dropped as formatting.
- `key` is reserved as an attribute name on elements.
- No threads in the browser (a Pyodide limit): blocking code freezes the page.
  Use `async`/`await` for waiting and `run_in_background` for heavy work.
- `run_in_background` uses one worker, one call at a time, and cannot
  interrupt a call already running; the function must be a plain
  (non-`async`) top-level function, and arguments and results must be
  picklable.
- `@effect` methods cannot be `async`; start a task from the effect instead.

## Roadmap

**Done:**

- Render core, differ and the JS runtime; the Pyodide web target.
- Composition: props, `:expr` bindings, `emit`, lifecycle, sibling-file and
  folder (`<widgets.Row>`) resolution.
- Scoped `<style>` blocks; `head.html` and `assets/` for CSS frameworks.
- `@effect` with automatic dependency tracking and cleanup.
- Async handlers, async `on_init`, `start_task()`, cancellation on removal.
- `run_in_background()`: heavy work in a Web Worker in the browser.
- The `pyweft` CLI: `new`, `run` with state-preserving hot reload and an
  error overlay, `build` to a static site; PyPI dependencies from
  `pyproject.toml`; a customizable loading screen.

**Next (finishes the PoC):** slots; a pywebview desktop host with the bridge
wired both ways.

**Later:** provide/inject; Briefcase packaging for
mobile; codegen-to-Python-source rendering if the tree-walking interpreter
gets hot; devtools.
