# Using pyweft-ui

This guide shows how to build screens with the ready-made controls: forms,
layouts, dialogs and themes, with complete examples you can paste into an
app. The [README](../README.md) has the compact reference of every control's
fields; this guide is the how-to.

**Contents**

1. [Setup](#1-setup)
2. [How controls work](#2-how-controls-work)
3. [Page layout](#3-page-layout)
4. [Forms](#4-forms)
5. [Buttons](#5-buttons)
6. [Messages, badges and loading](#6-messages-badges-and-loading)
7. [Dialogs](#7-dialogs)
8. [Tabs](#8-tabs)
9. [Tables](#9-tables)
10. [Toasts](#10-toasts)
11. [Icons](#11-icons)
12. [Themes](#12-themes)
13. [Changing how a control looks](#13-changing-how-a-control-looks)
14. [Building your own components from controls](#14-building-your-own-components-from-controls)
15. [Accessibility and keyboard](#15-accessibility-and-keyboard)

---

## 1. Setup

Install PyWeft and pyweft-ui (see the [README](../README.md#install)), add
`"pyweft-ui"` to the `dependencies` in your app's `pyproject.toml`, and import
the toolkit in the code block of any component that uses it:

```xml
<template>
  <ui.Theme>
    <ui.Card title="Hello">
      <ui.Button variant="primary" @click="count += 1">Clicked {{ count }} times</ui.Button>
    </ui.Card>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

count: int = 0
</code>
```

Every control is written `<ui.Name>`. `ui` is simply the name you imported:
`from pyweft_ui import ui as kit` would make them `<kit.Button>`.

Wrap your app in `<ui.Theme>` once, at the top. It sets the colours, font and
corner style for everything inside, and gives the page a matching background.
Controls also work without it, with the default look.

## 2. How controls work

Controls are ordinary PyWeft components, so everything you already know
applies. Five things are worth knowing up front.

**Attributes set a control's fields, converted to the right type.** Write
values as plain text: numbers become numbers and `true`/`false` become
`True`/`False`.

```xml
<ui.Grid cols="3">...</ui.Grid>             <!-- cols is the number 3 -->
<ui.Button disabled="true">Save</ui.Button>  <!-- disabled is True -->
```

To pass a Python value from your component, put a colon in front:

```xml
<ui.Button :disabled="not form_ok" :loading="saving">Save</ui.Button>
<ui.Select :options="countries" @bind="country" />
```

**`@bind` connects a control to one of your fields**, both ways: the control
shows the field's value, and when the user changes it, your field changes.

```xml
<ui.TextField label="Name" @bind="name" />
```

**Controls emit events** you handle with `@`, like page elements:
`@click` on `Button`, `@close` on `Alert` and `Dialog`, `@enter` on
`TextField`. A handler that takes a parameter receives what the control
sent: the browser event for a click, the new value for `@update`.

**`<Fill name="...">` puts content into a named place** in a control, such as
a card's footer or a dialog's buttons. Content outside any `<Fill>` goes in
the main area.

```xml
<ui.Card title="Invoice">
  <p>Main content.</p>
  <Fill name="footer"><ui.Button>Pay</ui.Button></Fill>
</ui.Card>
```

**`class`, `style`, `id` and `aria-*` go onto the control's outer element**,
so you can position it or label it without knowing what's inside:

```xml
<ui.Button class="checkout" id="pay" aria-label="Pay now">Pay</ui.Button>
```

## 3. Page layout

### The app frame: AppShell

`AppShell` gives you a header bar, an optional sidebar and a centred content
area. On narrow screens the sidebar moves above the content.

```xml
<template>
  <ui.Theme>
    <ui.AppShell title="Acme Admin" width="wide">
      <Fill name="actions">
        <ui.Badge kind="success">online</ui.Badge>
        <ui.Button size="sm" icon="user">Account</ui.Button>
      </Fill>
      <Fill name="nav">
        <For each="page in pages" key="page">
          <ui.Button variant="ghost" @click="current = page">{{ page }}</ui.Button>
        </For>
      </Fill>

      <h1>{{ current }}</h1>
      <p>The content of the {{ current }} page.</p>
    </ui.AppShell>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

pages: list = ["Dashboard", "Orders", "Customers"]
current: str = "Dashboard"
</code>
```

- `title` is the text at the top left. `<Fill name="brand">` replaces it with
  anything, such as a logo and a name.
- `<Fill name="actions">` sits at the top right.
- `<Fill name="nav">` is the sidebar. Leave it out for no sidebar.
- `width` is how wide the content may grow: `narrow` (40rem), `normal`
  (64rem, the default), `wide` (80rem), `full`, or any CSS width.

### Arranging things: Row, Column, Grid

These three replace almost all layout CSS.

```xml
<ui.Column gap="lg">                    <!-- stacked, with space between -->
  <ui.Row justify="between">            <!-- side by side, pushed apart -->
    <h2>Orders</h2>
    <ui.Button variant="primary" icon="plus">New order</ui.Button>
  </ui.Row>
  <ui.Grid min_width="16rem">           <!-- as many columns as fit -->
    <ui.Card title="Today">12</ui.Card>
    <ui.Card title="This week">87</ui.Card>
    <ui.Card title="This month">340</ui.Card>
  </ui.Grid>
</ui.Column>
```

| Control | Fields |
|---|---|
| `Row` | `gap`; `align` (vertical: `start`, `center`, `end`, `stretch`, `baseline`); `justify` (horizontal: `start`, `center`, `end`, `between`, `around`); `wrap` (`true` by default: move to a new line when out of room) |
| `Column` | `gap`; `align` (horizontal: `stretch`, the default, makes children full width; `start`, `center`, `end`) |
| `Grid` | `cols` (a fixed number of equal columns), or `min_width` (as many columns of at least this width as fit, `14rem` by default); `gap` |

`gap` takes `none`, `xs` (4px), `sm` (8px), `md` (12px, the default), `lg`
(20px), `xl` (32px), or any CSS length such as `1.5rem`.

### Grouping: Card

```xml
<ui.Card title="Payment method" subtitle="Charged on the 1st of each month">
  <p>Visa ending in 4242</p>
  <Fill name="actions"><ui.Button size="sm" variant="ghost" icon="edit">Change</ui.Button></Fill>
  <Fill name="footer"><ui.Button variant="danger">Remove card</ui.Button></Fill>
</ui.Card>
```

A card shows a header only when it has a `title`, `subtitle`, or a
`title`/`actions` fill, and a footer only when it has a `footer` fill.

## 4. Forms

### The fields

All fields take a `label`, a `hint` (small grey text underneath), an `error`
(shown instead of the hint, in red), `required` (adds a red `*`), `disabled`
and `name` (the field's name inside a `<form>`), and all work with `@bind`.

```xml
<ui.TextField label="Full name" @bind="name" placeholder="Ada Lovelace" />
<ui.TextField label="Email" type="email" @bind="email" autocomplete="email" />
<ui.TextField label="Password" type="password" @bind="password" />
<ui.TextField label="Birthday" type="date" @bind="birthday" />
<ui.TextArea label="Message" rows="5" @bind="message" />
<ui.NumberField label="Guests" min="1" max="12" @bind="guests" />
<ui.Select label="Room" placeholder="Choose a room" options="Single, Double, Suite" @bind="room" />
<ui.RadioGroup label="Breakfast" options="None, Continental, Full" inline="true" @bind="breakfast" />
<ui.Checkbox label="Airport pickup" @bind="pickup" />
<ui.Switch label="Email me offers" @bind="offers" />
```

What each one gives your field:

| Control | Your field gets |
|---|---|
| `TextField`, `TextArea` | a `str`. `TextField`'s `type` can be `text`, `email`, `password`, `search`, `url`, `tel`, `date`, `time`; dates and times arrive as text such as `"2026-10-29"` |
| `NumberField` | an `int` while your field is an `int` (or `None`), otherwise a `float`. While the box is empty or holds something that isn't a number yet, your field keeps its last value |
| `Select`, `RadioGroup` | the chosen option's value |
| `Checkbox`, `Switch` | a `bool` |

### Options for Select and RadioGroup

`options` accepts whatever is handiest:

```xml
<ui.Select options="Small, Medium, Large" @bind="size" />
<ui.Select :options="['Small', 'Medium', 'Large']" @bind="size" />
<ui.Select :options="[(1, 'One star'), (5, 'Five stars')]" @bind="rating" />
<ui.Select :options="[{'value': 'nl', 'label': 'Netherlands'}, {'value': 'in', 'label': 'India'}]" @bind="country" />
```

Your field receives the **value**, not the label, and keeps its type: with
the pairs above, `rating` becomes the `int` 5. A `Select` with a
`placeholder` shows it, greyed out, until something is chosen; your field
stays `None` until then.

### Checkbox and Switch labels with links

Put the label between the tags when it needs more than text:

```xml
<ui.Checkbox @bind="agreed">I agree to the <a href="/terms">terms</a></ui.Checkbox>
```

### A complete form: validation and submitting

This sign-up form checks its fields when submitted, shows messages next to
the fields that need attention, shows progress while saving, and confirms
when done.

```xml
<template>
  <ui.Theme>
    <ui.Card title="Create your account">
      <form novalidate="" @submit.prevent="submit">
        <ui.Column>
          <ui.TextField label="Email" type="email" required="true" autocomplete="email"
                        @bind="email" :error="errors.get('email', '')" />
          <ui.TextField label="Password" type="password" required="true"
                        hint="At least 8 characters"
                        @bind="password" :error="errors.get('password', '')" />
          <ui.Select label="Country" placeholder="Choose your country"
                     options="India, Netherlands, United States"
                     @bind="country" :error="errors.get('country', '')" />
          <ui.Checkbox @bind="agreed">I agree to the terms</ui.Checkbox>

          <If cond="done">
            <ui.Alert kind="success" title="Welcome!">Your account for {{ email }} is ready.</ui.Alert>
          </If>

          <ui.Button type="submit" variant="primary" block="true"
                     :loading="saving" :disabled="not agreed">Create account</ui.Button>
        </ui.Column>
      </form>
    </ui.Card>
  </ui.Theme>
</template>

<code>
import asyncio
from pyweft_ui import ui

email: str = ""
password: str = ""
country = None
agreed: bool = False
errors: dict = {}
saving: bool = False
done: bool = False

def check(self):
    errors = {}
    if "@" not in self.email:
        errors["email"] = "Enter an email address like you@example.com"
    if len(self.password) < 8:
        errors["password"] = "Use at least 8 characters"
    if self.country is None:
        errors["country"] = "Choose a country"
    return errors

async def submit(self):
    self.errors = self.check()
    if self.errors:
        return
    self.saving = True
    await asyncio.sleep(1)      # send it to your server here
    self.saving = False
    self.done = True
</code>
```

How it fits together:

- **`<form @submit.prevent="submit">`** runs `submit` when the user clicks the
  `type="submit"` button *or presses Enter in a field*, and `.prevent` stops
  the browser from reloading the page.
- **`novalidate=""`** turns off the browser's own pop-up checks, so your
  messages are the only ones. Leave it out and `required="true"` fields are
  also checked by the browser, which blocks submitting until they're filled.
- **`errors` is a dict of field name to message.** Each field shows
  `errors.get('email', '')`, so a field with no problem shows nothing.
  Setting `self.errors = {}` clears them all.
- **`:loading="saving"`** shows a spinner on the button and makes it
  unclickable while the `async` handler waits, so nobody submits twice.

To check each field as soon as the user leaves it, rather than on submit,
handle `@update` on the field and update `errors` there.

## 5. Buttons

```xml
<ui.Row>
  <ui.Button variant="primary">Save</ui.Button>        <!-- the main action -->
  <ui.Button>Cancel</ui.Button>                        <!-- secondary, the default -->
  <ui.Button variant="ghost">Skip</ui.Button>          <!-- low emphasis -->
  <ui.Button variant="danger" icon="trash">Delete</ui.Button>
</ui.Row>
<ui.Row>
  <ui.Button size="sm">Small</ui.Button>
  <ui.Button size="lg">Large</ui.Button>
  <ui.Button icon="download">With an icon</ui.Button>
  <ui.Button block="true">Full width</ui.Button>
</ui.Row>
```

- **`@click`** runs your handler. It can be `async`; pair it with `:loading`
  for long actions (see the form above).
- **`type="submit"`** inside a `<form>` submits the form. The default,
  `button`, never does, so buttons in forms don't submit by accident.
- **`loading`** shows a spinner instead of the icon and disables the button.
  **`disabled`** greys it out.
- An icon-only button needs a text alternative for screen readers:
  `<ui.Button icon="x" aria-label="Close" />`.

## 6. Messages, badges and loading

### Alert

```xml
<ui.Alert kind="info">Your trial ends in 3 days.</ui.Alert>
<ui.Alert kind="success" title="Saved">Your changes are live.</ui.Alert>
<ui.Alert kind="warning" title="Heads up">This affects every user.</ui.Alert>
<ui.Alert kind="danger" title="Payment failed">Check your card details and try again.</ui.Alert>
```

To let the user close it, add `dismissible="true"` and handle `@close`. The
alert doesn't hide itself; you decide, typically with a field:

```xml
<If cond="show_tip">
  <ui.Alert kind="info" dismissible="true" @close="show_tip = False">
    Tip: press Enter to search.
  </ui.Alert>
</If>
```

### Badge

Small labels for status and counts:

```xml
<ui.Badge>draft</ui.Badge>
<ui.Badge kind="success">paid</ui.Badge>
<ui.Badge kind="warning">due soon</ui.Badge>
<ui.Badge kind="danger">overdue</ui.Badge>
<ui.Badge kind="primary">{{ unread }} new</ui.Badge>
```

### Spinner and loading states

```xml
<If cond="loading">
  <ui.Row><ui.Spinner /><span>Loading orders…</span></ui.Row>
</If>
<Else>
  <p>{{ len(orders) }} orders</p>
</Else>
```

A pattern for loading data when a component appears:

```xml
<template>
  <ui.Card title="Orders">
    <If cond="orders is None"><ui.Spinner /></If>
    <Else>
      <For each="order in orders" key="order['id']">
        <ui.Row justify="between">
          <span>#{{ order['id'] }}</span>
          <ui.Badge :kind="'success' if order['paid'] else 'warning'">
            {{ 'paid' if order['paid'] else 'unpaid' }}
          </ui.Badge>
        </ui.Row>
      </For>
    </Else>
  </ui.Card>
</template>

<code>
import asyncio
from pyweft_ui import ui

orders = None

async def on_init(self):
    await asyncio.sleep(1)      # fetch from your server here
    self.orders = [{"id": 101, "paid": True}, {"id": 102, "paid": False}]
</code>
```

## 7. Dialogs

A dialog is open while the field you bind it to is `True`.

### Asking for confirmation

```xml
<template>
  <ui.Theme>
    <ui.Row>
      <ui.Button variant="danger" icon="trash" @click="confirming = True">Delete project</ui.Button>
      <span>{{ status }}</span>
    </ui.Row>

    <ui.Dialog title="Delete this project?" @bind="confirming">
      <p>“{{ project }}” and its files will be removed. This can't be undone.</p>
      <Fill name="footer">
        <ui.Button @click="confirming = False">Cancel</ui.Button>
        <ui.Button variant="danger" @click="delete_project">Delete</ui.Button>
      </Fill>
    </ui.Dialog>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

project: str = "Website redesign"
confirming: bool = False
status: str = ""

def delete_project(self):
    self.status = f"Deleted {self.project}."
    self.confirming = False
</code>
```

- **Opening and closing are just your field.** Set it to `True` to open and
  `False` to close.
- **The user can close it too,** with Esc, a click on the dark area around
  it, or the X. The dialog sets your field to `False` and emits `@close`.
  For a question the user must answer, add `dismissible="false"`: then only
  your own buttons can close it.
- **`width`** sets its maximum width (`32rem` by default).
- **Forms work inside dialogs:** put a `<form @submit.prevent>` with fields
  in it, and close the dialog from the submit handler when the input is valid.

### Running code whenever it closes

`@close` runs however the dialog was dismissed, which is handy for resetting
what was typed into it:

```xml
<ui.Dialog title="Rename" @bind="renaming" @close="new_name = ''">
  <ui.TextField label="New name" @bind="new_name" />
</ui.Dialog>
```

`@close` only fires when the *dialog* closes itself (Esc, the dark area, the
X); when your own code sets the field to `False`, you're already there to do
whatever's needed.

## 8. Tabs

`Tabs` shows a row of tabs. Bind it to a field, and put what each tab shows
between its tags:

```xml
<template>
  <ui.Theme>
    <ui.Tabs label="Account" options="Profile, Security, Billing" @bind="tab">
      <If cond="tab == 'Profile'">
        <ui.TextField label="Display name" @bind="display_name" />
      </If>
      <ElseIf cond="tab == 'Security'">
        <ui.Switch label="Two-step sign-in" @bind="two_step" />
      </ElseIf>
      <Else>
        <p>You're on the free plan.</p>
      </Else>
    </ui.Tabs>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

tab: str = "Profile"
display_name: str = "Ada"
two_step: bool = False
</code>
```

- **`options`** takes the same forms as `Select`'s: a comma-separated
  string, a list, `(value, label)` pairs or dicts. Your field gets the value.
- **Start your field at one of the values**, as `tab = "Profile"` does above.
  Until it is, the first tab is shown.
- **`tab` inside the tags is always the chosen tab**, even without `@bind`,
  for tabs nothing else needs to know about:

  ```xml
  <ui.Tabs options="Day, Week, Month" variant="pills">
    <p>Sales this {{ tab.lower() }}: {{ sales[tab] }}</p>
  </ui.Tabs>
  ```

- **`variant`** is `line` (underlined, the default) or `pills`.
- **`label`** names the tab row for screen readers.
- Leave the tags empty (`<ui.Tabs ... />`) to use the tab row on its own,
  for example to switch what a whole page shows.

Only the chosen tab's content exists on the page, so what's typed into a
field on another tab lives in your fields, not in the hidden tab.

## 9. Tables

`Table` shows a list of dicts (or objects) as rows. Name the fields to show
as columns:

```xml
<ui.Table :rows="orders" columns="id, customer, total" />
```

Leave out `columns` and every field of the first row becomes a column.
Headings come from the field names (`order_date` becomes "Order date"), and
columns of numbers line up on the right by themselves.

A complete example: headings to click for sorting, a formatted amount, a
badge in the status column, and a row the user can pick:

```xml
<template>
  <ui.Theme>
    <ui.Table :rows="orders" :columns="COLUMNS" row_key="id"
              sortable="true" sort="-total" @select="open_order">
      <Fill name="cell">
        <If cond="column == 'status'">
          <ui.Badge :kind="'success' if value == 'paid' else 'warning'">{{ text }}</ui.Badge>
        </If>
        <Else>{{ text }}</Else>
      </Fill>
      <Fill name="empty">No orders yet.</Fill>
    </ui.Table>
    <p>{{ message }}</p>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

COLUMNS = [
    ("id", "Order"),
    "customer",
    "status",
    {"key": "total", "label": "Amount", "format": ",.2f"},
]

orders: list = [
    {"id": 1041, "customer": "Ada Lovelace", "status": "paid", "total": 1250.0},
    {"id": 1042, "customer": "Grace Hopper", "status": "pending", "total": 89.9},
]
message: str = "Click an order."

def open_order(self, order):
    self.message = f"Order {order['id']} for {order['customer']}"
</code>
```

**Columns** can be written in four ways, mixed freely: a field name,
`(field, heading)`, or a dict with `key` and any of:

| Key | Meaning |
|---|---|
| `label` | the heading |
| `format` | a format such as `",.2f"` (1,250.00), `".0%"` or `"%d %b %Y"` for dates, or a function from the value to text |
| `align` | `start`, `center` or `end` |
| `sortable` | `False` to stop one column from sorting |

**Sorting:** `sortable="true"` lets the user click a heading to sort, and
again to reverse. `sort="total"` starts sorted by `total`, `sort="-total"`
largest first. Text sorts ignoring case, and empty cells always go last.

**Picking a row:** `@select` makes rows clickable (and reachable with Tab,
then Enter) and gives your handler the row. Without it, rows are plain.

**Your own cell content:** `<Fill name="cell">` replaces every cell. Inside
it, `row` is the row, `column` the column's field name, `value` the raw
value and `text` the formatted text, so `<Else>{{ text }}</Else>` keeps the
other columns as they were. A button in a cell also counts as a click on
its row; write `@click.stop` on it to keep the two apart.

**Rows that change:** give `row_key` a field that identifies each row, such
as `"id"`. Rows then keep their identity when the list is re-ordered or
filtered. Without it, rows are matched by their position in your list.

Other fields: `striped="true"` shades every other row, `dense="true"`
tightens the spacing, `caption` adds a title above the table, and `empty`
is the text shown when there are no rows ("Nothing to show"; the `empty`
fill replaces it with anything). On a narrow screen the table scrolls
sideways inside its frame.

## 10. Toasts

Toasts are short messages that appear in a corner of the page and go away
by themselves: "Saved", "Copied", "Message sent". Put one `<ui.Toaster />` on
the page, inside your `Theme`, then call `toast()` from any handler:

```xml
<template>
  <ui.Theme>
    <ui.Row>
      <ui.Button variant="primary" @click="save">Save</ui.Button>
      <ui.Button variant="danger" @click="archive">Archive</ui.Button>
    </ui.Row>
    <p>{{ len(notes) }} notes</p>
    <ui.Toaster />
  </ui.Theme>
</template>

<code>
from pyweft_ui import toast, ui

notes: list = ["Groceries", "Ideas", "Books"]

def save(self):
    toast("Your changes are saved.", "success")

def archive(self):
    gone = self.notes.pop()
    toast(f"Archived “{gone}”.", action="Undo", on_action=lambda: self.notes.append(gone))
</code>
```

`toast(message, kind, ...)` takes:

| Argument | Meaning |
|---|---|
| `kind` | `info` (the default), `success`, `warning` or `danger` |
| `title` | bold text above the message |
| `duration` | seconds before it closes, `4` by default; `None` keeps it until the user closes it |
| `action`, `on_action` | a button such as "Undo", and the function it calls (which may be `async`) |

Good to know:

- **It works from anywhere:** a handler, an `async` task after an `await`,
  or a plain Python module of yours. The Toaster shows every toast, whichever
  component raised it.
- **Timers pause** while the pointer is over the toasts or focus is in them,
  so nobody loses a message they're reading.
- **`toast()` returns the toast**; call `.close()` on it to take it away
  early, for example a "Uploading…" toast with `duration=None` that you close
  when the upload finishes. `clear_toasts()` closes them all.
- **`<ui.Toaster>` fields:** `position` (`bottom-right`, the default;
  `bottom-left`, `bottom-center`, `top-left`, `top-center`, `top-right`) and
  `limit` (at most 5 at once by default; older ones wait their turn).
- Toasts raised before the Toaster is on the page appear once it is.

## 11. Icons

```xml
<ui.Icon name="star" />
<ui.Icon name="heart" size="2em" />
```

Icons take the text colour around them and are `1em` by default, so they
match the text size. Buttons and alerts use them for you (`icon="send"`).

Available names: `check`, `x`, `plus`, `minus`, `search`, `info`, `alert`,
`chevron-up`, `chevron-down`, `chevron-left`, `chevron-right`, `menu`,
`trash`, `edit`, `send`, `user`, `home`, `star`, `heart`, `download`,
`upload`, `external`, `copy`, `settings`, `sun`, `moon`.

## 12. Themes

```xml
<ui.Theme mode="auto" primary="#0f766e" radius="12px" font="Inter, sans-serif">
  ...
</ui.Theme>
```

| Field | Effect |
|---|---|
| `mode` | `light` (the default), `dark`, or `auto` to follow the visitor's system setting |
| `primary` | the accent colour: primary buttons, focus rings, switches, checkboxes, spinners |
| `radius` | corner rounding: `0` for square, `12px` for round |
| `font` | a CSS font family; load web fonts in `head.html` |

### Letting users switch between light and dark

Bind the theme's mode to a field and give the user a control for it:

```xml
<template>
  <ui.Theme :mode="mode">
    <ui.AppShell title="My app">
      <Fill name="actions">
        <ui.Select :options="[('light', 'Light'), ('dark', 'Dark'), ('auto', 'System')]"
                   @bind="mode" aria-label="Colour mode" />
      </Fill>
      <p>Pick a colour mode at the top right.</p>
    </ui.AppShell>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

mode: str = "auto"
</code>
```

### Fine-tuning colours

Every colour the controls use is a CSS variable. Set any of them on the
`Theme` with `style`:

```xml
<ui.Theme style="--ui-surface: #fffdf7; --ui-border: #e7dcc5">...</ui.Theme>
```

| Variable | Used for |
|---|---|
| `--ui-primary`, `--ui-on-primary` | the accent colour, and text on it |
| `--ui-text`, `--ui-muted` | main text, secondary text |
| `--ui-bg` | the page background |
| `--ui-surface` | cards, fields, dialogs |
| `--ui-subtle` | hover backgrounds, card footers |
| `--ui-border` | borders and dividers |
| `--ui-info`, `--ui-success`, `--ui-warning`, `--ui-danger` | alerts, badges, errors |
| `--ui-radius` | corner rounding |
| `--ui-font` | the font family |

A `Theme` inside another restyles just that part of the page, for example a
dark sidebar in a light app.

## 13. Changing how a control looks

From the lightest touch to the heaviest:

1. **Use the control's own fields** first: `variant`, `size`, `kind`,
   `block`, and so on.
2. **Change theme variables** (above) to restyle every control at once.
3. **Add a `class` or `style`** to position or size one control. They go on
   its outer element, so your component's own `<style>` block can target
   them:

   ```xml
   <ui.Button class="hero-cta" variant="primary" size="lg">Get started</ui.Button>
   ```

   ```css
   .hero-cta { min-width: 14rem; margin-top: 2rem; }
   ```

4. **Wrap it in your own component** (next section) when you want a reusable
   variant with its own look.

What happens *inside* a control, such as the exact padding of a text field,
is styled by the toolkit. Prefer the theme variables over overriding those
details, so your app keeps working as the toolkit improves.

## 14. Building your own components from controls

Your own components can use controls in their templates and pass content
through to them.

A reusable stat card (`stat_card.weft`, next to your `app.weft`):

```xml
<!-- stat_card.weft -->
<template>
  <ui.Card :title="label">
    <p class="figure">{{ value }}</p>
    <If cond="change">
      <ui.Badge :kind="'success' if change > 0 else 'danger'">{{ change }}%</ui.Badge>
    </If>
  </ui.Card>
</template>

<code>
from pyweft_ui import ui

label: str = ""
value: str = ""
change: int = 0
</code>

<style>
.figure { margin: 0 0 4px; font-size: 2rem; font-weight: 700; }
</style>
```

Using it:

```xml
<template>
  <ui.Theme>
    <ui.Grid min_width="12rem">
      <StatCard label="Revenue" value="$48,200" change="12" />
      <StatCard label="Orders" value="1,204" change="-3" />
      <StatCard label="Customers" value="932" />
    </ui.Grid>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui
</code>
```

A field of your own that works with `@bind`, built on `TextField`
(`email_field.weft`). It receives your field as `value` and reports changes
with `emit("update", ...)`:

```xml
<!-- email_field.weft -->
<template>
  <ui.TextField :label="label" type="email" autocomplete="email"
                :value="value" :error="problem" @update="emit('update', event)" />
</template>

<code>
from pyweft_ui import ui

label: str = "Email"
value: str = ""

@property
def problem(self):
    if self.value and "@" not in self.value:
        return "That doesn't look like an email address"
    return ""
</code>
```

```xml
<template>
  <ui.Theme>
    <EmailField @bind="email" />
    <p>You typed: {{ email }}</p>
  </ui.Theme>
</template>

<code>
from pyweft_ui import ui

email: str = ""
</code>
```

## 15. Accessibility and keyboard

The controls are built on standard HTML elements, so keyboards, screen
readers and mobile devices work the way people expect:

- **Fields are labelled:** every field's `label` is connected to its input,
  so clicking the label focuses the field and screen readers announce it.
  `error` marks the field as invalid for screen readers as well as in red.
- **Everything is reachable with Tab**, shows a visible focus ring, and
  works with Space and Enter. Radio buttons move with the arrow keys.
- **Alerts are announced:** `warning` and `danger` alerts interrupt, `info`
  and `success` wait politely.
- **Dialogs** are announced as dialogs, move focus into themselves when they
  open (so Esc closes them straight away), and close with Esc.
- **Tabs** are announced as tabs, with the chosen one marked, and their
  content as the chosen tab's panel.
- **Tables** use real table headings, and tell screen readers which column
  is sorted and which way.
- **Toasts** are read out politely when they appear (`danger` ones
  interrupt), and pause while someone is reading them.
- **Motion is reduced** for visitors who ask their system for it: spinners
  slow down, and dialogs and toasts appear without animating.

What you should add yourself:

- A text alternative for buttons with only an icon:
  `aria-label="Close"`.
- An `aria-label` on fields with no visible `label`, like the colour-mode
  `Select` in section 12, and a `label` on `Tabs`.
- Don't put the only copy of something important in a toast: it goes away.
  Show errors that need fixing next to what needs fixing.

Not done yet:

- Dialogs don't keep Tab inside themselves, and don't return focus to the
  button that opened them when they close.
- Each tab is its own Tab stop; the arrow keys don't move between tabs.
