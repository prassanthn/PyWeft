"""Builds the PyWeft website into website/_build/site.

    uv sync --group website
    uv run python website/build.py
    uv run python -m http.server -d website/_build/site    # look at it

The pages come from the repository's own docs, so every guide has one copy:
docs/getting-started.md is split into a page per numbered section, the
pyweft-ui README and guide become the Controls section, and links between
them are rewritten to the site's pages (anything else links to GitHub).
Pages that exist only on the site live in website/pages. The live gallery
and examples are ordinary `pyweft build` output under live/.
"""

from __future__ import annotations

import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

from pymdownx.slugs import slugify

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BUILD = HERE / "_build"
DOCS = BUILD / "docs"
SITE = BUILD / "site"
GITHUB = "https://github.com/prassanthn/PyWeft"

GUIDE = "docs/getting-started.md"
# Page for each part of the guide: the intro, then sections 1, 2, ...
# Section 1 (Install) is short, so it shares the intro's page.
GUIDE_PAGES = [
    "guide/index.md",
    "guide/index.md",
    "guide/first-component.md",
    "guide/templates.md",
    "guide/components.md",
    "guide/projects.md",
    "guide/testing.md",
    "guide/roadmap.md",
]
# Repository files copied whole, and where they land
COPIED = {
    "packages/pyweft-ui/README.md": "controls/index.md",
    "packages/pyweft-ui/docs/guide.md": "controls/guide.md",
    "CHANGELOG.md": "changelog/index.md",
    "packages/pyweft-ui/CHANGELOG.md": "changelog/pyweft-ui.md",
}
# The home page does the root README's job; links to it go there.
LINKED = {**COPIED, "README.md": "index.md"}
# Apps built with `pyweft build` and served live: live/<name>/
LIVE = {
    "gallery": "packages/pyweft-ui/gallery",
    "todo": "examples/todo",
    "shop": "examples/shop",
}

_slug = slugify(case="lower")
_HEADING = re.compile(r"(#{1,6}) (.+)")
_LINK = re.compile(r"\]\(([^()\s]+)\)")


def slug(heading: str) -> str:
    # The anchor mkdocs gives a heading: its text without the code marks
    return _slug(re.sub(r"`([^`]*)`", r"\1", heading), "-")


def prose(lines: list[str]) -> list[bool]:
    """False for lines of fenced code (and the fences), True otherwise."""
    mask, fence = [], None
    for line in lines:
        marker = re.match(r"\s*(```|~~~)", line)
        if fence is None and marker:
            fence = marker[1]
            mask.append(False)
        elif fence is not None:
            if line.strip().startswith(fence):
                fence = None
            mask.append(False)
        else:
            mask.append(True)
    return mask


def drop_contents(text: str) -> str:
    # A hand-written table of contents: the site's sidebar does that job
    return re.sub(r"\*\*Contents\*\*\n.*?\n---(\n+|$)", "", text, count=1, flags=re.S)


def split_guide(text: str) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Returns {page: markdown} and {old anchor: (page, new anchor)}."""
    lines = text.split("\n")
    parts: list[list[str]] = [[]]
    anchors: dict[str, tuple[str, str]] = {}
    for line, is_prose in zip(lines, prose(lines)):
        heading = _HEADING.fullmatch(line) if is_prose else None
        number = heading and re.fullmatch(r"(\d+)\. (.+)", heading[2])
        if heading and len(heading[1]) == 2 and number:
            if int(number[1]) != len(parts):
                raise SystemExit(f"{GUIDE}: section {number[1]} is out of order")
            parts.append([])
        n = len(parts) - 1
        page = GUIDE_PAGES[n]
        if heading:
            level, title = len(heading[1]), heading[2]
            if n == 0 and level == 1:
                line, new = "# Getting started", ""
            elif level == 2 and number and n == 1:
                line, new = f"## {number[2]}", slug(number[2])
            elif level == 2 and number:
                line, new = f"# {number[2]}", ""
            elif n >= 2:
                line, new = "#" * (level - 1) + " " + title, slug(title)
            else:
                new = slug(title)
            anchors[slug(title)] = (page, new)
        parts[-1].append(line)
    if len(parts) != len(GUIDE_PAGES):
        raise SystemExit(f"{GUIDE}: expected {len(GUIDE_PAGES) - 1} sections")

    pages: dict[str, str] = {}
    for n, part in enumerate(parts):
        body = drop_contents("\n".join(part).strip())
        body = re.sub(r"\n+---$", "", body)  # the rule between sections
        page = GUIDE_PAGES[n]
        pages[page] = (pages[page] + "\n\n" + body) if page in pages else body
    return pages, anchors


def tidy_changelog(text: str) -> str:
    # Instructions for whoever releases, and an empty "Unreleased"
    text = re.sub(r"\nAdd a line under \*\*Unreleased\*\*.*?\n\n", "\n", text, flags=re.S)
    return re.sub(r"## Unreleased\n+(?=## )", "", text)


class Linker:
    def __init__(self, guide_anchors: dict[str, tuple[str, str]]):
        self.guide_anchors = guide_anchors

    def locate(self, path: str, anchor: str) -> tuple[str | None, str]:
        if path == GUIDE:
            if not anchor:
                return GUIDE_PAGES[0], ""
            if anchor not in self.guide_anchors:
                raise SystemExit(f"a link points at {GUIDE}#{anchor}, which doesn't exist")
            return self.guide_anchors[anchor]
        return LINKED.get(path), anchor

    def target(self, link: str, src: str, dest: str) -> str:
        """`link`, written in repository file `src`, as seen from page `dest`."""
        if link.startswith(("http://", "https://")):
            for prefix in (f"{GITHUB}/blob/main/", f"{GITHUB}/tree/main/"):
                if link.startswith(prefix):
                    path, _, anchor = link[len(prefix):].partition("#")
                    break
            else:
                if link != GITHUB and not link.startswith(GITHUB + "#"):
                    return link
                path, anchor = "README.md", link.partition("#")[2]
        elif ":" in link.split("/")[0]:  # mailto: and friends
            return link
        else:
            path, _, anchor = link.partition("#")
            path = posixpath.normpath(posixpath.join(posixpath.dirname(src), path)) if path else src
        page, anchor = self.locate(path, anchor)
        fragment = f"#{anchor}" if anchor else ""
        if page is None:
            kind = "tree" if (REPO / path).is_dir() else "blob"
            return f"{GITHUB}/{kind}/main/{path}{fragment}"
        if page == dest and fragment:
            return fragment
        return posixpath.relpath(page, posixpath.dirname(dest) or ".") + fragment

    def rewrite(self, text: str, src: str, dest: str) -> str:
        lines = text.split("\n")
        return "\n".join(
            _LINK.sub(lambda m: f"]({self.target(m[1], src, dest)})", line) if is_prose else line
            for line, is_prose in zip(lines, prose(lines))
        )


def write(page: str, text: str) -> None:
    path = DOCS / page
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def assemble() -> None:
    # Empty DOCS rather than delete it: on Windows a folder that is some
    # shell's current directory can't be removed. mkdocs empties SITE itself.
    for old in DOCS.glob("*"):
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    shutil.copytree(HERE / "pages", DOCS, dirs_exist_ok=True)

    guide_pages, anchors = split_guide((REPO / GUIDE).read_text(encoding="utf-8"))
    linker = Linker(anchors)
    for page, text in guide_pages.items():
        write(page, linker.rewrite(text, GUIDE, page))
    for src, page in COPIED.items():
        text = (REPO / src).read_text(encoding="utf-8")
        text = tidy_changelog(text) if src.endswith("CHANGELOG.md") else drop_contents(text)
        write(page, linker.rewrite(text, src, page))


def main() -> None:
    assemble()
    run = lambda *args: subprocess.run([sys.executable, *args], check=True, cwd=REPO)  # noqa: E731
    run("-m", "mkdocs", "build", "--strict", "--config-file", str(HERE / "mkdocs.yml"))
    for name, app in LIVE.items():
        run("-m", "pyweft", "build", app, "--out", str(SITE / "live" / name))
    print(f"built {SITE}")


if __name__ == "__main__":
    main()
