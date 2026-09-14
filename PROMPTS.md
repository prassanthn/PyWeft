# Task prompts for Claude Code

`CLAUDE.md` carries the standing context and is loaded automatically. These are
the per-task prompts — paste one at the start of a session.

---

## Task 1 — Component composition (do this first)

> Read `CLAUDE.md`, then `src/weft/renderer.py`, `src/weft/differ.py` and
> `src/weft/parser.py` before writing anything.
>
> Add component composition. A `.weft` template should be able to render another
> component and pass parameters:
>
> ```xml
> <template>
>   <div>
>     <TodoRow item="entry" on-remove="forget" key="entry['id']" />
>   </div>
> </template>
> ```
>
> Requirements:
> - Distinguish component tags from HTML tags. Propose a rule and justify it —
>   capitalised-tag convention, an explicit registry, or an import directive in
>   the code block. I lean toward an explicit registry so typos fail loudly
>   instead of silently emitting an unknown HTML element, but argue me out of it
>   if you have a better case.
> - Parameters are expressions evaluated in the parent's scope and set as
>   attributes on the child instance before its first render.
> - Callback parameters: a child must be able to invoke a parent method.
> - Child components own their own state and lifecycle (`on_init`,
>   `on_after_render`, `on_dispose`). A parent re-render must not reset child
>   state.
> - Child instances must persist across parent re-renders, keyed by position
>   *or* by `key` when given. Getting this wrong means a child in a list loses
>   its state whenever the list reorders — that's the case to design around.
> - Handler ids must stay unique across the composed tree and keep the existing
>   key-based stability property.
> - The diff must treat a child component's output as part of one flat tree.
>   Don't introduce a second tree type.
>
> Before coding, write out how component boundaries interact with the differ's
> ordering invariant and with `dommodel.py`. If composition requires changing the
> patch op contract, say so explicitly and explain why rather than changing it
> quietly.
>
> Add tests including: nested components, a keyed list of stateful child
> components that reorders (assert state follows the key), callbacks firing into
> the parent, and lifecycle call order. Keep the existing 442 tests green.

---

## Task 2 — JS runtime + pywebview host

> Read `CLAUDE.md` and `src/weft/dommodel.py` first. `dommodel.py` is the
> executable spec — the JS must do to real DOM nodes exactly what it does to
> dicts, including op ordering and index semantics.
>
> Build:
>
> 1. `src/weft/static/runtime.js` — applies patch ops to the real DOM, mounts an
>    initial tree from `to_dicts()` output, and uses **delegated** event
>    listeners at the root that post `{handler_id, event}` back over the bridge.
>    Serialise only what handlers need from the event (`value`, `checked`,
>    `key`, modifier flags), not the whole DOM event.
> 2. `src/weft/host.py` — a pywebview window that mounts a component, receives
>    events, dispatches to the renderer, re-renders, diffs, and pushes ops back.
>    Keep it thin; all logic stays in the core.
> 3. An asyncio render queue so async handlers work and concurrent events are
>    serialised. Do not let two renders interleave.
> 4. `weft run examples/counter.weft` as a CLI entry point.
>
> Constraints:
> - `src/weft/` core modules must not import pywebview. The host layer may.
> - Handle void elements, boolean attributes, and `value` on inputs correctly —
>   setting `value` as an attribute doesn't update a focused input's displayed
>   value, so use the property.
> - Don't clobber the caret position when a bound input re-renders. This is the
>   bug that makes naive two-way binding unusable; solve it deliberately.
> - Stale handler ids must be a no-op on both sides.
>
> Test the JS with a headless DOM or a jsdom-equivalent harness. At minimum,
> port the randomised convergence tests from `tests/test_differ.py`: generate
> trees in Python, apply patches in JS, assert the DOM matches.

---

## Task 3 — Pyodide target (after 1 and 2)

> Read `CLAUDE.md`. The point of this task is to prove the architecture bet:
> reaching the browser should be a new *transport*, not a new renderer.
>
> Add a Pyodide target that reuses `runtime.js` unchanged and calls the render
> core in-process instead of over IPC. If anything in `src/weft/` needs to
> change to make this work, that's a leak in the abstraction — report it rather
> than patching around it.
>
> Report honestly on startup weight and time to first paint. If it's bad enough
> to change what this target is good for, say so.

---

## Handy one-liners

**Review before extending:**
> Read `CLAUDE.md`, then review `src/weft/` for correctness bugs, unclear
> naming, and anywhere the "core never touches a DOM" rule has leaked. Don't
> refactor for style. List findings by severity before changing anything.

**Profile the renderer:**
> Benchmark `Renderer.render()` and `diff()` on a 1000-row keyed list with 10%
> of rows changing per frame. Report where the time goes. Don't optimise yet —
> I want the numbers before deciding whether codegen is worth it.

**Adding a feature:**
> Read `CLAUDE.md` first. I want [FEATURE]. Before coding, tell me which
> decisions in `CLAUDE.md` it touches and whether any need revisiting. Then
> implement with tests, keeping `pytest` green.
