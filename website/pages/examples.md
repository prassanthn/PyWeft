---
description: PyWeft apps running live in your browser, with their source.
---

# Examples

These are real PyWeft apps, running in your browser: Python runs on the page
itself, with no server behind it. Each starts in a few seconds the first time
while the browser downloads Python, and faster after that.

## Todos

The todo app from the [tutorial](tutorial.md), plus a package from PyPI
(`humanize`, which spells out "three left") and an effect that keeps the
browser tab's title up to date.

<a class="md-button" href="../live/todo/" target="_blank">Open full screen</a>
[Source](https://github.com/prassanthn/PyWeft/tree/main/examples/todo){ .md-button }

<iframe class="pw-live" src="../live/todo/" title="The todo example, running live" loading="lazy"></iframe>

## Shop orders

A small back office with several pages: a `pages/` folder for the screens,
links and the Back button, typed values from the address
(`#/orders/1001`), a `Store` for pinned orders shared between pages, a
shared Python module for the data, and exporting to a CSV file.

<a class="md-button" href="../live/shop/" target="_blank">Open full screen</a>
[Source](https://github.com/prassanthn/PyWeft/tree/main/examples/shop){ .md-button }

<iframe class="pw-live pw-live--tall" src="../live/shop/" title="The shop example, running live" loading="lazy"></iframe>

## Controls gallery

Every control in `pyweft-ui`, with light and dark themes. It has a page of
its own: [the live gallery](controls/gallery.md).

## Run them yourself

Clone the repository and run any of them with hot reload, so you can change
the code and watch:

```bash
git clone https://github.com/prassanthn/PyWeft.git && cd PyWeft
uv sync
uv run pyweft run examples/todo
```
