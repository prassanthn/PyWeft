"""The guide for AI coding assistants: written by `pyweft new` and
`pyweft agents`, and kept true. Its example component must work, the names
it mentions must exist, and its template snippets must parse: a wrong guide
is worse than none, since assistants follow it."""

import re

import pytest

import pyweft
from pyweft import Renderer, component_from_source
from pyweft.cli import CliError, agents_guide, cmd_agents, cmd_new, main
from pyweft.parser import parse_template
from pyweft.vdom import Element

GUIDE = agents_guide()


def blocks(lang):
    return re.findall(rf"```{lang}\n(.*?)```", GUIDE, re.S)


def test_new_apps_get_agents_md_and_claude_md(tmp_path):
    target = tmp_path / "app"
    cmd_new(target)
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert agents == GUIDE and f"pyweft {pyweft.__version__}" in agents
    assert "{version}" not in agents
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_agents_command_refreshes_and_keeps_an_existing_claude_md(tmp_path, capsys):
    (tmp_path / "app.weft").write_text("<template><p/></template>", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("old", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("my own notes\n", encoding="utf-8")
    assert main(["agents", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == GUIDE
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "my own notes\n"
    assert "wrote AGENTS.md in" in capsys.readouterr().out


def test_agents_command_needs_an_app(tmp_path):
    with pytest.raises(CliError, match="no app.weft"):
        cmd_agents(tmp_path)


def test_the_example_component_works():
    source = blocks("xml")[0]
    assert source.lstrip().startswith("<template>") and "<code>" in source
    App = component_from_source(source, "Todo")
    app = App()
    renderer = Renderer(app)
    renderer.init_root()
    renderer.render()
    app.text = "  Write docs "
    app.add()
    app.text = "Ship"
    app.add()
    assert [i["text"] for i in app.items] == ["Write docs", "Ship"] and app.text == ""
    app.toggle(app.items[0])
    assert app.left == 1
    app.remove(app.items[1])
    tree = renderer.render()

    def texts(nodes):
        out = []
        for n in nodes:
            if isinstance(n, Element):
                out.extend(texts(n.children))
            else:
                out.append(n.text)
        return out

    flat = " ".join(" ".join(texts(tree)).split())
    assert "Write docs" in flat and "Ship" not in flat and "0 left" in flat


def test_template_snippets_parse():
    for snippet in blocks("xml")[1:]:
        if "<template>" in snippet:
            continue
        # Snippets are fragments: wrap them in one root to parse.
        parse_template(f"<div>{snippet}</div>")


def test_names_it_imports_from_pyweft_exist():
    imported = set()
    for line in re.findall(r"from pyweft import ([\w, ]+)", GUIDE):
        imported.update(n.strip() for n in line.split(","))
    for name in re.findall(r"`pyweft\.(\w+)`", GUIDE):
        imported.add(name)
    assert {"http", "storage", "run_in_background", "Link", "router", "effect", "Store"} <= imported
    for name in imported:
        assert hasattr(pyweft, name), name
    from pyweft import http, routing, storage

    for module, names in ((http, ["get", "post", "get_json"]), (storage, ["get", "set", "delete", "keys", "has", "clear"]),
                          (routing, ["back", "navigate"])):
        for n in names:
            assert hasattr(module, n), (module.__name__, n)


def test_the_controls_it_lists_exist():
    ui = pytest.importorskip("pyweft_ui").ui
    section = GUIDE[GUIDE.index("## pyweft-ui"):]
    names = set(re.findall(r"`([A-Z][A-Za-z]+)`", section)) - {"Form"}
    assert len(names) > 30
    for name in names:
        assert getattr(ui, name, None) is not None, name
    from pyweft_ui import Form, rules, toast  # noqa: F401  (named in the guide)
