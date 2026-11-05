# PyWeft

**Build web and desktop apps in Python.** Write components as `.weft` files,
an XML template plus a Python code block, and PyWeft runs them in the browser
with real CPython compiled to WebAssembly, or in a native window with Python
running on your machine. No JavaScript to write, no build step.

*PyWeft: the weft is the thread woven through the warp to make fabric.*

**[Website](https://prassanthn.github.io/PyWeft/)**: a step-by-step
[tutorial](https://prassanthn.github.io/PyWeft/tutorial/), the
[guide](https://prassanthn.github.io/PyWeft/guide/), and the
[controls](https://prassanthn.github.io/PyWeft/live/gallery/) and
[examples](https://prassanthn.github.io/PyWeft/examples/) running live.

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

> **Status:** a working proof of concept. Web apps and desktop apps (run
> locally or built into a program to hand out) work today. APIs may still
> change.

## Quick start

You need Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/):

```bash
uv init myproject && cd myproject
uv add pyweft
uv run pyweft new myapp
uv run pyweft run myapp
```

Open <http://127.0.0.1:8642/>. Your page shows straight away, dimmed, while
the browser downloads Python in the background (a few seconds the first
time, cached after that); then it comes alive.

With pip instead:

```bash
pip install pyweft
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
  AGENTS.md        how to write this app, for AI coding assistants
```

**Using an AI coding assistant?** PyWeft is too new for it to know, so
`AGENTS.md` (read by Claude Code, Codex, Cursor, Copilot and others) teaches
it the file format, the directives and the usual mistakes, and
`uv run pyweft check myapp` lets it (or you) find mistakes without opening
a browser: unknown names, props and events, with the file, the line and
the name you probably meant. `uv run pyweft agents myapp` refreshes
`AGENTS.md` after an upgrade. All the docs as
one text file, to paste or point a tool at:
<https://prassanthn.github.io/PyWeft/llms-full.txt>.

When you're ready to publish, `uv run pyweft build myapp` writes a static site
to `myapp/dist/` that any web host can serve, such as GitHub Pages or Netlify.

The same app also runs as a desktop app, in a native window with Python on
your machine:

```bash
uv add "pyweft[desktop]"
uv run pyweft run myapp --desktop
```

To hand it to people without Python, build it into one program (an `.exe`
on Windows, a `.app` on macOS) in `myapp/dist-desktop/`:

```bash
uv add --dev "pyweft[package]"
uv run pyweft build myapp --desktop
```

Name the app and give it an icon in `myapp/pyproject.toml`, for the browser
tab and the window alike, and size the window there too:

```toml
[tool.pyweft]
title = "Acme Orders"
icon = "assets/icon.ico"

[tool.pyweft.desktop]
width = 1200
height = 800
```

## Ready-made controls (no HTML or CSS needed)

[`pyweft-ui`](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/README.md) gives you styled, accessible
controls as components: buttons, menus, text fields, autocomplete, chips, sliders, selects, date pickers,
event calendars, charts,
checkboxes, switches, cards, tabs, sortable tables, dialogs, alerts, toasts,
layout and light/dark
themes, plus form validation that shows what to fix next to each field.

```bash
uv add pyweft-ui
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
    in sync, and `data-mask="(999) 999-9999"` shapes what's typed.
  - **Events:** `@click="method"` handles an event, with modifiers like
    `@submit.prevent` and `@keydown.enter`.
  - **Focus:** `ref="name"` marks an element; `self.focus("name")` and
    `self.scroll_to("name")` move the keyboard focus or the page to it, and
    `self.keep_in_view("name")` keeps a popup inside the window.
  - **Control flow:** `<If>`, `<ElseIf>`, `<Else>` and `<For>`.
- **Composition:** components inside components, with props, events, slots
  for passing content, and `@bind` on your own components. Organise them in
  folders, or install them as packages.
- **Shared state:** a `Store` holds what many components use, like a cart
  or the signed-in user; change it from anywhere and every page showing it
  updates.
- **Pages:** a `pages/` folder becomes your app's screens, with links, Back
  and Forward, typed values from the address (`/orders/{id}`), and a
  not-found page.
- **Lifecycle and effects:** `on_init`, `on_after_render` and `on_dispose`
  run as a component appears, updates and goes away; `@effect` methods
  re-run when the state they read changes.
- **Async:** `async def` handlers, plus `run_in_background()` to run heavy
  Python in a Web Worker so the page never freezes.
- **Styling your way:** scoped styles, plain CSS files, or frameworks such as
  Tailwind and Bootstrap through `head.html`.
- **Packages:** any pure-Python package from PyPI, declared in
  `pyproject.toml`, works in the browser.
- **Files and dialogs:** `pyweft.dialogs` opens and saves files and asks for
  confirmation with the same code on both targets: the browser's picker and
  downloads on the web, the system's own dialogs on the desktop.
- **Data in and out:** `pyweft.http` calls web APIs and loads your app's
  data files, and `pyweft.storage` keeps settings and lists between visits,
  with the same code in the browser and on the desktop.
- **A fast dev loop:** hot reload that keeps your app's state, and readable
  errors that point to your `.weft` file and line.
- **Fast first load:** your app's first screen is rendered ahead of time and
  shows at once, while Python starts in the background.

## Learn more

| You want to | Read |
|---|---|
| Learn the basics: state, templates, events | [Getting started](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md), sections 1–3 |
| Run code when a component appears, updates or goes away | [Lifecycle](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#lifecycle-when-your-code-runs) |
| Split an app into components, use slots | [Composing components](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#4-composing-components) |
| Build an app with several pages | [Pages and navigation](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#pages-and-navigation) |
| Handle forms and keyboard input | [Binding form controls](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#binding-form-controls), [event modifiers](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#event-modifiers), [input masks](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#input-masks) |
| Check a form, pick dates, show a calendar of events | [pyweft-ui guide: forms](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/docs/guide.md#4-forms), [calendars of events](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/docs/guide.md#10-calendars-of-events) |
| Load data, run async code, do heavy work | [Async handlers](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#async-handlers-and-background-work), [`run_in_background`](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#heavy-work-run_in_background) |
| Style with Tailwind or Bootstrap | [Using CSS frameworks](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#using-css-frameworks) |
| Build screens with the ready-made controls | [pyweft-ui guide](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/docs/guide.md), then the [reference](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/README.md) |
| Deploy your app | [Building for deployment](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#building-for-deployment) |
| Run it as a desktop app | [A desktop app](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#a-desktop-app-pyweft-run---desktop) |
| Hand out a desktop app (`.exe`, `.app`) | [Handing out a desktop app](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#handing-out-a-desktop-app-pyweft-build---desktop) |
| Open and save files, ask for confirmation | [Files and dialogs](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#files-and-dialogs) |
| Call web APIs, save data between visits | [Loading data](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#loading-data-pywefthttp), [saving data](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#saving-data-between-visits-pyweftstorage) |
| Name the app, give it an icon | [The app's title and icon](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#the-apps-title-and-icon) |
| Test components without a browser | [Using the engine from plain Python](https://github.com/prassanthn/PyWeft/blob/main/docs/getting-started.md#6-using-the-engine-from-plain-python) |

`examples/todo/` is a small complete app, and `examples/shop/` one with
pages; run them from a clone with `uv run pyweft run examples/todo`.

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
| Web | Pyodide, in the browser | the browser |
| Desktop (`pyweft run --desktop`) | CPython on the machine | a webview (WebView2, WKWebView, WebKitGTK) |
| Mobile (later) | CPython via Briefcase | a webview |

There is no reactive state system to learn: a handler runs, the component
renders again, and the comparison finds what changed. `@effect` is the one
place where PyWeft tracks which fields you read.

## Working on PyWeft

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync --extra dev          # also installs packages/pyweft-ui, editable
uv run pytest                # 920 tests, including pyweft-ui's
uv run python examples/demo.py              # render -> event -> diff -> apply, no browser
uv run pyweft run examples/todo             # the todo app
uv run pyweft run packages/pyweft-ui/gallery  # every control
```

With pip: `pip install -e ".[dev]"` and `pip install -e packages/pyweft-ui`.

Releases go to PyPI by pushing a version tag; [RELEASING.md](https://github.com/prassanthn/PyWeft/blob/main/RELEASING.md)
has the steps, and [CHANGELOG.md](https://github.com/prassanthn/PyWeft/blob/main/CHANGELOG.md) what each release changed.

The website is rebuilt and published on every push to `main`. To build it
locally:

```bash
uv sync --group website
uv run python website/build.py
uv run python -m http.server -d website/_build/site    # http://127.0.0.1:8000/
```

```
src/pyweft/           the framework (zero runtime dependencies)
  static/             the browser side: runtime.js, the page shell, the worker
packages/pyweft-ui/   the control toolkit, released as its own package
docs/                 the guide (the website splits it into pages)
examples/             a headless demo, the todo app and the shop (pages)
website/              the website: home page, tutorial, build script
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

**Done:** the render core and differ; the browser target; the desktop target
(pywebview), and standalone desktop programs (PyInstaller); components with props, events, slots and component libraries;
pages and navigation; shared state with stores; events with modifiers and
`@bind` for every form control; moving focus from Python; effects; async
handlers and Web Worker background work; file and confirmation dialogs on
both targets; the app's title and icon, and window settings; scoped styles
and CSS framework support; the `pyweft` CLI with hot reload, static builds
and pre-rendered first screens; calling web APIs and saving data between
visits (`pyweft.http`, `pyweft.storage`); `pyweft-ui` with 50
keyboard-accessible controls (autocomplete, chips, sliders, date and date-range pickers, an
event calendar, charts and a menu among them), form
validation and a gallery; both released
on PyPI.

**Next:** a faster first start that also works offline; more charts
(scatter, histograms, heatmaps, candlesticks); installers (`.msi`, `.dmg`) and code signing
for desktop apps.

**Later:** mobile packaging with Briefcase, developer tools.

## License

MIT. See [LICENSE](https://github.com/prassanthn/PyWeft/blob/main/LICENSE).
