"""pyweft check: what it finds, where, and that a good app is clean."""

import importlib.util
import json
import textwrap

from pyweft.check import check_app
from pyweft.cli import main


def make(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    return tmp_path


def found(tmp_path, files):
    problems, _ = check_app(make(tmp_path, files))
    return [(p.file, p.line, p.severity, p.code) for p in problems], problems


GOOD = {
    "app.weft": """
        <template>
          <div>
            <Row :item="{'name': 'a'}" label="Hi" @pick="chosen = event" class="wide" aria-label="row">
              <Fill name="extra"><b>{{ note }} {{ item_count }}</b></Fill>
              <i>{{ label_text }}</i>
            </Row>
            <For each="n in numbers" key="n" index="i"><p @click="pick(n)">{{ i }}: {{ n * 2 }}</p></For>
            <input @bind="text" @keydown.enter="save" />
            <p>{{ [x for x in numbers if x > 1] }}</p>
          </div>
        </template>
        <code>
        numbers: list = [1, 2, 3]
        text: str = ""
        chosen = None
        label_text: str = "x"

        def on_init(self):
            self._ready = True

        def pick(self, n):
            self.chosen = n

        def save(self):
            self.text = ""
        </code>
        """,
    "row.weft": """
        <template>
          <div @click="emit('pick', item)">
            <Slot name="extra" :item_count="len(item)" :note="'n'" />
            <Slot />
          </div>
        </template>
        <code>
        item = None
        label: str = ""
        </code>
        """,
}


def test_a_good_app_is_clean(tmp_path, capsys):
    rows, problems = found(tmp_path, GOOD)
    # The list comprehension reads only its own variable and the outer
    # iterable: fine everywhere.
    assert problems == [], problems
    assert main(["check", str(tmp_path)]) == 0
    assert "No problems found in 2 component files." in capsys.readouterr().out


def test_names_handlers_and_bind(tmp_path):
    rows, problems = found(tmp_path, {"app.weft": """
        <template>
          <div>
            <p>{{ cout }}</p>
            <button @click="incremnt">+</button>
            <button @click="count += 1; totl = 2">+</button>
            <input @bind="nme" />
            <If cond="missing_flag"><p/></If>
          </div>
        </template>
        <code>
        count: int = 0
        name: str = ""
        total: int = 0

        def increment(self):
            self.count += 1
        </code>
        """})
    assert rows == [
        ("app.weft", 3, "error", "unknown-name"),
        ("app.weft", 4, "error", "unknown-handler"),
        ("app.weft", 5, "warning", "new-state"),
        ("app.weft", 6, "error", "unknown-bind"),
        ("app.weft", 7, "error", "unknown-name"),
    ]
    messages = [p.message for p in problems]
    assert "did you mean 'count'?" in messages[0]
    assert "did you mean 'increment'?" in messages[1]
    assert "did you mean 'total'?" in messages[2]
    assert "did you mean 'name'?" in messages[3]


def test_components_props_events_slots(tmp_path):
    rows, problems = found(tmp_path, {
        "app.weft": """
            <template>
              <div>
                <Card lable="Hi" title="t" data-x="1" @closd="x = 1" @open.prevent="x = 2">
                  <Fill name="footr">f</Fill>
                </Card>
                <Plain>loose</Plain>
                <Card @bind="x" />
              </div>
            </template>
            <code>
            x = 0
            </code>
            """,
        "card.weft": """
            <template><div @click="emit('open')"><Slot name="footer" /><button @click="emit('close')"/></div></template>
            <code>
            label: str = ""
            </code>
            """,
        "plain.weft": "<template><p>no slots</p></template>",
    })
    codes = [(r[1], r[3]) for r in rows if r[0] == "app.weft"]
    assert codes == [  # errors first on a line, then warnings
        (3, "component-event-modifier"),
        (3, "unknown-prop"),
        (3, "unknown-event"),
        (4, "unknown-slot"),
        (6, "unknown-slot"),
        (7, "component-bind"),
    ]
    text = " ".join(p.message for p in problems)
    assert "'lable' is not one of its props" in text and "did you mean 'label'?" in text
    assert "never emits 'closd'" in text and "did you mean 'close'?" in text
    assert "did you mean 'footer'?" in text
    # title= is a global attribute: it may go to the root, no warning.
    assert "'title'" not in text


def test_traps(tmp_path):
    rows, problems = found(tmp_path, {"app.weft": """
        <template>
          <div>
            <For each="r in rows" key="r"><p>{{ r }}</p><p>again</p></For>
            <p class="a" :class="'b'">x</p>
            <For each="r in rows" key="r"><p>{{ sum(r * scale for r in rows) }}</p></For>
            <p>{{ [r * scale for r in rows] }}</p>
            <p :title="(lambda: scale)()">x</p>
          </div>
        </template>
        <code>
        rows: list = [1, 2]
        scale: int = 2
        max: int = 10

        def biggest(self):
            return max(self.rows)
        </code>
        """})
    assert rows == [
        ("app.weft", 3, "error", "keyed-for"),
        ("app.weft", 4, "warning", "class-replaced"),
        ("app.weft", 5, "error", "template-closure"),
        ("app.weft", 6, "warning", "template-closure"),
        ("app.weft", 7, "error", "template-closure"),
        ("app.weft", 16, "warning", "shadowed-builtin"),
    ]
    assert "max(...) calls this component's 'max'" in problems[-1].message


def test_load_errors_with_lines(tmp_path):
    rows, problems = found(tmp_path, {
        "app.weft": """
            <template>
              <div>
                <Widgt />
              </div>
            </template>
            """,
        "widget.weft": "<template><p>ok</p></template>",
        "broken.weft": """
            <template>
              <div>
                <p>unclosed
              </div>
            </template>
            """,
        "bad_code.weft": """
            <template><p/></template>
            <code>
            def oops(self)
                return 1
            </code>
            """,
        "raises.weft": """
            <template><p/></template>
            <code>
            x = 1
            y = 1 / 0
            </code>
            """,
        "needs.weft": """
            <template><p/></template>
            <code>
            import not_a_real_module_xyz
            </code>
            """,
    })
    assert ("app.weft", 3, "error", "unknown-component") in rows
    assert "did you mean 'Widget'?" in next(p.message for p in problems if p.code == "unknown-component")
    assert ("broken.weft", 4, "error", "template") in rows
    assert ("bad_code.weft", 3, "error", "syntax") in rows
    assert ("raises.weft", 4, "error", "code-block") in rows
    assert ("needs.weft", 3, "error", "import") in rows


def test_library_tags_get_suggestions_and_browser_imports_pass(tmp_path):
    rows, problems = found(tmp_path, {"app.weft": """
        <template><div><ui.Sldier /><ui.Button lable="x">Go</ui.Button></div></template>
        <code>
        import js
        from pyweft_ui import ui
        </code>
        """})
    text = " ".join(p.message for p in problems)
    assert "did you mean 'ui.Slider'?" in text
    # (The missing component stops the load, so the Button isn't reached.)
    assert all(p.code != "import" for p in problems)


def test_json_output_and_exit_code(tmp_path, capsys):
    make(tmp_path, {"app.weft": "<template><p>{{ nope }}</p></template>"})
    assert main(["check", str(tmp_path), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["files"] == 1
    assert data["problems"] == [{
        "file": "app.weft", "line": 1, "severity": "error", "code": "unknown-name",
        "message": "{{ }}: unknown name 'nope'",
    }]


def test_the_examples_and_gallery_are_clean():
    from pathlib import Path

    root = Path(__file__).parent.parent
    # The todo example's own dependency comes with the website group, which
    # CI's test run doesn't install; check reports that as an import error.
    absent = [] if importlib.util.find_spec("humanize") else ["no module named 'humanize'"]
    for app in ("examples/todo", "examples/shop", "packages/pyweft-ui/gallery"):
        problems, files = check_app(root / app, deps=False)   # (PyPI is off in tests)
        problems = [p for p in problems if not (p.code == "import" and any(a in p.message for a in absent))]
        assert files and [str(p) for p in problems] == [], app


def test_a_new_app_is_clean(tmp_path):
    from pyweft.cli import cmd_new

    cmd_new(tmp_path / "fresh")
    problems, files = check_app(tmp_path / "fresh")
    assert files == 1 and problems == []
