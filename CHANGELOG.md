# Changelog

What changed in each release of `pyweft`. Newest first. The toolkit,
`pyweft-ui`, has [its own](packages/pyweft-ui/CHANGELOG.md).

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see [RELEASING.md](RELEASING.md)).

## Unreleased

- **Live data in `pyweft.http`:** `http.events(url)` reads server-sent
  events (reconnecting with `Last-Event-ID` after the server's `retry`
  time, headers included, unlike the browser's EventSource);
  `http.websocket(url)` opens a WebSocket (text, bytes, JSON, subprotocols,
  close codes; the browser's own, and a standard-library client on the
  desktop and in tests); `http.stream(method, url)` reads a response as it
  arrives (`iter_bytes`, `iter_text`, `iter_lines`).
- **`http.Client(base_url, headers=...)`:** an address and headers (such as
  `Authorization`) for every request; `headers` may be a function, async
  too, for tokens that change.

## 0.7.0

- **Embedding in other websites:** `pyweft build` writes an `embed.js`;
  any page that loads it can place the app with `<pyweft-app>` (`src`,
  `route`, `height`, `label`, `data-*`). The app runs in its own frame
  that follows its content's height. `pyweft.embed` reads the `data-*`
  attributes (`params()`), fires DOM events on the element (`send()`) and
  receives the page's `el.send()` messages (`on_message()`).
- **`<Head>`:** `<title>`, `<meta>`, `<link>` and `<style>` for the page's
  head while a component is shown, with expressions, `<If>` and `<For>`
  inside; tags of several components add up and the last title wins. The
  pre-rendered first screen carries them in the HTML (`pyweft build`), for
  link previews and search engines; a desktop window takes the title.
- **Compiled templates:** each component's template is compiled into a
  Python function the first time it renders, instead of being walked node
  by node on every render: about twice as fast (a 1000-row table renders
  in half the time). Output is identical; `PYWEFT_INTERPRET=1` turns it off.
  Expressions are compiled to functions too, so generator expressions,
  lambdas and comprehensions in `{{ }}`, `:attr` and expression handlers
  now see the component's names and loop variables. `pyweft check` only
  reports them in inline statement handlers, where the limit remains.
- **`<Html :content="...">`:** shows an HTML string (rendered Markdown,
  rich text) as markup. It is sanitized by default: scripts, frames,
  forms, `on...` attributes, `javascript:` links and styles that load
  files or cover the page are removed. `trusted="true"` keeps everything
  but `<script>`. The markup becomes ordinary page nodes, so updates are
  diffed and the component's scoped styles apply to it.
- **`<Await task="..." key="...">`:** waits for an async call in the
  template: its content shows while the call runs, then `<Then as="x">`
  with the result or `<Catch as="error">` with the exception. The call
  runs once (not on every render) and starts over when `key` changes;
  a replaced or removed one is cancelled. The shop example's order page
  uses it.
- **Context: `self.provide(key, value)` and `self.inject(key, default)`:**
  pass a value (a theme, the signed-in user, a form) to every component
  below one, without threading it through props. The nearest provider
  wins, and content passed into a slot sees what the component showing it
  provides.
- **Checkbox groups:** checkboxes with `@bind` on a `list` (or `set`,
  `tuple`) field add and remove their own `value`; `:value="row['id']"`
  keeps the value's type.
- **Accessibility checks in `pyweft check`:** warnings (`a11y-*`) for
  images without alt text, clicks with no keyboard way to do them, links
  without `href`, unlabelled form fields, buttons with nothing to read
  out, positive `tabindex`, and misspelt roles or `aria-*` attributes.
  `<!-- pyweft-ignore: code -->` above an element silences a warning
  there (for any check, not only these); `--no-a11y` skips them. The app
  `pyweft new` writes now labels its input.
- **`class:` and `style:` directives:** `class:active="item == chosen"`
  adds a class while the condition holds, and `style:width="f'{pct}%'"`
  sets one CSS property (custom properties too) unless it is `None` or
  `False`. Both add to the element's `class`/`style`, so fixed classes no
  longer have to be repeated in a `:class` expression. On a component tag
  they reach its root element. `pyweft check` checks their expressions.
- **`<Window>` and `<Document>`:** handlers for the whole page, such as
  `<Window @keydown.ctrl.k.prevent="open_search" />`, `@scroll` or
  `<Document @visibilitychange=...>`. They listen while the component that
  renders them is shown. Window events carry the window's size and scroll
  position; document events carry `hidden`.
- **Transitions and animations:** `transition="fade"` (or `in=` / `out=`)
  animates an element appearing and leaving, with `fade`, `fly`, `slide`,
  `scale` and `blur` built in, options such as `duration=300 y=-20`, or the
  app's own CSS `@keyframes`; `animate="flip"` slides elements to where a
  render moved them, as in a reordered keyed list. A leaving element stays
  on screen until its animation ends. Reduced-motion settings are honoured.

## 0.6.0

- **`@resize`** on any element: `event.width` and `event.height` when it is
  first laid out and whenever its size changes, so a component can lay
  itself out for the space it has.
- Mouse and pointer events carry `localX`/`localY`, the position inside the
  element the handler is on (with its `width`/`height`).

## 0.5.0

- **`pyweft check` checks dependencies for the browser:** it follows the
  app's dependencies through their own requirements, as micropip would,
  against the packages the Pyodide in use has built (a snapshot ships with
  PyWeft) and PyPI's pure-Python wheels, and names the one that won't
  install: native code Pyodide doesn't build, a version that clashes with
  a built-in one, a source-only release. `--no-deps` skips it.
- **Breadcrumb trails:** `pyweft.routing.trail()` names each level of the
  current URL from the router: a page's `crumb = "Orders"` (or
  `"Order #{id}"`, filled from the route), else its URL segment.
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
