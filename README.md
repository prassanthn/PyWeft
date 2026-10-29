# PyWeft

**Build web apps in Python.** Write components as `.weft` files, an XML
template plus a Python code block, and PyWeft runs them in the browser with
real CPython compiled to WebAssembly. No JavaScript to write, no build step,
and the same components are designed to run as desktop apps later.

*PyWeft: the weft is the thread woven through the warp to make fabric.*

```xml
<template>
  <div>
    <h1>Hello, {{ name or "stranger" }}!</h1>
    <input @bind="name" placeholder="your name" />
    <button @click="count += 1">Clicked {{ count }} times</button>
  </div>
</template>

<code>
name: str = ""
count: int = 0
</code>
```

Type in the box and the heading follows; click and the count goes up. State
is plain Python fields, and the page updates itself after every event.

> **Status:** a working proof of concept. The web target runs today; a
> desktop target is planned. APIs may still change. Not on PyPI yet, so you
> install from GitHub (below).

## Quick start

You need Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/):

```bash
uv init myproject && cd myproject
uv add git+https://github.com/prassanthn/PyWeft.git
uv run pyweft new myapp
uv run pyweft run myapp
```

Open <http://127.0.0.1:8642/>. The first load takes a few seconds while the
browser downloads Python (it is cached after that).

With pip instead:

```bash
pip install git+https://github.com/prassanthn/PyWeft.git
pyweft new myapp
pyweft run myapp
```

Now open `myapp/app.weft` in your editor, change something and save: the page
updates in place and keeps what you'd typed. Make a mistake and an overlay
shows the file and line; fix it and save again.

`myapp/` is your whole app:

```
myapp/
  app.weft         the root component
  styles.css       page-wide CSS (optional)
  pyproject.toml   your app's dependencies, installed in the browser
  head.html        extra <head> tags: fonts, CDN stylesheets (optional)
  loading.html     what visitors see while Python starts (optional)
```

When you're ready to publish, `uv run pyweft build myapp` writes a static site
to `myapp/dist/` that any web host can serve, such as GitHub Pages or Netlify.

## Ready-made controls (no HTML or CSS needed)

[`pyweft-ui`](packages/pyweft-ui/README.md) gives you styled, accessible
controls as components: buttons, text fields, selects, checkboxes, switches,
cards, tabs, sortable tables, dialogs, alerts, toasts, layout and light/dark
themes.

```bash
uv add "pyweft-ui @ git+https://github.com/prassanthn/PyWeft.git#subdirectory=packages/pyweft-ui"
```

Add `"pyweft-ui"` to the `dependencies` list in `myapp/pyproject.toml`, then
use the controls:

```xml
<template>
  <ui.Theme mode="auto">
    <ui.AppShell title="Orders">
      <ui.Card title="New order">
        <ui.TextField label="Customer" @bind="customer" required="true" />
        <ui.Select label="Size" options="Small, Medium, Large" @bind="size" />
        <ui.Switch label="Express delivery" @bind="express" />
        <Fill name="footer">
          <ui.Button variant="primary" icon="send" @click="place_order">Place order</ui.Button>
        </Fill>
      </ui.Card>
    </ui.AppShell>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

customer: str = ""
size: str = "Medium"
express: bool = False

def place_order(self):
    ...
</code>
```

PyWeft notices the toolkit is installed and sends it to the browser for you.
To see every control live, clone this repository and run
`uv run pyweft run packages/pyweft-ui/gallery`.

## What you get

- **Components in one file:** template, Python code and a `<style>` block
  that only applies to that component.
- **Template syntax:**
  - **Values:** `{{ expression }}` shows a value, `:attr="expression"` sets an
    attribute from Python, `@bind="field"` keeps a form control and a field
    in sync.
  - **Events:** `@click="method"` handles an event, with modifiers like
    `@submit.prevent` and `@keydown.enter`.
  - **Control flow:** `<If>`, `<ElseIf>`, `<Else>` and `<For>`.
- **Composition:** components inside components, with props, events, slots
  for passing content, and `@bind` on your own components. Organise them in
  folders, or install them as packages.
- **Effects:** `@effect` methods re-run when the state they read changes.
- **Async:** `async def` handlers, plus `run_in_background()` to run heavy
  Python in a Web Worker so the page never freezes.
- **Styling your way:** scoped styles, plain CSS files, or frameworks such as
  Tailwind and Bootstrap through `head.html`.
- **Packages:** any pure-Python package from PyPI, declared in
  `pyproject.toml`, works in the browser.
- **A fast dev loop:** hot reload that keeps your app's state, and readable
  errors that point to your `.weft` file and line.

## Learn more

| You want to | Read |
|---|---|
| Learn the basics: state, templates, events | [Getting started](docs/getting-started.md), sections 1–3 |
| Split an app into components, use slots | [Composing components](docs/getting-started.md#4-composing-components) |
| Handle forms and keyboard input | [Binding form controls](docs/getting-started.md#binding-form-controls), [event modifiers](docs/getting-started.md#event-modifiers) |
| Load data, run async code, do heavy work | [Async handlers](docs/getting-started.md#async-handlers-and-background-work), [`run_in_background`](docs/getting-started.md#heavy-work-run_in_background) |
| Style with Tailwind or Bootstrap | [Using CSS frameworks](docs/getting-started.md#using-css-frameworks) |
| Build screens with the ready-made controls | [pyweft-ui guide](packages/pyweft-ui/docs/guide.md), then the [reference](packages/pyweft-ui/README.md) |
| Deploy your app | [Building for deployment](docs/getting-started.md#building-for-deployment) |
| Test components without a browser | [Using the engine from plain Python](docs/getting-started.md#6-using-the-engine-from-plain-python) |

`examples/todo/` is a small complete app; run it from a clone with
`uv run pyweft run examples/todo`.

## Good to know

- **Templates must be well-formed XML:** close every tag (`<br/>`, `<input />`)
  and quote every attribute.
- **No threads in the browser.** Use `async`/`await` for waiting and
  `run_in_background` for heavy computation.
- **Code runs in the visitor's browser.** Your `.weft` files are visible to
  them, as with any website's JavaScript, so keep secrets on a server.
- **Not every package works in a browser:** pure-Python packages do, and so
  do the ~250 that Pyodide ships prebuilt (NumPy, pandas, …). Anything that
  needs raw sockets or subprocesses doesn't.

## How it works

PyWeft renders HTML rather than native widgets. A component renders to a
lightweight tree of elements; after every event PyWeft renders again, compares
the new tree with the old one and sends only the differences to the page as
small JSON instructions. The core never touches the page itself. That is what
makes other targets cheap: a desktop app is a webview showing the same page,
with Python running natively and the same instructions crossing a bridge.

| Target | Where Python runs | What draws the page |
|---|---|---|
| Web (today) | Pyodide, in the browser | the browser |
| Desktop (planned) | CPython on the machine | a webview (WebView2, WKWebView, WebKitGTK) |
| Mobile (later) | CPython via Briefcase | a webview |

There is no reactive state system to learn: a handler runs, the component
renders again, and the comparison finds what changed. `@effect` is the one
place where PyWeft tracks which fields you read.

## Working on PyWeft

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync --extra dev          # also installs packages/pyweft-ui, editable
uv run pytest                # 807 tests, including pyweft-ui's
uv run python examples/demo.py              # render -> event -> diff -> apply, no browser
uv run pyweft run examples/todo             # the todo app
uv run pyweft run packages/pyweft-ui/gallery  # every control
```

With pip: `pip install -e ".[dev]"` and `pip install -e packages/pyweft-ui`.

```
src/pyweft/           the framework (zero runtime dependencies)
  static/             the browser side: runtime.js, the page shell, the worker
packages/pyweft-ui/   the control toolkit, released as its own package
docs/                 the guide
examples/             a headless demo and the todo app
tests/                the framework's tests
```

Under the hood:
- **Patches:** each patch instruction says where to insert, remove, move or
  change something. They're ordered so the page can apply them front to back
  with no bookkeeping.
- **Testing the differ:** tests apply the patches to the old tree and check
  the result equals the new one, rather than checking the exact instructions.
  400 of the tests do this on randomly generated trees.
- **Handler ids** are built from list keys where available, so a row keeps
  its handlers when a list is reordered.

## Roadmap

**Done:** the render core and differ; the browser target; components with
props, events, slots and component libraries; events with modifiers and
`@bind` for every form control; effects; async handlers and Web Worker
background work; scoped styles and CSS framework support; the `pyweft` CLI
with hot reload and static builds; `pyweft-ui` with 22 controls and a gallery.

**Next:** more controls (menus, a date picker, form validation); publishing `pyweft` and `pyweft-ui` to PyPI; a desktop host
using pywebview.

**Later:** shared state across components, mobile packaging with Briefcase,
developer tools.

## License

MIT. See [LICENSE](LICENSE).
