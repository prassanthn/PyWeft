---
description: PyWeft apps running live in your browser, with their source.
---

# Examples

These are real PyWeft apps, running in your browser: Python runs on the page
itself, with no server behind it. Each opens in a new tab, and starts in a
few seconds the first time while the browser downloads Python, faster after
that. The todo and shop apps are styled with [Tailwind
CSS](guide/projects.md#using-css-frameworks), in light and dark.

<!-- Raw HTML because the live apps aren't pages mkdocs knows; paths are
     relative to this page's address, /examples/. -->

## Todos

The todo app from the [tutorial](tutorial.md): it remembers your list
between visits with `pyweft.storage`, uses a package from PyPI
(`humanize`, which spells out "three left"), and keeps the browser tab's
title up to date with an effect. Rows slide in and out and the list closes
up smoothly (`transition` and `animate="flip"`), and ++ctrl+k++ jumps to
the input from anywhere (a `<Window>` shortcut).

<a class="md-button md-button--primary" href="../live/todo/" target="_blank">Open the app</a>
[Source](https://github.com/prassanthn/PyWeft/tree/main/examples/todo){ .md-button }

## Shop orders

A small back office: a dashboard, an orders table with filters, and a page
per order. It shows a `pages/` folder for the screens, links and the Back
button, typed values from the address (`#/orders/1047`), a `Store` for
pinned orders shared between pages, a shared Python module for the data, a
component used by several pages, and exporting to a CSV file. Each order
page loads its data with `<Await>` (a skeleton while it waits) and names
the browser tab with `<Head>`.

<a class="md-button md-button--primary" href="../live/shop/" target="_blank">Open the app</a>
[Source](https://github.com/prassanthn/PyWeft/tree/main/examples/shop){ .md-button }

## Controls gallery

Every control in `pyweft-ui`, with light and dark themes, and the code that
produced each one.

<a class="md-button md-button--primary" href="../live/gallery/" target="_blank">Open the app</a>
[Source](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/gallery/app.weft){ .md-button }

## Run them yourself

Clone the repository and run any of them with hot reload, so you can change
the code and watch:

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync
uv run pyweft run examples/todo
```
