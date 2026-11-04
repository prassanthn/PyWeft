# Changelog

What changed in each release of `pyweft-ui`. Newest first.

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see
[RELEASING.md](../../RELEASING.md)).

## Unreleased

- **Form validation**: `Form` and `rules`. Name each field's rules
  (`required`, `email`, `min_length`, `same_as`, `check`, your own
  functions...), show `form.error("field")` under it, and call
  `form.check()` on submit. Messages show once a field is left or a submit
  is tried, then follow what's typed; `check()` focuses the first field to
  fix.
- `Checkbox`, `Switch` and `RadioGroup` take an `error`; `RadioGroup` a
  `hint` too. `TextField`, `TextArea`, `NumberField` and `Select` emit
  `blur` when left.
- The gallery has a Validation section, and the guide's sign-up recipe uses
  `Form`.

## 0.2.0

- For `pyweft` 0.3, which adds `pyweft.http` and `pyweft.storage`. The
  controls themselves are unchanged.

## 0.1.1

- The PyPI page installs from PyPI, and its link to the guide works there.

## 0.1.0

The first release, for `pyweft` 0.2.

- **22 controls**: `Theme`, `AppShell`, `Row`, `Column`, `Grid`, `Card`,
  `Button`, `Icon`, `TextField`, `TextArea`, `NumberField`, `Select`,
  `RadioGroup`, `Checkbox`, `Switch`, `Alert`, `Badge`, `Spinner`,
  `Dialog`, `Tabs`, `Table` and `Toaster` with `toast()`.
- Light, dark and system themes, every colour a `--ui-*` CSS variable.
- Keyboard and screen reader support: labelled fields, focus kept inside
  dialogs and returned on close, arrow keys between tabs, sortable table
  headings announced.
- A gallery app and a guide with tested examples.
