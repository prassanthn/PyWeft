# PyWeft

A Blazor-shaped UI framework for Python. Markup in XML, logic in Python, and a
render core that emits transport-agnostic patches so desktop, web and mobile
can share one codebase.

*PyWeft: the weft is the thread woven through the warp to make fabric.*

**New here? Read [docs/getting-started.md](docs/getting-started.md)** — how to
write components and start a project.

## Status

**The render core is done and tested, and the web target works**: components
run in the browser on Pyodide (CPython in WebAssembly), patching real DOM
through `web/runtime.js`. Component composition is in — props, `:expr`
bindings, `emit`, lifecycle, Vue-SFC-style file resolution.

```bash
pip install -e ".[dev]"
pytest                      # 464 tests
python examples/demo.py     # render -> event -> diff -> apply, no browser
pyweft run examples/todo      # the todo app live in the browser at :8642 —
                            # composed components + a PyPI dep via micropip
pyweft new myapp              # scaffold your own
```

## The architecture bet

Blazor doesn't render native widgets, it renders HTML — `BlazorWebView` is a
webview hosting the same DOM, and Blazor Server proves the component code can
live in a different process from the renderer and ship only diffs.

Copy that and the three targets come nearly free:

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
Razor-style `@if` blocks. Lexing indentation-sensitive Python inside markup is a
tarpit; elements sidestep it entirely and read closer to XAML anyway.

- `{{ expr }}` interpolates in text and attribute values
- `@click="handler"` binds an event — a bare name calls that method, anything
  else is evaluated, so `@click="forget(entry)"` works inside a loop
- `@bind="field"` is two-way, and coerces back to the field's existing type so a
  bound `int` doesn't become a string on first keystroke
- `key="..."` on `<For>` gives rows stable identity across reorders

Split files work too: put the markup in `Counter.weft` and the code in a normal
module if you prefer code-behind to single-file.

## Reactivity

Blazor's model, not React's. No observables, no proxies. A handler runs, the
component re-renders, the tree is diffed. Mutating state outside a handler (a
timer, an async callback) means calling `state_has_changed()` yourself.

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
the old tree and assert the result equals the new tree. 400 of the 442 tests are
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

## Roadmap

**Done:** the JS runtime mirroring `dommodel.py`; the Pyodide web target;
component composition (props, `:expr` bindings, `emit`, lifecycle, SFC-style
file resolution).

**Done (continued):** the `pyweft` CLI — `new` scaffolds an app, `run` serves it
with refresh-on-save, `build` emits a static site; PyPI dependencies declared
in the app's ordinary `pyproject.toml` (add them with `uv add`/pip) and
installed in-browser by micropip at load.

**Next (finishes the PoC):** slots; a pywebview desktop host with the bridge
wired both ways; an asyncio render queue so async handlers and re-entrant
events work; hot-reload for `pyweft run`.

**Later:** watchers, provide/inject, scoped CSS; Briefcase packaging for
mobile; codegen-to-Python-source rendering if the tree-walking interpreter
gets hot; devtools.
