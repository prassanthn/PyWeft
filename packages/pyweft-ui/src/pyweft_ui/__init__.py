"""pyweft-ui: ready-made controls for PyWeft.

In a component's code block::

    from pyweft_ui import ui

then in its template ``<ui.Button>``, ``<ui.TextField @bind="name" />``,
``<ui.Card>`` and the rest. Each control is a ``.weft`` file in this folder,
loaded the first time it is used.
"""

from pathlib import Path

from pyweft import ComponentLibrary

__version__ = "0.0.1"

ui = ComponentLibrary(Path(__file__).parent, prefix="ui")

__all__ = ["ui", "__version__"]
