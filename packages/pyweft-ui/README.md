# pyweft-ui

Ready-made controls for [PyWeft](https://github.com/prassanthn/PyWeft):
buttons, form fields, cards, layout, tabs, tables, dialogs, toasts and more,
styled and accessible out of the box. Build a good-looking app in Python without writing HTML or
CSS.

```xml
<template>
  <ui.Theme>
    <ui.AppShell title="Orders">
      <ui.Card title="New order">
        <ui.Column>
          <ui.TextField label="Customer" @bind="customer" required="true" />
          <ui.Select label="Size" options="Small, Medium, Large" @bind="size" />
          <ui.Switch label="Express delivery" @bind="express" />
        </ui.Column>
        <Fill name="footer">
          <ui.Button variant="ghost" @click="reset">Reset</ui.Button>
          <ui.Button variant="primary" icon="send" :loading="saving" @click="submit">
            Place order
          </ui.Button>
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
saving: bool = False

def reset(self):
    self.customer, self.size, self.express = "", "Medium", False

async def submit(self):
    ...
</code>
```

**New to the toolkit? Read the [guide](docs/guide.md)**: page layout, forms
with validation, dialogs, themes and building your own components, with
complete examples. This README is the compact reference.

## Install

It isn't on PyPI yet, so install it from GitHub, into the same environment
as PyWeft itself (see PyWeft's [quick start](../../README.md#quick-start)):

```bash
uv add "pyweft-ui @ git+https://github.com/prassanthn/PyWeft.git#subdirectory=packages/pyweft-ui"
```

With pip:

```bash
pip install "git+https://github.com/prassanthn/PyWeft.git#subdirectory=packages/pyweft-ui"
```

Then add `"pyweft-ui"` to the `dependencies` list in your app's own
`pyproject.toml` (`myapp/pyproject.toml`), import it in a component's code
block with `from pyweft_ui import ui`, and use the controls as `<ui.Name>`.
`pyweft run` and `pyweft build` see that it is installed locally and send it
to the browser for you.

## Controls

Every control is a PyWeft component: attributes set its fields, `@bind`
connects it to a field of yours, and attributes it doesn't have, such as
`class`, `style`, `id` and `aria-*`, go onto its outer element. Plain
attribute values are converted to each field's type, so `cols="3"` is the
number 3 and `disabled="true"` is `True`.

### Layout

| Control | Fields | Notes |
|---|---|---|
| `Theme` | `mode` (light, dark, auto), `primary`, `radius`, `font` | Wrap your app in it to set colours and corners for everything inside. Optional. |
| `AppShell` | `title`, `width` (narrow, normal, wide, full) | Header, optional sidebar and content. Fills: `brand`, `actions`, `nav`. |
| `Row` | `gap`, `align`, `justify` (start, center, end, between), `wrap` | Children side by side. |
| `Column` | `gap`, `align` | Children stacked. |
| `Grid` | `cols`, `min_width`, `gap` | Fixed columns, or as many as fit. |
| `Card` | `title`, `subtitle` | Fills: `title`, `actions`, `footer`. |

Gaps take `none`, `xs`, `sm`, `md`, `lg`, `xl`, or any CSS length.

### Form fields

All have `label`, `hint`, `error`, `required`, `disabled`, `name`, and take
`@bind`.

| Control | Binds | Extra fields |
|---|---|---|
| `TextField` | `str` | `type` (text, email, password, search, url, tel, date, time), `placeholder`, `autocomplete`; emits `enter` on Enter |
| `TextArea` | `str` | `rows`, `placeholder` |
| `NumberField` | `int` or `float` | `min`, `max`, `step`, `placeholder` |
| `Select` | the chosen option's value | `options`, `placeholder` |
| `RadioGroup` | the chosen option's value | `options`, `inline` |
| `Checkbox` | `bool` | |
| `Switch` | `bool` | |

`options` can be a comma-separated string (`"Small, Medium, Large"`), a list
of values, a list of `(value, label)` pairs or a list of
`{"value": ..., "label": ...}` dicts. The bound field gets the value itself,
so `[(1, "One"), (2, "Two")]` binds an `int`.

### Data and navigation

| Control | Fields | Notes |
|---|---|---|
| `Tabs` | `options`, `label`, `variant` (line, pills) | `@bind` to the chosen option's value. The content between the tags is the panel; `tab` inside it is the chosen value. |
| `Table` | `rows`, `columns`, `row_key`, `sortable`, `sort`, `striped`, `dense`, `caption`, `empty` | `rows` are dicts or objects. Emits `select` with the clicked row. Fills: `cell` (with `row`, `column`, `value`, `text`), `empty`. |

`Table` columns are field names (`"id, customer"`), `(field, heading)` pairs,
or dicts with `key` and optionally `label`, `format` (`",.2f"` or a
function), `align` and `sortable`. Left out, they come from the first row.
`sort="-total"` starts sorted by `total`, largest first.

### Actions and feedback

| Control | Fields | Notes |
|---|---|---|
| `Button` | `variant` (primary, secondary, ghost, danger), `size` (sm, md, lg), `icon`, `loading`, `disabled`, `block`, `type` | Emits `click`. |
| `Dialog` | `title`, `width`, `dismissible` | `@bind` to a `bool`: open while it is `True`. Esc, a click outside or the X close it. Fill: `footer`. |
| `Toaster` | `position` (bottom-right, bottom-left, bottom-center, top-left, top-center, top-right), `limit` | Put one on the page; it shows what `toast()` raises. |
| `Alert` | `kind` (info, success, warning, danger), `title`, `dismissible` | Emits `close`. |
| `Badge` | `kind` (neutral, primary, info, success, warning, danger) | |
| `Spinner` | `size`, `label` | |
| `Icon` | `name`, `size` | check, x, plus, minus, search, info, alert, chevron-up/down/left/right, menu, trash, edit, send, user, home, star, heart, download, upload, external, copy, settings, sun, moon |

## Toasts

```python
from pyweft_ui import toast, clear_toasts

toast("Saved")                                   # info, closes after 4 s
toast("Payment failed", "danger", title="Oops")  # kind: info, success, warning, danger
toast("Archived", action="Undo", on_action=undo) # a button that calls undo()
note = toast("Uploading…", duration=None)        # stays until note.close()
```

Call it from any handler or task; the page's `<ui.Toaster />` shows it.

## Theming

```xml
<ui.Theme mode="auto" primary="#0f766e" radius="12px">
  ...
</ui.Theme>
```

Every colour is a CSS variable (`--ui-primary`, `--ui-text`, `--ui-surface`,
`--ui-border`, `--ui-danger` ...), so you can also set them in your own CSS.

## The gallery

`gallery/` is a PyWeft app showing every control. From the PyWeft repository:

```bash
uv run pyweft run packages/pyweft-ui/gallery
```
