"""``run_in_background``: run a plain function off the UI thread.

The core does not know what "off the UI thread" means on a given target, so a
host provides it. The browser host runs calls in a Web Worker: a second
Pyodide on its own browser thread, so the page keeps responding. With no host
installed (headless tests; the desktop target until its host exists) a call
runs on a thread via ``asyncio.to_thread``.

The worker is a separate interpreter, so a function cannot be sent there as
an object. It is sent by *name* -- an importable module plus a qualified name,
or a ``.weft`` file plus a name defined at the top level of its ``<code>``
block -- and the worker looks it up in its own copy of that code. Arguments
and the result travel pickled, both ways. The thread fallback goes through
exactly the same lookup and pickling, so what works in a headless test works
in the browser, and what would fail in the browser fails in the test too.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import pickle
import traceback
from typing import Any, Callable, Protocol


class BackgroundError(RuntimeError):
    """A background call failed in a way that could not be raised as the
    original exception (it could not be pickled), or could not be made."""


class BackgroundHost(Protocol):
    """What a host provides. ``call`` takes a request from ``pack_call`` and
    returns the reply that ``execute`` produced for it, wherever it ran."""

    async def call(self, request: bytes) -> bytes: ...

    def warm_up(self) -> None: ...


_host: BackgroundHost | None = None


def set_host(host: BackgroundHost | None) -> None:
    global _host
    _host = host


async def run_in_background(fn: Callable, /, *args: Any, **kwargs: Any) -> Any:
    """Run ``fn(*args, **kwargs)`` off the UI thread and return its result.

    ``fn`` must be a plain function the background side can find by name:
    defined at the top level of a ``.weft`` code block, or in an importable
    module (the standard library, a PyPI package). Not a method, lambda or
    nested function: it runs in another interpreter and cannot see the
    component. Arguments and the return value must be picklable.

    Exceptions raised by ``fn`` are re-raised here. If the awaiting task is
    cancelled, a call that has not started yet is dropped; one already
    running finishes and its result is thrown away.
    """
    request = pack_call(fn, args, kwargs)
    if _host is None:
        reply = await asyncio.to_thread(execute, request)
    else:
        reply = await _host.call(request)
    return unpack_reply(reply)


def warm_up() -> None:
    """Start the background worker now, so the first ``run_in_background``
    doesn't wait for it (in the browser that is a few seconds). Optional."""
    if _host is not None:
        _host.warm_up()


# ------------------------------------------------------------- the request


def function_ref(fn: Callable) -> tuple[str, str, str]:
    """How the background side finds ``fn``: ``("module", name, qualname)``
    or ``("weft", path, name)``."""
    if getattr(fn, "__self__", None) is not None and not isinstance(
        getattr(fn, "__self__"), type(os)
    ):
        raise TypeError(
            f"run_in_background needs a plain function, not the method "
            f"{getattr(fn, '__qualname__', fn)!r}: it runs in another "
            "interpreter and cannot see the object. Define it at the top of "
            "the <code> block (no self) and pass the data it needs."
        )
    qualname = getattr(fn, "__qualname__", None)
    if not qualname or "<lambda>" in qualname or "<locals>" in qualname:
        raise TypeError(
            "run_in_background needs a function defined at the top level of "
            "a <code> block or a module, so it can be found by name; got "
            f"{qualname or fn!r} (lambdas and nested functions cannot be)"
        )
    module = getattr(fn, "__module__", None)
    code = getattr(fn, "__code__", None)
    if module is None and code is not None and code.co_filename.endswith(".weft"):
        return ("weft", code.co_filename, qualname)
    if module and module != "__main__":
        return ("module", module, qualname)
    raise TypeError(
        f"run_in_background cannot find {qualname!r} by name: define it at "
        "the top level of a .weft <code> block or in an importable module"
    )


def pack_call(fn: Callable, args: tuple, kwargs: dict) -> bytes:
    ref = function_ref(fn)
    try:
        return pickle.dumps((ref, args, kwargs))
    except Exception as exc:
        raise TypeError(
            f"the arguments to run_in_background({ref[2]}, ...) must be "
            f"picklable: {exc}"
        ) from None


def unpack_reply(reply: bytes) -> Any:
    status, value, where = pickle.loads(reply)
    if status == "ok":
        return value
    text, frames = where
    if hasattr(value, "add_note"):  # 3.11+
        value.add_note(f"Raised in the background, by:\n{text}")
    # (file, line, code) frames, so error displays can point at the line
    # in the background function, not only at the await that received it.
    value._pyweft_background_frames = frames
    raise value


# --------------------------------------------------- the background side


# path -> ((mtime_ns, size), namespace). Keyed on the file's stat so a worker
# whose files were updated by hot reload runs the new code.
_weft_namespaces: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def _weft_namespace(path: str) -> dict[str, Any]:
    from .component import compile_code_block

    st = os.stat(path)
    stamp = (st.st_mtime_ns, st.st_size)
    cached = _weft_namespaces.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    with open(path, encoding="utf-8") as f:
        src = f.read()
    namespace: dict[str, Any] = {"__name__": f"weft:{os.path.basename(path)}"}
    exec(compile_code_block(src, path), namespace)
    _weft_namespaces[path] = (stamp, namespace)
    return namespace


def resolve(ref: tuple[str, str, str]) -> Callable:
    kind, where, qualname = ref
    if kind == "weft":
        target: Any = _weft_namespace(where)
        first, *rest = qualname.split(".")
        target = target[first]
    else:
        target = importlib.import_module(where)
        rest = qualname.split(".")
    for part in rest:
        target = getattr(target, part)
    return target


def execute(request: bytes) -> bytes:
    """Run a packed call and pack its outcome. This is what the worker runs;
    it never raises, so every failure reaches the caller."""
    try:
        ref, args, kwargs = pickle.loads(request)
        fn = resolve(ref)
        result = fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 -- all of it goes back
        return _pack_error(exc)
    try:
        return pickle.dumps(("ok", result, ""))
    except Exception as exc:
        return _pack_error(
            BackgroundError(f"the result of {ref[2]} could not be pickled: {exc}")
        )


def _pack_error(exc: BaseException) -> bytes:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    frames = [
        (f.filename, f.lineno, f.line) for f in traceback.extract_tb(exc.__traceback__)
    ]
    where = (text, frames)
    try:
        payload = pickle.dumps(("error", exc, where))
        pickle.loads(payload)  # some exceptions pickle but do not unpickle
        return payload
    except Exception:
        portable = BackgroundError(f"{type(exc).__name__}: {exc}")
        return pickle.dumps(("error", portable, where))
