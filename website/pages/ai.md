---
title: Using AI coding assistants
description: How PyWeft helps Claude Code, Codex, Cursor, Copilot and other AI assistants write correct apps.
---

# Using AI coding assistants

PyWeft is new, so no AI model learned it in training. Ask one to write a
`.weft` file cold and it will guess, and its guesses lean on Vue or Razor:
`v-if`, `@if`, `$event`, unclosed `<input>` tags. PyWeft fixes that in three
ways: it tells the assistant how PyWeft works, it gives the assistant a
checker to test its own work against, and it publishes the docs in a form
AI tools can read in one go.

## 1. Every app comes with instructions: AGENTS.md

`pyweft new` puts an `AGENTS.md` in the new app, and a one-line `CLAUDE.md`
(`@AGENTS.md`) that points Claude Code at it. Claude Code, Codex, Cursor,
GitHub Copilot and most other assistants read these files on their own,
so the knowledge is there from the first prompt.

It covers, in a few hundred lines: the commands, the app folder, the file
format and its XML rules, every directive and modifier, components, props,
events, slots, async work, data, routing, the `pyweft-ui` controls, and a
list of **the mistakes generated code usually makes**, such as a field named
`max` hiding Python's `max()`, a keyed `<For>` with two root elements, or a
generator expression in a template.

It is written for the PyWeft version you have. After upgrading, refresh it
(this also adds it to an app made before PyWeft wrote one):

```bash
uv run pyweft agents myapp
```

An existing `CLAUDE.md` is left alone; add `@AGENTS.md` to it yourself if
you keep your own notes there.

## 2. A checker it can run: pyweft check

```bash
uv run pyweft check myapp
```

Assistants work in a loop: write code, run something, read the errors, fix
them. `pyweft check` makes that loop work without a browser. It loads every
component and reads every template against what the component defines,
then reports each problem with its file and line, and the name you
probably meant:

```
app.weft:12: error: {{ }}: unknown name 'cout' (did you mean 'count'?) [unknown-name]
app.weft:20: warning: <ui.TextField>: 'lable' is not one of its props, so it goes to its root element as an attribute (did you mean 'label'?) [unknown-prop]
1 error, 1 warning in 4 component files.
```

`AGENTS.md` tells the assistant to run it after every change and fix what
it finds. It exits with 1 when there are errors, so it also works as a
pre-commit or CI step, and `--json` gives editors and tools the same
results as data. The full list of what it checks is in the guide:
[Checking an app](guide/projects.md#checking-an-app-pyweft-check).

## 3. The docs, as text: llms.txt

For assistants that read the web, and for pasting into a chat, the site
follows the [llms.txt](https://llmstxt.org) convention:

- [llms.txt](https://prassanthn.github.io/PyWeft/llms.txt): a short index of the site, with a summary of what
  PyWeft is and isn't.
- [llms-full.txt](https://prassanthn.github.io/PyWeft/llms-full.txt): everything in one plain-text file: the
  assistant guide, the framework guide, and the `pyweft-ui` reference and
  guide (about 50,000 tokens).
- [agents.md](https://prassanthn.github.io/PyWeft/agents.md): the same guide `pyweft new` writes into apps.

## Tips

- **Start the assistant in the app folder**, so it finds `AGENTS.md`. In a
  bigger repository, keep the app in its own folder; most assistants read
  the `AGENTS.md` nearest the files they edit.
- **Ask it to check its work.** "Run `uv run pyweft check .` and fix what
  it reports" is usually enough when it forgets.
- **Have it test behaviour without a browser.** PyWeft components can be
  rendered and clicked from plain Python tests, which an assistant can run;
  see [Testing without a browser](guide/testing.md).
- **Keep `pyweft-ui` in mind.** Asked for "a date picker" or "a sortable
  table", an assistant that has read `AGENTS.md` uses `ui.DatePicker` and
  `ui.Table` instead of building them from scratch.
