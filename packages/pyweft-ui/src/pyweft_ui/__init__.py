"""pyweft-ui: ready-made controls for PyWeft.

In a component's code block::

    from pyweft_ui import ui

then in its template ``<ui.Button>``, ``<ui.TextField @bind="name" />``,
``<ui.Card>`` and the rest. Each control is a ``.weft`` file in this folder,
loaded the first time it is used. ``toast()`` shows a message in the
page's ``<ui.Toaster />``. ``Form`` and ``rules`` check a component's
fields and say what needs fixing (forms.py).
"""

from pathlib import Path

from pyweft import ComponentLibrary

from . import rules
from .forms import BoundForm, Form
from .toasts import Toast, clear_toasts, toast

__version__ = "0.6.0"

ui = ComponentLibrary(Path(__file__).parent, prefix="ui")

__all__ = ["ui", "toast", "clear_toasts", "Toast", "Form", "BoundForm", "rules", "__version__"]
