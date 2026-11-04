"""Input masks: pyweft.masks, and runtime.js agreeing with it."""

import json
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pyweft import masks

PHONE = "(999) 999-9999"


@pytest.mark.parametrize("mask, text, shown", [
    (PHONE, "5551234567", "(555) 123-4567"),
    (PHONE, "(555) 123-4567", "(555) 123-4567"),
    (PHONE, "555", "(555"),                   # no literal after the last character
    (PHONE, "5", "(5"),
    (PHONE, "", ""),
    (PHONE, "55a5-12", "(555) 12"),           # a letter can't go in a 9
    (PHONE, "555123456789", "(555) 123-4567"),  # extra characters are dropped
    ("99/99/9999", "03112026", "03/11/2026"),
    ("+1 (999) 999", "+1 (555) 12", "+1 (555) 12"),  # the literal 1 isn't typed
    ("+1 (999) 999", "555", "+1 (555"),
    ("aa-9999", "ab1234", "ab-1234"),
    ("****-****", "ab12cd34", "ab12-cd34"),
    ("\\9-999", "123", "9-123"),               # \ makes 9 literal
])
def test_apply(mask, text, shown):
    assert masks.apply(mask, text) == shown


def test_complete_slots_and_typed():
    assert masks.slots(PHONE) == 10
    assert masks.complete(PHONE, "(555) 123-4567") and not masks.complete(PHONE, "(555) 123")
    assert masks.typed(PHONE, "(555) 123-4567") == "5551234567"
    assert masks.fill(PHONE, "5551")[1] == [2, 3, 4, 7]  # where each typed char ends


# ------------------------------------------------------------------ runtime.js

RUNTIME = Path(__file__).parent.parent / "src" / "pyweft" / "static" / "runtime.js"


def _js_mask_functions():
    src = RUNTIME.read_text(encoding="utf-8")
    start = src.index("  const MASK_SLOTS")
    end = src.index("  function applyMask")
    return src[start:end]


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_runtime_js_masks_like_python():
    rng = random.Random(7)
    masks_ = [PHONE, "99/99/9999", "+1 (999) 999", "aa-9999", "****-****", "\\9-999", "999.999"]
    alphabet = "0123456789abcXYZ()-/ +."
    cases = [(m, "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14))))
             for m in masks_ for _ in range(40)]
    script = _js_mask_functions() + """
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map(([mask, text]) => {
  const toks = maskTokens(mask);
  return maskFill(toks, maskTyped(toks, text));
})));
"""
    out = subprocess.run(["node", "-e", script], input=json.dumps(cases), capture_output=True,
                         text=True, encoding="utf-8", check=True)
    got = json.loads(out.stdout)
    for (mask, text), (shown, ends) in zip(cases, got):
        assert [shown, ends] == list(masks.fill(mask, masks.typed(mask, text))), (mask, text)
