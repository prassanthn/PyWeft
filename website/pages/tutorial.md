---
description: Build a todo app with PyWeft, step by step.
---

# Tutorial: a todo app

In this tutorial you build a small todo app: add items, tick them off,
filter them and remove them. It takes about fifteen minutes. Along the way
you'll use most of what everyday PyWeft code needs:

- state, and showing it with `{{ }}`
- lists with `<For>`, and conditions with `<If>`
- handlers, `@bind` for form controls, and event modifiers
- computed values with `@property`
- a component of your own, with props and events
- scoped styles
- building the app for the web and the desktop

You need Python 3.10 or newer and a terminal. The commands use
[uv](https://docs.astral.sh/uv/); with pip, drop the `uv run` in front of
each command.

## 1. Create the app

```bash
uv init todo-tutorial && cd todo-tutorial
uv add pyweft
uv run pyweft new todo
uv run pyweft run todo
```

`pyweft new` makes a folder called `todo` with a starter app in it, and
`pyweft run` serves it. Open <http://127.0.0.1:8642/>: the page shows a
greeting with a text box and a button.

The first visit takes a few seconds while the browser downloads Python;
after that it's cached. Leave `pyweft run` running for the whole tutorial.
Every time you save a file, the page updates on its own.

The `todo` folder holds:

```text
todo/
  app.weft        the app's root component; you'll replace it
  styles.css      CSS for the whole page
  pyproject.toml  the app's name and dependencies
  head.html       extra tags for the page's <head>
  loading.html    what visitors see while Python starts
```

## 2. Show a list

Open `todo/app.weft` and replace everything in it with:

```xml title="todo/app.weft"
<template>
  <div class="todo-app">
    <h1>Todos</h1>
    <ul>
      <For each="item in items" key="item['id']">
        <li>{{ item['text'] }}</li>
      </For>
    </ul>
  </div>
</template>

<code>
items: list = [
    {"id": 1, "text": "Buy milk", "done": False},
    {"id": 2, "text": "Learn PyWeft", "done": False},
]
</code>
```

Save, and the page shows the two items.

A `.weft` file has two parts:

- **`<template>`** is what the component shows. It is XML, so every tag must
  be closed (`<br/>`, `<input />`) and every attribute quoted.
- **`<code>`** is ordinary Python. Fields such as `items: list = [...]` are
  the component's **state**. Each copy of the component gets its own copy
  of the list, so you don't have to worry about Python's shared mutable
  defaults.

In the template, `{{ item['text'] }}` shows a Python value, and
`<For each="item in items">` repeats its content once per item. The `key`
gives each row an identity, so PyWeft can tell which row is which when items
are added, removed or reordered. Give every list a key when its items have
something unique, like an id.

## 3. Add items

Now let people add items. Replace the file again:

```xml title="todo/app.weft" hl_lines="4 5 15-25"
<template>
  <div class="todo-app">
    <h1>Todos</h1>
    <input @bind="draft" @keydown.enter="add" placeholder="What needs doing?" />
    <button @click="add">Add</button>
    <ul>
      <For each="item in items" key="item['id']">
        <li>{{ item['text'] }}</li>
      </For>
    </ul>
  </div>
</template>

<code>
items: list = []
draft: str = ""
next_id: int = 1

def add(self):
    text = self.draft.strip()
    if not text:
        return
    self.items.append({"id": self.next_id, "text": text, "done": False})
    self.next_id += 1
    self.draft = ""
</code>
```

- **`@bind="draft"`** keeps the text box and the `draft` field in step:
  typing changes `draft`, and setting `draft` in Python changes the box.
  That is how `add` reads what was typed, and how `self.draft = ""` clears
  it.
- **`@click="add"`** calls the `add` method when the button is clicked.
  **`@keydown.enter="add"`** does the same when Enter is pressed in the box.
  `.enter` is a *modifier*: it only lets the Enter key through.
- **Methods** take `self`, like any Python method. After a handler runs,
  PyWeft renders the component again and updates the page. There is nothing
  to call to make that happen.

!!! note "Where did the two items go?"

    Saving keeps the app's state, so the page still shows the old items even
    though `items` now starts empty. That's what lets you change code without
    losing your place. Reload the page to start fresh.

Type a few items and press Enter after each.

## 4. Tick off and remove

Each row gets a checkbox and a remove button. Change the `<li>` inside the
`<For>`, and add a `<style>` block and two methods:

```xml title="todo/app.weft" hl_lines="8-12 18-21 36-40"
<template>
  <div class="todo-app">
    <h1>Todos</h1>
    <input @bind="draft" @keydown.enter="add" placeholder="What needs doing?" />
    <button @click="add">Add</button>
    <ul>
      <For each="item in items" key="item['id']">
        <li>
          <input type="checkbox" :checked="item['done']" @change="toggle(item)" />
          <span :class="'done' if item['done'] else None">{{ item['text'] }}</span>
          <button class="remove" @click="remove(item)">✕</button>
        </li>
      </For>
    </ul>
  </div>
</template>

<style>
.done { text-decoration: line-through; color: #999; }
.remove { border: none; background: none; color: #c0392b; cursor: pointer; }
</style>

<code>
items: list = []
draft: str = ""
next_id: int = 1

def add(self):
    text = self.draft.strip()
    if not text:
        return
    self.items.append({"id": self.next_id, "text": text, "done": False})
    self.next_id += 1
    self.draft = ""

def toggle(self, item):
    item["done"] = not item["done"]

def remove(self, item):
    self.items = [i for i in self.items if i["id"] != item["id"]]
</code>
```

- **`:checked="item['done']"`** sets an attribute from a Python expression.
  With `True` the attribute is there, with `False` or `None` it's left out.
  `:class` works the same way: the span gets `class="done"` only when the
  item is done.
- **`@change="toggle(item)"`** calls a method with an argument. Inside a
  `<For>`, `item` is that row's item, so each checkbox toggles its own.
- **`toggle` changes the item in place**, and that's fine: PyWeft compares
  what the page should show with what it shows, so it notices either way.

## 5. Count and filter

Two more things: show how many items are left, and filter the list. Values
worked out from state are **properties**: plain Python `@property` methods,
used in the template like fields.

```xml title="todo/app.weft" hl_lines="3 7-13 16 25-30 37-38 45 47-57"
<template>
  <div class="todo-app">
    <h1>Todos <small>{{ remaining }} left</small></h1>
    <input @bind="draft" @keydown.enter="add" placeholder="What needs doing?" />
    <button @click="add">Add</button>

    <nav class="filters">
      <For each="name in ['all', 'active', 'done']">
        <button :class="'current' if name == show else None" @click="show = name">
          {{ name }}
        </button>
      </For>
    </nav>

    <ul>
      <For each="item in shown" key="item['id']">
        <li>
          <input type="checkbox" :checked="item['done']" @change="toggle(item)" />
          <span :class="'done' if item['done'] else None">{{ item['text'] }}</span>
          <button class="remove" @click="remove(item)">✕</button>
        </li>
      </For>
    </ul>

    <If cond="not items">
      <p class="hint">Nothing yet. Add something above.</p>
    </If>
    <ElseIf cond="not shown">
      <p class="hint">Nothing {{ show }}.</p>
    </ElseIf>
  </div>
</template>

<style>
.done { text-decoration: line-through; color: #999; }
.remove { border: none; background: none; color: #c0392b; cursor: pointer; }
.filters .current { font-weight: bold; }
.hint { color: #888; }
</style>

<code>
items: list = []
draft: str = ""
next_id: int = 1
show: str = "all"

@property
def remaining(self):
    return sum(1 for item in self.items if not item["done"])

@property
def shown(self):
    if self.show == "active":
        return [item for item in self.items if not item["done"]]
    if self.show == "done":
        return [item for item in self.items if item["done"]]
    return self.items

def add(self):
    text = self.draft.strip()
    if not text:
        return
    self.items.append({"id": self.next_id, "text": text, "done": False})
    self.next_id += 1
    self.draft = ""

def toggle(self, item):
    item["done"] = not item["done"]

def remove(self, item):
    self.items = [i for i in self.items if i["id"] != item["id"]]
</code>
```

- **`@click="show = name"`** is a statement rather than a method name. A
  short handler can live right in the template, and assigning to a field
  name sets that field.
- **`<If>`, `<ElseIf>` and `<Else>`** show their content only when their
  condition is true. They sit side by side, the way `if` / `elif` / `else`
  do in Python.
- **The properties run on every render**, so `remaining` and `shown` are
  always up to date and never need storing.

## 6. A component of its own

`app.weft` is getting long. Move a row into a component of its own: create
`todo/todo_item.weft` next to it.

```xml title="todo/todo_item.weft"
<template>
  <li class="todo-item">
    <input type="checkbox" :checked="item['done']" @change="emit('toggle', item)" />
    <span :class="'done' if item['done'] else None">{{ item['text'] }}</span>
    <button class="remove" aria-label="Remove" @click="emit('remove', item)">✕</button>
  </li>
</template>

<style>
.todo-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.2rem 0; }
.done { text-decoration: line-through; color: #999; }
.remove { margin-left: auto; border: none; background: none; color: #c0392b; cursor: pointer; }
</style>

<code>
item: dict = {}
</code>
```

Then, in `app.weft`, replace the whole `<li>...</li>` with one tag, and drop
the `.done` and `.remove` rules from its `<style>` block:

```xml title="todo/app.weft (inside the list)"
<For each="item in shown" key="item['id']">
  <TodoItem :item="item" @toggle="toggle(event)" @remove="remove(event)" />
</For>
```

- **The tag names the file.** `<TodoItem>` finds `todo_item.weft` (or
  `TodoItem.weft`) next to the file that uses it. There's nothing to import
  or register.
- **Props go down.** `item: dict = {}` declares a prop, and
  `:item="item"` passes the row's item to it.
- **Events come up.** The row doesn't change the list itself: it calls
  `emit('toggle', item)`, and the parent decides what that means.
  `@toggle="toggle(event)"` listens for it, with the emitted value as
  `event`.
- **Styles stay put.** A `<style>` block applies only to the component it's
  in. The parent's `.done` rule can't reach elements the row renders, which
  is why those rules moved with the row.

The page looks and works the same as before. That's the point.

## 7. Style it

Give the app a frame. Replace the `<style>` block in `app.weft`:

```css title="todo/app.weft (the style block)"
.todo-app { border: 1px solid #ddd; border-radius: 8px; padding: 1.5rem; }
h1 small { color: #999; font-size: 0.9rem; font-weight: normal; }
input, button { font: inherit; padding: 0.35rem 0.7rem; }
ul { padding-left: 0; list-style: none; }
.filters { display: flex; gap: 0.3rem; margin-top: 1rem; }
.filters .current { font-weight: bold; }
.hint { color: #888; }
```

`input, button` here styles only the app's own inputs and buttons, not the
remove buttons inside `TodoItem`. For rules that should reach everything, use
`todo/styles.css`: it applies to the whole page. It already sets the font
and centres the app in a column.

??? example "The finished `app.weft`"

    ```xml
    <template>
      <div class="todo-app">
        <h1>Todos <small>{{ remaining }} left</small></h1>
        <input @bind="draft" @keydown.enter="add" placeholder="What needs doing?" />
        <button @click="add">Add</button>

        <nav class="filters">
          <For each="name in ['all', 'active', 'done']">
            <button :class="'current' if name == show else None" @click="show = name">
              {{ name }}
            </button>
          </For>
        </nav>

        <ul>
          <For each="item in shown" key="item['id']">
            <TodoItem :item="item" @toggle="toggle(event)" @remove="remove(event)" />
          </For>
        </ul>

        <If cond="not items">
          <p class="hint">Nothing yet. Add something above.</p>
        </If>
        <ElseIf cond="not shown">
          <p class="hint">Nothing {{ show }}.</p>
        </ElseIf>
      </div>
    </template>

    <style>
    .todo-app { border: 1px solid #ddd; border-radius: 8px; padding: 1.5rem; }
    h1 small { color: #999; font-size: 0.9rem; font-weight: normal; }
    input, button { font: inherit; padding: 0.35rem 0.7rem; }
    ul { padding-left: 0; list-style: none; }
    .filters { display: flex; gap: 0.3rem; margin-top: 1rem; }
    .filters .current { font-weight: bold; }
    .hint { color: #888; }
    </style>

    <code>
    items: list = []
    draft: str = ""
    next_id: int = 1
    show: str = "all"

    @property
    def remaining(self):
        return sum(1 for item in self.items if not item["done"])

    @property
    def shown(self):
        if self.show == "active":
            return [item for item in self.items if not item["done"]]
        if self.show == "done":
            return [item for item in self.items if item["done"]]
        return self.items

    def add(self):
        text = self.draft.strip()
        if not text:
            return
        self.items.append({"id": self.next_id, "text": text, "done": False})
        self.next_id += 1
        self.draft = ""

    def toggle(self, item):
        item["done"] = not item["done"]

    def remove(self, item):
        self.items = [i for i in self.items if i["id"] != item["id"]]
    </code>
    ```

## 8. Ship it

Stop `pyweft run` with ++ctrl+c++, then build the app:

```bash
uv run pyweft build todo
```

`todo/dist/` is now a complete static website: put it on any web host, such
as GitHub Pages or Netlify, and the app runs in each visitor's browser. No
server runs Python for you, so it costs nothing to keep online.

The same app also runs as a desktop app, in a native window with Python on
your machine:

```bash
uv add "pyweft[desktop]"
uv run pyweft run todo --desktop
```

To hand it to people who don't have Python, build it into one program (an
`.exe` on Windows, a `.app` on macOS), in `todo/dist-desktop/`:

```bash
uv add --dev "pyweft[package]"
uv run pyweft build todo --desktop
```

## Where next

- **Save the list between visits**, load data from the web or run slow work
  in the background: [async handlers and background
  work](guide/first-component.md#async-handlers-and-background-work).
- **Use ready-made controls** instead of plain inputs and buttons:
  [pyweft-ui](controls/index.md), and the
  <a href="../live/gallery/" target="_blank">live gallery</a>.
- **Add more screens** with a `pages/` folder: [pages and
  navigation](guide/components.md#pages-and-navigation).
- **Test it without a browser**: [testing](guide/testing.md).
- **Everything else**: the [guide](guide/index.md).
