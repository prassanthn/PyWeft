---
description: Build web and desktop apps in Python. Components are .weft files, an XML template plus a Python code block.
hide:
  - navigation
  - toc
---

<div class="pw-hero" markdown>

# Build web and desktop apps in Python

Write components as `.weft` files, an XML template plus a Python code block.
PyWeft runs them in the browser on real CPython compiled to WebAssembly, or in
a native window with Python on your machine. No JavaScript to write, no build
step.

[Start the tutorial](tutorial.md){ .md-button .md-button--primary }
<a class="md-button" href="live/gallery/" target="_blank">See the controls, live</a>

</div>

<div class="pw-split" markdown>

<div markdown>

```xml title="app.weft"
<template>
  <div>
    <h1>Hello, {{ name or "stranger" }}!</h1>
    <input @bind="name" placeholder="your name" aria-label="Your name" />
    <button @click="count += 1">Clicked {{ count }} times</button>
  </div>
</template>

<code>
name: str = ""
count: int = 0
</code>
```

</div>

<div markdown>

Type in the box and the heading follows; click and the count goes up.

State is plain Python fields. After every event PyWeft renders the component
again, works out what changed and updates only that part of the page. There
are no signals or observables to learn, and your code is ordinary Python that
you can test without a browser.

</div>

</div>

## Quick start

You need Python 3.10 or newer. With [uv](https://docs.astral.sh/uv/):

```bash
uv init myproject && cd myproject
uv add pyweft
uv run pyweft new myapp
uv run pyweft run myapp
```

Open <http://127.0.0.1:8642/>, then edit `myapp/app.weft` and save: the page
updates in place and keeps what you'd typed. With pip, `pip install pyweft`,
then `pyweft new myapp` and `pyweft run myapp`.

## What you get

<div class="grid cards" markdown>

-   :material-file-code-outline:{ .lg .middle } **Components in one file**

    ---

    Template, Python code and a `<style>` block that only applies to that
    component. Props, events, slots and `@bind` for composing them.

    [:octicons-arrow-right-24: Your first component](guide/first-component.md)

-   :material-web:{ .lg .middle } **Web and desktop from one app**

    ---

    `pyweft build` makes a static site any host can serve. `pyweft run
    --desktop` opens it in a native window, and `pyweft build --desktop`
    makes a program to hand out.

    [:octicons-arrow-right-24: Apps, building and desktop](guide/projects.md)

-   :material-view-dashboard-outline:{ .lg .middle } **Ready-made controls**

    ---

    `pyweft-ui`: buttons, menus, chips, sliders, form fields with validation,
    autocomplete and input masks, date and range pickers, an event calendar, charts, tabs, sortable
    tables, dialogs, toasts, layout, and light and dark themes. No HTML or
    CSS needed.

    <a href="live/gallery/" target="_blank">:octicons-arrow-right-24: Try them live</a>

-   :material-sitemap-outline:{ .lg .middle } **Pages and shared state**

    ---

    A `pages/` folder becomes your app's screens, with links, Back and
    Forward. A `Store` holds what many components use.

    [:octicons-arrow-right-24: Pages and navigation](guide/components.md#pages-and-navigation)

-   :material-lightning-bolt-outline:{ .lg .middle } **Async and background work**

    ---

    `async def` handlers, `run_in_background()` to run heavy Python in a
    Web Worker so the page never freezes, and live data from server-sent
    events, WebSockets and streamed responses.

    [:octicons-arrow-right-24: Async handlers](guide/first-component.md#async-handlers-and-background-work)

-   :material-code-tags:{ .lg .middle } **Templates that do the work**

    ---

    `<Await>` shows loading, result and error states of async calls;
    `transition="fade"` and `animate="flip"` animate elements and lists;
    `<Html>` shows sanitized Markdown output; `<Head>` sets each page's
    title and meta tags; `<Defer>` keeps big pages quick to start;
    `sortable` lists reorder by dragging;
    `provide`/`inject` pass values down the tree.

    [:octicons-arrow-right-24: Template syntax](guide/templates.md)

-   :material-application-brackets-outline:{ .lg .middle } **Inside any website**

    ---

    Put a built app into another page, a blog post, an intranet or your
    docs, with one `<script>` and a `<pyweft-app>` tag, and pass data and
    events between them.

    [:octicons-arrow-right-24: Embedding an app](guide/projects.md#putting-an-app-inside-another-website)

-   :material-reload:{ .lg .middle } **A fast dev loop**

    ---

    Hot reload that keeps your app's state, readable errors that point to
    your `.weft` file and line, `pyweft check` for mistakes and
    accessibility problems, and a first screen that shows before Python
    has even started.

    [:octicons-arrow-right-24: Hot reload](guide/projects.md#hot-reload)

</div>

## Where next

- **New here?** The [tutorial](tutorial.md) builds a todo app step by step,
  in about fifteen minutes.
- **Looking something up?** The [guide](guide/index.md) covers every part of
  PyWeft, and the [controls guide](controls/guide.md) the toolkit.
- **Want to see it working first?** Try the [examples](examples.md), running
  live in this browser.
- **Working with an AI assistant?** Every app comes with an `AGENTS.md`
  that teaches it PyWeft, and `pyweft check` lets it find its own mistakes:
  see [AI assistants](ai.md).
