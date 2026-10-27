"""run_in_background: lookup by name, pickling both ways, hosts, errors."""

import asyncio
import math
import subprocess
import sys
import threading

import pytest

from pyweft import BackgroundError, Renderer, load_component, run_in_background
from pyweft import background

APP = """
<template><p><button @click="analyse">go</button>{{ status }}</p></template>
<code>
from pyweft import run_in_background

status: str = "idle"
rows: list = [3, 1, 2]

async def analyse(self):
    self.status = "working"
    self.status = await run_in_background(build_report, self.rows, title="R")

def build_report(rows, title=""):
    return f"{title}: {sorted(rows)} by {helper()}"

def helper():
    return "helper"

def fails(n):
    raise ValueError(f"bad {n}")

def where_am_i():
    import threading
    return threading.current_thread().name
</code>
"""


@pytest.fixture(autouse=True)
def no_host():
    background.set_host(None)
    yield
    background.set_host(None)


def load(tmp_path, src=APP):
    path = tmp_path / "app.weft"
    path.write_text(src, encoding="utf-8")
    return load_component(path)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- lookups


def test_component_handler_runs_weft_function_with_its_helpers(tmp_path):
    App = load(tmp_path)

    async def main():
        app = App()
        r = Renderer(app)
        click = r.render()[0].children[0].events["click"]
        r.dispatch(click, {})
        assert app.status == "working"
        await r.idle()
        assert app.status == "R: [1, 2, 3] by helper"

    run(main())


def test_without_a_host_it_runs_on_a_thread(tmp_path):
    App = load(tmp_path)
    name = run(run_in_background(App.where_am_i))
    assert name != threading.main_thread().name


def test_module_and_builtin_functions():
    assert run(run_in_background(math.factorial, 10)) == 3628800
    assert run(run_in_background(sorted, [3, 1, 2], reverse=True)) == [3, 2, 1]


def test_weft_ref_points_at_the_file(tmp_path):
    App = load(tmp_path)
    kind, path, name = background.function_ref(App.build_report)
    assert kind == "weft" and path.endswith("app.weft") and name == "build_report"


@pytest.mark.parametrize(
    "make_fn, message",
    [
        (lambda App: (lambda x: x), "lambdas and nested"),
        (lambda App: App().analyse, "not the method"),
        (lambda App: _nested(), "lambdas and nested"),
    ],
)
def test_functions_that_cannot_be_found_by_name_are_rejected(tmp_path, make_fn, message):
    App = load(tmp_path)
    with pytest.raises(TypeError, match=message):
        run(run_in_background(make_fn(App), 1))


def _nested():
    def inner(x):
        return x

    return inner


def test_unpicklable_arguments_are_rejected_up_front(tmp_path):
    App = load(tmp_path)
    with pytest.raises(TypeError, match="picklable"):
        run(run_in_background(App.build_report, [threading.Lock()]))


# ----------------------------------------------------------------- errors


def test_exception_is_reraised_with_its_type_and_where_it_happened(tmp_path):
    App = load(tmp_path)
    with pytest.raises(ValueError, match="bad 7") as info:
        run(run_in_background(App.fails, 7))
    notes = "".join(getattr(info.value, "__notes__", []))
    if sys.version_info >= (3, 11):
        assert "app.weft" in notes and "line" in notes


def test_error_display_points_at_the_line_in_the_background_function(tmp_path):
    from pyweft.hotreload import format_error

    App = load(tmp_path, APP.replace(
        "self.status = await run_in_background(build_report, self.rows, title=\"R\")",
        "self.status = await run_in_background(fails, 1)",
    ))
    with pytest.raises(ValueError) as info:
        run(run_in_background(App.fails, 1))
    text = format_error(info.value)
    line = APP.split("\n").index('    raise ValueError(f"bad {n}")') + 1
    assert f'app.weft, line {line}: raise ValueError(f"bad {{n}}")' in text
    assert text.endswith("ValueError: bad 1")


class _Unpicklable(Exception):
    def __reduce__(self):
        raise TypeError("nope")


def _raise_unpicklable():
    raise _Unpicklable("odd")


def _return_unpicklable():
    return threading.Lock()


def test_unpicklable_exception_becomes_background_error():
    with pytest.raises(BackgroundError, match="_Unpicklable: odd"):
        run(run_in_background(_raise_unpicklable))


def test_unpicklable_result_becomes_background_error():
    with pytest.raises(BackgroundError, match="could not be pickled"):
        run(run_in_background(_return_unpicklable))


# ------------------------------------------------------------------ hosts


class SubprocessHost:
    """Runs each call in a fresh Python process: a separate interpreter,
    like the browser's worker, so lookup by name is tested for real."""

    def __init__(self):
        self.calls = 0
        self.warmed = False

    async def call(self, request):
        self.calls += 1
        code = (
            "import sys; from pyweft.background import execute; "
            "sys.stdout.buffer.write(execute(sys.stdin.buffer.read()))"
        )
        done = await asyncio.to_thread(
            subprocess.run, [sys.executable, "-c", code], input=request,
            capture_output=True, check=True,
        )
        return done.stdout

    def warm_up(self):
        self.warmed = True


def test_host_receives_calls_and_another_interpreter_finds_the_function(tmp_path):
    App = load(tmp_path)
    host = SubprocessHost()
    background.set_host(host)
    assert run(run_in_background(App.build_report, [2, 1], title="T")) == (
        "T: [1, 2] by helper"
    )
    with pytest.raises(ValueError, match="bad 3"):
        run(run_in_background(App.fails, 3))
    assert host.calls == 2

    background.warm_up()
    assert host.warmed


def test_edited_file_is_picked_up_by_the_background_side(tmp_path):
    App = load(tmp_path)
    ref = background.function_ref(App.helper)
    assert background.resolve(ref)() == "helper"
    path = tmp_path / "app.weft"
    path.write_text(APP.replace('return "helper"', 'return "edited!"'), encoding="utf-8")
    assert background.resolve(ref)() == "edited!"


def test_cancelled_wait_does_not_break_later_calls(tmp_path):
    App = load(tmp_path)

    async def main():
        task = asyncio.ensure_future(run_in_background(App.build_report, [1]))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return await run_in_background(App.build_report, [5], title="ok")

    assert run(main()) == "ok: [5] by helper"


# ------------------------------------------------------------------- CLI


def test_build_ships_the_worker(tmp_path):
    from pyweft.cli import cmd_build

    (tmp_path / "app.weft").write_text(APP, encoding="utf-8")
    cmd_build(tmp_path, tmp_path / "dist")
    assert "loadPyodide" in (tmp_path / "dist" / "worker.js").read_text(encoding="utf-8")
    assert (tmp_path / "dist" / "pyweft-src" / "background.py").is_file()
