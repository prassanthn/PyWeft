"""Will an app's dependencies install in the browser?

In the browser, micropip installs an app's dependencies as the page loads:
packages Pyodide has built (numpy, pydantic, ... at fixed versions, listed
in pyodide_packages.json for the Pyodide version PyWeft loads) and pure-
Python wheels from PyPI. Anything else (native code without a Pyodide
build, a version Pyodide doesn't have, a source-only release) makes the
page fail to load. This walks the dependency tree the way micropip would,
before anything ships, and says which package fails and why.

Approximate on purpose: PEP 440 versions and PEP 508 markers are handled
well enough for this question, without a dependency (the core has none).
Host-only: never shipped to the browser. Answers from PyPI are cached for
a day in the user's cache folder.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_SNAPSHOT = Path(__file__).parent / "pyodide_packages.json"
_PYPI = "https://pypi.org/pypi/{}/json"
_PYPI_RELEASE = "https://pypi.org/pypi/{}/{}/json"
_TTL = 24 * 3600


def pyodide_packages() -> dict[str, Any]:
    return json.loads(_SNAPSHOT.read_text(encoding="utf-8"))


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ------------------------------------------------------------------ versions

_VERSION = re.compile(
    r"^\s*v?(?:\d+!)?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-_.]?(?P<pre>a|b|c|rc|alpha|beta|pre|preview)[-_.]?(?P<pre_n>\d*))?"
    r"(?:(?:[-_.]?(?:post|rev|r)[-_.]?(?P<post>\d*))|-(?P<post2>\d+))?"
    r"(?:[-_.]?(?P<dev>dev)[-_.]?(?P<dev_n>\d*))?"
    r"(?:\+[a-z0-9.]+)?\s*$",
    re.I,
)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
_INF = float("inf")


@functools.total_ordering
class Version:
    def __init__(self, text: str):
        m = _VERSION.match(text)
        if not m:
            raise ValueError(text)
        self.text = text
        release = [int(p) for p in m["release"].split(".")]
        self.release = tuple(release)
        self.pre = (_PRE_RANK[m["pre"].lower()], int(m["pre_n"] or 0)) if m["pre"] else None
        post = m["post"] if m["post"] is not None else m["post2"]
        self.post = int(post or 0) if (m["post"] is not None or m["post2"]) else None
        self.dev = int(m["dev_n"] or 0) if m["dev"] else None

    @property
    def is_pre(self) -> bool:
        return self.pre is not None or self.dev is not None

    def key(self) -> tuple:
        release = list(self.release)
        while len(release) > 1 and release[-1] == 0:
            release.pop()
        if self.pre is None and self.post is None and self.dev is not None:
            pre: tuple = (-1, 0)
        else:
            pre = self.pre if self.pre is not None else (_INF, 0)
        post = self.post if self.post is not None else -1
        dev = self.dev if self.dev is not None else _INF
        return (tuple(release), pre, post, dev)

    def __lt__(self, other: Version) -> bool:
        return self.key() < other.key()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def __str__(self) -> str:
        return self.text


def _parse(text: str) -> Version | None:
    try:
        return Version(text)
    except ValueError:
        return None


_CLAUSE = re.compile(r"^\s*(===|==|!=|~=|<=|>=|<|>)\s*(\S+?)\s*$")


def satisfies(version: str, spec: str, allow_pre: bool = False) -> bool:
    """Does ``version`` meet a specifier such as ``">=2.7.4,<3"``? A
    pre-release only counts when ``allow_pre`` or the specifier names one."""
    v = _parse(version)
    if v is None:
        return False
    clauses = [c for c in spec.split(",") if c.strip()]
    mentions_pre = any((p := _parse(c.strip().lstrip("=!<>~").rstrip(".*"))) and p.is_pre for c in clauses)
    if v.is_pre and not (allow_pre or mentions_pre):
        return False
    for clause in clauses:
        m = _CLAUSE.match(clause)
        if not m:
            return False
        op, target = m.groups()
        if op == "===":
            if version.strip() != target:
                return False
            continue
        if target.endswith(".*"):
            prefix = [int(p) for p in target[:-2].split(".") if p.isdigit()]
            same = list(v.release[: len(prefix)]) + [0] * (len(prefix) - len(v.release)) == prefix
            if (op == "==" and not same) or (op == "!=" and same):
                return False
            continue
        t = _parse(target)
        if t is None:
            return False
        if op == "==" and not v == t:
            return False
        if op == "!=" and v == t:
            return False
        if op == ">=" and v < t:
            return False
        if op == "<=" and t < v:
            return False
        if op == ">" and not t < v:
            return False
        if op == "<" and not v < t:
            return False
        if op == "~=":
            if v < t:
                return False
            stem = list(t.release[:-1]) if len(t.release) > 1 else list(t.release)
            if list(v.release[: len(stem)]) != stem:
                return False
    return True


# ------------------------------------------------------------- requirements


@dataclass
class Requirement:
    text: str
    name: str
    extras: frozenset[str]
    spec: str
    marker: str
    url: str


_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*"
    r"(?:\[(?P<extras>[^\]]*)\])?\s*"
    r"(?:@\s*(?P<url>[^;\s]+)\s*)?"
    r"(?P<spec>\(?[^;]*?\)?)\s*"
    r"(?:;\s*(?P<marker>.+))?$"
)


def parse_requirement(text: str) -> Requirement | None:
    m = _REQ.match(text)
    if not m:
        return None
    extras = frozenset(normalise(e) for e in (m["extras"] or "").split(",") if e.strip())
    spec = (m["spec"] or "").strip().strip("()").strip()
    return Requirement(text, normalise(m["name"]), extras, spec, (m["marker"] or "").strip(), m["url"] or "")


# ------------------------------------------------------------------ markers

_MARKER_TOKEN = re.compile(
    r"\s*(\(|\)|not\s+in\b|in\b|and\b|or\b|===|==|!=|<=|>=|~=|<|>|\"[^\"]*\"|'[^']*'|[A-Za-z_][A-Za-z0-9_.]*)"
)
_VERSION_VARS = {"python_version", "python_full_version", "implementation_version"}


def browser_environment(python: str) -> dict[str, str]:
    """PEP 508 marker values inside Pyodide."""
    major_minor = ".".join(python.split(".")[:2])
    return {
        "python_version": major_minor, "python_full_version": python,
        "implementation_version": python, "implementation_name": "cpython",
        "platform_python_implementation": "CPython", "sys_platform": "emscripten",
        "platform_system": "Emscripten", "platform_machine": "wasm32",
        "platform_release": "", "platform_version": "", "os_name": "posix",
    }


def marker_holds(marker: str, env: dict[str, str], extras: frozenset[str] = frozenset()) -> bool:
    """Evaluate a PEP 508 marker; an unreadable one counts as holding (it is
    safer to check a dependency too many than to skip one)."""
    tokens = _MARKER_TOKEN.findall(marker)
    if "".join(t.replace(" ", "") for t in tokens) != re.sub(r"\s+", "", marker):
        return True
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def take() -> str:
        nonlocal pos
        pos += 1
        return tokens[pos - 1]

    def value() -> tuple[str, bool, bool]:
        token = take()
        if token[0] in "\"'":
            return token[1:-1], False, False
        if token == "extra":
            return "", True, True
        return env.get(token, ""), token in _VERSION_VARS, False

    def compare() -> bool:
        if peek() == "(":
            take()
            result = expr()
            take()  # ")"
            return result
        left, left_version, left_extra = value()
        op = re.sub(r"\s+", " ", take())
        right, right_version, right_extra = value()
        if left_extra or right_extra:
            other = right if left_extra else left
            hit = normalise(other) in extras
            return hit if op == "==" else (not hit if op == "!=" else False)
        if (left_version or right_version) and op in ("==", "!=", "<", "<=", ">", ">=", "~=", "==="):
            if left_version:
                return satisfies(left, f"{op}{right}", allow_pre=True)
            flipped = {"<": ">", ">": "<", "<=": ">=", ">=": "<="}.get(op, op)
            return satisfies(right, f"{flipped}{left}", allow_pre=True)
        if op == "in":
            return left in right
        if op == "not in":
            return left not in right
        return {"==": left == right, "!=": left != right, "<": left < right, ">": left > right,
                "<=": left <= right, ">=": left >= right}.get(op, False)

    def conj() -> bool:
        result = compare()
        while peek() == "and":
            take()
            result = compare() and result
        return result

    def expr() -> bool:
        result = conj()
        while peek() == "or":
            take()
            result = conj() or result
        return result

    try:
        return expr()
    except (IndexError, KeyError):
        return True


# --------------------------------------------------------------------- PyPI


def _cache_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "pyweft" / "cache" / "pypi"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "pyweft" / "pypi"


def fetch_json(url: str) -> dict | None:
    """PyPI's JSON for ``url``, from a day-old cache or the network; None
    for a 404. Network trouble raises OSError."""
    cache = _cache_dir() / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
    try:
        if time.time() - cache.stat().st_mtime < _TTL:
            return json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    request = urllib.request.Request(url, headers={"User-Agent": "pyweft-check", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    return data


def _pure(filename: str) -> bool:
    """A wheel any Python 3 can install: ...-py3-none-any.whl."""
    if not filename.endswith(".whl"):
        return False
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return False
    python, abi, platform = parts[-3:]
    return abi == "none" and platform == "any" and any(p.startswith("py3") or p == "py2.py3" for p in python.split("."))


# ------------------------------------------------------------------ checking


@dataclass
class Finding:
    root: str          # the app's dependency that brought this in
    severity: str      # "error" or "warning"
    code: str
    message: str


def check(
    requirements: list[str],
    fetch: Callable[[str], dict | None] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> list[Finding]:
    """What would stop these requirements installing in the browser."""
    fetch = fetch or fetch_json   # looked up now, so tests can stand in for PyPI
    data = snapshot or pyodide_packages()
    builtin = {normalise(k): v for k, v in data["packages"].items()}
    env = browser_environment(data["python"])
    pyodide = f"Pyodide {data['pyodide']}"
    findings: list[Finding] = []
    chosen: dict[str, str | None] = {}
    via: dict[str, str] = {}          # name -> who needed it first (for messages)
    done_extras: dict[str, set[str]] = {}
    queue: list[tuple[str, str, str]] = [(r, "", "") for r in requirements]  # (requirement, needed by, root)

    def needed(name: str, by: str) -> str:
        return f"{name!r} (needed by {by})" if by else repr(name)

    while queue:
        text, by, root = queue.pop(0)
        req = parse_requirement(text)
        if req is None:
            findings.append(Finding(root or text, "warning", "dependency-unreadable",
                                    f"can't read the requirement {text!r}"))
            continue
        root = root or req.name
        if req.marker and not marker_holds(req.marker, env):
            continue
        if req.url:
            findings.append(Finding(root, "warning", "dependency-url",
                                    f"{needed(req.name, by)} comes from a URL: not checked"))
            continue
        if req.name in chosen:
            have = chosen[req.name]
            if have is not None and req.spec and not satisfies(have, req.spec, allow_pre=True):
                if req.name in builtin:
                    message = (f"{needed(req.name, by)} must be {req.spec}, but the browser has {req.name} "
                               f"{have}, built into {pyodide} (it can't be replaced)")
                else:
                    message = (f"{needed(req.name, by)} must be {req.spec}, but {have} is the newest that "
                               f"installs for {via[req.name] or 'the app'}")
                findings.append(Finding(root, "error", "dependency-conflict", message))
            new_extras = set(req.extras) - done_extras.get(req.name, set())
            if have is not None and new_extras and req.name not in builtin:
                done_extras[req.name] |= new_extras
                _queue_dependencies(req.name, have, frozenset(new_extras), root, fetch, env, queue, findings)
            continue
        via[req.name] = by
        if req.name in builtin:
            version = builtin[req.name]
            chosen[req.name] = version
            if req.spec and not satisfies(version, req.spec, allow_pre=True):
                findings.append(Finding(root, "error", "dependency-version",
                                        f"{needed(req.name, by)} must be {req.spec}, but the browser has "
                                        f"{req.name} {version}, built into {pyodide} (it can't be replaced)"))
            continue
        try:
            project = fetch(_PYPI.format(req.name))
        except OSError as exc:
            findings.append(Finding(root, "warning", "dependencies-unchecked",
                                    f"couldn't reach PyPI, so whether {req.name!r} installs in the browser "
                                    f"wasn't checked ({exc})"))
            return findings
        if project is None:
            chosen[req.name] = None
            findings.append(Finding(root, "error", "dependency-missing",
                                    f"{needed(req.name, by)} isn't on PyPI or built into {pyodide}"))
            continue
        python = data["python"]
        pure_versions, any_versions = [], []
        for version, files in (project.get("releases") or {}).items():
            live = [f for f in files if not f.get("yanked")]
            if not live or not satisfies(version, req.spec, allow_pre=False) or _parse(version) is None:
                continue
            fits = [f for f in live if not f.get("requires_python")
                    or satisfies(python, f["requires_python"].replace(" ", ""), allow_pre=True)]
            if not fits:
                continue
            any_versions.append(version)
            if any(_pure(f["filename"]) for f in fits):
                pure_versions.append(version)
        if not pure_versions:
            chosen[req.name] = None
            if any_versions:
                latest = max(any_versions, key=Version)
                files = project["releases"][latest]
                kind = ("has native code (wheels only for Windows, macOS and Linux)"
                        if any(f["filename"].endswith(".whl") for f in files)
                        else "only has a source release (micropip installs wheels)")
                findings.append(Finding(root, "error", "dependency-native",
                                        f"{needed(req.name, by)} {kind}, and {pyodide} doesn't build it, "
                                        "so it can't be installed in the browser"))
            else:
                wanted = f" matching {req.spec}" if req.spec else ""
                findings.append(Finding(root, "error", "dependency-version",
                                        f"{needed(req.name, by)}: no release{wanted} runs on Python {python} "
                                        "in the browser"))
            continue
        version = max(pure_versions, key=Version)
        chosen[req.name] = version
        done_extras[req.name] = set(req.extras)
        _queue_dependencies(req.name, version, req.extras, root, fetch, env, queue, findings)
    # One finding per package: several packages needing a newer
    # typing-extensions say the same thing.
    seen: set[str] = set()
    unique = []
    for finding in findings:
        named = re.match(r"^'([^']+)'", finding.message)
        key = named.group(1) if named else finding.message
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def _queue_dependencies(name, version, extras, root, fetch, env, queue, findings) -> None:
    try:
        release = fetch(_PYPI_RELEASE.format(name, version)) or {}
    except OSError:
        return
    for dep in (release.get("info") or {}).get("requires_dist") or []:
        req = parse_requirement(dep)
        if req is None:
            continue
        if req.marker and not marker_holds(req.marker, env, frozenset(extras)):
            continue
        # The marker has been applied; pass the rest on.
        queue.append((dep.split(";")[0].strip(), name, root))
