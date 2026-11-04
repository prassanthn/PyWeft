/* PyWeft browser runtime: applies patch ops to real DOM nodes.
 *
 * This file is the JS twin of src/pyweft/dommodel.py -- whatever that file does
 * to dicts, this one must do to DOM nodes. Keep them in lockstep.
 *
 * The container element acts as the virtual root: patch paths index into
 * childNodes exactly as they index into the dict tree, which holds because the
 * runtime alone builds and mutates the container's subtree (the parser already
 * dropped formatting whitespace, so there are no stray text nodes).
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
      node = node.childNodes[index];
    }
    return node;
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

  function ensureListener(el, spec) {
    if (!el._pyweftBound) el._pyweftBound = {};
    if (el._pyweftBound[spec]) return;
    el._pyweftBound[spec] = true;
    const [name, ...mods] = spec.split(".");
    // Browsers fire no click for the right or middle button.
    let type = name;
    if (name === "click" && mods.includes("right")) type = "contextmenu";
    if (name === "click" && mods.includes("middle")) type = "mouseup";
    el.addEventListener(
      type,
      (ev) => {
        const events = el._pyweftEvents;
        if (!events || !(spec in events)) return; // unbound since; a no-op, matching the renderer
        if (!accepts(ev, mods)) return;
        if (mods.includes("prevent")) ev.preventDefault();
        if (mods.includes("stop")) ev.stopPropagation();
        const handlerId = events[spec];
        if (handlerId) dispatch(handlerId, eventPayload(ev));
      },
      {
        capture: mods.includes("capture"),
        once: mods.includes("once"),
        passive: mods.includes("passive"),
      }
    );
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
    for (const op of ops) {
      switch (op.op) {
        case "insert": {
          const parent = nodeAt(op.path);
          const node = createNode(op.node, childNamespace(parent));
          parent.insertBefore(node, parent.childNodes[op.index] || null);
          break;
        }
        case "remove": {
          nodeAt(op.path).childNodes[op.index].remove();
          break;
        }
        case "replace": {
          const parent = nodeAt(op.path);
          parent.replaceChild(createNode(op.node, childNamespace(parent)), parent.childNodes[op.index]);
          break;
        }
        case "move": {
          // Pop then insert, exactly like dommodel.py: removal happens first,
          // so `to` indexes the list *after* the node has come out.
          const parent = nodeAt(op.path);
          const node = parent.childNodes[op.from];
          node.remove();
          parent.insertBefore(node, parent.childNodes[op.to] || null);
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
          el?.scrollIntoView({ block: "nearest" });
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
