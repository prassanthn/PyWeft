/* PyWeft browser runtime: applies patch ops to real DOM nodes.
 *
 * This file is the JS twin of src/pyweft/dommodel.py -- whatever that file does
 * to dicts, this one must do to DOM nodes. Keep them in lockstep.
 *
 * The container element acts as the virtual root: patch paths index into
 * childNodes exactly as they index into the dict tree, which holds because the
 * runtime alone builds and mutates the container's subtree (the parser already
 * dropped formatting whitespace, so there are no stray text nodes). An element
 * playing its out-transition is still on screen but no longer counts: every
 * index goes through kids(), which skips it.
 */
"use strict";

const PyWeftRuntime = (() => {
  let container = null;
  let dispatch = null; // (handlerId, eventPayload) -> void
  // Host hooks. typing(el): true while events from el are still on their way
  // to Python, so a value from an older render must not overwrite it.
  const options = { typing: null };

  function init(el, dispatchFn) {
    container = el;
    dispatch = dispatchFn;
    container.replaceChildren();
    // Capture: an input's mask is applied before its own listeners (and so
    // before @bind) see the event. Added once per container.
    if (!container._pyweftMasks) {
      container.addEventListener("input", applyMask, true);
      container._pyweftMasks = true;
    }
  }

  // ------------------------------------------------------------- input masks
  // <input data-mask="(999) 999-9999">: 9 a digit, a a letter, * either,
  // \ makes the next character literal, anything else is literal text.
  // The JS twin of src/pyweft/masks.py (tokens, typed, fill): keep them in
  // lockstep. Applied here, in the page, so the cursor stays put.
  const MASK_SLOTS = { 9: /[0-9]/, a: /[A-Za-z]/, "*": /[A-Za-z0-9]/ };

  function maskTokens(mask) {
    const out = [];
    let escaped = false;
    for (const char of mask) {
      if (escaped) { out.push(["literal", char]); escaped = false; }
      else if (char === "\\") escaped = true;
      else if (char in MASK_SLOTS) out.push(["slot", char]);
      else out.push(["literal", char]);
    }
    return out;
  }

  function maskTyped(toks, text) {
    let chars = text.replace(/[^A-Za-z0-9]/g, "");
    let prefix = "";
    for (const [kind, char] of toks) {
      if (kind === "slot") break;
      if (/[A-Za-z0-9]/.test(char)) prefix += char;
    }
    if (prefix && chars.startsWith(prefix)) chars = chars.slice(prefix.length);
    return chars;
  }

  function maskFill(toks, chars) {
    let out = "", pending = "", i = 0;
    const ends = [];
    for (const [kind, char] of toks) {
      if (kind === "literal") { pending += char; continue; }
      while (i < chars.length && !MASK_SLOTS[char].test(chars[i])) i++;
      if (i >= chars.length) break;
      out += pending + chars[i];
      pending = "";
      i++;
      ends.push(out.length);
    }
    return [out, ends];
  }

  function applyMask(ev) {
    const el = ev.target;
    if (!(el instanceof HTMLInputElement) || !el.dataset.mask) return;
    const toks = maskTokens(el.dataset.mask);
    const caret = el.selectionStart ?? el.value.length;
    let chars = maskTyped(toks, el.value);
    // Typed characters before the cursor that the mask takes (a refused
    // letter mustn't move the cursor on).
    let before = maskFill(toks, maskTyped(toks, el.value.slice(0, caret)))[1].length;
    // Backspace over a literal (the ")" in "(555) ") would put it straight
    // back: take the character before it instead.
    const previous = el._pyweftMasked;
    if (ev.inputType === "deleteContentBackward" && previous !== undefined
        && maskTyped(toks, previous) === chars && before > 0) {
      chars = chars.slice(0, before - 1) + chars.slice(before);
      before -= 1;
    }
    const [text, ends] = maskFill(toks, chars);
    el.value = text;
    el._pyweftMasked = text;
    // The cursor goes just before the next typed character (so after any
    // literals in between), or after the last one.
    let at = 0;
    if (ends.length) at = before < ends.length ? ends[before] - 1 : ends[ends.length - 1];
    if (document.activeElement === el) el.setSelectionRange(at, at);
  }

  function mount(rootDicts) {
    for (const dict of rootDicts) {
      container.appendChild(createNode(dict));
    }
  }

  function nodeAt(path) {
    let node = container;
    for (const index of path) {
      node = kids(node)[index];
    }
    return node;
  }

  /* ----------------------------------------------------------- transitions
   * data-pw-in / data-pw-out (transition=, in=, out= in a template) hold
   * "fade", "fly y=-20 duration=300" and so on. An element that leaves stays
   * on screen until its out-animation ends, but leaves the tree the patch
   * paths index at once: kids() skips it, so the structure is still exactly
   * dommodel.py's. data-pw-animate="flip" slides elements to where a
   * render moved them. Animations play for elements an op inserts, removes
   * or replaces itself, not for their descendants, and not on first mount. */
  const kids = (parent) => Array.prototype.filter.call(parent.childNodes, (n) => !n._pyweftLeaving);

  const reducedMotion = () =>
    typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

  function parseMotion(spec) {
    const [name, ...rest] = String(spec).trim().split(/\s+/);
    const opts = {};
    for (const part of rest) {
      const [key, value] = part.split("=");
      if (value === undefined) continue;
      opts[key] = value !== "" && !isNaN(value) ? Number(value) : value;
    }
    return { name, opts };
  }

  const MOTIONS = {
    fade: () => [{ opacity: 0 }, { opacity: 1 }],
    fly: (o) => [
      { opacity: o.opacity ?? 0, transform: `translate(${o.x ?? 0}px, ${o.y ?? 16}px)` },
      { opacity: 1, transform: "none" },
    ],
    scale: (o) => [{ opacity: o.opacity ?? 0, transform: `scale(${o.start ?? 0.9})` }, { opacity: 1, transform: "none" }],
    blur: (o) => [{ opacity: 0, filter: `blur(${o.amount ?? 6}px)` }, { opacity: 1, filter: "none" }],
    slide: (o, el) => {
      // Height (or width, axis=x) from nothing to what the element measures.
      const cs = getComputedStyle(el);
      const [size, a, b] = o.axis === "x" ? ["width", "Left", "Right"] : ["height", "Top", "Bottom"];
      const zero = { [size]: "0px", overflow: "hidden", opacity: 0 };
      const full = { [size]: cs[size], overflow: "hidden", opacity: 1 };
      for (const box of ["padding", "margin"]) {
        zero[box + a] = zero[box + b] = "0px";
        full[box + a] = cs[box + a];
        full[box + b] = cs[box + b];
      }
      return [zero, full];
    },
  };

  // Plays a motion on el; resolves when done (at once when nothing plays).
  function play(el, spec, entering) {
    if (!spec || reducedMotion() || typeof el.animate !== "function") return Promise.resolve();
    const { name, opts } = parseMotion(spec);
    const duration = opts.duration ?? 200;
    const delay = opts.delay ?? 0;
    const easing = opts.easing ?? "cubic-bezier(0.2, 0, 0, 1)";
    const make = MOTIONS[name];
    if (make) {
      const frames = make(opts, el);
      const anim = el.animate(entering ? frames : frames.slice().reverse(), {
        duration, delay, easing, fill: entering ? "backwards" : "forwards",
      });
      return anim.finished.catch(() => {});
    }
    // Any other name is the app's own CSS @keyframes (they aren't scoped):
    // forwards to enter, backwards to leave.
    return new Promise((done) => {
      const finish = () => {
        el.removeEventListener("animationend", finish);
        done();
      };
      el.addEventListener("animationend", finish);
      el.style.animation = `${name} ${duration}ms ${easing} ${delay}ms ${entering ? "both" : "reverse both"}`;
      setTimeout(finish, duration + delay + 50); // no such keyframes: don't wait forever
    });
  }

  function enter(node) {
    if (node.nodeType === 1 && node.hasAttribute("data-pw-in")) play(node, node.getAttribute("data-pw-in"), true);
  }

  function leave(node) {
    const spec = node.nodeType === 1 && node.getAttribute("data-pw-out");
    if (!spec || reducedMotion()) {
      node.remove();
      return;
    }
    node._pyweftLeaving = true;
    node.setAttribute("inert", ""); // nothing to click or focus on its way out
    // In a list that slides (animate="flip"), take it out of the flow so
    // the others move into place while it goes.
    if (node.hasAttribute("data-pw-animate") && node instanceof HTMLElement) {
      const { offsetLeft, offsetTop, offsetWidth, offsetHeight } = node;
      Object.assign(node.style, {
        position: "absolute", left: `${offsetLeft}px`, top: `${offsetTop}px`,
        width: `${offsetWidth}px`, height: `${offsetHeight}px`, margin: "0",
      });
    }
    play(node, spec, false).then(() => node.remove());
  }

  // FLIP: where every animate="flip" element was before a batch of ops...
  function measureFlips() {
    const before = new Map();
    for (const el of container.querySelectorAll("[data-pw-animate]")) {
      if (!el._pyweftLeaving) before.set(el, el.getBoundingClientRect());
    }
    return before;
  }

  // ... and, after it, a slide from there to where each one is now.
  function playFlips(before) {
    if (reducedMotion()) return;
    for (const [el, was] of before) {
      if (!el.isConnected || el._pyweftLeaving || typeof el.animate !== "function") continue;
      const now = el.getBoundingClientRect();
      const dx = was.left - now.left;
      const dy = was.top - now.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
      const { opts } = parseMotion(el.getAttribute("data-pw-animate") || "flip");
      el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], {
        duration: opts.duration ?? 250, easing: opts.easing ?? "cubic-bezier(0.2, 0, 0, 1)",
      });
    }
  }

  const SVG_NS = "http://www.w3.org/2000/svg";

  // Children of an <svg> must be created in the SVG namespace or the
  // browser treats them as unknown HTML and draws nothing.
  const childNamespace = (el) =>
    el.namespaceURI === SVG_NS && el.localName !== "foreignObject" ? SVG_NS : null;

  function createNode(dict, ns = null) {
    if (dict.type === "text") {
      return document.createTextNode(dict.text);
    }
    const el =
      dict.tag === "svg" || ns === SVG_NS
        ? document.createElementNS(SVG_NS, dict.tag)
        : document.createElement(dict.tag);
    setAttrs(el, dict.attrs || {}, []);
    setEvents(el, dict.events || {}, []);
    for (const child of dict.children || []) {
      el.appendChild(createNode(child, childNamespace(el)));
    }
    // Browsers honour autofocus once per page load; an element this runtime
    // inserts later (a dialog, a field that just appeared) would be skipped.
    if (dict.attrs && "autofocus" in dict.attrs) {
      queueMicrotask(() => el.isConnected && el.focus());
    }
    // A <select>'s value only sticks once its options exist.
    if (el.tagName === "SELECT" && dict.attrs && "value" in dict.attrs) {
      el.value = dict.attrs.value;
    }
    return el;
  }

  // Controls whose typed-in value lives in the .value property. For any other
  // element (an <option>, a <button>) value is a plain attribute: an option's
  // .value even falls back to its text, so it must never be written that way.
  const liveValue = (el) =>
    el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement;

  function setAttrs(el, set, remove) {
    for (const name of remove) {
      if (name === "value" && liveValue(el)) el.value = "";
      if (name === "checked" && "checked" in el) el.checked = false;
      el.removeAttribute(name);
    }
    for (const [name, value] of Object.entries(set)) {
      // "value" must land on the live property, not just the attribute, or a
      // re-render never updates an input the user has typed in. Skip the write
      // when it already matches so the caret position survives.
      if (name === "value" && liveValue(el)) {
        // A host whose events reach Python asynchronously (the desktop
        // bridge) can be a keystroke behind: don't type over the user.
        if (el.value !== value && !(options.typing && options.typing(el))) el.value = value;
      } else if (name === "checked" && "checked" in el) {
        // Present means checked: the renderer writes checked="" (valueless),
        // and drops the attribute for unchecked.
        el.checked = true;
        el.setAttribute(name, value);
      } else {
        el.setAttribute(name, value);
      }
    }
  }

  /* Handler ids live in a map on the element and are resolved at fire time,
   * so set_events just updates the map -- listeners are added once per event
   * spec and never need rebinding when a diff swaps the id.
   *
   * A spec is the template's attribute minus the @: "click", or with
   * modifiers, "keydown.enter.ctrl" (validated by events.py). Modifiers are
   * applied here, in the listener, because preventDefault/stopPropagation
   * cannot wait for a round trip to Python. An empty handler id means
   * modifiers only (@submit.prevent=""): nothing to dispatch. */
  function setEvents(el, set, remove) {
    if (!el._pyweftEvents) el._pyweftEvents = {};
    for (const spec of remove) {
      delete el._pyweftEvents[spec];
    }
    for (const [spec, handlerId] of Object.entries(set)) {
      ensureListener(el, spec);
      el._pyweftEvents[spec] = handlerId;
    }
  }

  const OPTIONS = new Set(["prevent", "stop", "self", "once", "capture", "passive"]);
  const SYSTEM_KEYS = ["ctrl", "alt", "shift", "meta"];
  const BUTTONS = { left: 0, middle: 1, right: 2 };
  // Modifier name -> KeyboardEvent.key values (kebab-cased) it also matches.
  const KEY_ALIASES = {
    esc: ["escape"],
    space: [" ", "spacebar"],
    up: ["arrow-up"],
    down: ["arrow-down"],
    left: ["arrow-left"],
    right: ["arrow-right"],
    delete: ["delete", "backspace"],
  };

  // "PageDown" -> "page-down", "Enter" -> "enter", "A" -> "a".
  const kebabKey = (key) =>
    key.length === 1 ? key.toLowerCase() : key.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();

  function accepts(ev, mods) {
    if (mods.includes("self") && ev.target !== ev.currentTarget) return false;
    for (const sys of SYSTEM_KEYS) {
      if (mods.includes(sys) && !ev[`${sys}Key`]) return false;
    }
    if (mods.includes("exact") && SYSTEM_KEYS.some((s) => !mods.includes(s) && ev[`${s}Key`])) {
      return false;
    }
    const isKey = typeof KeyboardEvent !== "undefined" && ev instanceof KeyboardEvent;
    const rest = mods.filter((m) => !OPTIONS.has(m) && !SYSTEM_KEYS.includes(m) && m !== "exact");
    if (isKey) {
      if (rest.length) {
        const key = kebabKey(ev.key || "");
        if (!rest.some((m) => m === key || (KEY_ALIASES[m] || []).includes(key))) return false;
      }
    } else {
      const buttons = rest.filter((m) => m in BUTTONS);
      if (buttons.length && !buttons.some((b) => ev.button === BUTTONS[b])) return false;
    }
    return true;
  }

  /* @resize: not a DOM event. A ResizeObserver reports the element's size
   * (content box, whole pixels) when it is first laid out and whenever it
   * changes, so a component can lay itself out for the space it really has.
   * One observer serves every element; it doesn't keep removed ones alive. */
  let resizeObserver = null;

  function observeSize(el, spec) {
    if (typeof ResizeObserver === "undefined") return;
    if (!resizeObserver) {
      resizeObserver = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const target = entry.target;
          const width = Math.round(entry.contentRect.width);
          const height = Math.round(entry.contentRect.height);
          const last = target._pyweftSize;
          if (last && last[0] === width && last[1] === height) continue;
          target._pyweftSize = [width, height];
          for (const s of target._pyweftResizeSpecs || []) {
            const handlerId = (target._pyweftEvents || {})[s];
            if (handlerId) dispatch(handlerId, { type: "resize", width, height });
          }
        }
      });
    }
    (el._pyweftResizeSpecs = el._pyweftResizeSpecs || []).push(spec);
    resizeObserver.observe(el);
  }

  // <Window> and <Document> in a template render as these hidden
  // placeholders: their listeners go on window or document, and come off
  // the first time they fire after the placeholder has left the page.
  const GLOBAL_TARGETS = { "PYWEFT-WINDOW": () => window, "PYWEFT-DOCUMENT": () => document };

  function ensureListener(el, spec) {
    if (!el._pyweftBound) el._pyweftBound = {};
    if (el._pyweftBound[spec]) return;
    el._pyweftBound[spec] = true;
    const [name, ...mods] = spec.split(".");
    const global = GLOBAL_TARGETS[el.tagName];
    if (name === "resize" && !global) return observeSize(el, spec);
    const target = global ? global() : el;
    // Browsers fire no click for the right or middle button.
    let type = name;
    if (name === "click" && mods.includes("right")) type = "contextmenu";
    if (name === "click" && mods.includes("middle")) type = "mouseup";
    const options = {
      capture: mods.includes("capture"),
      once: mods.includes("once"),
      passive: mods.includes("passive"),
    };
    const listener = (ev) => {
      if (global && !el.isConnected) {
        // Its component is gone: no handler, and no preventDefault either.
        target.removeEventListener(type, listener, options);
        return;
      }
      const events = el._pyweftEvents;
      if (!events || !(spec in events)) return; // unbound since; a no-op, matching the renderer
      if (!accepts(ev, mods)) return;
      if (mods.includes("prevent")) ev.preventDefault();
      if (mods.includes("stop")) ev.stopPropagation();
      const handlerId = events[spec];
      if (handlerId) dispatch(handlerId, eventPayload(ev));
    };
    target.addEventListener(type, listener, options);
  }

  // The keys a handler's event receives; documented on events.Event.
  function eventPayload(ev) {
    const payload = { type: ev.type };
    const target = ev.target;
    if (target && typeof target.value === "string") payload.value = target.value;
    if (target && (target.type === "checkbox" || target.type === "radio")) {
      payload.checked = target.checked;
    }
    if ("key" in ev) {
      payload.key = ev.key;
      payload.code = ev.code;
      payload.repeat = ev.repeat;
    }
    if ("ctrlKey" in ev) {
      payload.ctrlKey = ev.ctrlKey;
      payload.shiftKey = ev.shiftKey;
      payload.altKey = ev.altKey;
      payload.metaKey = ev.metaKey;
    }
    if ("clientX" in ev) {
      Object.assign(payload, {
        clientX: ev.clientX, clientY: ev.clientY,
        offsetX: ev.offsetX, offsetY: ev.offsetY,
        button: ev.button, buttons: ev.buttons,
      });
      // Relative to the element the handler is on, not the innermost one
      // under the pointer (offsetX), which inside an SVG is rarely useful.
      const here = ev.currentTarget;
      if (here && here !== window && here !== document && here.getBoundingClientRect) {
        const box = here.getBoundingClientRect();
        payload.localX = ev.clientX - box.left;
        payload.localY = ev.clientY - box.top;
        payload.width = box.width;
        payload.height = box.height;
      }
    }
    // <Window>: the window's size and scroll; <Document>: whether the page
    // is hidden (visibilitychange).
    if (ev.currentTarget === window) {
      Object.assign(payload, { width: innerWidth, height: innerHeight, scrollX, scrollY });
    } else if (ev.currentTarget === document) {
      payload.hidden = document.hidden;
    }
    if ("deltaY" in ev) {
      payload.deltaX = ev.deltaX;
      payload.deltaY = ev.deltaY;
    }
    if (ev.type === "submit" && target instanceof HTMLFormElement) {
      payload.form = formFields(target);
    }
    return payload;
  }

  // {name: value}, or a list when several fields share a name. File inputs
  // are left out: a File cannot travel as JSON.
  function formFields(form) {
    const fields = {};
    for (const [name, value] of new FormData(form)) {
      if (typeof value !== "string") continue;
      fields[name] = name in fields ? [].concat(fields[name], value) : value;
    }
    return fields;
  }

  function applyOps(ops) {
    const flips = container.querySelector("[data-pw-animate]") ? measureFlips() : null;
    for (const op of ops) {
      switch (op.op) {
        case "insert": {
          const parent = nodeAt(op.path);
          const node = createNode(op.node, childNamespace(parent));
          parent.insertBefore(node, kids(parent)[op.index] || null);
          enter(node);
          break;
        }
        case "remove": {
          leave(kids(nodeAt(op.path))[op.index]);
          break;
        }
        case "replace": {
          const parent = nodeAt(op.path);
          const old = kids(parent)[op.index];
          const node = createNode(op.node, childNamespace(parent));
          parent.insertBefore(node, old);
          leave(old);
          enter(node);
          break;
        }
        case "move": {
          // Pop then insert, exactly like dommodel.py: removal happens first,
          // so `to` indexes the list *after* the node has come out.
          const parent = nodeAt(op.path);
          const node = kids(parent)[op.from];
          node.remove();
          parent.insertBefore(node, kids(parent)[op.to] || null);
          break;
        }
        case "set_text": {
          nodeAt(op.path).textContent = op.text;
          break;
        }
        case "set_attrs": {
          setAttrs(nodeAt(op.path), op.set || {}, op.remove || []);
          break;
        }
        case "set_events": {
          setEvents(nodeAt(op.path), op.set || {}, op.remove || []);
          break;
        }
        case "set_key": {
          // Keys are differ bookkeeping; they have no DOM representation.
          break;
        }
        default:
          throw new Error(`unknown op ${op.op}`);
      }
    }
    if (flips && flips.size) playFlips(flips);
  }

  // Elements the keyboard can reach. Focus guards (a dialog's Tab-wrapping
  // sentinels) are reachable too but never a target themselves.
  const FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
    'select:not([disabled]), textarea:not([disabled]), [contenteditable="true"], ' +
    '[tabindex]:not([tabindex="-1"])';

  const focusables = (el) =>
    [...el.querySelectorAll(FOCUSABLE)].filter(
      (e) => !e.hasAttribute("data-focus-guard") && e.getClientRects().length
    );

  const savedFocus = [];

  // <Head> content (Renderer.head): the elements this runtime added to
  // document.head carry data-pyweft-head, and are replaced as a set; ones
  // pre-rendered into the page carry it too. A <title> sets the page title
  // while one is shown, and the title from before comes back after.
  let titleBefore = null;
  const textOf = (dict) => dict.type === "text" ? dict.text : (dict.children || []).map(textOf).join("");

  function setHead(nodes) {
    for (const old of document.head.querySelectorAll("[data-pyweft-head]")) old.remove();
    let title = null;
    for (const dict of nodes) {
      if (dict.type !== "element") continue;
      if (dict.tag === "title") {
        title = textOf(dict);
        continue;
      }
      const el = createNode(dict);
      el.setAttribute("data-pyweft-head", "");
      document.head.appendChild(el);
    }
    if (title !== null) {
      // The app's own title, even when the page was pre-rendered with a
      // <Head> title in place of it.
      const shell = document.querySelector("title[data-pyweft-title]");
      if (titleBefore === null) titleBefore = shell ? shell.dataset.pyweftTitle : document.title;
      document.title = title;
    } else if (titleBefore !== null) {
      document.title = titleBefore;
      titleBefore = null;
    }
  }

  // Requests from Python's focus(), scroll_to() ... (Renderer.take_commands),
  // run once the render they refer to is on the page. Not patch ops: they
  // change no node, so dommodel.py has nothing to mirror.
  function runCommands(commands) {
    for (const cmd of commands) {
      const el = cmd.path ? nodeAt(cmd.path) : null;
      switch (cmd.op) {
        case "focus": {
          // A component's root is often a wrapper: focus what's inside.
          const target = el && (el.matches(FOCUSABLE) || el.hasAttribute("tabindex") ? el : focusables(el)[0]);
          target?.focus();
          break;
        }
        case "focus_first":
          el && focusables(el)[0]?.focus();
          break;
        case "focus_last":
          el && focusables(el).at(-1)?.focus();
          break;
        case "scroll_to":
          el?.scrollIntoView({ block: cmd.align || "nearest" });
          break;
        case "keep_in_view": {
          // Measured where its CSS put it, then nudged back inside the
          // window with `translate`, which leaves `transform` (and any
          // animation using it) alone. 8px of margin from either edge;
          // up and down too only when asked (cmd.vertical).
          if (!el) break;
          el.style.translate = "";
          const box = el.getBoundingClientRect();
          const width = document.documentElement.clientWidth;
          const height = document.documentElement.clientHeight;
          let dx = 0;
          let dy = 0;
          // Beside its anchor (the offset parent): try the anchor's other
          // side first, keeping the same gap, before sliding over it.
          const anchor = cmd.flip && el.offsetParent ? el.offsetParent.getBoundingClientRect() : null;
          if (anchor && box.right > width - 8 && box.left >= anchor.right) {
            const left = anchor.left - (box.left - anchor.right) - box.width;
            if (left >= 8) dx = left - box.left;
          } else if (anchor && box.left < 8 && box.right <= anchor.left) {
            const left = anchor.right + (anchor.left - box.right);
            if (left + box.width <= width - 8) dx = left - box.left;
          }
          if (box.right + dx > width - 8) dx = width - 8 - box.right;
          if (box.left + dx < 8) dx = 8 - box.left;
          if (cmd.vertical) {
            if (box.bottom > height - 8) dy = height - 8 - box.bottom;
            if (box.top + dy < 8) dy = 8 - box.top;
          }
          if (dx || dy) el.style.translate = `${Math.round(dx)}px ${Math.round(dy)}px`;
          break;
        }
        case "save_focus":
          savedFocus.push(document.activeElement);
          break;
        case "set_title":
          document.title = cmd.text;
          break;
        case "head":
          setHead(cmd.nodes);
          break;
        case "restore_focus": {
          const target = savedFocus.pop();
          if (target && target.isConnected) target.focus();
          break;
        }
        default:
          throw new Error(`unknown command ${cmd.op}`);
      }
    }
  }

  return { init, mount, applyOps, runCommands, options };
})();
