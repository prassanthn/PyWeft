"""Refresh src/pyweft/pyodide_packages.json: which packages the Pyodide
version PyWeft loads has built in, at which versions, for `pyweft check`.

Run it after changing the Pyodide version in src/pyweft/static/shell.html:

    uv run python scripts/update_pyodide_packages.py

(tests/test_browser_deps.py fails until the two agree.)
"""

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL = ROOT / "src" / "pyweft" / "static" / "shell.html"
OUT = ROOT / "src" / "pyweft" / "pyodide_packages.json"


def main() -> None:
    version = re.search(r"pyodide/v([\d.]+)/full/pyodide\.js", SHELL.read_text(encoding="utf-8")).group(1)
    url = f"https://cdn.jsdelivr.net/pyodide/v{version}/full/pyodide-lock.json"
    with urllib.request.urlopen(url, timeout=30) as response:
        lock = json.load(response)
    packages = {
        name: entry["version"]
        for name, entry in sorted(lock["packages"].items())
        if entry.get("package_type", "package") == "package"
    }
    data = {"pyodide": version, "python": lock["info"]["python"], "packages": packages}
    OUT.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUT.name}: Pyodide {version}, Python {data['python']}, {len(packages)} packages")


if __name__ == "__main__":
    main()
