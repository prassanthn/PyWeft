# Changelog

What changed in each release of `pyweft`. Newest first. The toolkit,
`pyweft-ui`, has [its own](packages/pyweft-ui/CHANGELOG.md).

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see [RELEASING.md](RELEASING.md)).

## Unreleased

- **`pyweft check APP`** finds mistakes without running the app: template
  and Python errors, missing components, unknown names in expressions,
  handlers and `@bind` fields that don't exist, props a component doesn't
  take, events it never emits, slots it doesn't have, and known traps, each
  with file, line and a "did you mean". Exit code 1 on errors; `--json`.
- Template nodes know their line in the `.weft` file, and "not well-formed
  XML" errors give the file's line and column (they counted from the
  template block before).
- **AI-friendly apps:** `pyweft new` writes an `AGENTS.md` (and a
  `CLAUDE.md` importing it) that teaches AI coding assistants how to write
  a PyWeft app: the file format, directives, components, async, routing,
  pyweft-ui and the usual mistakes. `pyweft agents APP` refreshes it after
  an upgrade, or adds it to an existing app. The website publishes it as
  `agents.md`, with `llms.txt` and `llms-full.txt` (all the docs as one
  plain-text file).
- `scroll_to(ref, align="start")` brings the element to the top of the
  window (also `"center"`, `"end"`), instead of scrolling just enough to
  show it.
- `keep_in_view(ref, vertical=True)` also shifts the element up or down
  to keep it inside the window, for popups placed at a point (a context
  menu at the pointer). Without it, only sideways, as before.
- `keep_in_view(ref, flip=True)`: a popup opened beside its positioned
  parent (a submenu) moves to the parent's other side when it doesn't fit,
  instead of sliding over it.
- Fixed: an apostrophe in an HTML comment in a template (`<!-- the box's
  -->`) left every later `@event` and `:attr` unrewritten, so the template
  failed to parse. Comments are now passed through untouched, and
  directives inside them are no longer rewritten.

## 0.4.0

- **Input masks:** `<input data-mask="(999) 999-9999">` shapes what's typed
  (`9` digit, `a` letter, `*` either), in the page so the cursor stays put.
  `pyweft.masks` has the same rules in Python (`apply`, `complete`,
  `typed`), and a test checks the runtime agrees with it.

- **`keep_in_view(ref)`**: a component asks for an element to be shifted
  sideways just enough to stay inside the window, measured once it's on
  the page: for menus and pop-ups opening near the edge. Carried out by
  the browser and the desktop window alike.

- Fixed: a function in a code block that ran C code importing through its
  globals failed with `KeyError: '__builtins__'`; `datetime.date.today()`
  did. The loader no longer removes `__builtins__` from the code block's
  globals.

## 0.3.0

- **`pyweft.http`**: call web APIs and load the app's data files, with the
  same code in the browser (the page's fetch) and on the desktop (the
  standard library). `get_json`, `get`/`post`/`put`/`patch`/`delete`,
  `request`; JSON, form and text bodies, query parameters, timeouts. A
  relative URL is a file the app ships (`assets/prices.json`).
- **`pyweft.storage`**: keep data between visits: `get`, `set`, `delete`,
  `has`, `keys`, `clear`, for any JSON value. The browser's local storage,
  kept apart per app; on the desktop, a JSON file in the user's data
  folder; in tests, memory.
- The todo example remembers its list, and the tutorial has a step for it.
- The todo and shop examples are restyled with Tailwind CSS (built with
  its CLI), in light and dark, and work at phone width. The shop has a
  dashboard, an orders table and a reusable status badge.

## 0.2.1

- The PyPI page installs from PyPI, and its links to the guide and the
  toolkit work there.

## 0.2.0

The first release. (It starts at 0.2.0 because an earlier, unrelated
project named `pyweft` used 0.1.0 to 0.1.3 and deleted them, and PyPI never
lets a deleted file name be used again.)

- **Components** in `.weft` files: an XML template, a Python code block and
  a scoped `<style>` block. `{{ }}`, `:attr`, `@event` handlers with
  modifiers and a detailed event object, `@bind` for every form control,
  `<If>`/`<ElseIf>`/`<Else>`, keyed `<For>`, `@property` values.
- **Composition**: props, `emit`, slots (named, with fallbacks and slot
  props), `@bind` on components, attributes passed to the root element,
  components in folders, component libraries from packages, `<Dynamic>`.
- **Pages**: `router("pages")`, `<Link>`, `navigate()`, `back()`, typed
  values from the address and query, a not-found page.
- **State**: `Store` for state shared across components, `@effect`,
  lifecycle hooks, `state_has_changed()`.
- **Async**: async handlers and `on_init`, `start_task()`, and
  `run_in_background()` (a Web Worker in the browser, a thread elsewhere).
- **Focus and the page**: `ref=` with `focus()`, `scroll_to()` and friends;
  `set_title()`; `pyweft.dialogs` for opening and saving files and asking
  for confirmation.
- **Browser target**: Pyodide, with the first screen rendered ahead of time
  and a loading screen that shows real progress.
- **Desktop target**: `pyweft run --desktop` (pywebview, the `desktop` extra)
  and `pyweft build --desktop` for a standalone program (PyInstaller, the
  `package` extra); title, icon and window settings in `[tool.pyweft]`.
- **CLI**: `pyweft new`, `run` (hot reload that keeps state, error overlay)
  and `build` (a static site); PyPI dependencies installed in the browser;
  `head.html`, `assets/` and CSS frameworks.
