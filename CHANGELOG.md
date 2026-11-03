# Changelog

What changed in each release of `pyweft`. Newest first. The toolkit,
`pyweft-ui`, has [its own](packages/pyweft-ui/CHANGELOG.md).

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see [RELEASING.md](RELEASING.md)).

## Unreleased

## 0.1.0

The first release.

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
