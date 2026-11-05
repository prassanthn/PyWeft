# pyweft-ui

Ready-made controls for [PyWeft](https://github.com/prassanthn/PyWeft):
buttons, menus, chips, sliders, form fields with validation, autocomplete and input masks, date and
date-range pickers, an event calendar, charts, cards, layout, tabs, tables,
dialogs, toasts and more, styled and accessible out of the box. Build a good-looking app in Python without writing HTML or
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

**New to the toolkit? Read the [guide](https://github.com/prassanthn/PyWeft/blob/main/packages/pyweft-ui/docs/guide.md)**: page layout, forms
with validation, dialogs, themes and building your own components, with
complete examples. This README is the compact reference.

## Install

Install it into the same environment as PyWeft itself (see PyWeft's
[quick start](https://github.com/prassanthn/PyWeft#quick-start)):

```bash
uv add pyweft-ui
```

With pip:

```bash
pip install pyweft-ui
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
| `AppShell` | `title`, `width` (narrow, normal, wide, full), `sticky_nav` | Header, optional sidebar and content; the sidebar stays in view while the page scrolls. Fills: `brand`, `actions`, `nav`. |
| `Row` | `gap`, `align`, `justify` (start, center, end, between), `wrap` | Children side by side. |
| `Column` | `gap`, `align` | Children stacked. |
| `Grid` | `cols`, `min_width`, `gap` | Fixed columns, or as many as fit. |
| `Card` | `title`, `subtitle` | Fills: `title`, `actions`, `footer`. |
| `Carousel` | `items`, `label`, `per_view`, `gap`, `loop`, `autoplay` (seconds), `arrows`, `indicators` (dots, none) | Slides moved by arrows, dots, swipe or drag; `@bind` to the first shown slide's index; emits `change`. Fill: `slide` (with `slide`, `index`, `active`). |
| `Divider` | `label`, `align` (center, start, end), `vertical`, `inset` (`"true"` or a length), `spacing` (none, sm, md, lg) | A thin line; with `label`, text on the line; `vertical` between items in a Row. |
| `Expansion` | `title`, `description`, `icon`, `open`, `disabled`, `toggle` (after, before, none), `level`, `lazy` | `@bind` to a bool; emits `open`, `close`. Fills: `header`, `actions`. |
| `Accordion` | `options` (dicts may add `description`, `icon`, `disabled`), `multiple`, `disabled`, `toggle`, `level`, `lazy` | `@bind` to the open panel's value (`multiple`: a list). The content between the tags is each panel's body; `panel` inside it is that panel's value. Up/Down, Home/End move between headers. |

Gaps take `none`, `xs`, `sm`, `md`, `lg`, `xl`, or any CSS length.

### Form fields

All have `label`, `hint`, `error`, `required`, `disabled`, `name`, and take
`@bind`.

| Control | Binds | Extra fields |
|---|---|---|
| `TextField` | `str` | `type` (text, email, password, search, url, tel, date, time), `placeholder`, `autocomplete`, `mask` (`"(999) 999-9999"`: 9 digit, a letter, * either), `readonly`; emits `enter` on Enter |
| `TextArea` | `str` | `rows`, `placeholder`, `readonly` |
| `NumberField` | `int` or `float` | `min`, `max`, `step`, `placeholder`, `readonly` |
| `Select` | the chosen option's value | `options`, `placeholder` |
| `RadioGroup` | the chosen option's value | `options`, `inline` |
| `Checkbox` | `bool` | |
| `Switch` | `bool` | |
| `Autocomplete` | the chosen option's value (`free="true"`: the typed text) | `options`, `match` (contains, starts, none), `max_results`, `min_chars`, `free`, `loading`, `empty`, `placeholder`, `align`; emits `search` (the text, each keystroke), `select` (the whole option), `enter`. Fills: `option` (with `option`, `active`, `query`), `empty` |
| `CascadeSelect` | the chosen option's value | nested `options` (`value`, `label`, `children`; `children: None` loads on demand via `load`), `any_level`, `show_path`, `separator`, `clearable`, `placeholder`, `name`; emits `select` (the path), `load`, `blur`. Fill: `option` (with `option`, `chosen`) |
| `ButtonToggle` | the chosen value; `multiple="true"`: a list | `options` (dicts may add `icon`, `icon_only`, `disabled`), `multiple`, `allow_none`, `check`, `size` (sm, md, lg), `full_width`, `orientation`, `aria_label`, `name` |
| `Chips` | the chosen value; `multiple="true"`: a list | `options` (dicts may add `icon`, `disabled`), `multiple`, `required`, `removable` (emits `remove`), `selectable`. Fill: `option` (with `option`, `selected`) |
| `ChipInput` | a list | `options` (suggestions), `free`, `separators`, `max`, `add_on_blur`, `match`, `placeholder`, `name`; emits `add`, `remove`. Fills: `chip` (with `chip`), `option` |
| `Slider` | an `int` or `float`; `range="true"`: `(low, high)` | `min`, `max`, `step`, `range`, `value_label` (drag/always/side/none), `format`, `ticks`, `marks`, `lazy`, `name`; emits `change`, `blur` |
| `DateRangePicker` | `(start, end)` dates or `None` | `min`, `max`, `min_days`, `max_days`, `months`, `placeholder`, `format`, `week_start`, `align`; `name` sends `<name>_start` and `<name>_end` |
| `Calendar` | `datetime.date`, or with `range="true"` `(start, end)` | always open on the page: `range`, `months`, `min`, `max`, `min_days`, `max_days`, `week_start` |
| `DatePicker` | `datetime.date` or `None` | `min`, `max` (a date or `"YYYY-MM-DD"`), `placeholder`, `format` (strftime), `week_start` (monday, sunday), `align` |

`options` can be a comma-separated string (`"Small, Medium, Large"`), a list
of values, a list of `(value, label)` pairs or a list of
`{"value": ..., "label": ...}` dicts. The bound field gets the value itself,
so `[(1, "One"), (2, "Two")]` binds an `int`.

`TextField`, `TextArea`, `NumberField`, `Select` and `DatePicker` emit
`blur` when the user leaves them, which is when a [form](#checking-forms) starts showing
that field's message.

### Data and navigation

| Control | Fields | Notes |
|---|---|---|
| `Tabs` | `options`, `label`, `variant` (line, pills) | `@bind` to the chosen option's value. The content between the tags is the panel; `tab` inside it is the chosen value. Arrow keys, Home and End move between tabs. |
| `Stepper` | `steps` (dicts may add `description`, `optional`, `error`, `done`, `disabled`), `linear`, `orientation` (horizontal, vertical), `label_position` (end, bottom), `label`, `back_label`, `next_label`, `finish_label` | `@bind` to the current step's value; the content between the tags is its body (`step`, `index`). `@next` runs before moving on (returning `False` stays); emits `finish`, `back`. Fill: `actions` (with `go_next()`, `go_back()`, `first`, `last`). |
| `Tree` | `nodes` (dicts with `value`, `label`, `icon`, `children` (None: load on open), `disabled`), `checkable`, `expanded`, `expand_all`, `filter`, `lines`, `label`, `empty`, `no_matches` | `@bind` to the selected node's value (`checkable`: the list of checked leaves). Emits `activate`, `toggle`, `load`. Fill: `node` (with `node`, `level`, `expanded`, `selected`). Arrow keys, Home/End, `*`, type-ahead. |
| `Breadcrumbs` | `items`, `auto`, `home`, `home_icon`, `separator` (chevron, slash, text), `max`, `label` | The trail to the current page; links go through the router. `auto="true"`: built from the URL and each page's `crumb`. With `@select`, items are buttons. Fill: `item` (with `item`, `current`). |
| `EventCalendar` | `events`, `view` (month, week, agenda), `months`, `date`, `week_start`, `day_start`, `day_end`, `max_per_day`, `time_format`, `switcher`, `label` | Events (dicts or objects with `title`, `start`, `end`, `color`) by month, week or day; a `date` start is all day. Emits `select` (your event), `day` (the date or hour clicked), `navigate` (`(first, last)` showing). |
| `Table` | `rows`, `columns`, `row_key`, `sortable`, `sort`, `striped`, `dense`, `caption`, `empty` | `rows` are dicts or objects. Emits `select` with the clicked row. Fills: `cell` (with `row`, `column`, `value`, `text`), `empty`. |

`Table` columns are field names (`"id, customer"`), `(field, heading)` pairs,
or dicts with `key` and optionally `label`, `format` (`",.2f"` or a
function), `align` and `sortable`. Left out, they come from the first row.
`sort="-total"` starts sorted by `total`, largest first.

### Charts

| Control | Fields | Notes |
|---|---|---|
| `BarChart` | `data`, `x`, `y`, `series`, `horizontal`, `stacked` (true, percent), `labels`, `y_min`, `y_max`, `y2_label` | Grouped, stacked or 100% bars, across or up; with `series` of `type` line or area, a combo chart, and `axis="right"`, a second scale. |
| `LineChart` | `data`, `x`, `y`, `series`, `curve` (linear, smooth, step, step-before, step-after), `fill`, `stacked`, `points`, `connect_gaps`, `labels` | Lines, or areas with `fill="true"`; series can be dashed (`dash`), on a second scale or bars. |
| `PieChart` | `data`, `label`, `value`, `donut`, `hole`, `half`, `labels` (percent, value, label, none), `center`, `center_label` | Pie, doughnut or half circle; `center="total"` writes the sum in the hole. |
| `PolarAreaChart` | `data`, `label`, `value` | Equal angles, each slice as long as its value. |
| `RadarChart` | `data`, `x`, `y`, `series`, `points` | One shape per series over three or more spokes. |

All five take `title`, `subtitle`, `height`, `legend` (auto, top, bottom,
right, none), `format`, `tick_format`, `x_label`, `y_label`, `colors`,
`aria_label` and `empty`, and emit `select` with what was clicked. `data`
is rows (dicts or objects), a dict of columns, a pandas or polars
DataFrame, a `{label: value}` dict or Chart.js's `{"labels", "datasets"}`.
Charts are SVG drawn in Python: themed, sized to their container, with
tooltips, a legend that hides series, arrow-key reading and a data table
for screen readers.

### Actions and feedback

| Control | Fields | Notes |
|---|---|---|
| `Button` | `variant` (primary, secondary, ghost, danger), `size` (sm, md, lg), `icon`, `loading`, `disabled`, `block`, `type` | Emits `click`. |
| `Menu` | `label`, `items`, `icon`, `icon_only`, `variant`, `align` (start, end), `position` (below, above), `caret`, `disabled` | A button that opens a list of actions; emits `select` with the chosen item's value. `items`: text, `(value, label)` pairs, or dicts with `value`, `label`, `icon`, `description`, `hint`, `danger`, `disabled` and `items` (a submenu); `"-"` is a divider, `{"heading": ...}` a group heading. Fills: `trigger` (your own button content), `item` (with `item`). |
| `ContextMenu` | `items`, `label`, `disabled` | Wraps content; right-click (or the Menu key, Shift+F10) opens `items` at the pointer. Emits `select`, `open`. Fill: `item`. |
| `Dialog` | `title`, `width`, `dismissible` | `@bind` to a `bool`: open while it is `True`. Esc, a click outside or the X close it. Keeps Tab inside while open and gives focus back when closed. Fill: `footer`. |
| `BottomSheet` | `title`, `items` (dicts may add `icon`, `description`, `danger`, `disabled`), `max_width`, `dismissible`, `aria_label` | `@bind` to a `bool`. Slides up from the bottom; choosing an item emits `select` and closes it. Esc, a tap outside or a swipe down close it; emits `close` with how. Fill: `actions`. |
| `Popover` | `label`, `icon`, `icon_only`, `variant` (primary, secondary, ghost, link), `caret`, `title`, `open_on` (click, hover), `position` (below, above, start, end), `align` (start, center, end), `arrow`, `width`, `disabled` | A button opening a panel of your content beside it. Click mode: `@bind` a bool, emits `open`/`close`; click outside or Esc closes. Hover mode: a preview card shown by CSS. Fill: `trigger`. |
| `Tooltip` | `text`, `position` (above, below, start, end), `tip_id`, `disabled` | Wraps a control; shows `text` on hover or keyboard focus (CSS only). Pair `tip_id` with the control's `aria-describedby`. |
| `Toaster` | `look` (toast, snackbar), `position` (bottom-right, bottom-left, bottom-center, top-left, top-center, top-right), `limit`, `dismissible` | Put one on the page; it shows what `toast()` raises. `look="snackbar"`: a compact dark bar, bottom centre, one at a time. |
| `Alert` | `kind` (info, success, warning, danger), `title`, `dismissible` | Emits `close`. |
| `Badge` | `kind` (neutral, primary, info, success, warning, danger) | |
| `Spinner` | `size`, `label` | |
| `Progress` | `value` (none: indeterminate), `max`, `buffer`, `label`, `aria_label`, `show_value`, `format`, `shape` (bar, circle), `kind`, `size` (sm, md, lg), `striped` | How far along something is; a bar, or a ring with the value inside. |
| `Icon` | `name`, `size` | check, x, plus, minus, search, info, alert, chevron-up/down/left/right, menu, trash, edit, send, user, home, star, heart, download, upload, external, copy, settings, sun, moon, calendar, more, bold, italic, underline, align-left/center/right, list, grid, folder, folder-open, file |

## Checking forms

```python
from pyweft_ui import Form, rules

form = Form(
    email=[rules.required(), rules.email()],
    password=[rules.required(), rules.min_length(8)],
    agreed=rules.accepted("Agree to the terms to continue"),
)

async def submit(self):
    if not self.form.check():     # shows every message, focuses the first field to fix
        return
    ...
```

```xml
<ui.TextField ref="email" label="Email" @bind="email"
              :error="form.error('email')" @blur="form.touch('email')" />
```

A field's message shows once the user has left it or tried to submit, then
follows what they type. Rules: `required`, `accepted`, `email`, `url`,
`min_length`, `max_length`, `min_value`, `max_value`, `pattern`, `one_of`,
`same_as` and `check`, or any function of the value that returns a message.
`form.valid`, `form.errors` and `form.reset()` do what they say. The
[guide](https://prassanthn.github.io/PyWeft/controls/guide/#a-complete-form-validation-and-submitting)
has the details.

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
