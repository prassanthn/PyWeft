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

  function init(el, dispatchFn) {
    container = el;
    dispatch = dispatchFn;
    container.replaceChildren();
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

  function createNode(dict) {
    if (dict.type === "text") {
      return document.createTextNode(dict.text);
    }
    const el = document.createElement(dict.tag);
    setAttrs(el, dict.attrs || {}, []);
    setEvents(el, dict.events || {}, []);
    for (const child of dict.children || []) {
      el.appendChild(createNode(child));
    }
    return el;
  }

  function setAttrs(el, set, remove) {
    for (const name of remove) {
      if (name === "value" && "value" in el) el.value = "";
      el.removeAttribute(name);
    }
    for (const [name, value] of Object.entries(set)) {
      // "value" must land on the live property, not just the attribute, or a
      // re-render never updates an input the user has typed in. Skip the write
      // when it already matches so the caret position survives.
      if (name === "value" && "value" in el) {
        if (el.value !== value) el.value = value;
      } else if (name === "checked" && "checked" in el) {
        el.checked = Boolean(value);
      } else {
        el.setAttribute(name, value);
      }
    }
  }

  /* Handler ids live in a map on the element and are resolved at fire time,
   * so set_events just updates the map -- listeners are added once per event
   * name and never need rebinding when a diff swaps the id. */
  function setEvents(el, set, remove) {
    if (!el._pyweftEvents) el._pyweftEvents = {};
    for (const name of remove) {
      delete el._pyweftEvents[name];
    }
    for (const [name, handlerId] of Object.entries(set)) {
      ensureListener(el, name);
      el._pyweftEvents[name] = handlerId;
    }
  }

  function ensureListener(el, name) {
    if (!el._pyweftBound) el._pyweftBound = {};
    if (el._pyweftBound[name]) return;
    el._pyweftBound[name] = true;
    el.addEventListener(name, (ev) => {
      const handlerId = el._pyweftEvents && el._pyweftEvents[name];
      if (!handlerId) return; // unbound since; a no-op, matching the renderer
      dispatch(handlerId, eventPayload(ev));
    });
  }

  function eventPayload(ev) {
    const payload = {};
    const target = ev.target;
    if (target && "value" in target) payload.value = target.value;
    if (target && target.type === "checkbox") payload.checked = target.checked;
    return payload;
  }

  function applyOps(ops) {
    for (const op of ops) {
      switch (op.op) {
        case "insert": {
          const parent = nodeAt(op.path);
          parent.insertBefore(createNode(op.node), parent.childNodes[op.index] || null);
          break;
        }
        case "remove": {
          nodeAt(op.path).childNodes[op.index].remove();
          break;
        }
        case "replace": {
          const parent = nodeAt(op.path);
          parent.replaceChild(createNode(op.node), parent.childNodes[op.index]);
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

  return { init, mount, applyOps };
})();
