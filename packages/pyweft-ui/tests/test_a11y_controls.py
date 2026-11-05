"""Every control passes pyweft check's accessibility rules: apps can't
check the toolkit's markup themselves, so the toolkit checks it here. An
exception carries a pyweft-ignore comment saying where its keyboard way is."""

from pathlib import Path

import pyweft_ui
from pyweft.a11y import audit, ignored
from pyweft.component import is_component_tag
from pyweft.parser import block_spans, parse_template, split_source


def test_controls_are_accessible():
    found = []
    for path in sorted(Path(pyweft_ui.__file__).parent.glob("*.weft")):
        src = path.read_text(encoding="utf-8")
        template, _, _ = split_source(src)
        first = src.count("\n", 0, block_spans(src)["template"][0]) + 1
        lines = src.splitlines()

        def add(line, severity, code, message, path=path, lines=lines):
            if not ignored(lines, line, code):
                found.append(f"{path.name}:{line}: {message} [{code}]")

        audit(parse_template(template, first), add, is_component_tag)
    assert found == []
