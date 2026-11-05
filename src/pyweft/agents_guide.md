# Writing this app: a PyWeft guide for coding assistants

This is a **PyWeft** app: a Python UI framework. Components are `.weft`
files with an XML template, a Python code block and scoped CSS. It runs in
the browser (Python on WebAssembly via Pyodide) or as a desktop window.
PyWeft is new: don't assume Vue, React, Svelte, Blazor or Jinja syntax. The
rules below are the ones that differ.

Written for pyweft {version}. Refresh with `pyweft agents .` after upgrading.
Full documentation: https://prassanthn.github.io/PyWeft/ (all of it as plain
text: https://prassanthn.github.io/PyWeft/llms-full.txt).

## Commands

```bash
uv run pyweft check .          # find mistakes without running it (exit 1 on errors)
uv run pyweft run .            # dev server with hot reload: http://127.0.0.1:8642/
uv run pyweft run . --desktop  # in a native window (needs: uv add "pyweft[desktop]")
uv run pyweft build .          # static site in dist/ (any static host)
uv add <package>               # a dependency, installed in the browser at load
```

**After changing any `.weft` file, run `uv run pyweft check .` and fix
what it reports** before saying you're done. It loads every component and
reports, with file and line: template and Python errors, unknown names,
handlers, `@bind` fields and components, props a component doesn't take,
events it never emits, slots it doesn't have, and the traps below. It
suggests the name you probably meant. `--json` gives the same as JSON.

(`pip install`/`python -m pyweft` work too.) Dependencies go in
`pyproject.toml`'s `[project].dependencies`, managed with `uv add`; in the
browser they (and everything they depend on) must be pure-Python wheels or
packages Pyodide has built (numpy, pandas, pydantic 2.7, ...). LangChain and
the OpenAI and Anthropic SDKs don't install in the browser (native code);
call an HTTP API with `pyweft.http`, or use the desktop app, where any
package works. `pyweft check` reports a dependency that won't install. There
is no other manifest.

## The app folder

- `app.weft`: the root component. Other `.weft` files are components.
- `<TodoItem>` in a template is `TodoItem.weft` or `todo_item.weft` **next to
  the file using it**; `<widgets.Row>` is `widgets/row.weft` from the app root.
- `.py` files are ordinary modules (shared data, a `Store`); import them by
  name from a code block. A changed `.py` reloads the page.
- `styles.css` (any `.css` at the root): global CSS. `head.html`: extra
  `<head>` content (fonts, CDN CSS). `assets/`: files served at `assets/...`.
- `pyproject.toml` `[tool.pyweft]`: `title`, `icon = "assets/icon.png"`.
- Folders starting with `_`, `dist/` and `node_modules/` are not shipped.
  Everything else in the app is visible to visitors: no secrets in it.

## A component

```xml
<template>
  <div class="todo">
    <input @bind="text" @keydown.enter="add" placeholder="New task" />
    <button @click="add" :disabled="not text.strip()">Add</button>
    <If cond="not items"><p>Nothing to do.</p></If>
    <ul>
      <For each="item in items" key="item['id']">
        <li :class="'done' if item['done'] else ''">
          <input type="checkbox" :checked="item['done']" @change="toggle(item)" />
          {{ item['text'] }}
          <button @click="remove(item)">x</button>
        </li>
      </For>
    </ul>
    <p>{{ left }} left</p>
  </div>
</template>

<code>
items: list = []
text: str = ""
next_id: int = 1

@property
def left(self):
    return sum(1 for item in self.items if not item["done"])

def add(self):
    if self.text.strip():
        self.items.append({"id": self.next_id, "text": self.text.strip(), "done": False})
        self.next_id += 1
        self.text = ""

def toggle(self, item):
    item["done"] = not item["done"]

def remove(self, item):
    self.items = [i for i in self.items if i["id"] != item["id"]]
</code>

<style>
/* Scoped: these rules only reach this component's own elements. */
.done { text-decoration: line-through; opacity: 0.6; }
</style>
```

- **Three blocks:** `<template>` (one), `<code>` and `<style>` (optional), in
  any order.
- **The template is XML, not HTML.** Close every element (`<input />`,
  `<br />`, `<img ... />`), quote every attribute, write `<` as `&lt;` and `&`
  as `&amp;` inside attributes and text (`cond="count &lt; 3"`; prefer `and`
  / `or` over `&&`). One root element is recommended.
- **The code block is the class body**, without `class ...:` and without
  indentation. Annotated fields (`count: int = 0`) are state and props.
  Mutable defaults (`[]`, `{}`) are copied per instance. Methods take `self`.
  `@property` gives computed values. Imports go at the top.
- **Reactivity:** a handler runs, then the whole page re-renders and is
  diffed. Just assign or mutate state in handlers; no setState, signals or
  `.value`. Outside a handler (a timer, a background task, a callback), call
  `self.state_has_changed()` afterwards.

## Template syntax

| Write | Means |
|---|---|
| `{{ expr }}` | the value as text, in text and inside attribute values |
| `:attr="expr"` | attribute from a Python expression; `None`/`False` drop it, `True` makes it present (`:disabled="busy"`) |
| `@click="save"` | call the method (it gets the event if it takes an argument) |
| `@click="remove(item)"` | an expression; `event` is the event (`event.value`, `event.key`) |
| `@click="count += 1"` | a statement; assigning a bare name sets component state |
| `@bind="name"` | two-way binding for input, textarea, select, checkbox, radio; converts to the field's declared type |
| `@bind.number` / `.lazy` / `.trim` | parse as a number / update on change, not each key / strip spaces |
| `@keydown.enter.ctrl.prevent="send"` | modifiers: key names (`enter`, `esc`, `up`, `page-down`, `a`), `ctrl alt shift meta exact`, `prevent stop self once capture passive`; `click.right` |
| `@resize="fit"` | not a DOM event: the element's `event.width`/`event.height` when laid out and on every size change (never in tests or pre-rendering). Mouse events carry `event.localX`/`localY`, the position inside the handler's element |
| `ref="name"` | name an element for `self.focus("name")`, `self.scroll_to("name")` |
| `key="..."` | identity for a `<For>` row (or a component) |

Control flow is **elements**, never `v-if` / `@if` / `{% if %}`:

```xml
<If cond="user is None"><Login /></If>
<ElseIf cond="user.admin"><AdminHome :user="user" /></ElseIf>
<Else><Home :user="user" /></Else>

<For each="order in orders" key="order['id']" index="i">
  <OrderRow :order="order" :odd="i % 2 == 1" @open="show(event)" />
</For>
```

- `<For>` takes `each="name in expression"`, an optional `index="i"`, and
  `key`. **A keyed `<For>` body must render exactly one element per item**:
  wrap several in a `<div>`.
- Prefer a `key` on `<For>` rows whose order or number changes; without one,
  rows (and their components' state) are matched by position.
- `<If>` / `<ElseIf>` / `<Else>` must be siblings, in that order.

## Components

```xml
<!-- parent -->
<Counter :start="5" label="Clicks" @changed="log(event)" />
<Rating @bind="stars" />
```

```python
# counter.weft's code block
label: str = ""
start: int = 0
count: int = 0

def on_init(self):
    self.count = self.start

def bump(self):
    self.count += 1
    self.emit("changed", self.count)    # the parent's @changed gets it as event
```

- **Props:** declared fields. `label="Clicks"` passes text (converted to the
  field's type: `max="5"` gives an int for `max: int`); `:start="5"` passes a
  Python value. Props flow down on every render: don't edit a prop to keep
  your own state, copy it in `on_init`.
- **Events up:** `self.emit("name", payload)`; the parent writes
  `@name="handler(event)"`. Component events take no modifiers.
- **`@bind` on a component** = the `value` prop plus an `update` event: the
  child declares `value` and calls `self.emit("update", new_value)`.
- **Attributes the child doesn't declare** (`class`, `id`, `style`,
  `aria-*`) go to the child's single root element.
- **Slots:** the child places `<Slot />` (default) or `<Slot name="footer"
  :row="row">fallback</Slot>`; the parent passes content between the tags,
  `<Fill name="footer">...</Fill>` for named slots, and slot props are
  variables inside it (`{{ row['name'] }}`). `self.has_slot("footer")`.
- **`<Dynamic :is="cls" :props="{'a': 1}" />`** renders a component class
  chosen at runtime.
- **Lifecycle:** `on_init(self)` (first appearance; may be `async`),
  `on_after_render(self, first)`, `on_dispose(self)`.
- **Effects:** `from pyweft import effect`, then `@effect` on a method: it
  re-runs after a render when state it read has changed; return a function to
  clean up. Effects must not be `async` (start a task inside instead).

## Async, background work, data

```python
import asyncio
from pyweft import http, storage, run_in_background

async def load(self):                      # an async handler is fine
    self.loading = True                    # shows at once (before the first await)
    self.rows = await http.get_json("https://api.example.org/rows")
    self.loading = False                   # the page re-renders when it ends

def on_init(self):
    self.theme = storage.get("theme", "light")   # small JSON data, kept per app

def save_theme(self, name):
    storage.set("theme", name)
```

- An `async` handler or `on_init` runs as a task. What it changes before its
  first `await` shows at once; after that, changes show when it ends, or
  sooner if you call `self.state_has_changed()` (a progress count in a loop).
  `self.start_task(coro)` starts one yourself (cancelled when the component
  goes away).
- `await run_in_background(fn, *args)` runs a slow, synchronous **module-level**
  function in a Web Worker (a thread on the desktop) so the page stays
  responsive. No lambdas or methods; arguments and results must pickle.
- `pyweft.http`: `await http.get(url)` / `post(url, json=...)` return a
  `Response` (`.status`, `.ok`, `.text`, `.json()`); `await http.get_json(url)`.
  Relative URLs (`assets/data.json`) work. Browser rules (CORS) apply.
- `pyweft.storage`: `get(key, default)`, `set(key, value)`, `delete`, `keys`,
  `has`, `clear`; JSON values, kept in the browser (a file on the desktop).
- `pyweft.dialogs`: `await dialogs.open_file(types=["csv"])` returns a
  `PickedFile` (`.name`, `.data` bytes, `.text()`), `save_file(name, data)`,
  `await confirm(message)`.
- **Shared state:** subclass `pyweft.Store` in a `.py` module, create one
  instance, import it where needed. Setting its fields or calling its methods
  updates every component that shows it.
- `pyweft.set_title(text)` sets the window or tab title.

## Pages and routing

```python
# app.weft's code block
from pyweft import Link, router
Pages = router("pages")         # one page per .weft file in pages/
```

```xml
<nav><Link to="/">Home</Link> <Link to="/orders">Orders</Link></nav>
<Pages />
```

- `pages/index.weft` is `/`, `pages/orders.weft` is `/orders`,
  `pages/not_found.weft` is the 404 page. In a page's code block,
  `route = "/orders/{id}"` sets the URL; `{id}` fills the declared field
  `id: int = 0`. Query values fill fields of the same name.
- `navigate("/orders", query={"status": "paid"})` from code;
  `pyweft.routing.back()`. URLs are hash URLs (`#/orders`).
- `crumb = "Orders"` (or `"Order #{id}"`) in a page's code block names it
  in breadcrumbs: `pyweft.routing.trail()`, or
  `<ui.Breadcrumbs auto="true" />`.

## Traps (where generated code usually goes wrong)

1. **Fields named like builtins hide them in that code block**: a field
   called `min`, `max`, `range`, `format`, `filter`, `type`, `id`, `sum`,
   `len` or `list` makes `max(...)` etc. call your field. Pick another name
   or keep a reference first (`_builtin_range = range`).
2. **Generator expressions and lambdas inside `{{ }}`, `:attr` or a handler
   can't see the component's names or template variables** (they run in a
   scope of their own): `{{ sum(i['price'] for i in items) }}` fails. On
   Python 3.10/3.11 list, set and dict comprehensions can't either. Put the
   computation in a property or method: `{{ total }}`.
3. **A keyed `<For>` renders one element per item** (see above).
4. **`:class` replaces `class`** on the same element: write the whole class
   list in the expression (`:class="'row ' + ('active' if on else '')"`).
5. **State changed outside a handler doesn't show** until you call
   `self.state_has_changed()` (timers, callbacks, after awaits).
6. **Don't copy a prop into a field of the same name** or edit a prop to
   change what you show: props are overwritten on every render.
7. **The event is `event`**, not `$event` or `e`: `@input="search(event.value)"`.
   There is no `v-model`, `onClick=`, `this.` or JSX: fields, methods and
   properties are plain names in templates (`{{ count }}`, `@click="bump"`).
8. **`key` is reserved**, and `<If>`, `<ElseIf>`, `<Else>`, `<For>`, `<Slot>`,
   `<Fill>`, `<Dynamic>` are framework tags. Component tags start with a capital
   letter (or are dotted, `ui.Button`); lower-case tags are HTML.
9. **No `document`, `window` or DOM access** from Python: the page is updated
   from the rendered template only. Use refs + `self.focus()` for focus.
10. **Imported functions are plain functions**: `from math import floor` and
    `{{ floor(x) }}` works; a module-level `def` in a `.py` file too.

## pyweft-ui (if the app depends on it)

`uv add pyweft-ui`, then `from pyweft_ui import ui` in a code block and
`<ui.Button>`, `<ui.TextField>`, ... in templates. Wrap the page in
`<ui.Theme>` (light/dark/auto, `primary`, `radius`). Form fields take
`label`, `hint`, `error`, `required`, `disabled`, `name` and `@bind`; option
lists take `"A, B, C"`, a list of values, `(value, label)` pairs or dicts.

- Layout: `AppShell` (header, sticky `nav` fill), `Row`, `Column`, `Grid`,
  `Card`, `Divider`, `Carousel`, `Expansion`, `Accordion`, `Tabs`, `Stepper`.
- Fields: `TextField` (`mask="(999) 999-9999"`), `TextArea`, `NumberField`,
  `Select`, `Autocomplete`, `CascadeSelect`, `Chips`, `ChipInput`, `ButtonToggle`, `Slider`,
  `RadioGroup`, `Checkbox`, `Switch`, `DatePicker`, `DateRangePicker`,
  `Calendar`.
- Data and navigation: `Table` (sortable), `Tree`, `EventCalendar`,
  `Breadcrumbs`.
- Charts (SVG, themed, sized to their container): `BarChart`
  (`stacked="true"`/`"percent"`, `horizontal`), `LineChart` (`curve="smooth"`,
  `fill` for areas), `PieChart` (`donut`, `center="total"`), `PolarAreaChart`,
  `RadarChart`; dashboards: `ScatterChart` (`group`, `size` = bubbles,
  `trend="true"`), `Sparkline` (numbers, `kind`), `Gauge` (`:value`,
  `bands="60:success, 85:warning, 100:danger"`), `FunnelChart`,
  `WaterfallChart` (`totals="Start, End"`). `:data` = rows, a dict of columns or a DataFrame; `x=` the
  category field, `y="a, b"` the series; `:series` dicts add `type`
  (line/bar/area: combo), `axis="right"`, `dash`, `color`. `@select` gets
  `{index, label, series, value, values, row}`. Don't hand-draw SVG charts.
- Actions and feedback: `Button`, `Menu`, `ContextMenu`, `Dialog`,
  `BottomSheet`, `Popover`, `Tooltip`, `Alert`, `Badge`, `Spinner`,
  `Progress`, `Icon`, and toasts: `<ui.Toaster />` once, then
  `from pyweft_ui import toast` and `toast("Saved", "success")`.
- Validation: `from pyweft_ui import Form, rules`;
  `form = Form(email=[rules.required(), rules.email()])` in the code block,
  `:error="form.error('email')" @blur="form.touch('email')"` on the field,
  `if self.form.check(): ...` on submit.

Each control's fields and events: https://pypi.org/project/pyweft-ui/ and the
guide at https://prassanthn.github.io/PyWeft/controls/guide/
