# Changelog

What changed in each release of `pyweft-ui`. Newest first.

Add a line under **Unreleased** with each change worth knowing about;
releasing moves them under the new version (see
[RELEASING.md](../../RELEASING.md)).

## Unreleased

- Charts keep their layout while their data, settings, width and hidden
  series stay the same: a click or hover anywhere on a page of charts no
  longer lays every chart out again (the gallery with all its charts
  renders in half the time).
- Hiding a series from a chart's legend hid it in every other chart too,
  and in charts created later.

## 0.8.0

- Needs `pyweft` 0.9.
- `Progress` without a value (busy) animates with `translate` instead of
  `left`, so the bar keeps moving while Python is busy.
- Gallery: picking a section that isn't built yet highlights it and shows a
  loading bar at the top first, then builds it, and scrolls once the cards
  above have laid themselves out (jumps below the charts used to land
  thousands of pixels short).

## 0.7.0

- Needs `pyweft` 0.8.
- The gallery renders its first group at once and the others when the
  page is idle (its charts once scrolled near), with `<Defer>`.

- **`Splitter`:** two or three panes, side by side or stacked, with
  draggable dividers; keyboard (arrows, Home/End, Enter to collapse),
  `min`/`max`, `@bind` to the sizes in %, `storage_key` to remember them,
  nesting, and stacking below `stack_below` px on phones.
- **`AppShell resizable_nav="true"`:** drag the sidebar wider or narrower
  (`nav_width`, `nav_min`, `nav_max`), also by keyboard; remembered between
  visits. The gallery uses it.

- **`FileDrop`:** a drop zone for files, with a "Choose files" button
  (`pyweft.dialogs`), `accept` (extensions), `max_mb` and `multiple`;
  emits `files` (PickedFile list) and `reject` (name, reason), and keeps
  a file dropped beside it from opening in the browser. Needs pyweft's
  dropped-file support.

## 0.6.0

- Needs `pyweft` 0.7.
- `EventCalendar`: with `@day`, days can be picked from the keyboard (the
  day numbers, and the week view's column headings, are buttons); the
  mouse-only cells behind them are hidden from screen readers.
- Click-outside backdrops (menus, pickers, popovers, bottom sheet) are
  hidden from screen readers. Every control now passes `pyweft check`'s
  accessibility rules, and a test keeps it that way.

## 0.5.0

- **Data-science charts:** `Histogram` (round bins, overlapping groups, a
  KDE curve, means), `BoxPlot` (quartiles, outliers, violins, all points),
  `Heatmap`, `CorrelationMatrix` (Pearson or Spearman), `CandlestickChart`
  (volume, moving averages, hollow and OHLC styles), `Treemap`,
  `SankeyChart` and `CalendarHeatmap`. Bar and line series take error
  bars, shaded bands (`lower`/`upper`) and trend lines. The statistics are
  plain Python: no numpy needed in the browser.
- **Dashboard charts:** `ScatterChart` (groups, bubbles sized by area,
  least-squares trend lines with R²), `Sparkline` (line, area or bars, for
  stat cards and table cells), `Gauge` (270° or half dial, coloured bands,
  a needle, read as a meter), `FunnelChart` (share of the first stage,
  conversion between stages) and `WaterfallChart` (running totals,
  subtotals).
- **Charts:** `BarChart` (grouped, stacked, 100%, horizontal, value
  labels), `LineChart` (smooth, stepped, dashed, areas, stacked areas,
  gaps), `PieChart` (doughnut, half circle, a total in the middle),
  `PolarAreaChart` and `RadarChart`. Mix bars and lines in one chart, and
  put series on a second scale. Data can be rows, columns, a DataFrame, a
  `{label: value}` dict or Chart.js's `{"labels", "datasets"}`. Drawn as
  SVG in Python, so they follow the theme (new `--ui-chart-1` ...
  `--ui-chart-10` colours) and work on the desktop and in tests; they lay
  themselves out for their real width with PyWeft 0.6's `@resize`.
  Tooltips, a legend that hides series, arrow keys to read values aloud,
  a data table for screen readers, and `@select` for clicks.

## 0.4.0

- **`CascadeSelect`**: choose from nested options one level at a time,
  with children loaded on demand, the chosen path shown, groups
  choosable, and a drill-down layout on narrow screens.
- **`Breadcrumbs`**: the trail to the current page, with icons, a "…"
  menu for long trails, any separator, and `auto="true"` to build it from
  the router (pages name themselves with `crumb = "..."`).
- **`Carousel`**: slides moved by arrows, dots, a swipe or a mouse drag;
  several per view, looping, and autoplay that pauses on hover and focus,
  stops when someone takes over, and has a stop button.
- `TextField`, `TextArea` and `NumberField` take `readonly`. (The gallery's
  share popover used it before it existed, which `pyweft check` caught.)
- **`AppShell`**: the sidebar's contents stay in view while the page
  scrolls (scrolling on their own when taller than the window);
  `sticky_nav="false"` turns it off.
- Fixed: a hidden `Tooltip`, or `Popover` hover card, near the window's
  edge widened the page (phones zoomed out to fit it).
- Gallery: search the controls from the sidebar (by section or control
  name; Enter jumps to the first match).
- **`Autocomplete`**: a text field with suggestions that narrow as you type
  (matched text in bold), picked with the keyboard or a click. Lay out each
  suggestion yourself with `<Fill name="option">` (`option`, `active`,
  `query`) and the empty state with `<Fill name="empty">`. For server
  results: `@search`, `match="none"` and `loading`. `free="true"` keeps
  whatever was typed.
- **`Progress`**: a progress bar or ring, determinate or not, with a
  buffer, a formatted value, colours, sizes and stripes.
- **`Toaster look="snackbar"`**: `toast()` messages as a compact dark
  bar at the bottom centre, one at a time (a new one replaces the one
  showing), with a text action. `Toaster` also gained `dismissible`.
- **`Popover`**: a button opening a small panel of your own content,
  placed on any side with an arrow; or, with `open_on="hover"`, a preview
  card.
- **`Tooltip`**: a short label on hover or keyboard focus, shown by CSS.
- **`Divider`**: a line between things, inset, labelled ("or") or
  vertical between items in a row.
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
