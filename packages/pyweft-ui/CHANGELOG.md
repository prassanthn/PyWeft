# Changelog

What changed in each release of `pyweft-ui`. Newest first.

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see
[RELEASING.md](../../RELEASING.md)).

## Unreleased

- **`Autocomplete`**: a text field with suggestions that narrow as you type
  (matched text in bold), picked with the keyboard or a click. Lay out each
  suggestion yourself with `<Fill name="option">` (`option`, `active`,
  `query`) and the empty state with `<Fill name="empty">`. For server
  results: `@search`, `match="none"` and `loading`. `free="true"` keeps
  whatever was typed.
- **`Tree`**: nested nodes that open and close, with selection,
  checkboxes (partly checked parents), loading children on demand, a
  filter that keeps the parents of matches, and the full tree keyboard.
- Icons: `folder`, `folder-open`, `file`.
- **`ButtonToggle`**: a joined row of buttons, one choice (a radio group)
  or several, with icon-only buttons, a check mark, sizes, full width and
  a vertical layout.
- Icons: `bold`, `italic`, `underline`, `align-left`, `align-center`,
  `align-right`, `list`, `grid`.
- **`BottomSheet`**: a panel sliding up from the bottom, as a list of
  actions or any content with an actions row; closes with Esc, a tap
  outside or a swipe down, and keeps focus inside like `Dialog`.
- **`Stepper`**: a task in steps with Back / Next, per-step checks
  through `@next` (a `Form` per step), optional and error steps, `linear`
  mode, vertical layout and labels under the numbers.
- **`Menu`**: submenus (an item with `items`, opened on hover, click or
  the right arrow, flipping sides when there's no room), group headings,
  `hint` (a shortcut) and `description` on items, `position="above"`,
  and fills for your own trigger (`trigger`) and item layout (`item`).
- **`ContextMenu`**: a right-click menu for an area, opened at the
  pointer (or with the Menu key or Shift+F10), with the same items.
- **`Expansion`**: a panel that opens and closes under its header, with a
  description, icon, action row, custom header and `lazy` content.
- **`Accordion`**: a stack of expansion panels, one open at a time or
  `multiple`, with arrow-key movement between headers.
- **`Slider`**: drag a thumb to pick a number, or two for a range; steps,
  ticks and labelled marks, a value bubble with a `format`, keyboard
  support, and `lazy` updates on release.
- **`Chips`**: a row of chips to choose one or several from, with icons,
  removable chips (`@remove`) and a keyboard row (arrows, Space, Delete).
- **`ChipInput`**: type and press Enter or a comma to add a chip, × or
  Backspace to remove one; suggestions from `options`, `free`, `max`,
  custom chips and suggestions.
- `AppShell`'s content area can shrink beside the sidebar, so wide content
  (a long line of code) no longer widens the page.

## 0.3.0

For `pyweft` 0.4 (the date controls need its fix for `date.today()` in a
component, and the menus and calendars its `keep_in_view`).

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
- **`DatePicker`**: a field with a calendar that binds a `datetime.date`,
  with `min`/`max`, Monday- or Sunday-first weeks, Today and Clear, and the
  full keyboard (arrows, Page Up/Down, Home/End, Esc). Click the month or
  the year in its header to jump to another month or year.
- **`Menu`**: a button that opens a list of actions (icons, dividers,
  disabled and danger items) and emits `select`; arrow keys, Esc, and a
  click outside to close.
- **`DateRangePicker`**: two months side by side; click the first day, then
  the last, with the range previewed as you go. Binds `(start, end)`;
  `min_days`/`max_days` limit its length.
- **`Calendar`**: the calendar on its own, always open, for a date or a
  range. `DatePicker` and `DateRangePicker` are built on it.
- **`EventCalendar`**: events by month (bars across days, "+N more"),
  week (timed events by the hour, side by side when they overlap) or
  agenda; `months="3"` shows several months. Emits `select`, `day` and
  `navigate`.
- `TextField` takes a `mask` (`"(999) 999-9999"`) that shapes what's typed,
  with a matching placeholder and the number pad for digits; and
  `rules.masked(mask)` checks it's complete.
- Menus and calendars shift sideways to stay inside the window.
- `AppShell`'s header wraps onto a second row when its actions don't fit
  beside the title, so a phone no longer scrolls sideways.
- Icons `calendar` and `more`. `Card` no longer clips what's inside it, so
  a menu or calendar can open past its edge.

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
