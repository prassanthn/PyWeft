# Using pyweft-ui

This guide shows how to build screens with the ready-made controls: forms,
autocomplete, chips, sliders and validation, dates and calendars, layouts, menus, dialogs, tables
and themes, with complete examples you can paste into an app. The [README](../README.md) has the compact reference of every control's
fields; this guide is the how-to.

**Contents**

1. [Setup](#1-setup)
2. [How controls work](#2-how-controls-work)
3. [Page layout](#3-page-layout)
4. [Forms](#4-forms)
   - [The fields](#the-fields)
   - [Shaped input: mask](#shaped-input-mask)
   - [Options for Select and RadioGroup](#options-for-select-and-radiogroup)
   - [Suggestions as you type: Autocomplete](#suggestions-as-you-type-autocomplete)
   - [A row of choices: ButtonToggle](#a-row-of-choices-buttontoggle)
   - [Chips: Chips and ChipInput](#chips-chips-and-chipinput)
   - [Sliders](#sliders)
   - [Checkbox and Switch labels with links](#checkbox-and-switch-labels-with-links)
   - [Dates: DatePicker](#dates-datepicker)
   - [Date ranges: DateRangePicker](#date-ranges-daterangepicker)
   - [A calendar on the page: Calendar](#a-calendar-on-the-page-calendar)
   - [A complete form: validation and submitting](#a-complete-form-validation-and-submitting)
   - [Rules](#rules)
   - [What the form can tell you](#what-the-form-can-tell-you)
5. [Buttons](#5-buttons)
   - [A menu of actions: Menu](#a-menu-of-actions-menu)
   - [Right-click menus: ContextMenu](#right-click-menus-contextmenu)
6. [Messages, badges and loading](#6-messages-badges-and-loading)
   - [How far along: Progress](#how-far-along-progress)
7. [Dialogs](#7-dialogs)
   - [Sheets from the bottom: BottomSheet](#sheets-from-the-bottom-bottomsheet)
   - [Small panels beside a button: Popover](#small-panels-beside-a-button-popover)
   - [Labels on hover: Tooltip](#labels-on-hover-tooltip)
8. [Tabs](#8-tabs)
   - [A task in steps: Stepper](#a-task-in-steps-stepper)
9. [Tables and trees](#9-tables-and-trees)
   - [Trees: Tree](#trees-tree)
10. [Calendars of events](#10-calendars-of-events)
11. [Toasts](#11-toasts)
12. [Icons](#12-icons)
13. [Themes](#13-themes)
14. [Changing how a control looks](#14-changing-how-a-control-looks)
15. [Building your own components from controls](#15-building-your-own-components-from-controls)
16. [Accessibility and keyboard](#16-accessibility-and-keyboard)

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
- `<Fill name="nav">` is the sidebar. Leave it out for no sidebar. Its
  contents stay in view while the page scrolls, scrolling on their own
  when they're taller than the window; `sticky_nav="false"` lets them
  scroll away with the page. (On narrow screens, above the content, they
  scroll with the page.)
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

### Separating things: Divider

```xml
<ui.Divider />
<ui.Divider inset="true" spacing="none" />   <!-- between list rows with avatars -->
<ui.Divider label="or" />
<ui.Row align="center">
  <ui.Button variant="ghost" icon="bold" aria-label="Bold"></ui.Button>
  <ui.Divider vertical="true" />
  <ui.Button variant="ghost" icon="trash" aria-label="Delete"></ui.Button>
</ui.Row>
```

- A thin line in the theme's border colour. **`spacing`** is the room
  around it: `none`, `sm`, `md` (the default) or `lg`.
- **`inset`** indents it from the left so it lines up with text next to an
  avatar or icon: `"true"` for the usual indent, or a length (`"3.5rem"`).
- **`label`** puts text on the line ("or", "Today"); `align="start"` or
  `"end"` moves it to one side. A labelled divider is read as its text, a
  plain one as a separator.
- **`vertical="true"`** draws a vertical line as tall as the row, between
  items in a `Row` or a toolbar.

### Panels that open and close: Expansion and Accordion

**`Expansion`** is a panel whose content opens and closes under its header,
for details people only sometimes need:

```xml
<ui.Expansion title="Delivery" description="Address and speed" icon="send" @bind="delivery_open">
  <ui.TextField label="Street" @bind="street" />
  <Fill name="actions">
    <ui.Button variant="ghost" @click="delivery_open = False">Cancel</ui.Button>
    <ui.Button @click="save">Save</ui.Button>
  </Fill>
</ui.Expansion>
```

- `@bind` a bool to open and close it from code, or leave it unbound
  (`open="true"` starts it open). It emits `open` and `close` too.
- The header shows `title`, `description` and an optional `icon`;
  `<Fill name="header">` replaces them with your own. The arrow sits on the
  right; `toggle="before"` moves it left, `toggle="none"` hides it.
- `<Fill name="actions">` adds a row of buttons under the content.
- Closed content stays rendered, so what was typed in it survives, but it
  can't be reached with Tab or by screen readers. **`lazy="true"`** renders
  it only once the panel is first opened, for content that is slow to build.
- `disabled="true"` stops it opening; `level` sets the heading level of the
  header (3 by default).

**`Accordion`** stacks panels and keeps one open at a time:

```xml
<ui.Accordion :options="questions" @bind="question">
  <p>{{ answers[panel] }}</p>
</ui.Accordion>
```

- `options` take `Select`'s forms; a dict can add `description`, `icon`
  and `disabled`. The content between the tags is each panel's body, and
  `panel` inside it is that panel's value, like `Tabs`.
- `@bind` holds the open panel's value (`None` when all are closed).
  **`multiple="true"`** lets several stay open and binds a list. Unbound,
  it keeps its own state.
- `toggle`, `level`, `lazy` and `disabled` apply to every panel.
- **Keyboard:** Up and Down move between the headers (skipping disabled
  ones), Home and End jump to the first and last.

## 4. Forms

### The fields

All fields take a `label`, a `hint` (small grey text underneath), an `error`
(shown instead of the hint, in red), `required` (adds a red `*`), `disabled`
and `name` (the field's name inside a `<form>`), and all work with `@bind`.
`TextField`, `TextArea` and `NumberField` also take `readonly="true"`: the
text can be selected and copied but not changed (a link to share, say).

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
<ui.DatePicker label="Arrival" @bind="arrival" />
<ui.TextField label="Phone" mask="(999) 999-9999" @bind="phone" />
<ui.Autocomplete label="Country" :options="countries" @bind="country" />
```

What each one gives your field:

| Control | Your field gets |
|---|---|
| `TextField`, `TextArea` | a `str`. `TextField`'s `type` can be `text`, `email`, `password`, `search`, `url`, `tel`, `date`, `time`; dates and times arrive as text such as `"2026-10-29"` (for a real `date`, use `DatePicker`) |
| `NumberField` | an `int` while your field is an `int` (or `None`), otherwise a `float`. While the box is empty or holds something that isn't a number yet, your field keeps its last value |
| `Select`, `RadioGroup` | the chosen option's value |
| `Checkbox`, `Switch` | a `bool` |
| `DatePicker` | a `datetime.date`, or `None` until one is chosen |
| `Autocomplete` | the chosen option's value (with `free="true"`, the typed text) |
| `ButtonToggle` | the chosen value; with `multiple="true"`, a list |
| `Chips` | the chosen chip's value; with `multiple="true"`, a list |
| `ChipInput` | a list: the typed texts, or the chosen options' values |
| `Slider` | a number; with `range="true"`, a `(low, high)` tuple |

### Shaped input: mask

`TextField`'s `mask` shapes what's typed, keeping the cursor where the user
is typing: `9` is a digit, `a` a letter, `*` either, and anything else is
shown as it is.

```xml
<ui.TextField label="Phone" mask="(999) 999-9999" @bind="phone" />
<ui.TextField label="Card number" mask="9999 9999 9999 9999" @bind="card" />
<ui.TextField label="Plate" mask="aa-9999" placeholder="AB-1234" @bind="plate" />
```

Your field gets the shaped text, `"(555) 123-4567"`, and a starting value
such as `"5551234567"` is shown in the shape. Without a `placeholder` the
field shows the mask's shape, `(___) ___-____`, and a mask of digits only
brings up the number pad on phones. To check it's all there,
`rules.masked("(999) 999-9999")`; for just the digits,
`pyweft.masks.typed(mask, phone)`.

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

### Suggestions as you type: Autocomplete

A text field with a list of suggestions that narrows as the user types:

```xml
<ui.Autocomplete label="Country" :options="countries" @bind="country" />
```

It takes `options` like `Select` (text, `(value, label)` pairs, or dicts),
and your field gets the chosen option's **value**; the field shows its
label. The typed text is matched anywhere in a label (`match="starts"` for
the start only), the match is shown in bold, and up to `max_results` (8)
suggestions show. With `free="true"` your field gets whatever is typed,
so a suggestion is a shortcut rather than a must.

**Your own suggestions.** `<Fill name="option">` lays each one out; it gets
`option` (with `label`, `value`, and `data`, the dict you passed, so any
key of yours is there), `active` (the one Enter would pick) and `query`:

```xml
<ui.Autocomplete label="Assign to" :options="people" @bind="assignee">
  <Fill name="option">
    <span class="avatar">{{ option['data']['initials'] }}</span>
    <span>{{ option['label'] }} <small>{{ option['data']['email'] }}</small></span>
    <ui.Badge :kind="'primary' if active else 'neutral'">{{ option['data']['role'] }}</ui.Badge>
  </Fill>
  <Fill name="empty">Nobody matches "{{ query }}"</Fill>
</ui.Autocomplete>
```

```python
people = [
    {"value": "ada", "label": "Ada Lovelace", "email": "ada@engine.org", "initials": "AL", "role": "Owner"},
    {"value": "grace", "label": "Grace Hopper", "email": "grace@cobol.net", "initials": "GH", "role": "Admin"},
]
```

**Suggestions from a server.** `@search` gets the text on every keystroke;
fetch the matches into `options`, set `match="none"` so they're shown as
they come, and `loading` while you wait ("Searching…"):

```xml
<ui.Autocomplete label="City" :options="cities" match="none" :loading="searching"
                 @search="find_cities(event)" @bind="city" />
```

```python
from pyweft import http

cities: list = []
searching: bool = False
_searches: int = 0

async def find_cities(self, query):
    self._searches += 1
    mine = self._searches
    self.searching = True
    found = await http.get_json("https://api.example.com/cities", params={"q": query})
    if mine == self._searches:     # typing on started a newer search: drop this one
        self.cities = [(c["id"], c["name"]) for c in found]
        self.searching = False
```

- **Keyboard:** Down and Up move through the suggestions (Down also opens
  them), Enter picks, Esc closes them and, pressed again, puts back the
  chosen option's label. Leaving the field closes them too. While the list
  is closed, Enter emits `enter`, for submitting.
- **Also:** `@select` gets the whole option you passed (the dict, not just
  its value); `min_chars` waits for that many characters; `placeholder`,
  `hint`, `error`, `required`, `disabled` and `@blur` work as on the other
  fields, so `Form` checks it like any other.

### A row of choices: ButtonToggle

A button toggle is a joined row of buttons for a small, fixed set of
choices: a view switch, text styles, alignment.

```xml
<ui.ButtonToggle label="Range" options="Day, Week, Month" @bind="view" />

<ui.ButtonToggle aria_label="Text style" multiple="true" @bind="styles" :options="[
    {'value': 'bold', 'label': 'Bold', 'icon': 'bold', 'icon_only': True},
    {'value': 'italic', 'label': 'Italic', 'icon': 'italic', 'icon_only': True},
]" />

<ui.ButtonToggle label="Plan" options="Monthly, Yearly" full_width="true" @bind="plan" />
```

- One choice binds the chosen value; **`multiple="true"`** binds a list,
  in the options' order. Clicking the chosen button again keeps it chosen,
  unless `allow_none="true"`.
- `options` take `Select`'s forms; a dict can add `icon`, **`icon_only`**
  (just the icon: the label becomes its name for screen readers and its
  tooltip) and `disabled`. A chosen button shows a check mark;
  `check="false"` hides it.
- `size` is `sm`, `md` or `lg`; **`full_width="true"`** stretches the
  buttons evenly across the row; `orientation="vertical"` stacks them.
- `label`, `hint`, `error`, `required`, `disabled` and `name` work as on
  the other fields. Without a `label`, name the group with `aria_label`.
- **Keyboard:** the row is one Tab stop and the arrow keys move along it.
  With one choice it is a radio group, so moving chooses; with
  `multiple`, Space or Enter toggles the button with focus.

Compared with `Chips`, which also choose one or several: chips are
separate pills that wrap onto more lines and can be removed, for longer or
changing lists; a button toggle is one compact bar for a few fixed choices.

### Chips: Chips and ChipInput

**`Chips`** is a row of chips to choose from, a compact alternative to radio
buttons and checkboxes:

```xml
<ui.Chips label="Size" options="Small, Medium, Large" @bind="size" />
<ui.Chips label="Interests" :options="interests" multiple="true" @bind="chosen" />
<ui.Chips label="Filters" :options="filters" removable="true" selectable="false"
          @remove="drop_filter(event)" />
```

- One choice binds the chosen value (click it again to un-choose, unless
  `required="true"`); `multiple="true"` binds a list, in the options' order.
- `options` take `Select`'s forms; a dict can add `icon` and `disabled`. A
  chosen chip shows a check mark.
- **`removable="true"`** adds an × that emits `remove` with the chip's value:
  remove it from `options` yourself. With `selectable="false"` the chips are
  only labels, like a list of applied filters.
- `<Fill name="option">` lays out a chip's text (it gets `option` and
  `selected`).
- **Keyboard:** the row is one Tab stop; Left and Right move, Home and End
  jump, Space or Enter chooses, Delete or Backspace removes.

**`ChipInput`** turns what's typed into chips, for tags, recipients or
keywords. It binds a list:

```xml
<ui.ChipInput label="Tags" @bind="tags" />
<ui.ChipInput label="Invite" :options="people" free="false" @bind="invitees">
  <Fill name="chip">{{ chip['data']['initials'] }} {{ chip['label'] }}</Fill>
</ui.ChipInput>
```

- **Enter or a comma** adds what's typed (`separators=",;"` for more), and a
  pasted `"a, b, c"` adds three. **×** removes a chip, and so does
  **Backspace** in the empty box. Leaving the field adds what's left in it
  (`add_on_blur="false"` to drop it instead).
- **With `options`** it suggests as you type, leaving out the ones already
  added; the list holds the options' values, and text typed in full ("grace
  hopper") counts as that option. `free="false"` allows only the options.
- Duplicates are skipped (ignoring case for text); **`max`** limits how many
  chips. `<Fill name="chip">` lays out a chip (it gets `chip`: `label`,
  `value`, `data`), `<Fill name="option">` a suggestion, as in
  `Autocomplete`. It emits `add` and `remove` with the value, and works
  with `Form`: `rules.required()` asks for at least one, `rules.min_length(2)`
  for two.

### Sliders

**`Slider`** picks a number by dragging a thumb along a track, or with
`range="true"` a pair of numbers with two thumbs:

```xml
<ui.Slider label="Volume" @bind="volume" format="{}%" />
<ui.Slider label="Price" :min="0" :max="500" :step="10" range="true"
           @bind="price" format="${}" value_label="side" />
<ui.Slider label="Rating" :min="1" :max="5" ticks="true" marks="1, 3, 5" @bind="rating" />
```

- `min` (0), `max` (100) and `step` (1) set the scale. The value is an
  `int` while all three are whole numbers, else a `float`, and always lands
  on a step. A range binds a `(low, high)` tuple; with no value it spans
  the whole scale.
- The thumbs of a range can pass each other: the value is always the two
  positions in order.
- **`value_label`** shows the value: `drag` (default) in a bubble above the
  thumb while it's dragged, hovered or focused, `always`, `side` (next to the
  label) or `none`. **`format`** shapes it (`"{}%"`, `"${}"`,
  `"{:.2f}"`), and screen readers hear the same text.
- **`ticks="true"`** draws a dot at every step (up to 100 steps);
  **`marks`** labels points under the track: `"0, 50, 100"`, or
  `(value, label)` pairs.
- The bound field follows the thumb as it moves; **`lazy="true"`** updates it
  only when the thumb is let go. It emits `change` on release and `blur`.
- **Keyboard:** arrows move one step, Page Up and Page Down move further,
  Home and End jump to the ends.
- `label`, `hint`, `error`, `disabled` and `name` work as on the other
  fields (a range sends `name_min` and `name_max`), so it works with `Form`.

### Checkbox and Switch labels with links

Put the label between the tags when it needs more than text:

```xml
<ui.Checkbox @bind="agreed">I agree to the <a href="/terms">terms</a></ui.Checkbox>
```

### Dates: DatePicker

A field that opens a calendar, and gives your field a `datetime.date`:

```xml
<ui.DatePicker label="Check-in" @bind="check_in" :min="today" />
<ui.DatePicker label="Check-out" @bind="check_out" :min="check_in or today" required="true" />
<ui.DatePicker label="Birthday" @bind="birthday" max="2010-12-31" format="%d/%m/%Y" week_start="sunday" />
```

```python
import datetime

check_in = None           # a datetime.date once chosen
check_out = None

@property
def today(self):
    return datetime.date.today()
```

- **`min` and `max`** take a `date` or text such as `"2026-12-31"`. Days
  outside them are crossed out and can't be chosen, and the month arrows
  stop at them.
- **The field shows** the date as "3 Nov 2026", or `placeholder` ("Choose
  a date") before one is chosen; `format` takes a `strftime` pattern
  instead.
- **`week_start="sunday"`** starts the weeks on Sunday (Monday by default).
- **Today and Clear** buttons sit under the calendar. `required="true"`
  hides Clear, so a chosen date can only be changed, not removed.
- **`name`** sends the date as `YYYY-MM-DD` inside a `<form>`.
- **With a form**, it works like any field:
  `:error="form.error('check_in')" @blur="form.touch('check_in')"`. It emits
  `blur` when the calendar closes.
- **Jumping to another month or year:** click the month's name in the
  calendar's header to choose from the year's months, or the year to choose
  from twelve years at a time (the arrows then move a year, or twelve).
  Choosing a year shows its months, and choosing a month shows its days.
  Months and years outside `min` and `max` are crossed out.
- **Keyboard:** Enter, Space or the down arrow opens the calendar on the
  chosen day (or today). The arrows move by day and week, Page Up and Page
  Down by month, Home and End to the ends of the week, Enter picks, and Esc
  closes it. In the months and years, the arrows move between them, and Esc
  goes back a step.

### Date ranges: DateRangePicker

For a stay, a booking or a report period: two months side by side, the
first day clicked and then the last, with the range shown as a band while
the pointer (or the keyboard) moves.

```xml
<ui.DateRangePicker label="Stay" @bind="stay" :min="today" min_days="1" max_days="28" />
```

```python
stay = None               # (start, end) once both are chosen

def nights(self):
    return (self.stay[1] - self.stay[0]).days if self.stay else 0
```

- **Your field gets a `(start, end)` pair** of `datetime.date`s, start
  first whichever was clicked first, or `None` until both are chosen.
  Nothing changes until the last day is clicked.
- **`min_days` and `max_days`** limit the length, counted from the first
  day to the last (Saturday to Sunday is 1): once the first day is chosen,
  days that would make it too short or too long are crossed out.
- **The field shows** "3 – 10 Nov 2026" (or "28 Dec 2026 – 3 Jan 2027"), and
  the calendar's footer the number of days. `months="1"` shows one month;
  on a narrow screen two months stack.
- **Esc** while choosing drops the first day; again, it closes. `name`
  sends `<name>_start` and `<name>_end` in a `<form>`. The rest (`min`,
  `max`, `format`, `week_start`, `align`, `required`, `error`, `@blur`)
  work as for `DatePicker`.

### A calendar on the page: Calendar

`DatePicker` and `DateRangePicker` open a `Calendar`; it can also sit on the
page itself, always open:

```xml
<ui.Calendar @bind="day" :min="today" />
<ui.Calendar range="true" months="2" @bind="period" />
```

It takes the same `min`, `max`, `week_start`, `min_days` and `max_days`,
binds a `date` (or with `range="true"` a `(start, end)` pair), and has the
same keyboard and the month and year views.

### A complete form: validation and submitting

`Form` checks a component's fields against rules and says what needs
fixing, next to each field. This sign-up form shows nothing until a field
is left or the form is submitted; from then on each message follows what
the user types, so it disappears the moment the value is right.

```xml
<template>
  <ui.Theme>
    <ui.Card title="Create your account">
      <form novalidate="" @submit.prevent="submit">
        <ui.Column>
          <ui.TextField ref="email" label="Email" type="email" required="true" autocomplete="email"
                        @bind="email" :error="form.error('email')" @blur="form.touch('email')" />
          <ui.TextField ref="password" label="Password" type="password" required="true"
                        hint="At least 8 characters" @bind="password"
                        :error="form.error('password')" @blur="form.touch('password')" />
          <ui.Select ref="country" label="Country" placeholder="Choose your country"
                     options="India, Netherlands, United States" @bind="country"
                     :error="form.error('country')" @blur="form.touch('country')" />
          <ui.Checkbox ref="agreed" @bind="agreed" :error="form.error('agreed')">I agree to the terms</ui.Checkbox>

          <If cond="done">
            <ui.Alert kind="success" title="Welcome!">Your account for {{ email }} is ready.</ui.Alert>
          </If>

          <ui.Button type="submit" variant="primary" block="true" :loading="saving">Create account</ui.Button>
        </ui.Column>
      </form>
    </ui.Card>
  </ui.Theme>
</template>

<code>
import asyncio
from pyweft_ui import Form, rules, ui

email: str = ""
password: str = ""
country = None
agreed: bool = False
saving: bool = False
done: bool = False

form = Form(
    email=[rules.required("Enter your email"), rules.email()],
    password=[rules.required("Choose a password"), rules.min_length(8)],
    country=rules.required("Choose a country"),
    agreed=rules.accepted("Agree to the terms to continue"),
)

async def submit(self):
    if not self.form.check():   # shows every message, focuses the first field to fix
        return
    self.saving = True
    await asyncio.sleep(1)      # send it to your server here
    self.saving = False
    self.done = True
</code>
```

How it fits together:

- **`form = Form(field=rules, ...)`** names each field of the component and
  the rules it must pass: one rule, or a list checked in order (the first
  that fails gives the message).
- **`:error="form.error('email')"`** shows the field's message, or nothing
  while there's nothing to say. **`@blur="form.touch('email')"`** says the
  user has left the field, which is when its message starts to show.
  `TextField`, `TextArea`, `NumberField` and `Select` report leaving;
  every field, `Checkbox`, `Switch` and `RadioGroup` included, shows an
  `error`.
- **`self.form.check()`** is for submitting: it shows every message,
  moves the cursor to the first field to fix (the one whose `ref` has the
  same name) and returns `True` only when every field passes.
- **`<form @submit.prevent="submit">`** runs `submit` when the user clicks
  the `type="submit"` button *or presses Enter in a field*, and `.prevent`
  stops the browser from reloading the page. **`novalidate=""`** turns off
  the browser's own pop-up checks, so your messages are the only ones.
- **`:loading="saving"`** shows a spinner on the button and makes it
  unclickable while the `async` handler waits, so nobody submits twice.

### Rules

```python
from pyweft_ui import rules
```

| Rule | Passes when |
|---|---|
| `required(message)` | there is a value: not `None`, blank text or an empty list |
| `accepted(message)` | a `Checkbox` or `Switch` is on |
| `email(message)`, `url(message)` | the text looks like an email address, or an `http(s)://` address |
| `min_length(n)`, `max_length(n)` | the text has at least / at most `n` characters (a list, `n` items) |
| `min_value(n)`, `max_value(n)` | the number is at least / at most `n` |
| `pattern(regex, message)` | the whole text matches `regex` |
| `one_of(choices)` | the value is one of `choices` |
| `same_as("field", message)` | the value equals another field's, as when a password is typed twice |
| `masked(mask, message)` | the text fills every slot of an input `mask` |
| `check(test, message)` | `test(value)` is true: `check(lambda v: v != "admin", "That name is taken")` |

Every rule takes the message to show, and has a sensible one if you leave
it out. Only `required` and `accepted` complain about an empty field; the
others let it through, so put `required()` first when a field must be
filled in.

**Your own rule** is any function of the value that returns a message, or
`None` when the value is fine. Give it a second parameter to read the
other fields:

```python
def no_spaces(value):
    return "Leave out the spaces" if " " in value else None

def not_before_start(value, form):
    if value and form.value("start") and value < form.value("start"):
        return "The end can't be before the start"

form = Form(
    username=[rules.required(), no_spaces],
    end=not_before_start,
)
```

### What the form can tell you

| Call | Gives |
|---|---|
| `form.error("email")` | the message to show under the field: `""` until it's left or submitted, and while it passes |
| `form.touch("email")` | (nothing) the field was left: show its message from now on |
| `form.check()` | shows every message, focuses the first field to fix (`focus=False` skips that), returns whether all pass |
| `form.valid` | whether every field passes right now, messages showing or not, for `:disabled="not form.valid"` |
| `form.errors` | `{field: message}` for every message showing |
| `form.problem("email")` | the field's message whether it's showing or not |
| `form.reset()` | hides every message again: after saving, when the fields start over empty |

Rules are checked again on every update, against the fields' current
values, so there is nothing to keep in step. A name in `Form` must be a
field of the component; a `ref` of the same name is optional, and is what
`check()` focuses.

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

### A menu of actions: Menu

A button that opens a list of actions, and tells you which was chosen:

```xml
<ui.Menu label="Actions" @select="act(event)" :items="[
    {'value': 'edit', 'label': 'Edit', 'icon': 'edit'},
    {'value': 'copy', 'label': 'Duplicate', 'icon': 'copy'},
    {'value': 'archive', 'label': 'Archive', 'disabled': True},
    '-',
    {'value': 'delete', 'label': 'Delete', 'icon': 'trash', 'danger': True},
]" />

<ui.Menu label="More actions" icon="more" icon_only="true" variant="ghost" align="end"
         :items="['Rename', 'Move']" @select="act(event)" />
```

```python
def act(self, action):
    if action == "delete":
        self.confirming = True      # ask first, with a Dialog
    ...
```

- **`items`** are text (`"Rename"`, which is also its value), `(value,
  label)` pairs, or dicts with `value` and `label` and optionally `icon`,
  `danger` (red) and `disabled`. `"-"` draws a divider.
- **`@select`** gets the chosen item's value as `event`.
- **The button** takes `label`, `icon`, `variant` (`primary`, `secondary`,
  `ghost`) and `disabled`. With `icon_only="true"` it shows just the icon,
  and `label` becomes its name for screen readers. `align="end"` lines the
  list up with the button's right edge, for a button at the end of a row.
- **Keyboard:** Enter, Space or the down arrow opens it on the first item,
  the up arrow on the last. The arrows, Home and End move (skipping
  disabled items), Enter picks, Esc closes it and returns to the button,
  and Tab closes it and moves on. A click anywhere else closes it too.

#### Submenus, headings and richer items

```xml
<ui.Menu label="File" @select="act(event)" :items="[
    {'heading': 'Document'},
    {'value': 'new', 'label': 'New', 'icon': 'plus', 'hint': 'Ctrl+N'},
    {'label': 'Share', 'icon': 'send', 'items': [
        'Email',
        {'label': 'Export as', 'items': ['PDF', 'Word']},
    ]},
    '-',
    {'value': 'trash', 'label': 'Move to trash', 'danger': True,
     'description': 'Kept for 30 days'},
]" />
```

- An item with **`items`** opens a submenu beside it, as deep as you like.
  It opens on hover, on a click, or with the right arrow; the left arrow
  goes back. `@select` gets the value chosen at any depth.
- **`hint`** shows text at the right of an item (a keyboard shortcut),
  **`description`** a second line under its label, and
  `{"heading": "..."}` a small heading over a group of items.
- **`position="above"`** opens the list above the button, for a button at
  the bottom of the page. Submenus open to the right, or to the left with
  `align="end"`, and switch sides when there's no room.

#### Your own trigger and items

```xml
<ui.Menu label="Account" align="end" :items="account" @select="act(event)">
  <Fill name="trigger"><img class="avatar" src="assets/me.png" alt="" /></Fill>
  <Fill name="item">
    <b>{{ item['label'] }}</b>
    <If cond="item['data'].get('email')"><small>{{ item['data']['email'] }}</small></If>
  </Fill>
</ui.Menu>
```

- **`<Fill name="trigger">`** replaces the button's look with your own
  content: an avatar, a picture, some text. It is still the menu's button
  (focusable, opened with the keyboard, `label` as its name), so put
  content in it, not another button.
- **`<Fill name="item">`** lays out every item, submenus included. It gets
  `item`, with `label`, `value`, `icon`, `description`, `hint`, `items` and
  `data` (the item as you wrote it, for your own keys).

### Right-click menus: ContextMenu

```xml
<ui.ContextMenu :items="['Cut', 'Copy', 'Paste', '-', {'label': 'Sort by', 'items': ['Name', 'Date']}]"
                @select="act(event)">
  <div class="files">...</div>
</ui.ContextMenu>
```

- Right-clicking inside the content (a long press on most touch screens)
  opens the menu at the pointer instead of the browser's own. From the
  keyboard, the Menu key or Shift+F10 opens it while focus is inside.
- `items`, submenus and `<Fill name="item">` work as on `Menu`; `@select`
  gets the value and `@open` fires as it opens, for remembering what was
  right-clicked. Esc or choosing an item gives focus back to where it was.
- It stays inside the window, near the bottom or right edge too.
  `disabled="true"` leaves the browser's own menu alone.

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

### How far along: Progress

```xml
<ui.Progress label="Uploading" :value="sent" :max="total" format="{} of {} files" show_value="true" />
<ui.Progress label="Waiting for the server" />
<ui.Progress shape="circle" :value="72" kind="warning" size="lg" />
```

- **`value`** out of **`max`** (`100` by default; `0.4` with `max="1"`
  works too) fills the bar, sliding as the value changes. **Without a
  value** it is indeterminate: a bar moving back and forth, or a turning
  ring, for work whose length you don't know.
- `show_value="true"` puts the value beside the label, as a percentage;
  **`format`** shapes it from the value instead (`"{} of 12 files"`,
  `"{:.1f} MB"`). Screen readers hear that same text.
- **`buffer`** draws a lighter fill ahead of the value (buffered video).
- `kind` is `primary`, `success`, `warning` or `danger`; `size` is `sm`,
  `md` or `lg` (a bar's thickness, a ring's diameter); `striped="true"`
  adds moving stripes.
- **`shape="circle"`** draws a ring with the value in the middle (not at
  `size="sm"`), with `label` beside it.
- Without a `label`, name it for screen readers with `aria_label`.

To show progress from an `async` handler, change the value and call
`self.state_has_changed()` after each step, so the page updates before
the handler ends:

```python
async def upload(self):
    for self.sent in range(1, self.total + 1):
        await send_file(self.sent)
        self.state_has_changed()
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

### Sheets from the bottom: BottomSheet

A bottom sheet slides up from the bottom of the window, over a dimmed
page. It suits phones, where it sits under the thumb: a list of actions,
or a few settings such as filters.

```xml
<ui.Button @click="sharing = True">Share</ui.Button>
<ui.BottomSheet title="Share" @bind="sharing" @select="share(event)" :items="[
    {'value': 'link', 'label': 'Copy link', 'icon': 'copy'},
    {'value': 'email', 'label': 'Email', 'icon': 'send', 'description': 'Opens your mail app'},
]" />

<ui.BottomSheet title="Filters" @bind="filtering">
  <ui.Chips label="Status" options="Open, Done" multiple="true" @bind="status" />
  <Fill name="actions">
    <ui.Button variant="primary" @click="filtering = False">Show results</ui.Button>
  </Fill>
</ui.BottomSheet>
```

- **`@bind`** a bool, as with `Dialog`: open while it is `True`.
- **`items`** (the forms `Menu` takes; dicts may add `icon`,
  `description`, `danger`, `disabled`) make it a list of actions: choosing
  one emits `select` with its value and closes the sheet. Anything else
  goes between the tags, and `<Fill name="actions">` is a row of buttons
  pinned to its bottom.
- **Closing:** Esc, a tap on the dimmed page, or a swipe down on the top of
  the sheet (drag the handle down and let go). `dismissible="false"`
  leaves only your own buttons. `@close` says how it closed: `"esc"`,
  `"backdrop"`, `"swipe"` or `"select"`; setting the bound field yourself
  emits nothing.
- It is full width on a phone and centred on wider screens, at most
  `max_width` wide (`40rem`). Tall content scrolls inside it (it takes up
  to 85% of the window's height). Without a `title`, name it for screen
  readers with `aria_label`.
- Once opened, it stays on the page while closed (hidden and out of reach)
  so it can slide away; what was typed in it is kept until you clear it.

### Small panels beside a button: Popover

A popover is a button that opens a small panel of your own content beside
it: a share link, a quick setting, a short explanation, a preview.

```xml
<ui.Popover label="Share" icon="send" title="Share this page" @bind="sharing">
  <ui.TextField label="Link" :value="link" readonly="true" />
  <ui.Button variant="primary" @click="copy">Copy link</ui.Button>
</ui.Popover>

<ui.Popover open_on="hover" variant="link" label="Ada Lovelace">
  <Fill name="trigger">@ada</Fill>
  Ada Lovelace · Owner · 12 projects
</ui.Popover>
```

- **The button** takes `label`, `icon`, `icon_only`, `variant`
  (`primary`, `secondary`, `ghost` or `link`) and `caret`, like `Menu`'s.
  `<Fill name="trigger">` puts your own content in it, such as an avatar
  or a name; the popover's own button wraps it, so don't put another
  button there (`label` then names it for screen readers).
- **Click mode** (the default): `@bind` a bool to open and close it from
  code, or leave it unbound. A click outside or Esc closes it, and Esc
  gives focus back to the button. As it opens, focus moves to its first
  control. It emits `open` and `close`.
- **`open_on="hover"`** makes a preview card that shows after a short
  delay on hover or keyboard focus, and stays while the pointer is on the
  card, so links in it can be clicked. Esc hides it. It is shown by CSS
  alone, so `@bind` and the events don't apply.
- **Placement:** `position` is `below` (the default), `above`, `start` or
  `end`; `align` lines it up with the button's `start`, `center` or
  `end`. A small arrow points at the button (`arrow="false"` hides it).
  `width` defaults to `20rem` and never exceeds the window; `title` adds
  a heading.

### Labels on hover: Tooltip

```xml
<ui.Tooltip text="Bold (Ctrl+B)">
  <ui.Button variant="ghost" icon="bold" aria-label="Bold"></ui.Button>
</ui.Tooltip>

<ui.Tooltip text="Delete forever: there is no undo" tip_id="delete-tip">
  <ui.Button icon="trash" aria-label="Delete" aria-describedby="delete-tip"></ui.Button>
</ui.Tooltip>
```

- A short text label over whatever it wraps, shown on hover (after a
  short delay) and at once on keyboard focus. Esc hides it until the
  pointer or focus moves away. `position`: `above` (the default),
  `below`, `start`, `end`.
- It is shown by CSS, with no wait for Python. Text only: anything
  clickable belongs in a `Popover`.
- An icon-only button still needs its own `aria-label`; the tooltip is
  for sighted users. For screen readers to also read the tooltip as a
  description, give the tooltip a `tip_id` and the control
  `aria-describedby` with the same id.

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

### A task in steps: Stepper

A stepper splits a long task (a checkout, a sign-up) into steps shown one
at a time, with a numbered header and Back / Next under each step:

```xml
<ui.Stepper label="Checkout" :steps="steps" @bind="step" linear="true"
            @next="check(event)" @finish="place_order" finish_label="Place order">
  <If cond="step == 'account'"> ... </If>
  <ElseIf cond="step == 'delivery'"> ... </ElseIf>
  <ElseIf cond="step == 'gift'"> ... </ElseIf>
  <Else> ... a summary ... </Else>
</ui.Stepper>
```

```python
steps = [("account", "Account"), ("delivery", "Delivery"),
         {"value": "gift", "label": "Gift message", "optional": True},
         ("review", "Review")]

account = Form(email=[rules.required(), rules.email()])
delivery = Form(street=rules.required(), city=rules.required())

def check(self, step):          # False keeps the stepper on this step
    form = {"account": self.account, "delivery": self.delivery}.get(step)
    return form.check() if form is not None else True
```

- **`steps`** take `Select`'s forms; a dict can add `description` (a line
  under the label), `optional`, `error` (a message: the step turns red),
  `done` and `disabled`. The content between the tags is the current
  step's body; `step` (its value) and `index` are available in it.
- **`@next`** runs when Next is pressed, before moving on; if it returns
  `False` the stepper stays. With a `Form` per step, `form.check()` shows
  that step's messages and focuses the first field to fix. On the last
  step the button says **Finish** (`finish_label`) and emits `finish`.
- A step left with Next counts as done and shows a check mark (a step's
  `done` key overrides that). With **`linear="true"`** a step can't be
  opened from its header until the steps before it are done; optional
  ones don't hold it up. Without it, any header opens its step.
- **`orientation="vertical"`** puts each step's content under its header,
  which suits narrow pages; **`label_position="bottom"`** puts the labels
  under the numbers. On a narrow screen the header row scrolls sideways.
- `<Fill name="actions">` replaces the Back / Next row. It gets `step`,
  `index`, `first`, `last`, and `go_next()` / `go_back()` to call:

  ```xml
  <Fill name="actions">
    <ui.Button variant="ghost" @click="go_back()">Previous</ui.Button>
    <ui.Button variant="primary" @click="go_next()">{{ 'Pay now' if last else 'Continue' }}</ui.Button>
  </Fill>
  ```

- `back_label`, `next_label`, `finish_label` and `optional_label` change
  the words.

## 9. Tables and trees

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

### Trees: Tree

A tree shows nested items that open and close: folders and files,
categories, an org chart, permissions.

```xml
<ui.TextField label="Files" placeholder="Search" @bind="query" />
<ui.Tree label="Files" :nodes="files" @bind="selected" :filter="query"
         :expanded="['src']" @load="load_folder(event)" @activate="open_file(event)" />
```

```python
files = [
    {"value": "src", "label": "src", "icon": "folder", "children": [
        {"value": "app", "label": "app.weft", "icon": "file"},
    ]},
    {"value": "docs", "label": "docs", "icon": "folder", "children": None},  # loads on open
]

async def load_folder(self, value):
    children = await fetch_folder(value)      # your own code
    for node in self.files:
        if node["value"] == value:
            node["children"] = children
```

- **`nodes`** are dicts with `value` and `label` and optionally `icon`,
  `children`, `disabled` and keys of your own (`node['data']` in a fill);
  text and `(value, label)` or `(value, label, children)` tuples work too.
  Values must be unique across the tree. A `folder` icon shows as
  `folder-open` while its node is open.
- **Opening:** the arrow opens and closes a node; `expanded` lists the
  values open at the start and `expand_all="true"` opens everything.
  `@toggle` gets `{"value": ..., "open": True/False}`.
- **Choosing:** a click (or Space) selects a node and `@bind` gets its
  value; Enter or a double-click on a leaf emits **`activate`** (on a
  parent, they open or close it).
- **Loading on demand:** `"children": None` means "has children, not
  loaded yet". The first time such a node opens, the tree emits **`load`**
  with its value and shows a spinner until you put its children in. An
  `async` handler is fine.
- **`filter`** shows only the nodes whose label contains the text, with
  the parents leading to them opened and the match marked. Nodes not
  loaded yet aren't searched.
- `<Fill name="node">` lays out a node (it gets `node`, `level`,
  `expanded` and `selected`); `lines="true"` draws guide lines;
  `empty` and `no_matches` change the text shown when there's nothing.

#### Checkboxes

```xml
<ui.Tree :nodes="permissions" checkable="true" expand_all="true" @bind="granted" />
```

With `checkable="true"` every node has a checkbox and `@bind` is the list
of checked **leaves**. Checking a parent checks everything under it (and
unchecks it all when it was all checked); a parent with only some of its
leaves checked shows a dash. Disabled nodes keep their state. Values in
the list that aren't in the tree (yet) are kept.

**Keyboard:** the tree is one Tab stop. Up and Down move, Right opens a
node or moves to its first child, Left closes it or moves to its parent,
Home and End jump to the ends, `*` opens all the siblings, and typing a
letter jumps to the next node starting with it.

## 10. Calendars of events

`EventCalendar` shows events in a month, a week, or a list by day, the way
a team or booking calendar does:

```xml
<ui.EventCalendar :events="events" @select="open(event)" @day="add(event)" />
```

```python
import datetime

events = [
    {"title": "Standup", "start": datetime.datetime(2026, 11, 3, 9, 30),
     "end": datetime.datetime(2026, 11, 3, 9, 45), "color": "blue"},
    {"title": "Release", "start": datetime.date(2026, 11, 7), "color": "red"},
    {"title": "Trip", "start": datetime.date(2026, 11, 11), "end": datetime.date(2026, 11, 13)},
]

def open(self, event):
    self.editing = event          # the very dict (or object) you passed in

def add(self, when):
    self.events = self.events + [{"title": "New event", "start": when}]
```

- **Events** are dicts or objects with `title` and `start`, and optionally
  `end`, `color` and `id`. A `date` start (or text like `"2026-11-07"`)
  is **all day**, and `end` is then the last day; a `datetime` start (or
  `"2026-11-03T09:30"`) is **timed**, and `end` defaults to an hour later.
  `color` is `blue`, `green`, `amber`, `red`, `purple`, `teal`, `pink`,
  `gray`, or any CSS colour.
- **Month view:** all-day and multi-day events are bars across their days,
  continuing into the next week; timed ones show their time. A day with
  more than `max_per_day` (3) rows shows "+2 more", which opens up the
  week. `months="3"` shows three months, one under another.
- **Week view:** the hours from `day_start` to `day_end` (8 to 20), with
  timed events placed by their times and side by side where they overlap;
  all-day events in a row above.
- **Agenda:** the events by day, a good choice on phones.
- **`@select`** gets the event you passed in. **`@day`** gets the date of
  an empty day, or in the week view the `datetime` of the hour, so you can
  add one there; days are only clickable when you listen to `@day`.
- **`@navigate`** gets the `(first, last)` dates now showing, whenever the
  user moves or switches view: load just those events from your server
  with `pyweft.http`.
- **Settings:** `view` (`month`, `week`, `agenda`), `date` (where it starts;
  today), `week_start`, `time_format` (`"%I:%M %p"` for 9:30 AM),
  `switcher="false"` to hide the view buttons, and `label` to name it for
  screen readers. Every event is a button that reads out its title, day
  and time.

## 11. Toasts

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
  `bottom-left`, `bottom-center`, `top-left`, `top-center`, `top-right`),
  `limit` (at most 5 at once by default; older ones wait their turn),
  `dismissible` (the × on each toast) and `look` (see below).
- Toasts raised before the Toaster is on the page appear once it is.

### As a snackbar

```xml
<ui.Toaster look="snackbar" />
```

`look="snackbar"` shows the same `toast()` messages as a compact dark bar
at the bottom centre: one at a time, a new message replacing the one
showing, with no icon, the action as a text button, and no × (a message
with `duration=None` still gets one, or it could never be closed).
`position`, `limit` and `dismissible` change those defaults. The rest is
unchanged, so switching an app between the two looks is one attribute.

## 12. Icons

```xml
<ui.Icon name="star" />
<ui.Icon name="heart" size="2em" />
```

Icons take the text colour around them and are `1em` by default, so they
match the text size. Buttons and alerts use them for you (`icon="send"`).

Available names: `check`, `x`, `plus`, `minus`, `search`, `info`, `alert`,
`chevron-up`, `chevron-down`, `chevron-left`, `chevron-right`, `menu`,
`trash`, `edit`, `send`, `user`, `home`, `star`, `heart`, `download`,
`upload`, `external`, `copy`, `settings`, `sun`, `moon`, `calendar`,
`more`, `bold`, `italic`, `underline`, `align-left`, `align-center`,
`align-right`, `list`, `grid`, `folder`, `folder-open`, `file`.

## 13. Themes

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

## 14. Changing how a control looks

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

## 15. Building your own components from controls

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

## 16. Accessibility and keyboard

The controls are built on standard HTML elements, so keyboards, screen
readers and mobile devices work the way people expect:

- **Fields are labelled:** every field's `label` is connected to its input,
  so clicking the label focuses the field and screen readers announce it.
  `error` marks the field as invalid for screen readers as well as in red.
- **Everything is reachable with Tab**, shows a visible focus ring, and
  works with Space and Enter. Radio buttons move with the arrow keys.
- **Alerts are announced:** `warning` and `danger` alerts interrupt, `info`
  and `success` wait politely.
- **Popovers** say they open a dialog and whether it is open; focus moves
  into one as it opens and Esc brings it back. **Tooltips** appear on
  keyboard focus as well as hover, and Esc hides them.
- **Bottom sheets** behave like dialogs for the keyboard and screen
  readers: focus moves in, Tab stays inside, Esc closes, and focus goes
  back to where it was.
- **Dialogs** are announced as dialogs, move focus into themselves when they
  open (so Esc closes them straight away), keep Tab and Shift+Tab inside
  while open, close with Esc, and give focus back to whatever had it
  before, such as the button that opened them.
- **Tabs** are announced as tabs, with the chosen one marked, and their
  content as the chosen tab's panel. The tab row is one Tab stop: the arrow
  keys move between tabs, and Home and End jump to the first and last.
- **Expansion panels** have a real button in a heading, saying whether
  it's open; closed content is out of reach. In an `Accordion`, Up and
  Down move between the headers.
- **Steppers** read each header as "Step 2 of 4: Delivery", with done,
  optional and error states; the headers are one Tab stop moved with the
  arrow keys, and Next or Back moves focus to the new step's content.
- **Trees** read each node's level, its place among its siblings, and
  whether it is open, selected or checked (or partly checked); a folder
  that is loading says it is busy.
- **Tables** use real table headings, and tell screen readers which column
  is sorted and which way.
- **Menus** are announced as menus, with the button saying whether it's
  open, and items with a submenu saying so too. Focus moves into the list
  when it opens, into a submenu with the right arrow and back with the
  left, and back to the button when an item is chosen or Esc is pressed.
  A right-click menu gives focus back to where it was.
- **The date pickers'** calendar is a grid of days, each read out in full
  ("Tuesday 3 November 2026"), with today and the chosen days marked. It is
  one Tab stop, moved with the arrow keys.
- **Menus and calendars stay on screen:** opened next to something near
  the window's edge, they shift sideways to fit.
- **Progress bars and rings** are announced as progress bars with their
  value and its text ("4 of 12 files"); one without a value says it is
  busy.
- **Toasts and snackbars** are read out politely when they appear (`danger` ones
  interrupt), and pause while someone is reading them.
- **Motion is reduced** for visitors who ask their system for it: spinners
  slow down, and dialogs and toasts appear without animating.

What you should add yourself:

- A text alternative for buttons with only an icon:
  `aria-label="Close"`.
- An `aria-label` on fields with no visible `label`, like the colour-mode
  `Select` in section 13, and a `label` on `Tabs`.
- Don't put the only copy of something important in a toast: it goes away.
  Show errors that need fixing next to what needs fixing.
- After a failed submit, move focus to the first field with a problem, so
  keyboard and screen reader users land on it. `form.check()` does this
  for you when each field has a `ref` named like the field (see [the
  form](#a-complete-form-validation-and-submitting)); without a `Form`,
  give the control a `ref` and call `focus()` (see [moving
  focus](../../../docs/getting-started.md#moving-focus-and-scrolling-ref)):

  ```xml
  <ui.TextField ref="email" label="Email" @bind="email" :error="errors.get('email', '')" />
  ```

  ```python
  if "email" in self.errors:
      self.focus("email")
  ```
